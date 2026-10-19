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
from enum import Enum
from pathlib import Path
from typing import Optional

from afwip.core.constants import Side, Phase
from afwip.env import AFWIPEnv
from afwip.script import DecisionNode, Choice, NodeType
from afwip.view import serializer
from afwip.view.export import game_export
from afwip.view.events import EventRecorder, score_report
from afwip.view.models import GameView, ScoreReportView, AgentMoveView
from afwip.web.agents import Agent, make_agent
from afwip.rl.trajectory import TrajectoryRecorder
from afwip.rl.state_text import llm_state_text

# Hard ceiling on any automatic advancement loop. Full env games run a few
# thousand decisions; the env itself truncates at 20k steps.
MAX_AUTO_STEPS = 30000

# Opponent setup picks that the live tutorial may run in one Continue instead
# of pausing after every card. Mission stays one step (it is a single choice).
_DRAFT_BATCH_NODES = frozenset({
    NodeType.POSTURE_PICK,
    NodeType.SQUADRON_PICK,
    NodeType.SQUADRON_BASE,
    NodeType.ENABLER_PICK,
    NodeType.BID_SACRIFICE,
})


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
                 openai_api_key: Optional[str] = None):
        self.game_id = game_id
        self.campaign = campaign
        self.mode = mode
        self.human_side = human_side
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.agent_name = agent_name
        self._record = record
        self._openai_api_key = openai_api_key
        self.spectator_reveal = spectator_reveal
        self._human_choices: list[int] = []

        self.env = AFWIPEnv(campaign=campaign)
        self.env.reset(seed=self.seed)
        self.recorder = EventRecorder(self.env.engine)
        # Agent decisions draw from a session-local RNG, decoupled from the
        # engine's dice stream (mirrors the TUI's seed+1 convention).
        self.agent_rng = random.Random(self.seed + 1)

        # Lightweight in-memory decision tape, kept ONLY to power the live
        # agent-reasoning feed in Watch Agents (agent_v_agent). Saving/exporting
        # trajectories has been removed — nothing is ever written to disk.
        self.trajectory: Optional[TrajectoryRecorder] = (
            TrajectoryRecorder(campaign, self.seed, self.env.max_turns,
                               source="human")
            if mode == GameMode.AGENT_V_AGENT else None)

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
        # When True, the next Continue runs every remaining opponent draft pick
        # without pausing. Set from a hold that announces the draft batch.
        self.draft_skip_pending = False
        self._skip_draft_batch = False
        self._last_step_rolled = False
        self._last_step_setup_dice = False
        self.score_reports: list[ScoreReportView] = []
        # Hotseat: the side currently allowed to see private state.
        node = self._node
        self.authorized_viewer: Optional[Side] = node.side if node else None

        if mode == GameMode.HUMAN_V_AGENT:
            self.advance_until_human()

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
        self.recorder.record_decision(self.decision_no, node, node.choices[index])
        if self.trajectory is not None:
            self.trajectory.record(self.decision_no, node, index, justification,
                                   engine=self.env.engine)
        self._track_draft(node, node.choices[index])
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

        Opponent draft picks (posture, squadrons, placement, enablers) are an
        exception: the tutorial holds once before that stretch, and Continue
        runs the whole stretch so the student is not clicking through every card.
        """
        for _ in range(MAX_AUTO_STEPS):
            node = self._node
            if node is None:
                self._skip_draft_batch = False
                return
            agent = self._agent_for(node)
            if agent is None:
                self._skip_draft_batch = False
                return
            if (self.paced and not self._skip_draft_batch
                    and node.node_type in _DRAFT_BATCH_NODES):
                self.watch_pending = True
                self.draft_skip_pending = True
                return
            self._agent_step(node, agent)
            # Pause for the die screen on setup dice and on action dice
            # (acquire / to-hit / damage), including when the AI is rolling in
            # Practice vs Agent so the spectator can watch the tumble.
            if self._last_step_setup_dice or self._last_step_rolled:
                self.roll_pending = True
                self._skip_draft_batch = False
                return
            if self.paced and self._skip_draft_batch:
                nxt = self._node
                if (nxt is not None
                        and self._agent_for(nxt) is not None
                        and nxt.node_type in _DRAFT_BATCH_NODES):
                    continue
                self._skip_draft_batch = False
                if nxt is not None and self._agent_for(nxt) is not None:
                    self.watch_pending = True
                return
            if self.paced:
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
        self.roll_pending = False            # reflect only the action just taken
        self._step(index, justification=justification)
        self._human_choices.append(index)
        # Hold the outcome until the human clicks the die. Action dice pause in
        # every human mode. Setup dice (initiative, the cyber raise, intel)
        # pause in player-vs-AI as well, including when this choice caused them.
        setup_pause = (self.mode == GameMode.HUMAN_V_AGENT
                       and self._last_step_setup_dice)
        if self._last_step_rolled or setup_pause:
            self.roll_pending = True
        elif self.mode == GameMode.HUMAN_V_AGENT:
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
            record=self._record, openai_api_key=self._openai_api_key,
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
            self.watch_pending = True
            return
        self.advance_until_human()

    def continue_watch(self) -> None:
        """Leave the tutorial's hold and play the next opponent decision.

        If the hold was the draft-batch announcement, run every remaining
        opponent draft pick before pausing again.
        """
        if not self.watch_pending:
            raise SessionError("nothing to continue")
        self.watch_pending = False
        if self.draft_skip_pending:
            self.draft_skip_pending = False
            self._skip_draft_batch = True
        if self.mode == GameMode.HUMAN_V_AGENT:
            self.advance_until_human()

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
