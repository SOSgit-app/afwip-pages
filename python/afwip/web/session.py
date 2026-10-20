"""
session.py — GameSession: one game, one AFWIPEnv, revisioned state.

The session is the only writer of its env. Every applied decision bumps
`revision` and the decision counter behind `node_id`; a submitted choice must
echo both, and a mismatch raises StaleStateError (HTTP 409 upstream) so
double-clicks and auto-mode races can never desync the browser.

Modes:
  agent_v_agent  — spectator; `step_once()` advances exactly one decision.
  human_v_agent  — `apply_human()` then auto-advances the agent side until the
                   human must decide again or the game ends.
  hotseat        — both sides human on one device; `authorized_viewer` gates
                   whose private state is serialized, and `handoff()` is the
                   explicit pass-the-device transition.

Fog is applied at serialization time via afwip.view; the public (viewer=None)
view backs the handoff screen so the next side's hidden state is never sent
early.
"""

from __future__ import annotations

import random
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from afwip.core.constants import Side, Phase
from afwip.env import AFWIPEnv
from afwip.script import DecisionNode, Choice, NodeType
from afwip.view import serializer
from afwip.view.export import game_export
from afwip.view.events import EventRecorder, score_report
from afwip.view.models import GameView, ScoreReportView, AgentMoveView
from afwip.web.agents import Agent, make_agent
from afwip.rl.trajectory import (
    TrajectoryRecorder, Trajectory, write_trajectory, DEFAULT_TRAJECTORY_DIR,
)
from afwip.rl.state_text import llm_state_text

# Hard ceiling on any automatic advancement loop. Full env games run a few
# thousand decisions; the env itself truncates at 20k steps.
MAX_AUTO_STEPS = 30000

# Opponent setup: one Continue per *kind* of stretch (not per card).
_POSTURE_BATCH_NODES = frozenset({NodeType.POSTURE_PICK})
_SQUADRON_BATCH_NODES = frozenset({
    NodeType.SQUADRON_PICK,
    NodeType.SQUADRON_BASE,
})
_ENABLER_BATCH_NODES = frozenset({NodeType.ENABLER_PICK})
# One Continue runs posture → squadrons → enablers for the opponent.
_DRAFT_BATCH_NODES = (
    _POSTURE_BATCH_NODES | _SQUADRON_BATCH_NODES | _ENABLER_BATCH_NODES
)
_BID_BATCH_NODES = frozenset({NodeType.BID_SACRIFICE})

# Repeated same-type opponent nodes: one Continue runs the whole streak
# (e.g. every INTEL_REVEAL peek) instead of one click per card.
_REPEAT_BATCH_NODES = frozenset({
    NodeType.INTEL_REVEAL,
})

# Paced tutorial: after these human choices, hold Continue on the board change
# before the opponent moves — but only when the next node is *not* still yours
# (activate → SPAWN_BAND must not insert an empty Continue).
_PACE_WATCH_HUMAN = frozenset({
    NodeType.SPAWN_BAND,
    NodeType.TURN_ACTION,
    NodeType.ENABLER_BRANCH,
    NodeType.ALLOC_POINT,
    NodeType.MD_DECLARE,
    NodeType.RESPONSE,
})

# Choices that change nothing worth a "seen it" beat.
_PACE_WATCH_SKIP_KINDS = frozenset({
    "pass",
    "skip",
    "done",
})


def _batch_group(node_type: NodeType):
    """Node types that may advance together under one tutorial Continue."""
    if node_type in _POSTURE_BATCH_NODES:
        return _POSTURE_BATCH_NODES
    if node_type in _SQUADRON_BATCH_NODES:
        return _SQUADRON_BATCH_NODES
    if node_type in _ENABLER_BATCH_NODES:
        return _ENABLER_BATCH_NODES
    if node_type in _BID_BATCH_NODES:
        return _BID_BATCH_NODES
    if node_type in _REPEAT_BATCH_NODES:
        return frozenset({node_type})
    return None


def _batch_name(batch) -> str:
    if batch == _POSTURE_BATCH_NODES:
        return "posture"
    if batch == _SQUADRON_BATCH_NODES:
        return "squadrons"
    if batch == _ENABLER_BATCH_NODES:
        return "enablers"
    if batch == _BID_BATCH_NODES:
        return "bid"
    if batch == frozenset({NodeType.INTEL_REVEAL}):
        return "intel"
    return "batch"


class GameMode(str, Enum):
    AGENT_V_AGENT = "agent_v_agent"
    HUMAN_V_AGENT = "human_v_agent"
    HOTSEAT = "hotseat"                 # two humans, ONE device (pass-and-play)
    HUMAN_V_HUMAN = "human_v_human"     # two humans, TWO devices on a LAN


class SessionError(Exception):
    """Invalid request against the session (HTTP 400/403 upstream)."""


class StaleStateError(SessionError):
    """Submitted revision/node_id no longer current (HTTP 409 upstream)."""


