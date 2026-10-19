"""
harness.py — Terminal driver for the AFWIP rules engine.

Two modes, both campaign-aware:

  Interactive (hotseat): play a full, faithful game by hand — you control both
  sides. Exposes everything the engine supports: manual drafting (missions /
  posture / squadrons / enablers), squadron base placement (Airbase or
  Contingency Location), initiative-bid card sacrifices, spawn-band placement,
  fog-of-war (enemy tokens hidden until acquired), full Move-Acquire-Shoot
  turns (chain all three, end the turn yourself), missile-defense declaration
  (against token attacks and MD-eligible enabler strikes, with the Decoy
  Warheads / Air Launched Decoy cancel window), and response windows for
  reaction enablers.

      python -m afwip.harness --interactive --campaign 3 --seed 0
      python -m afwip.harness --interactive --auto-draft   # skip manual drafting
      python -m afwip.harness --interactive --reveal        # disable fog-of-war

  Autoplay stress: run many full games with random agents to shake out crashes
  and rule gaps; reports per-campaign stats.

      python -m afwip.harness --autoplay 200
      python -m afwip.harness --autoplay 50 --no-pass --campaign 5

  Env autoplay: the same stress report, but played through the PettingZoo env
  (afwip.env.AFWIPEnv) with random masked actions — exercising the FULL
  decision surface (drafting, bid sacrifices, intel reveals, missile defense,
  response windows, base-damage allocation).

      python -m afwip.harness --env-autoplay 50

The autoplay path is a thin layer over `RulesEngine.legal_actions` /
`apply_action`; interactive and the env additionally drive placement, missile
defense, and response-enabler timing.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Optional

from afwip.core.rules import RulesEngine, IllegalAction, LegalAction
from afwip.core.state import GameState, CardZone
from afwip.core.constants import (
    Side, Phase, BandID, PostureType, EnablerTrigger, TokenScoreType,
    AIRBASE_BONUS_DAMAGE_BOXES, DAMAGE_TO_DESTROY_SQUADRON,
)
from afwip.core.cards import MISSION_REGISTRY, SQUADRON_REGISTRY, ENABLER_REGISTRY, POSTURE_REGISTRY
from afwip.core.enablers import (
    AERIAL_REFUEL_CARDS, CONSTELLATION_CARDS, COUNTER_UAS_CARDS, CYBER_ACQUIRE_CARDS,
    DEFENSIVE_CYBER_CARDS, SHIP_KILL_CARDS,
    ENABLER_CHOICE_BRANCHES, FLYING_CREW_CHIEF_CARDS, INFANTRY_BATTALION_CARDS,
    JOINT_OFFENSIVE_CYBER_CARDS, MD_ELIGIBLE_STRIKE_CARDS,
    MUNITIONS_UPGRADE_CARDS, RAPID_RESUPPLY_CARDS, ROLL_ACQUIRE_CARDS,
    SPECIAL_MISSION_CARDS, SUBMARINE_STRIKE_CARDS,
    UAS_PROLIFERATION_CARDS, card_play_triggers,
)
from afwip.core.tokens import TOKEN_REGISTRY
from afwip.core import board


STANDARD_POSTURE = {Side.US: 49, Side.PRC: 103}


# ---------------------------------------------------------------------------
# Auto-draft (legal setup for a campaign)
# ---------------------------------------------------------------------------

def _legal_missions(camp, side: Side) -> list[int]:
    return [cid for cid, m in MISSION_REGISTRY.items()
            if m.side == side and camp.mission_allowed(m.mission_type)]


def _legal_squadrons(eng: RulesEngine, side: Side) -> list[int]:
    """Campaign-legal squadrons that were not destroyed in an earlier ATO cycle."""
    player = eng.state.player(side)
    return [cid for cid, s in SQUADRON_REGISTRY.items()
            if s.side == side and eng.campaign.squadron_allowed(cid)
            and not (cid in player.squadrons and player.squadrons[cid].is_destroyed)]


def _legal_enablers(eng: RulesEngine, side: Side) -> list[int]:
    """Campaign-legal enablers that are not out of play (spent single-use cards)."""
    player = eng.state.player(side)
    return [cid for cid, e in ENABLER_REGISTRY.items()
            if e.side == side and eng.campaign.enabler_allowed(cid)
            and not (cid in player.enablers and player.enablers[cid].zone == CardZone.REMOVED)]


def auto_draft(eng: RulesEngine, rng: random.Random, verbose: bool = False) -> None:
    """
    First ATO cycle: draft a legal mission/posture/card set. Later cycles
    auto-field the surviving roster (via `select_posture_only`) with fresh
    enablers — CARD damage persists, token losses reset (ruling 2026-07-22).
    """
    camp = eng.campaign
    if eng.state.ato_cycle > 1:
        for side in (Side.US, Side.PRC):
            prof = POSTURE_REGISTRY[STANDARD_POSTURE[side]]
            pool = _legal_enablers(eng, side) if camp.enablers_allowed else []
            enablers = rng.sample(pool, min(prof.enablers, len(pool)))
            eng.select_posture_only(side, STANDARD_POSTURE[side], enablers)
            if verbose:
                player = eng.state.player(side)
                print(f"  {side.value}: redeployed "
                      f"{sum(1 for s in player.squadrons.values() if s.zone == CardZone.SELECTED)}"
                      f" squadron(s), fresh hand {len(player.enablers_in_hand())}")
        return
    if eng.state.us.mission_card_id is None:
        us_m = rng.choice(_legal_missions(camp, Side.US))
        prc_m = rng.choice(_legal_missions(camp, Side.PRC))
        eng.setup_missions(us_m, prc_m)
        if verbose:
            print(f"  Missions: US={MISSION_REGISTRY[us_m].name}  PRC={MISSION_REGISTRY[prc_m].name}")

    for side in (Side.US, Side.PRC):
        posture = STANDARD_POSTURE[side]
        prof = POSTURE_REGISTRY[posture]

        pool = _legal_squadrons(eng, side)
        rng.shuffle(pool)
        forced = camp.forced_squadrons.get(side)
        if forced is not None:
            # Campaign 1: the forced card (F-16 / J-10) must be INCLUDED in an
            # otherwise-normal Standard roster — draft it plus fill to the count.
            forced_list = [c for c in forced if c in pool]
            rest = [c for c in pool if c not in forced_list]
            squads = forced_list + rest[:max(0, prof.squadrons - len(forced_list))]
        else:
            squads = pool[:prof.squadrons]   # exact count (or all that remain)

        if camp.enablers_allowed:
            # The posture's enabler count is exact (not "up to"): draft the
            # full amount, or all that remain if the pool has run dry.
            epool = _legal_enablers(eng, side)
            rng.shuffle(epool)
            enablers = epool[:prof.enablers]
        else:
            enablers = []

        # Occasionally deploy US squadrons at the Contingency Location so ACE /
        # CL generation rules get exercised in autoplay.
        locations = None
        if side == Side.US:
            locations = {cid: (BandID.US_CONTINGENCY_LOCATION if rng.random() < 0.25
                               else BandID.US_AIRBASE) for cid in squads}

        eng.select_posture(side, posture, squads, enablers, squadron_locations=locations)
        if verbose:
            print(f"  {side.value}: posture={prof.name} squadrons={squads} enablers={enablers}")


def _start_cycle(eng: RulesEngine, rng: random.Random, verbose: bool = False) -> None:
    if verbose:
        print(f"\n=== ATO Cycle {eng.state.ato_cycle}/{eng.state.total_ato_cycles} "
              f"(Campaign {eng.campaign.number}: {eng.campaign.name}) ===")
    auto_draft(eng, rng, verbose)
    eng.bid_for_initiative()
    eng.play_intel()
    eng.begin_player_turns()
    if verbose:
        print(f"  Initiative: {eng.state.initiative_holder.value}; first to move: {eng.state.active_side.value}")


# ---------------------------------------------------------------------------
# Autoplay stress mode
# ---------------------------------------------------------------------------

@dataclass
class GameOutcome:
    winner: str            # "US" / "PRC" / "DRAW" / "CAPPED"
    cyber_win: bool
    turns: int
    us_vp: int
    prc_vp: int
    error: str = ""
    us_mission: str = ""   # MissionType value drafted for the game
    prc_mission: str = ""


def autoplay_game(campaign: int, rng: random.Random,
                  pass_prob: float = 0.3, max_turns: int = 1500) -> GameOutcome:
    """Play one full game with random agents. Returns the outcome."""
    eng = RulesEngine(GameState.new_game(campaign=campaign), rng=rng)
    _start_cycle(eng, rng)
    # Missions are drafted once per game (they persist across ATO cycles).
    us_mt = eng.state.us.mission.mission_type.value
    prc_mt = eng.state.prc.mission.mission_type.value
    turns = 0
    try:
        while not eng.state.game_over and turns < max_turns:
            if eng.state.phase == Phase.ATO_SETUP:
                _start_cycle(eng, rng)
                continue
            side = eng.state.active_side
            actions = eng.legal_actions(side)
            non_pass = [a for a in actions if a.kind != "pass"]
            if not non_pass or rng.random() < pass_prob:
                choice = next(a for a in actions if a.kind == "pass")
            else:
                choice = rng.choice(non_pass)

            try:
                eng.apply_action(choice)
            except IllegalAction:
                # A default-parameter enabler play that didn't apply: advance safely.
                if eng.state.phase == Phase.PLAYER_TURN and not eng.state.game_over:
                    eng.pass_turn(side)
                turns += 1
                continue

            # A single sub-action per turn keeps games progressing; activate,
            # relaunch and pass already ended the turn themselves.
            if choice.kind not in ("activate", "relaunch", "pass") and \
                    eng.state.phase == Phase.PLAYER_TURN and not eng.state.game_over:
                eng.end_turn(side)
            turns += 1
    except Exception as exc:  # pragma: no cover - surfaced as a failing outcome
        return GameOutcome("ERROR", False, turns, 0, 0, error=f"{type(exc).__name__}: {exc}",
                           us_mission=us_mt, prc_mission=prc_mt)

    us_vp = eng.total_victory_points(Side.US)
    prc_vp = eng.total_victory_points(Side.PRC)
    cyber_win = eng.state.game_over and eng.state.winner is not None and turns < max_turns \
        and max(eng.state.us.cyber_rate, eng.state.prc.cyber_rate) >= 4
    if turns >= max_turns and not eng.state.game_over:
        return GameOutcome("CAPPED", False, turns, us_vp, prc_vp,
                           us_mission=us_mt, prc_mission=prc_mt)
    if eng.state.winner is not None:
        winner = eng.state.winner.value
    else:
        winner = "US" if us_vp > prc_vp else "PRC" if prc_vp > us_vp else "DRAW"
    return GameOutcome(winner, cyber_win, turns, us_vp, prc_vp,
                       us_mission=us_mt, prc_mission=prc_mt)


def _score_histogram(values: list[int], bins: int = 16) -> str:
    """Compact unicode histogram of `values`, labelled with the score range."""
    lo, hi = min(values), max(values)
    if lo == hi:
        return f"(all {lo})"
    bins = min(bins, hi - lo + 1)
    counts = [0] * bins
    for v in values:
        counts[(v - lo) * bins // (hi - lo + 1)] += 1
    blocks = " ▁▂▃▄▅▆▇█"
    peak = max(counts)
    bar = "".join(blocks[max(1, round(c / peak * 8))] if c else "·" for c in counts)
    return f"{lo} |{bar}| {hi}"


def _report_mission_scores(campaigns: list[int], mission_stats: dict) -> None:
    """Per-campaign, per-mission-type distribution of final VP scores."""
    import statistics
    print("\nScore distribution by mission type (completed games only):")
    for c in campaigns:
        rows = [(k[1:], v) for k, v in mission_stats.items() if k[0] == c]
        if not rows:
            continue
        print(f"\nCampaign {c}:")
        print(f"  {'Side':<5}{'Mission':<22}{'n':>4}{'win%':>6}{'min':>5}"
              f"{'med':>5}{'mean':>7}{'max':>5}  histogram")
        for (side, mission), samples in sorted(rows, key=lambda r: (r[0][0] != "US", r[0][1])):
            vps = [vp for vp, _ in samples]
            win = 100 * sum(won for _, won in samples) / len(samples)
            print(f"  {side:<5}{mission:<22}{len(samples):>4}{win:>5.0f}%{min(vps):>5}"
                  f"{statistics.median(vps):>5.0f}{statistics.mean(vps):>7.1f}{max(vps):>5}"
                  f"  {_score_histogram(vps)}")


def run_stress(campaigns: list[int], games: int, seed: int,
               pass_prob: float = 0.3, max_turns: int = 1500) -> int:
    """Run `games` autoplay games per campaign; print a report. Returns error count."""
    rng = random.Random(seed)
    total_errors = 0
    mission_stats: dict[tuple[int, str, str], list[tuple[int, bool]]] = {}
    mode = "pass only when forced" if pass_prob <= 0 else f"pass_prob={pass_prob}"
    print(f"Autoplay stress: {games} games/campaign, seed={seed}, {mode}, max_turns={max_turns}\n")
    header = f"{'Camp':<6}{'US':>5}{'PRC':>5}{'Draw':>6}{'Capped':>8}{'Cyber':>7}{'Err':>5}{'avgТurns':>10}"
    print(header.replace("Т", "T"))
    print("-" * len(header))
    for c in campaigns:
        tally = {"US": 0, "PRC": 0, "DRAW": 0, "CAPPED": 0, "cyber": 0, "err": 0, "turns": 0}
        for _ in range(games):
            out = autoplay_game(c, rng, pass_prob=pass_prob, max_turns=max_turns)
            if out.winner == "ERROR":
                tally["err"] += 1
                total_errors += 1
                print(f"  [C{c}] ERROR: {out.error}")
                continue
            tally[out.winner if out.winner in ("US", "PRC", "DRAW", "CAPPED") else "DRAW"] += 1
            tally["cyber"] += int(out.cyber_win)
            tally["turns"] += out.turns
            if out.winner != "CAPPED":   # capped games never ran final scoring
                for side, mission, vp in (("US", out.us_mission, out.us_vp),
                                          ("PRC", out.prc_mission, out.prc_vp)):
                    mission_stats.setdefault((c, side, mission), []).append(
                        (vp, out.winner == side))
        avg = tally["turns"] / max(1, games)
        print(f"C{c:<5}{tally['US']:>5}{tally['PRC']:>5}{tally['DRAW']:>6}"
              f"{tally['CAPPED']:>8}{tally['cyber']:>7}{tally['err']:>5}{avg:>10.1f}")
    _report_mission_scores(campaigns, mission_stats)
    print(f"\nTotal errors: {total_errors}")
    return total_errors


def run_env_stress(campaigns: list[int], games: int, seed: int) -> int:
    """
    Random-agent stress through the PettingZoo env (afwip.env.AFWIPEnv), which
    drives the FULL decision surface — drafting, bids, intel reveals, missile
    defense, response windows, and base-damage allocation are all agent
    decisions (autoplay mode scripts those and only randomises player turns).
    Prints the same style of report; returns the error count.
    """
    import numpy as np
    from afwip.env import AFWIPEnv

    rng = random.Random(seed)
    total_errors = 0
    mission_stats: dict[tuple[int, str, str], list[tuple[int, bool]]] = {}
    print(f"Env autoplay stress: {games} games/campaign, seed={seed} (full decision surface)\n")
    header = f"{'Camp':<6}{'US':>5}{'PRC':>5}{'Draw':>6}{'Trunc':>7}{'Err':>5}{'avgSteps':>10}"
    print(header)
    print("-" * len(header))
    for c in campaigns:
        tally = {"US": 0, "PRC": 0, "DRAW": 0, "TRUNC": 0, "err": 0, "steps": 0}
        for _ in range(games):
            env = AFWIPEnv(campaign=c)
            try:
                env.reset(seed=rng.randrange(2**31))
                steps, truncated = 0, False
                for _agent in env.agent_iter():
                    obs, _r, term, trunc, _info = env.last()
                    if term or trunc:
                        truncated |= trunc
                        env.step(None)
                        continue
                    legal = np.flatnonzero(obs["action_mask"])
                    env.step(int(rng.choice(legal)))
                    steps += 1
                tally["steps"] += steps
                if truncated:
                    tally["TRUNC"] += 1
                    continue
                eng = env.engine
                us_vp = eng.total_victory_points(Side.US)
                prc_vp = eng.total_victory_points(Side.PRC)
                if eng.state.winner is not None:
                    w = eng.state.winner.value
                else:
                    w = "US" if us_vp > prc_vp else "PRC" if prc_vp > us_vp else "DRAW"
                tally[w] += 1
                for side, vp in ((Side.US, us_vp), (Side.PRC, prc_vp)):
                    mt = eng.state.player(side).mission.mission_type.value
                    mission_stats.setdefault((c, side.value, mt), []).append(
                        (vp, w == side.value))
            except Exception as exc:
                tally["err"] += 1
                total_errors += 1
                print(f"  [C{c}] ERROR: {type(exc).__name__}: {exc}")
        avg = tally["steps"] / max(1, games)
        print(f"C{c:<5}{tally['US']:>5}{tally['PRC']:>5}{tally['DRAW']:>6}"
              f"{tally['TRUNC']:>7}{tally['err']:>5}{avg:>10.1f}")
    _report_mission_scores(campaigns, mission_stats)
    print(f"\nTotal errors: {total_errors}")
    return total_errors


# ---------------------------------------------------------------------------
# Interactive mode — full-fidelity human-controlled game
# ---------------------------------------------------------------------------

class _Quit(Exception):
    """Raised from an input prompt to abort the interactive game."""


def _ask(prompt: str) -> str:
    raw = input(prompt).strip()
    if raw.lower() in ("q", "quit", "exit"):
        raise _Quit
    return raw


def _ask_int(prompt: str, lo: int, hi: int, blank=None):
    """Prompt for an int in [lo, hi]; blank returns `blank` if it isn't None."""
    while True:
        raw = _ask(prompt)
        if raw == "" and blank is not None:
            return blank
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"  ! enter a number {lo}-{hi}" + ("" if blank is None else " (or blank)"))


