"""
tui.py — Zero-dependency terminal visualizer for AFWIP (debugging & rule checks).

A renderer + input loop over the decision-node stream (afwip.script.GameScript
— the same game flow the PettingZoo env uses). Plain ANSI escape codes, no
third-party packages.

  Watch (step through a random-vs-random game WITHOUT playing):

      python -m afwip.tui watch --campaign 2 --seed 7
        [Enter] advance one decision   <n> advance n decisions
        r      toggle fog/omniscient   q  quit

      python -m afwip.tui watch --auto 0.3         # free-run, 0.3s per step
      python -m afwip.tui watch --fog US            # view with US's fog of war
      python -m afwip.tui watch --node-filter TURN_ACTION,RESPONSE,ALLOC_POINT

  Play (answer your side's nodes by numbered menu; random agent for the rest):

      python -m afwip.tui play US --campaign 2 --seed 7

The board shows every band column with colored token chips (US cyan, PRC red;
`*` acquired, `W` winchester, `g` grounded; fogged enemy tokens render as
`?#uid(avN)`), squadron rosters (damage / permanent losses / activation),
hands, the VP/cyber status strip, and a scrolling event log synthesized by
diffing engine state around each decision.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections import deque
from typing import Optional

from afwip.script import GameScript, DecisionNode, NodeType
from afwip.core.rules import RulesEngine, RollMode
from afwip.core.state import GameState, CardZone
from afwip.core.constants import Side, BandID
from afwip.core.cards import ENABLER_REGISTRY, SQUADRON_REGISTRY, MISSION_REGISTRY, POSTURE_REGISTRY

# --- ANSI ------------------------------------------------------------------

RESET, BOLD, DIM = "\x1b[0m", "\x1b[1m", "\x1b[2m"
CYAN, RED, YELLOW, GREEN, MAGENTA = "\x1b[36m", "\x1b[31m", "\x1b[33m", "\x1b[32m", "\x1b[35m"
SIDE_COLOR = {Side.US: CYAN, Side.PRC: RED}


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def _clear() -> None:
    if sys.stdout.isatty():
        print("\x1b[2J\x1b[H", end="")


# --- board layout ------------------------------------------------------------

BOARD_COLUMNS = [
    (BandID.US_STANDOFF, "US-STANDOFF"),
    (BandID.US_AIRBASE, "US-AIRBASE"),
    (BandID.US_CONTINGENCY_LOCATION, "US-CL"),
    (BandID.BAND_A, "BAND A"),
    (BandID.BAND_B, "BAND B"),
    (BandID.BAND_C, "BAND C"),
    (BandID.BAND_D, "BAND D"),
    (BandID.BAND_E, "BAND E"),
    (BandID.PRC_AIRBASE, "PRC-AIRBASE"),
    (BandID.PRC_STANDOFF, "PRC-STANDOFF"),
]
COL_W = 14


def _token_cell(t, viewer: Optional[Side], reveal: bool) -> tuple[str, str]:
    """(plain, colored) cell for one token, applying fog for `viewer`."""
    color = SIDE_COLOR[t.side]
    hidden = (viewer is not None and not reveal and t.side != viewer
              and not t.acquired)
    if hidden:
        plain = f"?#{t.uid}(av{t.profile.acquisition_value})"
        return plain, _c(plain, DIM + color)
    flags = ("*" if t.acquired else "") + ("W" if t.is_winchester else "") \
        + ("g" if t.grounded else "")
    plain = f"{t.token_type.value}#{t.uid}{flags}"
    return plain, _c(plain, (DIM if t.grounded else "") + color)


def _pad(plain: str, colored: str, width: int = COL_W) -> str:
    return colored + " " * max(0, width - len(plain))


def render_board(eng: RulesEngine, viewer: Optional[Side] = None,
                 reveal: bool = True) -> str:
    """Multi-line board view. `viewer`+`reveal=False` applies that side's fog."""
    gs = eng.state
    columns: list[list[tuple[str, str]]] = []
    for band, header in BOARD_COLUMNS:
        cells = [(header, _c(header, BOLD))]
        for side in (Side.US, Side.PRC):
            for t in sorted(gs.player(side).tokens_at(band), key=lambda t: t.uid):
                cells.append(_token_cell(t, viewer, reveal))
        columns.append(cells)
    height = max(len(c) for c in columns)
    lines = []
    for row in range(height):
        line = "".join(
            _pad(*col[row]) if row < len(col) else " " * COL_W for col in columns)
        lines.append(line.rstrip())
    return "\n".join(lines)