class GameSession:
    def __init__(self, game_id: str, campaign: int = 2,
                 mode: GameMode = GameMode.HUMAN_V_AGENT,
                 human_side: Side = Side.US,
                 seed: Optional[int] = None,
                 agent_name: str = "random",
                 spectator_reveal: bool = True,
                 record: Optional[bool] = None,
                 trajectory_dir: Optional[Path] = None,
                 openai_api_key: Optional[str] = None,
                 restore: Optional[dict[str, Any]] = None):
        self.game_id = game_id
        self.campaign = campaign
        self.mode = mode
        self.human_side = human_side
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.agent_name = agent_name
        # Default: record every mode so Save / Load can replay the tape.
        # Pass record=False to opt out (training harness / tests).
        self._record = True if record is None else bool(record)
        self._openai_api_key = openai_api_key
        self.spectator_reveal = spectator_reveal
        self._human_choices: list[int] = []
        self._trajectory_dir = Path(trajectory_dir) if trajectory_dir else DEFAULT_TRAJECTORY_DIR
        self.trajectory_saved_path: Optional[Path] = None

        self.env = AFWIPEnv(campaign=campaign)
        self.env.reset(seed=self.seed)
        self.recorder = EventRecorder(self.env.engine)
        # Agent decisions draw from a session-local RNG, decoupled from the
        # engine's dice stream (mirrors the TUI's seed+1 convention).
        self.agent_rng = random.Random(self.seed + 1)

        self.trajectory: Optional[TrajectoryRecorder] = (
            TrajectoryRecorder(campaign, self.seed, self.env.max_turns,
                               source="human")
            if self._record else None)

        self.agents: dict[Side, Agent] = {}
        if mode == GameMode.AGENT_V_AGENT:
            self.agents = {s: make_agent(agent_name) for s in Side}
        elif mode == GameMode.HUMAN_V_AGENT:
            other = Side.PRC if human_side == Side.US else Side.US
            self.agents = {other: make_agent(agent_name)}
        # A UI-supplied OpenAI key reaches the "gpt" agent here (never logged,
        # never serialized — it lives only on the agent instance in memory).
        if openai_api_key:
            for agent in self.agents.values():
                if hasattr(agent, "set_api_key"):
                    agent.set_api_key(openai_api_key)

        self.revision = 0
        self.decision_no = 0
        # In-progress ATO-setup picks for the side currently drafting. The script
        # commits squadrons + enablers to engine state only at the END of a
        # side's draft (one select_posture call), so mid-draft picks — e.g. the
        # squadrons chosen before/while drafting enablers — live only in the
        # coroutine. We mirror them here so the AI export can show them; cleared
        # the moment the side commits (its picks then appear in engine state).
        self._draft: dict = {}
        # Human click-to-roll (human_v_agent): when a human action rolls dice we
        # PAUSE before advancing the agent, so the client can reveal the dice on a
        # "Roll" click before the outcome (and the AI's reply) are shown.
        self.roll_pending = False
        self.watch_pending = False
        # Live tutorial: show the opponent one decision at a time, and hold
        # after a roll so a result such as Winchester can be read on the board.
        self.paced = False
        # When True, the next Continue runs every remaining node in
        # `_watch_batch_nodes` without pausing (draft stretch, intel peeks, …).
        self.draft_skip_pending = False
        self.watch_batch = ""
        self._watch_batch_nodes = None
        self._skip_draft_batch = False
        self._last_choice_kind = ""
        self._last_step_rolled = False
        self._last_step_setup_dice = False
        # Paced tutorial: opponent's full TURN_ACTION may run only after the
        # human explicitly passed (or a rules-forced end_turn). Continue alone
        # must never arm this.
        self._handoff_armed = False
        self._human_saw_player_turn = False
        self.score_reports: list[ScoreReportView] = []
        # Cache for count_watch_continues_remaining (revision + hold flags).
        self._watch_continues_cache: Optional[tuple[tuple, int]] = None
        # Hotseat: the side currently allowed to see private state.
        node = self._node
        self.authorized_viewer: Optional[Side] = node.side if node else None

        if restore is not None:
            self._replay_save(restore)
        elif mode == GameMode.HUMAN_V_AGENT:
            self.advance_until_human()

    @property
    def recording(self) -> bool:
        return self.trajectory is not None

    def build_trajectory(self) -> Trajectory:
        if self.trajectory is None:
            raise SessionError("this game is not recording")
        return self.trajectory.finalize(self.env.engine)

    def save_trajectory(self) -> Path:
        """Write the current tape to disk (on-demand; used by tests / training)."""
        traj = self.build_trajectory()
        path = self._trajectory_dir / f"{self.game_id}.jsonl"
        write_trajectory(traj, path)
        self.trajectory_saved_path = path
        return path

    def export_save(self) -> dict[str, Any]:
        """JSON payload for browser download — enough to resume this session."""
        if self.trajectory is None:
            raise SessionError("this game is not recording a save tape")
        viewer = self.authorized_viewer.value if self.authorized_viewer else None
        return {
            "format": "afwip-save",
            "schema_version": 1,
            "campaign": self.campaign,
            "seed": self.seed,
            "mode": self.mode.value,
            "human_side": self.human_side.value,
            "agent": self.agent_name,
            "max_turns": self.env.max_turns,
            "paced": self.paced,
            "watch_pending": self.watch_pending,
            "roll_pending": self.roll_pending,
            "draft_skip_pending": self.draft_skip_pending,
            "watch_batch": self.watch_batch,
            "authorized_viewer": viewer,
            "human_choices": list(self._human_choices),
            "tape": [asdict(step) for step in self.trajectory.tape],
        }

    @classmethod
    def from_save(cls, game_id: str, save: dict[str, Any],
                  openai_api_key: Optional[str] = None) -> "GameSession":
        """Rebuild a session by replaying the saved decision tape."""
        if not isinstance(save, dict) or save.get("format") not in (
            "afwip-save", "afwip-trajectory", None
        ):
            # Accept bare trajectory dicts (campaign/seed/tape) too.
            if not (isinstance(save, dict) and "tape" in save and "seed" in save):
                raise SessionError("not a recognized AFWIP save file")
        try:
            mode = GameMode(save.get("mode", GameMode.HUMAN_V_AGENT.value))
            human_side = Side(save.get("human_side", "US"))
        except ValueError as e:
            raise SessionError(str(e)) from e
        return cls(
            game_id,
            campaign=int(save.get("campaign", 2)),
            mode=mode,
            human_side=human_side,
            seed=int(save["seed"]),
            agent_name=str(save.get("agent", "random")),
            record=True,
            openai_api_key=openai_api_key,
            restore=save,
        )

    def _replay_save(self, save: dict[str, Any]) -> None:
        """Apply every taped choice without re-asking agents; restore UI holds."""
        tape = save.get("tape") or []
        for step in tape:
            if self._node is None:
                break
            idx = int(step["index"])
            if not 0 <= idx < len(self._node.choices):
                raise SessionError(
                    f"save tape broken at decision {step.get('decision_no')}: "
                    f"index {idx} not in 0..{len(self._node.choices) - 1}"
                )
            self._step(idx, justification=step.get("justification"))
            # Mid-replay must not pause on dice / watch holds.
            self.roll_pending = False
            self.watch_pending = False
            self.draft_skip_pending = False
            self._skip_draft_batch = False
        human = self.human_side.value
        self._human_choices = list(save.get("human_choices") or [
            int(t["index"]) for t in tape if t.get("side") == human
        ])
        self.paced = bool(save.get("paced", self.mode == GameMode.HUMAN_V_AGENT))
        self.watch_pending = bool(save.get("watch_pending", False))
        self.roll_pending = bool(save.get("roll_pending", False))
        self.draft_skip_pending = bool(save.get("draft_skip_pending", False))
        self.watch_batch = str(save.get("watch_batch") or "")
        auth = save.get("authorized_viewer")
        if auth in ("US", "PRC"):
            self.authorized_viewer = Side(auth)
        elif self._node is not None:
            self.authorized_viewer = self._node.side

    # -- node access ----------------------------------------------------------

    @property
    def _node(self) -> Optional[DecisionNode]:
        # Single, deliberate access point to the env's private current node
        # (env.py is frozen this build; a public accessor can land there later).
        return self.env._node

    @property
    def terminal(self) -> bool:
        return self._node is None

    @property
    def node_id(self) -> Optional[str]:
        return None if self.terminal else f"{self.game_id}:{self.decision_no}"

    # -- stepping ------------------------------------------------------------

    def _step(self, index: int, justification: Optional[str] = None) -> None:
        """Apply one choice: record events, advance the env, bump revision."""
        node = self._node
        if node is None:
            raise SessionError("game is over")
        if not 0 <= index < len(node.choices):
            raise SessionError(
                f"choice index {index} out of range 0..{len(node.choices) - 1}")
        before = self.recorder.snapshot()
        prev_ato = self.env.engine.state.ato_cycle
        prev_over = self.env.engine.state.game_over
        choice = node.choices[index]
        self._last_choice_kind = choice.kind or ""
        self.recorder.record_decision(self.decision_no, node, choice)
        if self.trajectory is not None:
            self.trajectory.record(self.decision_no, node, index, justification,
                                   engine=self.env.engine)
        self._track_draft(node, choice)
        self.env.step(index)
        self._clear_draft_if_committed()
        # Labeled setup rolls (initiative / cyber / intel) first; this also drops
        # their raw dice so flush_dice won't re-emit them as an unlabeled blob.
        n_before = len(self.recorder.events)
        self.recorder.flush_setup(self.decision_no)
        self._last_step_setup_dice = any(
            ev.type == "dice" for ev in self.recorder.events[n_before:])
        n_events = len(self.recorder.events)
        self.recorder.flush_dice(self.decision_no, node.side.value)
        # flush_dice appends a "dice" event only when this step rolled in play
        # (a shot, a spot, a launch). Setup dice are tracked separately.
        self._last_step_rolled = len(self.recorder.events) > n_events
        self.recorder.emit_diff(self.decision_no, before)
        gs = self.env.engine.state
        if gs.ato_cycle != prev_ato or (gs.game_over and not prev_over):
            self.score_reports.append(score_report(self.env.engine, prev_ato))
        self.decision_no += 1
        self.revision += 1


    # -- in-progress draft mirror (AI export) --------------------------------

    def _track_draft(self, node: DecisionNode, choice: Choice) -> None:
        """Mirror a setup pick into `self._draft` as it is applied."""
        if self.env.engine.state.phase != Phase.ATO_SETUP:
            return
        nt = node.node_type
        if nt == NodeType.POSTURE_PICK:
            # A posture pick anchors a fresh draft for this side.
            self._draft = {"side": node.side, "posture": choice.value,
                           "squadrons": [], "locations": {}, "enablers": []}
        elif not self._draft or self._draft.get("side") != node.side:
            return
        elif nt == NodeType.SQUADRON_PICK and choice.kind == "pick" \
                and choice.card_id is not None:
            self._draft["squadrons"].append(choice.card_id)
        elif nt == NodeType.SQUADRON_BASE and choice.card_id is not None:
            self._draft["locations"][choice.card_id] = (
                choice.band.name if choice.band is not None else None)
        elif nt == NodeType.ENABLER_PICK and choice.kind == "pick" \
                and choice.card_id is not None:
            self._draft["enablers"].append(choice.card_id)

    def _clear_draft_if_committed(self) -> None:
        """Drop the mirror once the side commits (its picks now live in engine
        state) or setup ends."""
        side = self._draft.get("side")
        if side is None:
            return
        gs = self.env.engine.state
        if gs.phase != Phase.ATO_SETUP or gs.player(side).posture_card_id is not None:
            self._draft = {}

    def _draft_view(self, viewer: Optional[Side]) -> Optional[dict]:
        """The drafting side's in-progress picks, fog-gated to that side (or a
        spectator), as a plain dict for the export. None when nothing to show."""
        side = self._draft.get("side")
        if side is None or (viewer is not None and side != viewer):
            return None
        from afwip.core.cards import (
            SQUADRON_REGISTRY, ENABLER_REGISTRY, POSTURE_REGISTRY,
        )
        pid = self._draft.get("posture")
        squads = []
        for cid in self._draft.get("squadrons", []):
            sp = SQUADRON_REGISTRY[cid]
            loc = self._draft.get("locations", {}).get(cid)
            squads.append({
                "card": cid, "name": sp.name, "token": sp.token_type.value,
                "loc": ("CL" if loc == "US_CONTINGENCY_LOCATION"
                        else "AIRBASE" if loc else None),
            })
        enablers = [{"card": cid, "name": ENABLER_REGISTRY[cid].name}
                    for cid in self._draft.get("enablers", [])]
        return {"side": side.value,
                "posture": POSTURE_REGISTRY[pid].name if pid else None,
                "squadrons": squads, "enablers": enablers}

    def _agent_for(self, node: DecisionNode) -> Optional[Agent]:
        return self.agents.get(node.side)

    def _agent_step(self, node: DecisionNode, agent: Agent) -> None:
        # Give the agent the fogged copy-state text + side (lazy — cheap agents
        # never build it). LLM agents play from it and stash their reasoning.
        context = {"side": node.side.value,
                   "setup": self.env.engine.state.phase != Phase.PLAYER_TURN,
                   "state_text": lambda: llm_state_text(self.env.engine, node,
                                                        node.side)}
        idx = agent.choose(lambda: self.env.observe(node.side.value),
                           node.choices, self.agent_rng, context=context)
        self._step(idx, justification=getattr(agent, "last_justification", None))

    def step_once(self) -> None:
        """Advance exactly one decision (spectator mode).

        When that decision produced dice (setup or action), pause with
        `roll_pending` so Watch Agents can show the same roll screen as
        player modes before the next step.
        """
        if self.roll_pending:
            raise SessionError("reveal the pending roll first")
        node = self._node
        if node is None:
            raise SessionError("game is over")
        agent = self._agent_for(node)
        if agent is None:
            raise SessionError(f"{node.side.value} is human-controlled; POST a choice")
        self._agent_step(node, agent)
        if self._last_step_rolled or self._last_step_setup_dice:
            self.roll_pending = True

    def advance_until_human(self) -> None:
        """Run agent-controlled decisions until a human node or game end.

        Any step that rolls dice (setup, acquire, to-hit, damage) pauses with
        `roll_pending` so the die screen can show — including when the AI is
        the one rolling. In the live tutorial (`paced`), non-dice opponent
        decisions also pause for Continue so the board change can be seen.

        Opponent stretches of the same kind (all enabler picks, all squadron
        picks, intel peeks, …) hold once; Continue runs the whole stretch so
        the student is not clicking through every card. Activate + spawn is
        one launch beat.
        """
        for _ in range(MAX_AUTO_STEPS):
            node = self._node
            if node is None:
                self._skip_draft_batch = False
                self._watch_batch_nodes = None
                self.watch_batch = ""
                return
            agent = self._agent_for(node)
            if agent is None:
                self._skip_draft_batch = False
                self._watch_batch_nodes = None
                self.watch_batch = ""
                # Back on the human's player turn — they must Pass again to hand off.
                if (node.node_type == NodeType.TURN_ACTION
                        and self.env.engine.state.phase == Phase.PLAYER_TURN
                        and node.side == self.human_side):
                    self._human_saw_player_turn = True
                    self._handoff_armed = False
                return
            # Paced tutorial: do not play the opponent's full turn until the
            # human has explicitly handed off (Pass / forced end). Continue
            # must not walk into their TURN_ACTION otherwise.
            if (self.paced
                    and node.node_type == NodeType.TURN_ACTION
                    and self.env.engine.state.phase == Phase.PLAYER_TURN
                    and self._human_saw_player_turn
                    and not self._handoff_armed):
                return
            batch = _batch_group(node.node_type)
            if self.paced and not self._skip_draft_batch and batch is not None:
                self.watch_pending = True
                self.draft_skip_pending = True
                self._watch_batch_nodes = batch
                self.watch_batch = _batch_name(batch)
                return
            acted_type = node.node_type
            self._agent_step(node, agent)
            # Pause for the die screen on setup dice and on action dice
            # (acquire / to-hit / damage), including when the AI is rolling in
            # Practice vs Agent so the spectator can watch the tumble.
            # Keep an in-progress card streak across the die so the rest of
            # that streak (e.g. remaining enablers) still runs on one Continue.
            if self._last_step_setup_dice or self._last_step_rolled:
                self.roll_pending = True
                nxt = self._node
                batch = self._watch_batch_nodes
                # Keep a draft streak across setup dice only while the next
                # node is still part of that draft. Initiative after the last
                # enabler must not leave skip-batch stuck on.
                still_draft_streak = (
                    self._skip_draft_batch
                    and nxt is not None
                    and self._agent_for(nxt) is not None
                    and batch is not None
                    and (
                        nxt.node_type in batch
                        or (batch <= _DRAFT_BATCH_NODES
                            and nxt.node_type in _DRAFT_BATCH_NODES)
                    )
                )
                if not still_draft_streak:
                    self._skip_draft_batch = False
                    self._watch_batch_nodes = None
                    self.watch_batch = ""
                return
            if self.paced and self._skip_draft_batch:
                nxt = self._node
                batch = self._watch_batch_nodes
                if (nxt is not None
                        and self._agent_for(nxt) is not None
                        and batch is not None
                        and nxt.node_type in batch):
                    continue
                # Same Continue: keep going through the rest of their draft
                # (posture → squadrons → enablers) without another hold.
                if (nxt is not None
                        and self._agent_for(nxt) is not None
                        and batch is not None
                        and batch <= _DRAFT_BATCH_NODES
                        and nxt.node_type in _DRAFT_BATCH_NODES):
                    nxt_batch = _batch_group(nxt.node_type)
                    self._watch_batch_nodes = nxt_batch
                    self.watch_batch = _batch_name(nxt_batch) if nxt_batch else ""
                    continue
                self._skip_draft_batch = False
                self._watch_batch_nodes = None
                self.watch_batch = ""
                # Do not hold again on the last card of the streak — step into
                # whatever comes next (or return if it is the human's turn).
                if nxt is None or self._agent_for(nxt) is None:
                    return
                continue
            if self.paced:
                nxt = self._node
                # Activate squadron then pick the band = one "launch" Continue.
                if (acted_type == NodeType.TURN_ACTION
                        and self._last_choice_kind == "activate"
                        and nxt is not None
                        and self._agent_for(nxt) is not None
                        and nxt.node_type == NodeType.SPAWN_BAND):
                    continue
                # Pass / skip — keep going; nothing on the board changed.
                if self._last_choice_kind in _PACE_WATCH_SKIP_KINDS:
                    if nxt is None or self._agent_for(nxt) is None:
                        return
                    continue
                self.watch_pending = True
                return
        raise RuntimeError("advance_until_human exceeded MAX_AUTO_STEPS")

    # -- human input -----------------------------------------------------------

    def apply_human(self, index: int, revision: Optional[int] = None,
                    node_id: Optional[str] = None,
                    justification: Optional[str] = None,
                    actor_side: Optional[Side] = None) -> None:
        node = self._node
        if node is None:
            raise SessionError("game is over")
        # Continue hold must not be bypassed by a queued choice click
        # (a stale Pass after spawn was ending the turn before the student meant to).
        if self.watch_pending:
            raise SessionError("click Continue before choosing again")
        if revision is not None and revision != self.revision:
            raise StaleStateError(
                f"stale revision {revision} (current {self.revision})")
        if node_id is not None and node_id != self.node_id:
            raise StaleStateError(f"stale node {node_id} (current {self.node_id})")
        if self._agent_for(node) is not None:
            raise SessionError(f"{node.side.value} is agent-controlled")
        if self.mode == GameMode.HUMAN_V_AGENT and node.side != self.human_side:
            raise SessionError(f"not {self.human_side.value}'s decision")
        if self.mode == GameMode.HOTSEAT and node.side != self.authorized_viewer:
            raise SessionError("handoff required before acting for this side")
        # Two-device play: a device may only act for its own side, and only on
        # its own side's node.
        if self.mode == GameMode.HUMAN_V_HUMAN:
            if actor_side is None:
                raise SessionError("which side? (viewer required)")
            if node.side != actor_side:
                raise SessionError(f"not {actor_side.value}'s decision")
        acted = node.node_type
        acting_side = node.side
        if (acted == NodeType.TURN_ACTION
                and self.env.engine.state.phase == Phase.PLAYER_TURN
                and acting_side == self.human_side):
            self._human_saw_player_turn = True
        before_active = self.env.engine.state.active_side
        self.roll_pending = False            # reflect only the action just taken
        self._step(index, justification=justification)
        self._human_choices.append(index)
        # Arm opponent's full turn only on an explicit Pass (or a rules-forced
        # end_turn). Continue never sets this flag.
        if self._last_choice_kind == "pass":
            self._handoff_armed = True
        elif (self.env.engine.state.phase == Phase.PLAYER_TURN
              and before_active == acting_side
              and self.env.engine.state.active_side != acting_side):
            # Relaunch / failed recovered activation / IllegalAction end_turn.
            self._handoff_armed = True
        # Hold the outcome until the human clicks the die. Action dice pause in
        # every human mode. Setup dice (initiative, the cyber raise, intel)
        # pause in player-vs-AI as well, including when this choice caused them.
        setup_pause = (self.mode == GameMode.HUMAN_V_AGENT
                       and self._last_step_setup_dice)
        if self._last_step_rolled or setup_pause:
            self.roll_pending = True
        elif self.mode == GameMode.HUMAN_V_AGENT:
            if self.paced and acted in _PACE_WATCH_HUMAN:
                nxt = self._node
                still_yours = (
                    nxt is not None and self._agent_for(nxt) is None
                )
                noop = self._last_choice_kind in _PACE_WATCH_SKIP_KINDS
                if still_yours:
                    # Activate → choose band, enabler → branch, etc.
                    # Never hide Pass behind Continue after a launch.
                    return
                if noop:
                    # Pass / end turn: hold so the student sees that choice
                    # before the opponent's full turn starts. Other skips
                    # (no response, draft done, …) have nothing to stare at.
                    if self._last_choice_kind == "pass":
                        self.watch_pending = True
                        return
                    self.advance_until_human()
                    return
                # Board just changed (spawn landed, shot resolved, …) — hold.
                # Mid-turn MD / response for the opponent is not their turn yet;
                # after Continue the human still gets Pass / end turn.
                self.watch_pending = True
            else:
                self.advance_until_human()

    def undone(self) -> "GameSession":
        """Replay every human choice except the last, so a mis-clicked card
        can be taken again. Agent moves and dice come back from the same seed."""
        if not self._human_choices:
            raise SessionError("nothing to undo")
        fresh = GameSession(
            self.game_id, campaign=self.campaign, mode=self.mode,
            human_side=self.human_side, seed=self.seed,
            agent_name=self.agent_name, spectator_reveal=self.spectator_reveal,
            record=self._record, trajectory_dir=self._trajectory_dir,
            openai_api_key=self._openai_api_key,
        )
        for index in self._human_choices[:-1]:
            actor = None
            node = fresh._node
            if fresh.mode == GameMode.HOTSEAT and node is not None:
                fresh.authorized_viewer = node.side
            if fresh.mode == GameMode.HUMAN_V_HUMAN and node is not None:
                actor = node.side
            fresh.apply_human(index, actor_side=actor)
            for _ in range(8):
                if not fresh.roll_pending:
                    break
                fresh.reveal_roll()
        if fresh.mode == GameMode.HOTSEAT and fresh._node is not None:
            fresh.authorized_viewer = fresh._node.side
        fresh.paced = self.paced
        fresh.draft_skip_pending = False
        fresh.watch_batch = ""
        fresh._watch_batch_nodes = None
        fresh._skip_draft_batch = False
        return fresh

    def reveal_roll(self) -> None:
        """Clear a pending roll (the client has shown the dice).

        In the live tutorial, stop on the result so the board — and a notice
        such as Winchester — can be read before the next action. Otherwise let
        the agent play through to the human."""
        if not self.roll_pending:
            return
        self.roll_pending = False
        if self.mode != GameMode.HUMAN_V_AGENT:
            return
        if self.paced:
            # Mid-streak setup dice (initiative on the last enabler, …): the die
            # UI already showed the tumble. End the card streak here so the next
            # Continue is the next *kind* of action (bid / first player / turn),
            # not another per-card pause and not a swallowed setup step.
            if self._skip_draft_batch:
                self._skip_draft_batch = False
                self._watch_batch_nodes = None
                self.watch_batch = ""
            nxt = self._node
            # Still your decision (often Pass / end turn after a spot or shot) —
            # show the choices; do not hide them behind Continue.
            if nxt is not None and self._agent_for(nxt) is None:
                return
            self.watch_pending = True
            return
        self.advance_until_human()

    def continue_watch(self) -> None:
        """Leave the tutorial's hold and play the next opponent decision.

        Continue never submits Pass / end turn for the human. If the next node
        is still theirs, the hold simply clears so their choices reappear. The
        opponent's full turn runs only when `_handoff_armed` (explicit Pass).

        If the hold was a batch announcement (draft stretch, intel peeks, …),
        run every remaining node in that batch before pausing again.
        """
        if not self.watch_pending:
            raise SessionError("nothing to continue")
        self.watch_pending = False
        self._watch_continues_cache = None
        if self.draft_skip_pending:
            self.draft_skip_pending = False
            self._skip_draft_batch = True
            # `_watch_batch_nodes` / `watch_batch` stay set until the streak ends.
        if self.mode != GameMode.HUMAN_V_AGENT:
            return
        node = self._node
        # Still the human's decision — do not advance the AI or pass for them.
        if node is not None and self._agent_for(node) is None:
            return
        # Opponent's full turn without an armed handoff: refuse to play it.
        if (self.paced
                and node is not None
                and node.node_type == NodeType.TURN_ACTION
                and self.env.engine.state.phase == Phase.PLAYER_TURN
                and self._human_saw_player_turn
                and not self._handoff_armed):
            return
        self.advance_until_human()

    def _human_choices_ready(self) -> bool:
        """True when the human would see a decision panel (no Continue / Roll hold)."""
        node = self._node
        if node is None:
            return True
        if self._agent_for(node) is not None:
            return False
        if self.watch_pending or self.roll_pending:
            return False
        return node.side == self.human_side

    def _fork_for_pace_sim(self) -> "GameSession":
        """Replay tape into a disposable session aligned with this one's RNG.

        Tape replay does not call agents, so `agent_rng` would otherwise restart
        at seed+1 and future opponent picks (and Continue counts) would diverge.
        """
        if not self.recording:
            raise SessionError("pace sim needs a recording tape")
        sim = GameSession.from_save(
            f"{self.game_id}-pace-sim",
            self.export_save(),
            openai_api_key=self._openai_api_key,
        )
        sim._handoff_armed = self._handoff_armed
        sim._human_saw_player_turn = self._human_saw_player_turn
        sim._skip_draft_batch = self._skip_draft_batch
        sim._watch_batch_nodes = self._watch_batch_nodes
        sim._last_choice_kind = self._last_choice_kind
        # Match the live AI's next samples (TutorialAgent / PolicyAgent).
        sim.agent_rng.setstate(self.agent_rng.getstate())
        # Engine dice stream must match too if a later hold rolls.
        eng_rng = getattr(self.env.engine, "rng", None)
        sim_eng_rng = getattr(sim.env.engine, "rng", None)
        if eng_rng is not None and sim_eng_rng is not None:
            sim_eng_rng.setstate(eng_rng.getstate())
        return sim

    def count_watch_continues_remaining(self, max_clicks: int = 200) -> Optional[int]:
        """How many Continue clicks until the human can act again.

        Tutorial-only (paced + tutorial agent): dry-runs a fork with synced RNG.
        Opponent dice rolls are not counted (those use the die UI).
        """
        # Lobby Tutorial = agent "tutorial" + paced coach. Other modes stay quiet.
        if (
            self.mode != GameMode.HUMAN_V_AGENT
            or not self.paced
            or self.agent_name != "tutorial"
        ):
            return None
        if not self.watch_pending:
            return 0 if self._human_choices_ready() else None
        if not self.recording:
            return None
        key = (
            self.revision,
            self.watch_pending,
            self.roll_pending,
            self.draft_skip_pending,
            self.watch_batch,
            self._handoff_armed,
            self._human_saw_player_turn,
            self._skip_draft_batch,
            self.agent_rng.getstate(),
        )
        if self._watch_continues_cache and self._watch_continues_cache[0] == key:
            return self._watch_continues_cache[1]
        try:
            sim = self._fork_for_pace_sim()
        except SessionError:
            return None
        clicks = 0
        for _ in range(max_clicks):
            if sim._human_choices_ready():
                break
            if sim.roll_pending:
                sim.reveal_roll()
                continue
            if sim.watch_pending:
                before_rev = sim.revision
                sim.continue_watch()
                clicks += 1
                # Handoff gate / no-op Continue — stop rather than spin.
                if sim.revision == before_rev and sim.watch_pending is False \
                        and not sim._human_choices_ready() and not sim.roll_pending:
                    break
                continue
            break
        self._watch_continues_cache = (key, clicks)
        return clicks

    # -- hotseat ---------------------------------------------------------------

    @property
    def handoff_required(self) -> bool:
        node = self._node
        return (self.mode == GameMode.HOTSEAT and node is not None
                and node.side != self.authorized_viewer)

    def handoff(self) -> None:
        """Authorize the next side's view (the pass-the-device confirmation)."""
        if self.mode != GameMode.HOTSEAT:
            raise SessionError("handoff only applies to hotseat games")
        node = self._node
        if node is not None:
            self.authorized_viewer = node.side

    # -- serialization -----------------------------------------------------------

    def _view_params(self, viewer_override: Optional[Side] = None
                     ) -> tuple[Optional[Side], bool, bool]:
        """(viewer, reveal, include_decision) for the current mode/state.
        `viewer_override` names the requesting device's side (two-device play)."""
        if self.mode == GameMode.AGENT_V_AGENT:
            return None, self.spectator_reveal, True
        if self.mode == GameMode.HUMAN_V_AGENT:
            node = self._node
            return (self.human_side, False,
                    node is not None and node.side == self.human_side)
        # Two-device: fog to the requesting device's side; show its decision panel
        # only on its own turn. Without a viewer (e.g. lobby fetch) → public view.
        if self.mode == GameMode.HUMAN_V_HUMAN:
            node = self._node
            return (viewer_override, False,
                    viewer_override is not None and node is not None
                    and node.side == viewer_override)
        # Hotseat: during handoff serialize the PUBLIC view only — but while a
        # roll is pending the acting player is still looking (revealing their own
        # dice), so keep showing THEIR private view. Never expose the NEXT
        # player's decision, though: include it only when the current node is the
        # authorized viewer's own.
        if self.handoff_required and not self.roll_pending:
            return None, False, False
        node = self._node
        include = node is not None and node.side == self.authorized_viewer
        return self.authorized_viewer, False, include

    def _agent_log(self, limit: int = 15) -> list[AgentMoveView]:
        """Recent LLM moves + reasoning, for the Watch Agents feed only. Built
        from the recorded tape (steps that carry a justification)."""
        if self.mode != GameMode.AGENT_V_AGENT or self.trajectory is None:
            return []
        reasoned = [t for t in self.trajectory.tape if t.justification]
        return [AgentMoveView(decision_no=t.decision_no, side=t.side,
                              label=t.label, reasoning=t.justification)
                for t in reasoned[-limit:]]

    def state(self, viewer_override: Optional[Side] = None) -> GameView:
        eng = self.env.engine
        viewer, reveal, include_decision = self._view_params(viewer_override)
        node = self._node
        decision = (serializer.decision_view(node)
                    if include_decision and node is not None and not self.watch_pending
                    else None)
        view = GameView(
            game_id=self.game_id,
            revision=self.revision,
            node_id=self.node_id,
            viewer=viewer.value if viewer is not None else None,
            mode=self.mode.value,
            terminal=self.terminal,
            winner=eng.state.winner.value if eng.state.winner else None,
            handoff_required=self.handoff_required,
            roll_pending=self.roll_pending,
            watch_pending=self.watch_pending,
            draft_skip_pending=self.draft_skip_pending,
            watch_batch=self.watch_batch,
            recording=self.recording,
            trajectory_saved=self.trajectory_saved_path is not None,
            agent_log=self._agent_log(),
            status=serializer.status_view(eng),
            board=serializer.board_view(eng, viewer, reveal),
            squadrons=[serializer.squadron_panel(eng, s, viewer, reveal)
                       for s in Side],
            hands=[serializer.hand_view(eng, s, viewer, reveal) for s in Side],
            captures=[serializer.captures_panel(eng, s) for s in Side],
            decision=decision,
            event_log=self.recorder.visible_events(viewer, reveal),
            score_report=self.score_reports[-1] if self.score_reports else None,
        )
        # The copy-for-AI encoding is a pure function of the (already-fogged)
        # view, so it inherits fog safety and always matches what is displayed.
        # Suppressed behind the hotseat handoff screen, where no side's private
        # state is on screen to copy.
        if not (self.handoff_required and not self.roll_pending):
            view.llm_export = game_export(view, draft=self._draft_view(viewer))
        return view