def _summarize(kind: str, result) -> str:
    """One-line summary of an action result for the interactive log."""
    if kind == "activate":
        return f"generated {len(result)} token(s)"
    if kind == "acquire":
        return f"acquire success={result.success}"
    if kind in ("shoot_air", "shoot_surface"):
        killed = result.destroyed_token_uids + result.destroyed_squadron_ids
        roll = "auto-hit" if result.hit_roll is None else f"roll={result.hit_roll.value}({result.hit_roll.mode.value})"
        extra = " winchester" if result.attacker_winchester else ""
        md = f" [MD by #{result.missile_defense_uid}]" if result.missile_defense_uid else ""
        return f"hit={result.hit} {roll} damage={result.damage} destroyed={killed}{md}{extra}"
    if kind == "play_enabler":
        bits = []
        if result.tokens:      bits.append(f"tokens={result.tokens}")
        if result.acquired:    bits.append(f"acquired={result.acquired}")
        if result.destroyed:   bits.append(f"destroyed={result.destroyed}")
        if result.discarded:   bits.append(f"discarded={result.discarded}")
        if result.recovered:   bits.append(f"recovered={result.recovered}")
        if result.cyber_delta: bits.append(f"cyberΔ={result.cyber_delta:+d}")
        if result.base_damage: bits.append(f"base_dmg={result.base_damage}")
        if result.cancelled:   bits.append("cancelled")
        if result.note:        bits.append(result.note)
        return "enabler: " + (", ".join(bits) or "played (no effect this time)")
    return ""