def _squadron_line(eng: RulesEngine, side: Side, viewer: Optional[Side],
                   reveal: bool) -> str:
    p = eng.state.player(side)
    own_view = viewer is None or reveal or side == viewer
    bits, hidden = [], 0
    for cid, s in sorted(p.squadrons.items()):
        known = own_view or s.ever_activated or s.is_destroyed
        if not known:
            if s.zone == CardZone.SELECTED:
                hidden += 1
            continue
        flags = ("DEAD" if s.is_destroyed else
                 ("act" if s.activated else "rdy" if s.zone == CardZone.SELECTED else "out"))
        loc = "CL" if s.location == BandID.US_CONTINGENCY_LOCATION else ""
        bits.append(f"{cid}:{s.token_type.value}[{flags}"
                    f"{' d' + str(s.damage) if s.damage else ''}"
                    f"{' -' + str(s.tokens_lost) if s.tokens_lost else ''}"
                    f"{' ' + loc if loc else ''}]")
    if hidden:
        bits.append(f"{hidden}x face-down")
    off = sum(1 for t in p.tokens.values() if t.off_board)
    if off:
        bits.append(f"{off}x naval off-board")
    return _c(f"{side.value} squadrons: ", SIDE_COLOR[side]) + (", ".join(bits) or "-")


def _hand_line(eng: RulesEngine, side: Side, viewer: Optional[Side],
               reveal: bool) -> str:
    p = eng.state.player(side)
    hand = p.enablers_in_hand()
    own_view = viewer is None or reveal or side == viewer
    if own_view:
        names = [ENABLER_REGISTRY[c.card_id].name for c in hand]
        desc = ", ".join(names) or "-"
    else:
        shown = [ENABLER_REGISTRY[c.card_id].name for c in hand if c.revealed_to_opponent]
        n_hidden = sum(1 for c in hand if not c.revealed_to_opponent)
        desc = ", ".join(shown + ([f"{n_hidden}x hidden"] if n_hidden else [])) or "-"
    spent = sum(1 for c in p.enablers.values() if c.zone == CardZone.REMOVED)
    tail = f"  ({spent} spent)" if spent else ""
    return _c(f"{side.value} hand: ", SIDE_COLOR[side]) + desc + _c(tail, DIM)


def _status_line(eng: RulesEngine) -> str:
    gs = eng.state
    init = gs.initiative_holder.value if gs.initiative_holder else "-"

    def mission(side):
        p = gs.player(side)
        return MISSION_REGISTRY[p.mission_card_id].name if p.mission_card_id else "-"

    def posture(side):
        p = gs.player(side)
        return POSTURE_REGISTRY[p.posture_card_id].name if p.posture_card_id else "-"

    return (f"{BOLD}Campaign {gs.campaign} | ATO {gs.ato_cycle}/{gs.total_ato_cycles} "
            f"| turn {gs.turn_number} | initiative {init}{RESET}\n"
            f"VP  US={eng.total_victory_points(Side.US)} PRC={eng.total_victory_points(Side.PRC)}"
            f" | cyber US={gs.us.cyber_rate} PRC={gs.prc.cyber_rate}"
            f" | missions US:{mission(Side.US)} PRC:{mission(Side.PRC)}"
            f" | postures US:{posture(Side.US)} PRC:{posture(Side.PRC)}")