def _render(eng: RulesEngine, viewer: Side, fog: bool = True) -> None:
    """Render the board from `viewer`'s perspective (fog masks unacquired enemies)."""
    gs = eng.state
    print("\n" + "=" * 70)
    print(f"ATO {gs.ato_cycle}/{gs.total_ato_cycles} | turn {gs.turn_number} | "
          f"active: {gs.active_side.value} | "
          f"cyber US={gs.us.cyber_rate} PRC={gs.prc.cyber_rate} | "
          f"VP US={eng.total_victory_points(Side.US)} PRC={eng.total_victory_points(Side.PRC)}")
    for side in (viewer, eng.state.opponent(viewer).side):
        p = gs.player(side)
        own = side == viewer
        toks = []
        for t in p.living_tokens():
            flags = ("(W)" if t.is_winchester else "") + ("(g)" if t.grounded else "")
            if own or not fog or t.acquired:
                mark = "*" if (t.acquired and not own) else ""
                toks.append(f"{t.token_type.value}#{t.uid}@{t.location.name}{mark}{flags}")
            else:  # hidden enemy: position + acquisition value only
                toks.append(f"?#{t.uid}@{t.location.name}(av{t.profile.acquisition_value})")
        if own or not fog:
            sqs = [f"{s.card_id}({s.token_type.value}){'✓' if s.activated else ''}"
                   for s in p.squadrons.values() if not s.is_destroyed]
        else:  # enemy squadrons: activated ones are revealed, rest face-down
            revealed = [f"{s.card_id}({s.token_type.value})" for s in p.squadrons.values()
                        if s.activated and not s.is_destroyed]
            hidden = sum(1 for s in p.squadrons.values() if not s.activated and not s.is_destroyed)
            sqs = revealed + ([f"{hidden}x face-down"] if hidden else [])
        tag = "you" if own else "enemy"
        hand = p.enablers_in_hand()
        if own or not fog:
            hand_desc = ", ".join(ENABLER_REGISTRY[c.card_id].name for c in hand) or "-"
        else:   # enemy hand: revealed cards by name (Play Intel), rest hidden
            known = [ENABLER_REGISTRY[c.card_id].name for c in hand if c.revealed_to_opponent]
            hidden = sum(1 for c in hand if not c.revealed_to_opponent)
            hand_desc = ", ".join(known + ([f"{hidden}x hidden"] if hidden else [])) or "-"
        print(f"  {side.value} ({tag}): tokens[{', '.join(toks) or '-'}]  squadrons[{', '.join(sqs) or '-'}]")
        print(f"      enablers[{hand_desc}]")
    print("=" * 70)


# --- drafting ---------------------------------------------------------------

def _pick_conditional(title: str, pool: list[int], label, base: int, bonus_specs,
                      min_required: int = 0, preselected=None) -> list[int]:
    """
    Pick cards up to `base`, plus extra cards that qualify for a posture "bonus"
    slot. `bonus_specs` is a list of (predicate, count): a card matching the
    predicate may use one of `count` free slots instead of a general slot. A card
    is only offered while a slot it can occupy remains, so illegal drafts (e.g. a
    6th non-ADA squadron under the ADA posture) are impossible.

    `min_required` forces at least that many picks before "blank to finish" is
    accepted (the posture's Enabler Card count is exact, not a maximum).
    `preselected` cards (Campaign 1's forced squadron) start in the draft, count
    toward the base/min, and are not offered again.
    """
    chosen: list[int] = list(preselected or [])
    remaining = [c for c in pool if c not in chosen]

    def used_bonus() -> int:
        return sum(min(sum(1 for c in chosen if pred(c)), cnt) for pred, cnt in bonus_specs)

    def general_used() -> int:
        return len(chosen) - used_bonus()

    def can_add(cid: int) -> bool:
        for pred, cnt in bonus_specs:
            if pred(cid) and sum(1 for c in chosen if pred(c)) < cnt:
                return True   # fits a free bonus slot
        return general_used() < base

    while remaining:
        eligible = [c for c in remaining if can_add(c)]
        if not eligible:
            break
        note = f"base {general_used()}/{base}"
        for pred, cnt in bonus_specs:
            if cnt:
                note += f", bonus {min(sum(1 for c in chosen if pred(c)), cnt)}/{cnt}"
        must_pick = len(chosen) < min_required
        tail = f"must pick {min_required - len(chosen)} more" if must_pick else "blank to finish"
        print(f"  {title} ({note}) — {tail}:")
        for i, cid in enumerate(eligible):
            print(f"    [{i}] {label(cid)}")
        idx = _ask_int("    pick #> ", 0, len(eligible) - 1, blank=-1)
        if idx == -1:
            if must_pick:
                print(f"    ! exactly {min_required} card(s) must be selected")
                continue
            break
        pick = eligible[idx]
        chosen.append(pick)
        remaining.remove(pick)
    return chosen


def _is_score(card_id: int, score_type) -> bool:
    return TOKEN_REGISTRY[SQUADRON_REGISTRY[card_id].token_type].token_score_type == score_type


def _draft_side(eng: RulesEngine, side: Side) -> None:
    camp = eng.campaign
    player = eng.state.player(side)
    # Posture
    postures = [cid for cid, p in POSTURE_REGISTRY.items()
                if p.side == side and camp.posture_allowed(p.posture_type)
                and (p.can_repeat or p.posture_type not in player.postures_used)]
    print(f"\n {side.value} posture:")
    for i, cid in enumerate(postures):
        p = POSTURE_REGISTRY[cid]
        print(f"    [{i}] {p.name} (squadrons {p.squadrons}, enablers {p.enablers})")
    posture = postures[_ask_int("  posture #> ", 0, len(postures) - 1)]
    prof = POSTURE_REGISTRY[posture]

    # Squadrons AND enablers are re-drafted EVERY cycle (ruling 2026-07-22):
    # each cycle pick a posture, then which surviving Squadron Cards to field and
    # where (placement re-chosen; CARD damage persists, token losses reset). The
    # pool below excludes destroyed cards.
    # Squadrons — base limit plus posture-specific bonus slots (ADA / bomber only).
    forced = camp.forced_squadrons.get(side)
    squad_pool = _legal_squadrons(eng, side)
    if prof.flying_only:   # Joint Operations: all Squadrons must be flying units
        squad_pool = [c for c in squad_pool if SQUADRON_REGISTRY[c].flying]
    # Campaign 1 forces the side's specific card (F-16 / J-10) to be INCLUDED in
    # an otherwise-normal Standard draft: pre-select it, then draft the rest.
    preselected = [c for c in sorted(forced) if c in squad_pool] if forced else []
    if preselected:
        print(f"  {side.value} squadrons required by campaign (already selected): "
              f"{[SQUADRON_REGISTRY[c].name for c in preselected]}")
    sq_bonus = [(lambda c: _is_score(c, TokenScoreType.ADA), prof.ada_bonus_squadron),
                (lambda c: _is_score(c, TokenScoreType.BOMBER), prof.bomber_bonus)]
    squads = _pick_conditional(
        f"{side.value} squadrons", squad_pool,
        lambda c: f"{SQUADRON_REGISTRY[c].name} ({SQUADRON_REGISTRY[c].token_type.value})",
        prof.squadrons, sq_bonus,
        # May stop one below the posture count (ruling 2026-07-31); all
        # remaining are drafted if the pool can't reach one-below.
        min_required=min(max(prof.squadrons - 1, 0), len(squad_pool)),
        preselected=preselected)

    # US squadrons may deploy to the Contingency Location (not once SURGE has
    # been selected: CLs cannot be used for the rest of the campaign).
    locations = None
    if side == Side.US and squads and prof.posture_type != PostureType.SURGE \
            and not player.cl_banned_campaign:
        locations = {}
        for cid in squads:
            print(f"  place {SQUADRON_REGISTRY[cid].name}: [0] Airbase  [1] Contingency Location")
            pick = _ask_int("  base #> ", 0, 1, blank=0)
            locations[cid] = BandID.US_CONTINGENCY_LOCATION if pick == 1 else BandID.US_AIRBASE

    # Enablers — the posture count is exact (blank-finish only once reached),
    # plus an optional PLARF bonus slot (PRC Standoff).
    if camp.enablers_allowed:
        en_pool = _legal_enablers(eng, side)
        if prof.plaaf_only:   # PLAAF posture: enablers must be PLAAF cards
            en_pool = [c for c in en_pool if ENABLER_REGISTRY[c].plaaf]
        en_bonus = [(lambda c: bool(ENABLER_REGISTRY[c].plarf), prof.plarf_bonus or 0)]
        enablers = _pick_conditional(
            f"{side.value} enablers", en_pool,
            lambda c: f"{ENABLER_REGISTRY[c].name} [{ENABLER_REGISTRY[c].enabler_class.value}]",
            prof.enablers, en_bonus,
            min_required=min(prof.enablers, len(en_pool)))
    else:
        enablers = []
        print(f"  {side.value}: no enablers this campaign")

    eng.select_posture(side, posture, squads, enablers, squadron_locations=locations)

    # HEDGEHOG grants a free ADA token; the US owner places it on the Airbase or
    # the Contingency Location (unless a SURGE campaign ban is in force).
    if side == Side.US and prof.ada_bonus_token > 0 and not player.cl_banned_campaign:
        print(f"  place {prof.name} ADA token: [0] Airbase  [1] Contingency Location")
        pick = _ask_int("  ADA base #> ", 0, 1, blank=0)
        eng.state.player(side).posture_bonus_ada_location = (
            BandID.US_CONTINGENCY_LOCATION if pick == 1 else BandID.US_AIRBASE)