def render(eng: RulesEngine, node: Optional[DecisionNode], log,
           viewer: Optional[Side] = None, reveal: bool = True,
           step: int = 0) -> str:
    out = [_status_line(eng), "", render_board(eng, viewer, reveal), ""]
    for side in (Side.US, Side.PRC):
        out.append(_squadron_line(eng, side, viewer, reveal))
    for side in (Side.US, Side.PRC):
        out.append(_hand_line(eng, side, viewer, reveal))
    out.append("")
    out.append(_c("--- log " + "-" * 60, DIM))
    out.extend(f"  {line}" for line in log)
    out.append("")
    if node is None:
        winner = eng.state.winner.value if eng.state.winner else "DRAW"
        out.append(_c(f"### GAME OVER — winner: {winner} | "
                      f"VP US={eng.total_victory_points(Side.US)} "
                      f"PRC={eng.total_victory_points(Side.PRC)} ###", BOLD + GREEN))
    else:
        who = _c(node.side.value, SIDE_COLOR[node.side])
        out.append(_c(f"NEXT [{step}] ", BOLD) + _c(node.node_type.name, YELLOW)
                   + f" ({who}) — {len(node.choices)} choice(s)")
    return "\n".join(out)


# --- event log (state diffing) -----------------------------------------------

def _snapshot(eng: RulesEngine) -> dict:
    d = {}
    for side in (Side.US, Side.PRC):
        p = eng.state.player(side)
        d[side] = {
            # Keep the TokenInstance itself: a token that later leaves the board
            # still tells us WHY (destroyed vs recycled at cleanup vs off-board).
            "toks": {t.uid: t for t in p.living_tokens()},
            "winch": {t.uid for t in p.living_tokens() if t.is_winchester},
            "ground": {t.uid for t in p.living_tokens() if t.grounded},
            "vp": eng.total_victory_points(side),
            "cyber": p.cyber_rate,
            "sq_dmg": {cid: s.damage for cid, s in p.squadrons.items()},
            "sq_dead": {cid for cid, s in p.squadrons.items() if s.is_destroyed},
        }
    return d


def _gone_msg(tok) -> str:
    """Why a token left the board: real kill vs recycle vs off-board move."""
    name = f"{tok.token_type.value}#{tok.uid}"
    if tok.destroyed:
        return f"{name} destroyed"
    if tok.off_board:
        return f"{name} moves off-board (Winchester ship; not destroyed)"
    return f"{name} recycles to its Squadron Card (ATO cleanup; not destroyed)"


def _diff(before: dict, after: dict) -> list[str]:
    msgs = []
    for side in (Side.US, Side.PRC):
        b, a, tag = before[side], after[side], side.value
        for uid, tok in b["toks"].items():
            if uid not in a["toks"]:
                msgs.append(f"{tag} {_gone_msg(tok)}")
        for uid, tok in a["toks"].items():
            if uid not in b["toks"]:
                msgs.append(f"{tag} {tok.token_type.value}#{uid} enters play")
        for uid in (a["winch"] - b["winch"]) & set(b["toks"]):
            msgs.append(f"{tag} {b['toks'][uid].token_type.value}#{uid} is Winchester")
        for uid in (a["ground"] - b["ground"]) & set(b["toks"]):
            msgs.append(f"{tag} {b['toks'][uid].token_type.value}#{uid} returns to base (done this ATO)")
        for cid in a["sq_dead"] - b["sq_dead"]:
            msgs.append(f"{tag} squadron {cid} ({SQUADRON_REGISTRY[cid].name}) DESTROYED")
        for cid, dmg in a["sq_dmg"].items():
            prev = b["sq_dmg"].get(cid, 0)
            if dmg > prev and cid not in a["sq_dead"] - b["sq_dead"]:
                msgs.append(f"{tag} squadron {cid} damage {prev}->{dmg}")
        if a["vp"] != b["vp"]:
            msgs.append(f"{tag} VP {b['vp']}->{a['vp']}")
        if a["cyber"] != b["cyber"]:
            msgs.append(f"{tag} cyber rate {b['cyber']}->{a['cyber']}")
    return msgs


# --- game loops ----------------------------------------------------------------

class _Quit(Exception):
    pass