def _prompt_bid_sacrifices(eng: RulesEngine, side: Side) -> list[int]:
    """Pick Enabler Cards to sacrifice for the initiative bid (+1 each, back to deck)."""
    hand = eng.state.player(side).enablers_in_hand()
    if not hand or eng.campaign.number == 2:   # Tournament: no sacrifices
        return []
    chosen: list[int] = []
    while len(chosen) < len(hand):
        avail = [c for c in hand if c.card_id not in chosen]
        print(f"  {side.value} bid: sacrifice an enabler for +1? (blank = done, {len(chosen)} so far)")
        for i, c in enumerate(avail):
            print(f"    [{i}] {ENABLER_REGISTRY[c.card_id].name}")
        idx = _ask_int("  sacrifice #> ", 0, len(avail) - 1, blank=-1)
        if idx == -1:
            break
        chosen.append(avail[idx].card_id)
    return chosen


def _play_intel_interactive(eng: RulesEngine, manual: bool) -> None:
    """
    Run the Play Intel phase visibly: announce each side's D4 (the initiative
    holder rolls at advantage), let each card owner pick which of their
    enablers to show (manual mode), then print what each side saw.
    """
    counts = eng.play_intel_roll()
    for viewer in (Side.US, Side.PRC):
        roll = eng.last_intel_rolls[viewer]
        owner = eng.state.opponent(viewer)
        print(f"  Intel: {viewer.value} rolls D4 = {roll.value} ({roll.mode.value.lower()})"
              f" -> {owner.side.value} must show {counts[owner.side]} of their"
              f" {len(owner.enablers_in_hand())} card(s) (>=1 always stays hidden)")

    for owner_side in (Side.US, Side.PRC):
        hand_ids = [c.card_id for c in eng.state.player(owner_side).enablers_in_hand()]
        n = counts[owner_side]
        if manual and n > 0:
            chosen: list = []
            avail = list(hand_ids)
            print(f"  Intel: {owner_side.value} picks {n} enabler card(s) to show:")
            while len(chosen) < n and avail:
                for i, cid in enumerate(avail):
                    print(f"    [{i}] {ENABLER_REGISTRY[cid].name}")
                idx = _ask_int(f"  show card {len(chosen) + 1}/{n} #> ", 0, len(avail) - 1, blank=0)
                chosen.append(avail.pop(idx))
        else:
            chosen = hand_ids[:n]
        eng.play_intel_reveal(owner_side, chosen)

    for viewer in (Side.US, Side.PRC):
        opp = eng.state.opponent(viewer)
        names = [ENABLER_REGISTRY[c.card_id].name for c in opp.enablers.values()
                 if c.revealed_to_opponent]
        print(f"  Intel: {viewer.value} sees {counts[opp.side]} {opp.side.value} "
              f"enabler(s): {', '.join(names) or 'none'}")


def _manual_start_cycle(eng: RulesEngine, rng: random.Random, auto: bool) -> None:
    print(f"\n=== ATO Cycle {eng.state.ato_cycle}/{eng.state.total_ato_cycles} "
          f"(Campaign {eng.campaign.number}: {eng.campaign.name}) ===")
    if auto:
        auto_draft(eng, rng, verbose=True)
        eng.bid_for_initiative()
    else:
        if eng.state.us.mission_card_id is None:
            for side in (Side.US, Side.PRC):
                opts = _legal_missions(eng.campaign, side)
                print(f" {side.value} mission:")
                for i, cid in enumerate(opts):
                    print(f"    [{i}] {MISSION_REGISTRY[cid].name}")
                pick = opts[_ask_int("  mission #> ", 0, len(opts) - 1)]
                eng.state.player(side).mission_card_id = pick
        for side in (Side.US, Side.PRC):
            _draft_side(eng, side)
        us_sac = _prompt_bid_sacrifices(eng, Side.US)
        prc_sac = _prompt_bid_sacrifices(eng, Side.PRC)
        eng.bid_for_initiative(us_sacrifice=us_sac, prc_sacrifice=prc_sac)
        # "The winner chooses who will take the first turn."
        winner = eng.state.initiative_holder
        loser = board.opponent(winner)
        print(f"  {winner.value} holds initiative and chooses who takes the first turn:")
        pick = _ask_int(f"  [0] {winner.value} first  [1] {loser.value} first > ", 0, 1, blank=0)
        eng.choose_first_player(winner if pick == 0 else loser)
    _play_intel_interactive(eng, manual=not auto)
    eng.begin_player_turns()
    print(f"  Initiative: {eng.state.initiative_holder.value}; first to move: {eng.state.active_side.value}")


# --- action helpers ---------------------------------------------------------

def _prompt_spawn_band(eng: RulesEngine, side: Side, token_type):
    from afwip.core import board
    legal = board.valid_spawn_locations(token_type, side, eng.state.player(side).posture_type)
    if eng.state.player(side).cl_banned_campaign:
        legal = legal - {BandID.US_CONTINGENCY_LOCATION}
    bands = sorted(legal, key=lambda b: b.name)
    if len(bands) <= 1:
        return bands[0] if bands else None
    print("  place where?")
    for i, b in enumerate(bands):
        print(f"    [{i}] {b.name}")
    return bands[_ask_int("  band #> ", 0, len(bands) - 1)]


def _prompt_tokens(eng: RulesEngine, side: Side, n: int, pool_fn, verb: str) -> list[int]:
    """Prompt for `n` enemy tokens to acquire/destroy (fog-safe labels)."""
    chosen: list[int] = []
    for _ in range(n):
        avail = [u for u in pool_fn(side) if u not in chosen]
        if not avail:
            break
        print(f"  {verb} which token? ({len(chosen) + 1} of {n})")
        for i, u in enumerate(avail):
            t = eng.state.get_token(u)
            label = (f"{t.token_type.value}#{u}" if t.acquired
                     else f"?#{u}(av{t.profile.acquisition_value})")
            print(f"    [{i}] {label} in {t.location.name}")
        chosen.append(avail[_ask_int("  token #> ", 0, len(avail) - 1)])
    return chosen


def _build_enabler_play(eng: RulesEngine, side: Side, card_id: int, response: bool = False):
    from afwip.core.enablers import EnablerPlay
    profile = ENABLER_REGISTRY[card_id]
    play: EnablerPlay = eng._default_enabler_play(side, card_id)   # sensible defaults for targets
    if profile.generates_token is not None:
        play.spawn_band = _prompt_spawn_band(eng, side, profile.generates_token)
    if card_id in AERIAL_REFUEL_CARDS:
        # "Place one squadron card in addition to the Posture limit" — choose it.
        cands = eng.aerial_refuel_candidates(side)
        if cands:
            print("  place which squadron on the airbase (beyond the posture limit)?")
            for i, c in enumerate(cands):
                sp = SQUADRON_REGISTRY[c]
                print(f"    [{i}] {sp.name} ({sp.token_type.value})")
            play.target_squadron_id = cands[_ask_int("  squadron #> ", 0, len(cands) - 1)]
    if card_id in RAPID_RESUPPLY_CARDS:
        cands = eng.rapid_resupply_targets(side)
        if cands:
            print("  recover which discarded card?")
            for i, c in enumerate(cands):
                prof = SQUADRON_REGISTRY.get(c) or ENABLER_REGISTRY[c]
                print(f"    [{i}] {prof.name}")
            play.target_squadron_id = cands[_ask_int("  card #> ", 0, len(cands) - 1)]
    if card_id in CONSTELLATION_CARDS:
        cands = eng.reconstitutable_plassf(side)
        if cands:
            print("  return which spent PLASSF card to the deck?")
            for i, c in enumerate(cands):
                print(f"    [{i}] {ENABLER_REGISTRY[c].name}")
            play.target_squadron_id = cands[_ask_int("  card #> ", 0, len(cands) - 1)]
        else:
            print("  (no spent PLASSF card to return)")
    if card_id in CYBER_ACQUIRE_CARDS:
        play.target_uids = _prompt_tokens(
            eng, side, eng.state.player(side).cyber_rate,
            eng.acquirable_enemy_tokens, "acquire")
    if card_id in ROLL_ACQUIRE_CARDS:
        play.rolled_count = eng._d4()
        print(f"  rolled {play.rolled_count} — choose that many to acquire")
        play.target_uids = _prompt_tokens(
            eng, side, play.rolled_count, eng.acquirable_enemy_tokens, "acquire")
    if card_id in JOINT_OFFENSIVE_CYBER_CARDS:
        play.target_uids = _prompt_tokens(
            eng, side, eng.state.player(side).cyber_rate * 2,
            eng.removable_enemy_tokens, "destroy")
    if card_id in COUNTER_UAS_CARDS:
        # Destroys Cyber-Rate enemy UAS tokens — choose which UAS.
        play.target_uids = _prompt_tokens(
            eng, side, eng.state.player(side).cyber_rate,
            eng.removable_enemy_uas, "destroy")
    if card_id in UAS_PROLIFERATION_CARDS:
        # One extra acquisition attempt — the owner picks the enemy token.
        picks = _prompt_tokens(eng, side, 1, eng.acquirable_enemy_tokens, "acquire")
        if picks:
            play.target_uids = picks
    if card_id in SHIP_KILL_CARDS and play.choice != "cancel":
        ships = eng.enemy_ship_targets(side)
        if len(ships) > 1:
            print("  sink which enemy surface combatant?")
            for i, u in enumerate(ships):
                t = eng.state.get_token(u)
                label = (f"{t.token_type.value}#{u}" if t.acquired
                         else f"?#{u}(av{t.profile.acquisition_value})")
                print(f"    [{i}] {label} in {t.location.name}")
            play.target_uids = [ships[_ask_int("  ship #> ", 0, len(ships) - 1)]]
        elif ships:
            play.target_uids = [ships[0]]
    if card_id in INFANTRY_BATTALION_CARDS:
        bands = eng.infantry_battalion_bases(side)
        if len(bands) > 1:
            print("  place the Infantry Battalion on which base?")
            for i, b in enumerate(bands):
                print(f"    [{i}] {b.name}")
            play.target_band = bands[_ask_int("  base #> ", 0, len(bands) - 1)]
        elif bands:
            play.target_band = bands[0]
    if card_id in FLYING_CREW_CHIEF_CARDS:
        # "Max aircraft for 1 Squadron at a contingency location" — choose it.
        cands = eng.flying_crew_chief_candidates(side)
        if cands:
            print("  which Contingency Location squadron generates max (no roll)?")
            for i, c in enumerate(cands):
                sp = SQUADRON_REGISTRY[c]
                print(f"    [{i}] {sp.name} ({sp.token_type.value})")
            play.target_squadron_id = cands[_ask_int("  squadron #> ", 0, len(cands) - 1)]
        else:
            print("  (no un-activated Contingency Location squadron to apply it to)")
    if card_id in MUNITIONS_UPGRADE_CARDS:
        # "One fighter squadron shoots air-to-air at range 4" — choose it.
        cands = eng.munitions_upgrade_candidates(side)
        if cands:
            print("  which fighter squadron shoots air-to-air at range 4?")
            for i, c in enumerate(cands):
                sp = SQUADRON_REGISTRY[c]
                print(f"    [{i}] {sp.name} ({sp.token_type.value})")
            play.target_squadron_id = cands[_ask_int("  squadron #> ", 0, len(cands) - 1)]
        else:
            print("  (no fighter squadron to apply it to)")
    choices = ENABLER_CHOICE_BRANCHES.get(card_id)
    if card_id in SUBMARINE_STRIKE_CARDS:
        # Branch fixed by context (user ruling 2026-07-14): CANCEL only as a
        # response to the opponent's submarine card, ATTACK on the owner's turn.
        play.choice = "cancel" if response else "attack"
    elif card_id in DEFENSIVE_CYBER_CARDS:
        # Same treatment (user ruling 2026-07-17): CANCEL only as a response to
        # the opponent's cyber card, DEGRADE on the owner's own turn.
        play.choice = "cancel" if response else "degrade"
    elif choices:
        print("  choose branch:")
        for i, c in enumerate(choices):
            print(f"    [{i}] {c}")
        play.choice = choices[_ask_int("  choice #> ", 0, len(choices) - 1)]
    if card_id in SPECIAL_MISSION_CARDS and play.choice == "acquire":
        # Roll-then-choose on the acquire branch (the handler reuses the roll).
        play.rolled_count = eng._d4()
        print(f"  rolled {play.rolled_count} — choose that many to acquire")
        play.target_uids = _prompt_tokens(
            eng, side, play.rolled_count, eng.acquirable_enemy_tokens, "acquire")
    return play


def _prompt_missile_defense(eng: RulesEngine, defender_side: Side, attacker, target_band):
    """Let the defender optionally declare a covering naval missile-defense token."""
    elig = eng.eligible_missile_defenders(defender_side, attacker.location, attacker.side, target_band)
    if not elig:
        return None
    print(f"  {defender_side.value} may declare naval missile defense (blank = none):")
    for i, t in enumerate(elig):
        print(f"    [{i}] {t.token_type.value}#{t.uid} (air salvos {t.air_salvos_remaining})")
    idx = _ask_int("  MD #> ", 0, len(elig) - 1, blank=-1)
    return None if idx == -1 else elig[idx].uid