def _tap_dice(eng: RulesEngine) -> list:
    """Wrap the engine's dice so every roll is captured for the log."""
    sink: list = []
    orig_roll, orig_d4 = eng.roll, eng._d4

    def d4():
        v = orig_d4()
        sink.append(("d4", v))
        return v

    def roll(mode=RollMode.NORMAL, bonus=0, note=None):
        start = len(sink)
        r = orig_roll(mode, bonus)     # routes through the wrapped d4 above
        del sink[start:]               # fold the raw dice into one entry
        sink.append(("roll", r))       # note is display-only (web); TUI ignores it
        return r

    eng._d4, eng.roll = d4, roll
    return sink


def _fmt_die(entry) -> str:
    if entry[0] == "d4":
        return f"D4={entry[1]}"
    r = entry[1]
    bonus = f"+{r.value - r.natural}" if r.value != r.natural else ""
    if r.mode == RollMode.NORMAL:
        return f"D4={r.natural}{bonus}"
    dice = ",".join(str(d) for d in r.dice)
    return f"D4={r.natural}{bonus} ({r.mode.value.lower()}: {dice})"


def _score_report(eng: RulesEngine, ato: int) -> list[str]:
    """
    Per-side VP attribution for one ATO cycle: every capture (token / squadron
    card) with its mission value, plus the accrued entries from the engine's
    vp_log (airbase boxes, per-turn/per-ATO mission scoring).
    """
    lines = [_c(f"===== ATO {ato} SCORING =====", BOLD + YELLOW)]
    for side in (Side.US, Side.PRC):
        p = eng.state.player(side)
        mission = MISSION_REGISTRY[p.mission_card_id].name if p.mission_card_id else "-"
        tok_bits, sq_bits, cap_vp = [], [], 0
        for c in p.captures:
            if c.ato_cycle != ato:
                continue
            v = eng.capture_value(side, c)
            cap_vp += v
            if c.is_squadron_card:
                name = SQUADRON_REGISTRY[c.card_id].name if c.card_id else "squadron"
                sq_bits.append(f"{name} (+{v})")
            else:
                tag = f"{c.token_type.value}#{c.uid}" if c.uid else c.token_type.value
                if c.destroyed_on_ground:
                    tag += " [ground]"
                tok_bits.append(f"{tag} (+{v})")
        accrued: dict[str, int] = {}
        for a, reason, pts in p.vp_log:
            if a == ato:
                accrued[reason] = accrued.get(reason, 0) + pts
        ato_total = cap_vp + sum(accrued.values())
        lines.append(_c(f"{side.value} [{mission}]: +{ato_total} this ATO"
                        f" | campaign total {eng.total_victory_points(side)}",
                        BOLD + SIDE_COLOR[side]))
        if tok_bits:
            lines.append(f"  tokens destroyed: {', '.join(tok_bits)}")
        if sq_bits:
            lines.append(f"  squadrons destroyed: {', '.join(sq_bits)}")
        for reason, pts in accrued.items():
            lines.append(f"  {reason}: +{pts}")
        if not tok_bits and not sq_bits and not accrued:
            lines.append("  no points scored this ATO")
    return lines


def _apply(eng, gen, node, choice, log, step, dice=None) -> Optional[DecisionNode]:
    """Apply one decision, appending the action, dice, and effects to the log."""
    before = _snapshot(eng)
    prev_ato = eng.state.ato_cycle
    prev_over = eng.state.game_over
    who = _c(node.side.value, SIDE_COLOR[node.side])
    log.append(f"[{step}] {who} {node.node_type.name}: {choice.label}")
    try:
        nxt = gen.send(choice)
    except StopIteration:
        nxt = None
    if dice:
        log.append(_c("      dice: " + "  ".join(_fmt_die(e) for e in dice), MAGENTA))
        dice.clear()
    log.extend(f"      -> {m}" for m in _diff(before, _snapshot(eng)))
    # The step just closed an ATO cycle (or ended the game): show who scored
    # what — captures by name plus the accrued-VP audit trail.
    if eng.state.ato_cycle != prev_ato or (eng.state.game_over and not prev_over):
        log.extend(_score_report(eng, prev_ato))
    return nxt


def watch(campaign: int, seed: int, auto: Optional[float] = None,
          fog: Optional[Side] = None, node_filter: Optional[set] = None) -> None:
    """Step through a random-vs-random game without playing."""
    eng = RulesEngine(GameState.new_game(campaign=campaign), rng=random.Random(seed))
    dice = _tap_dice(eng)
    agent_rng = random.Random(seed + 1)
    gen = GameScript(eng).run()
    node = next(gen)
    log: deque = deque(maxlen=24)
    reveal = fog is None
    step, skip = 0, 0

    while True:
        shown = node is None or node_filter is None \
            or node.node_type.name in node_filter
        if shown and skip <= 0:
            _clear()
            print(render(eng, node, log, viewer=fog, reveal=reveal, step=step))
            if node is None:
                return
            if auto is not None:
                time.sleep(auto)
            else:
                cmd = input("[Enter]=step  <n>=step n  r=toggle fog  q=quit > ").strip().lower()
                if cmd == "q":
                    return
                if cmd == "r":
                    reveal = not reveal
                    continue
                if cmd.isdigit():
                    skip = int(cmd)
        elif node is None:
            _clear()
            print(render(eng, None, log, viewer=fog, reveal=reveal, step=step))
            return
        node = _apply(eng, gen, node, agent_rng.choice(node.choices), log, step, dice)
        step += 1
        skip -= 1


def play(human: Side, campaign: int, seed: int, fog: bool = True) -> None:
    """Play one side by numbered menu against a random agent."""
    eng = RulesEngine(GameState.new_game(campaign=campaign), rng=random.Random(seed))
    dice = _tap_dice(eng)
    agent_rng = random.Random(seed + 1)
    gen = GameScript(eng).run()
    node = next(gen)
    log: deque = deque(maxlen=24)
    step = 0

    try:
        while node is not None:
            if node.side != human:
                node = _apply(eng, gen, node, agent_rng.choice(node.choices), log, step, dice)
                step += 1
                continue
            _clear()
            print(render(eng, node, log, viewer=human, reveal=not fog, step=step))
            for i, ch in enumerate(node.choices):
                print(f"  [{i:>2}] {ch.label}")
            while True:
                raw = input(f"{human.value} choice #> ").strip().lower()
                if raw in ("q", "quit", "exit"):
                    raise _Quit
                if raw.isdigit() and int(raw) < len(node.choices):
                    break
                print(f"  ! enter a number 0-{len(node.choices) - 1} (or q)")
            node = _apply(eng, gen, node, node.choices[int(raw)], log, step, dice)
            step += 1
    except _Quit:
        print("Quit.")
        return
    _clear()
    print(render(eng, None, log, viewer=human, reveal=not fog, step=step))


# --- CLI -------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="AFWIP terminal visualizer (zero-dependency)")
    sub = parser.add_subparsers(dest="mode", required=True)

    w = sub.add_parser("watch", help="step through a random-vs-random game")
    w.add_argument("--campaign", type=int, default=2)
    w.add_argument("--seed", type=int, default=0)
    w.add_argument("--auto", type=float, nargs="?", const=0.3, default=None,
                   metavar="SECS", help="free-run with SECS between steps (default 0.3)")
    w.add_argument("--fog", choices=["US", "PRC"], default=None,
                   help="view with this side's fog of war (default: omniscient)")
    w.add_argument("--node-filter", default=None, metavar="TYPES",
                   help="comma-separated NodeType names to pause on "
                        "(e.g. TURN_ACTION,RESPONSE,ALLOC_POINT)")

    p = sub.add_parser("play", help="play one side against a random agent")
    p.add_argument("side", choices=["US", "PRC"])
    p.add_argument("--campaign", type=int, default=2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--reveal", action="store_true", help="disable fog of war")

    args = parser.parse_args(argv)
    if args.mode == "watch":
        node_filter = set(args.node_filter.upper().split(",")) if args.node_filter else None
        bad = (node_filter or set()) - {n.name for n in NodeType}
        if bad:
            parser.error(f"unknown node type(s): {', '.join(sorted(bad))}")
        watch(args.campaign, args.seed, auto=args.auto,
              fog=Side(args.fog) if args.fog else None, node_filter=node_filter)
    else:
        play(Side(args.side), args.campaign, args.seed, fog=not args.reveal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