def _base_damage_allocator(eng: RulesEngine, defender_side: Side,
                           target_band: Optional[BandID] = None):
    """
    Returns a callback that, once the base-strike damage is rolled, lets the
    attacker distribute it point-by-point across the squadrons at the base and
    the airbase VP boxes (the rulebook's free distribution).

    Targets are Squadron CARDS (grounded flights die with their card), cardless
    tokens (e.g. US ADA), the Infantry Battalion, and airbase VP boxes.
    Saturated targets drop out of the menu; face-down (never-activated) enemy
    cards are shown without their identity. At a Contingency Location the
    first pick locks the single target — no spillover, excess damage is lost.
    """
    def allocate(amount: int, targets: list) -> list:
        if not targets or amount <= 0:
            return []
        defender = eng.state.player(defender_side)
        at_cl = target_band == BandID.US_CONTINGENCY_LOCATION
        counts: dict[tuple, int] = {}
        locked: Optional[tuple] = None

        def capacity(kind, cid) -> int:
            if kind == "squadron":
                squad = defender.squadrons.get(cid)
                return 0 if squad is None else DAMAGE_TO_DESTROY_SQUADRON - squad.damage
            if kind == "vp":
                return AIRBASE_BONUS_DAMAGE_BOXES - defender.airbase_vp_damage
            if kind == "token":
                tok = eng.state.get_token(cid)
                if tok is None or tok.destroyed:
                    return 0
            return 1

        def is_facedown(kind, cid) -> bool:
            if kind != "squadron":
                return False
            squad = defender.squadrons.get(cid)
            return squad is not None and not squad.ever_activated and not squad.is_destroyed

        def open_targets() -> list:
            out = []
            for kind, cid in targets:
                if at_cl and locked is not None and (kind, cid) != locked:
                    continue
                if counts.get((kind, cid), 0) < capacity(kind, cid):
                    out.append((kind, cid))
            return out

        allocation = []
        n = 0
        while n < amount:
            avail = open_targets()
            if not avail:
                print(f"  all targets saturated; {amount - n} remaining damage is lost")
                break
            if len(avail) == 1:   # no choice to make: auto-assign what fits
                kind, cid = avail[0]
                pts = min(amount - n, capacity(kind, cid) - counts.get((kind, cid), 0))
                counts[(kind, cid)] = counts.get((kind, cid), 0) + pts
                allocation.append((kind, cid, pts))
                print(f"  {pts} damage point(s) -> {kind}"
                      f"{'' if cid is None else f' {cid}'} (only eligible target)")
                n += pts
                continue
            print(f"  distribute damage {n + 1}/{amount}:")
            for i, (kind, cid) in enumerate(avail):
                pts = counts.get((kind, cid), 0)
                if kind == "squadron":
                    s = defender.squadrons.get(cid)
                    if is_facedown(kind, cid):
                        print(f"    [{i}] face-down Squadron Card "
                              f"dmg={s.damage}+{pts} of {DAMAGE_TO_DESTROY_SQUADRON}")
                    else:
                        print(f"    [{i}] Squadron {cid} ({s.token_type.value}) "
                              f"dmg={s.damage}+{pts} of {DAMAGE_TO_DESTROY_SQUADRON}")
                elif kind == "token":
                    t = eng.state.get_token(cid)
                    print(f"    [{i}] Token {t.token_type.value}#{cid} on the base (1 hit kills)")
                elif kind == "infantry":
                    print(f"    [{i}] Infantry Battalion protecting the base (1 hit kills)")
                else:
                    left = AIRBASE_BONUS_DAMAGE_BOXES - defender.airbase_vp_damage - pts
                    print(f"    [{i}] Airbase VP damage boxes (+VP, {left} left)")
            idx = _ask_int("  point -> #> ", 0, len(avail) - 1, blank=0)
            kind, cid = avail[idx]
            counts[(kind, cid)] = counts.get((kind, cid), 0) + 1
            allocation.append((kind, cid, 1))
            n += 1
            if at_cl and locked is None:
                locked = (kind, cid)
        return allocation
    return allocate


def _response_window(eng: RulesEngine, side: Side, note: str, triggers: set,
                     md_context: bool = False) -> None:
    """
    Offer `side` a chance to play a reaction enabler — but only cards whose
    declared trigger actually matches the event that just happened. Cards playable
    only "anytime" are not surfaced here (they are played on the owner's own turn).

    `md_context` marks the window opened right after the opponent declares naval
    missile defense: a dual-purpose card played here takes its cancel-MD branch.
    """
    hand = eng.legal_responses(side, triggers)
    if not hand:
        return
    active = eng.state.active_side.value
    print(f"  -- REACTION WINDOW: {side.value} may play a response card ({note}).")
    print(f"     This is not a turn change — {active}'s turn continues afterwards. Blank = skip:")
    for i, cid in enumerate(hand):
        prof = ENABLER_REGISTRY[cid]
        print(f"    [{i}] {prof.name}: {prof.effect_text[:64]}")
    idx = _ask_int(f"  {side.value} response #> ", 0, len(hand) - 1, blank=-1)
    if idx == -1:
        return
    card_id = hand[idx]
    play = _build_enabler_play(eng, side, card_id, response=True)
    if md_context:
        play.choice = "cancel_md"   # Air Launched Decoy's MD branch (79 ignores it)
    try:
        result = eng.play_enabler(side, card_id, play, response=True)
        print(f"    -> {_summarize('play_enabler', result)}")
    except IllegalAction as e:
        print(f"    ! {e}")
        return
    print(f"  -- reaction resolved; {eng.state.active_side.value}'s turn continues.")
    # A response card is itself a card the OTHER side may answer (e.g.
    # Anti-Access/Area Denial cancels a US mobility card played in response).
    counter = card_play_triggers(ENABLER_REGISTRY[card_id])
    if counter:
        _response_window(eng, eng.state.opponent(side).side,
                         "respond to the response card", counter)


def _perform_action(eng: RulesEngine, side: Side, action: LegalAction, rng: random.Random) -> None:
    """Execute one chosen sub-action, with placement / missile-defense / response prompts."""
    opp = eng.state.opponent(side).side
    kind = action.kind

    if kind == "activate":
        squad = eng.state.player(side).squadrons[action.card_id]
        band = _prompt_spawn_band(eng, side, squad.token_type)
        toks = eng.activate_squadron(side, action.card_id, band)
        print(f"  -> generated {len(toks)} token(s) at {band.name if band else '-'}")
        return

    if kind == "relaunch":
        tok = eng.state.get_token(action.token_uid)
        label = f"{tok.token_type.value}#{action.token_uid}" if tok else f"#{action.token_uid}"
        roll = eng.relaunch_fighter(side, action.token_uid)
        print(f"  -> relaunch {label}: rolled {roll} — "
              f"{'BROKEN (surrendered to opponent)' if roll == 1 else 'relaunched'}")
        return

    if kind == "move":
        eng.move(side, action.token_uid, action.dest_band)
        print(f"  -> moved to {action.dest_band.name}")
        return

    if kind == "acquire":
        acquirer = eng.state.get_token(action.token_uid)
        r = eng.acquire(side, action.token_uid, action.target_uid)
        print(f"  -> {_summarize('acquire', r)}")
        # A UAS acquire roll (hit or miss) lets the owner play UAS Proliferation.
        if acquirer is not None and acquirer.score_type == TokenScoreType.UAS:
            _response_window(eng, side, "your UAS rolled to acquire — self response",
                             {EnablerTrigger.OWN_UAS_ACQUIRE_ROLL})
        return

    if kind == "shoot_air":
        # Missile Defense (FAQ): the defender may activate a naval MD covering the
        # air-to-air shot's WEZ (ADA coverage is automatic); the attacker may then
        # cancel a declared MD (Air Launched Decoy / Decoy Warheads).
        attacker = eng.state.get_token(action.token_uid)
        target = eng.state.get_token(action.target_uid)
        md_uid = _prompt_missile_defense(eng, opp, attacker, target.location)
        if md_uid is not None:
            _response_window(eng, side, "opponent declared missile defense",
                             {EnablerTrigger.OPP_DECLARES_MISSILE_DEFENSE}, md_context=True)
        r = eng.shoot_air(side, action.token_uid, action.target_uid,
                          missile_defense_uid=md_uid)
        print(f"  -> {_summarize('shoot_air', r)}")
        if r.hit:
            # Opponent lost an aircraft to a hit: cancel-the-hit or recover it.
            triggers = {EnablerTrigger.OPP_ROLLS_HIT, EnablerTrigger.OWN_AIRCRAFT_LOST}
            # Reserves: only when this hit emptied a squadron of tokens.
            if eng.reserves_playable(opp):
                triggers.add(EnablerTrigger.OWN_SQUADRON_LOST_ALL_TOKENS)
            _response_window(eng, opp, "opponent may respond to the hit", triggers)
        return

    if kind == "shoot_surface":
        attacker = eng.state.get_token(action.token_uid)
        target_band = action.target_band or eng.state.get_token(action.target_uid).location
        md_uid = _prompt_missile_defense(eng, opp, attacker, target_band)
        if md_uid is not None:
            # The attacker may cancel the declared MD (Decoy Warheads / ALD).
            _response_window(eng, side, "opponent declared missile defense",
                             {EnablerTrigger.OPP_DECLARES_MISSILE_DEFENSE}, md_context=True)
        # Your own pre-roll response (Forward Observers guarantees an air-to-surface hit).
        _response_window(eng, side, "your air-to-surface strike — self response",
                         {EnablerTrigger.OWN_AIR_TO_SURFACE_DECLARED})
        # For a base strike, distribute the rolled damage freely once it's known.
        allocator = None
        if action.target_band is not None:
            allocator = _base_damage_allocator(eng, opp, action.target_band)
        r = eng.shoot_surface(side, action.token_uid, target_uid=action.target_uid,
                              target_band=action.target_band,
                              damage_allocator=allocator, missile_defense_uid=md_uid)
        print(f"  -> {_summarize('shoot_surface', r)}")
        if r.hit:
            if action.target_band is not None:   # base attack
                triggers = {EnablerTrigger.OPP_ATTACKS_BASE, EnablerTrigger.OPP_ROLLS_HIT}
                if eng.reserves_playable(opp):
                    triggers.add(EnablerTrigger.OWN_SQUADRON_LOST_ALL_TOKENS)
                _response_window(eng, opp, "opponent may cancel the base damage", triggers)
            else:                                # ship attack
                _response_window(eng, opp, "opponent may respond to the hit",
                                 {EnablerTrigger.OPP_ROLLS_HIT})
        return

    if kind == "play_enabler":
        play = _build_enabler_play(eng, side, action.card_id)
        if action.card_id in MD_ELIGIBLE_STRIKE_CARDS:
            # The defender may declare naval missile defense against the strike;
            # the strike is launched from the attacker's own base area.
            from types import SimpleNamespace
            origin = SimpleNamespace(location=board.own_airbase(side), side=side)
            play.missile_defense_uid = _prompt_missile_defense(
                eng, opp, origin, board.own_airbase(opp))
            if play.missile_defense_uid is not None:
                _response_window(eng, side, "opponent declared missile defense",
                                 {EnablerTrigger.OPP_DECLARES_MISSILE_DEFENSE}, md_context=True)
        r = eng.play_enabler(side, action.card_id, play)
        print(f"  -> {_summarize('play_enabler', r)}")
        # Cancel-the-card responses (matched to the card's class) plus
        # event-driven responses to what the card actually did: base damage
        # opens the Red Horse / Resilient Bases / Reserves window, and a lost
        # aircraft opens Personnel Recovery / Quick-Turn Mobility.
        triggers = card_play_triggers(ENABLER_REGISTRY[action.card_id])
        if r.base_damage:
            triggers.add(EnablerTrigger.OPP_ATTACKS_BASE)
        if r.destroyed:
            undo = eng._last_attack_undo
            if undo is not None and any(not t.is_naval for t in undo.revived_tokens):
                triggers.add(EnablerTrigger.OWN_AIRCRAFT_LOST)
        if eng.reserves_playable(opp):
            triggers.add(EnablerTrigger.OWN_SQUADRON_LOST_ALL_TOKENS)
        _response_window(eng, opp, "opponent may respond to the card", triggers)
        return


def interactive(campaign: int, seed: int, auto_draft_setup: bool = False, fog: bool = True) -> None:
    rng = random.Random(seed)
    eng = RulesEngine(GameState.new_game(campaign=campaign), rng=rng)
    print(f"Campaign {eng.campaign.number}: {eng.campaign.name} ({eng.state.total_ato_cycles} ATO cycle(s)).")
    print("Hotseat: you control both sides. A full turn = optional enabler + Move/Acquire/Shoot,")
    print("then pick [0] End turn. 'q' quits.\n")
    try:
        _manual_start_cycle(eng, rng, auto_draft_setup)
        while not eng.state.game_over:
            if eng.state.phase == Phase.ATO_SETUP:
                print("\n--- ATO cleanup complete; next cycle ---")
                _manual_start_cycle(eng, rng, auto_draft_setup)
                continue

            side = eng.state.active_side
            # One player's whole turn: keep taking sub-actions until End turn / activate.
            while side == eng.state.active_side and eng.state.phase == Phase.PLAYER_TURN \
                    and not eng.state.game_over:
                _render(eng, side, fog)
                actions = eng.legal_actions(side)
                for i, a in enumerate(actions):
                    lbl = "End turn (pass if no action taken)" if a.kind == "pass" else a.label
                    print(f"  [{i:>2}] {lbl}")
                idx = _ask_int(f"{side.value} action #> ", 0, len(actions) - 1)
                choice = actions[idx]
                if choice.kind == "pass":
                    eng.end_turn(side)
                    break
                try:
                    _perform_action(eng, side, choice, rng)
                except IllegalAction as e:
                    print(f"  ! illegal: {e}")
    except _Quit:
        print("Quit.")
        return

    print("\n" + "#" * 70)
    print(f"GAME OVER. Winner: {eng.state.winner.value if eng.state.winner else 'DRAW'} | "
          f"VP US={eng.total_victory_points(Side.US)} PRC={eng.total_victory_points(Side.PRC)}")
    print("#" * 70)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AFWIP rules-engine terminal harness")
    parser.add_argument("--interactive", action="store_true", help="Play a hotseat game")
    parser.add_argument("--autoplay", type=int, metavar="N", help="Run N random games per campaign")
    parser.add_argument("--env-autoplay", type=int, metavar="N", dest="env_autoplay",
                        help="Run N random games per campaign through the PettingZoo env "
                             "(full decision surface: draft/MD/responses/allocation).")
    parser.add_argument("--campaign", type=int, help="Restrict to one campaign (1-5)")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed")
    parser.add_argument("--pass-prob", type=float, default=0.3, dest="pass_prob",
                        help="Voluntary-pass probability for random agents. "
                             "Use 0 to pass only when no other action is legal, so games "
                             "play out instead of ending on early random double-passes.")
    parser.add_argument("--no-pass", action="store_true",
                        help="Shorthand for --pass-prob 0 (agents never pass voluntarily).")
    parser.add_argument("--max-turns", type=int, default=1500, dest="max_turns",
                        help="Per-game turn cap (games exceeding it are reported as CAPPED).")
    parser.add_argument("--auto-draft", action="store_true", dest="auto_draft",
                        help="Interactive: auto-draft setup instead of picking cards by hand.")
    parser.add_argument("--reveal", action="store_true",
                        help="Interactive: disable fog-of-war (show all tokens).")
    args = parser.parse_args(argv)

    campaigns = [args.campaign] if args.campaign else [1, 2, 3, 4, 5]
    pass_prob = 0.0 if args.no_pass else args.pass_prob

    if args.interactive:
        interactive(args.campaign or 3, args.seed,
                    auto_draft_setup=args.auto_draft, fog=not args.reveal)
        return 0
    if args.autoplay:
        errors = run_stress(campaigns, args.autoplay, args.seed, pass_prob, args.max_turns)
        return 1 if errors else 0
    if args.env_autoplay:
        return 1 if run_env_stress(campaigns, args.env_autoplay, args.seed) else 0

    # Default: a small autoplay sanity sweep.
    return 1 if run_stress(campaigns, 20, args.seed, pass_prob, args.max_turns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
