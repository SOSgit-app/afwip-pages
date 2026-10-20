"""Live coach copy for a Watch Agents game.

The browser asks for a note on the current view. In the live tutorial the
player is one side, and the note says why the choice in front of them matters.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from afwip.core.cards import ENABLER_REGISTRY, SQUADRON_REGISTRY
from afwip.core.constants import TokenScoreType
from afwip.core.tokens import TOKEN_REGISTRY
from afwip.view.models import ChoiceView, GameView


class CoachNote(BaseModel):
    revision: int
    concept: str
    title: str
    lesson: str
    now: str
    why: str
    just: str = ""
    look: str = ""
    suggest: str = ""
    hold: str = ""
    cards: list[int] = Field(default_factory=list)
    tokens: list[str] = Field(default_factory=list)
    # When hold=="watch", which side just acted (for board/side-column highlights).
    watch_side: str = ""
    watch_labels: list[str] = Field(default_factory=list)
    watch_bands: list[str] = Field(default_factory=list)
    # Board token uids to blink (Winchester, kills, moves) — not the coach art strip.
    watch_uids: list[int] = Field(default_factory=list)
    # Move trail: [from_band, to_band] when the held step relocated a token.
    watch_trail: list[str] = Field(default_factory=list)


_LESSONS: dict[str, tuple[str, str, str]] = {
    "mission": (
        "The hidden mission",
        "Campaign 1 and Campaign 2 both lock the mission to Attrition. A destroyed squadron card is worth 2. A ship, bomber, ADA, or AEW is worth 3. Any other token is worth 1.",
        "The card shown here is Attrition, the list those points come from.",
    ),
    "posture": (
        "The posture",
        "Standard allows 4 squadron cards, and a side may take one fewer, plus 6 enabler cards. Campaign 1 and Campaign 2 allow only Standard. Campaign 1 deals no enablers. The recycle mark means Standard can be chosen every cycle. Every other posture can be used only once.",
        "The recycle mark is the symbol that lets this card return next cycle.",
    ),
    "squadron_draft": (
        "Drafting squadrons",
        "Each side drafts from its own deck, so one side cannot take the other's aircraft. A fighter card puts four aircraft in the air. A bomber or AEW puts one. Campaign 1 also requires the US F-16 and the PRC J-10.",
        "The cards on the right are the ones still in your deck.",
    ),
    "placement": (
        "Placing the cards",
        "The airbase launches every aircraft on the card. The contingency location sits off to the side: a strike there does not fill the airbase's point boxes, and a multi-aircraft card rolls a die for how many jets take off.",
        "The card stays face-down, so the enemy does not know which squadron it is until it launches.",
    ),
    "enabler_draft": (
        "Enabler cards",
        "Cyber, missiles, ships, electronic warfare, and special operations live on these cards. A single-use card is gone for the campaign once played. A red pin lasts the whole ATO. A yellow bolt is a response, played when its trigger happens.",
        "These are the cards in your hand. You pick all 6 now. During the fight you may play one of them on your turn.",
    ),
    "initiative": (
        "Bidding for initiative",
        "Both sides roll a D4, and a tie is rolled again. The winner also gets one attempt to raise cyber rate. You start at rate 1. Rate 4 wins the game immediately, and the points are not compared.",
        "The dice in the log are that bid.",
    ),
    "first_player": (
        "Who moves first",
        "A launch is that side's main action for the turn (they may still play one enabler, then pass). The side that goes first spends that turn getting aircraft up. The side that waits still has its launch. The choice does not move a token by itself.",
        "This choice is only about who acts next.",
    ),
    "intel": (
        "The intel peek",
        "The initiative winner rolls this peek at advantage. At least one enemy card always stays hidden.",
        "A card that flips face-up here is known. Anything still on its back is not.",
    ),
    "turn": (
        "A turn",
        "Activate one squadron, or take one move, one acquire, and one shoot, in any order, and you may skip any of them. You cannot launch and shoot on the same turn. One enabler may be played before or after that branch; after a launch, pass when you are done.",
        "The buttons on the right are the only legal actions. A move that is missing is out of range or already used.",
    ),
    "spawn": (
        "Activating a squadron",
        "Fighters appear on your front band: Band A for the US, Band E for the PRC. Bombers and AEW may appear there or in standoff. Drones may appear on any of the five center bands. A fighter card puts four counters in the air. A bomber puts one.",
        "Count the new counters after they appear.",
    ),
    "move": (
        "Movement",
        "Fighters move 2 bands. Bombers, AEW, and drones move 1. ADA does not move. Only bombers and AEW may enter standoff. The move is once this turn, up to the Move Range on the counter.",
        "Follow the one counter that changed bands. Every other token stayed put.",
    ),
    "acquire": (
        "Acquire and fog of war",
        "You can see that a token is there, and you can see the number you must roll, but not its type. A success flips it face-up for the rest of the ATO. AEW rolls twice and adds 2, which is why it hunts stealth fighters.",
        "A question mark on the board is an unacquired token. The AV on it is the roll you need.",
    ),
    "shoot": (
        "Shooting",
        "Air-to-air against an acquired aircraft is one hit: there is no second damage die. A base strike does not need a prior spot. A bomber then rolls a D4 and you assign that many hits.",
        "Watch which counter is the shooter and which is the target. Range is the steps between their bands.",
    ),
    "pass": (
        "Passing",
        "The other side does not get a full turn until you choose Pass / end turn. One pass does not end the cycle. If they also pass, aircraft still in the air land, end-of-cycle points are scored, and the board clears for the next ATO.",
        "The button reads Pass / end turn. That means this turn, not the whole game.",
    ),
    "missile_defense": (
        "Missile defense",
        "If an attack crosses an ADA weapon zone, the attacker rolls at disadvantage automatically. A ship can defend too, but someone must declare it before the roll, and that spends one of the ship's air salvos. The disadvantage hits both the to-hit die and the damage die. This is not the defender's turn — your turn ends only when you choose Pass / end turn.",
        "ADA does this for free. A ship only does it when the declare button is taken.",
    ),
    "response": (
        "A response",
        "Some enablers are played when their trigger happens, including on the opponent's turn. That is an answer inside the current turn, not a handoff. A cancel undoes the damage, the kill, or the cyber gain. A recovered aircraft comes back face-down, so it must be acquired again. Their full turn still waits until you Pass / end turn.",
        "If a yellow-bolt card is offered, the trigger is happening right now.",
    ),
    "damage": (
        "Assigning damage",
        "A hit on a base gives you points of damage to place. A squadron card takes 2 hits. Each of the three airbase boxes takes 1 and is worth 1 victory point, once, and the base keeps operating. One point of damage on a card that survives resets next cycle. A destroyed card is gone for the game.",
        "Click through where each point lands. Excess damage at the contingency location is lost, and that site has no victory-point boxes.",
    ),
    "enabler_play": (
        "Playing an enabler",
        "One enabler can be played on your turn, before or after the launch or the move-acquire-shoot. Read the bottom of the card. Single use leaves the campaign. Multiple use can be drafted again. The effect happens now.",
        "The card art on the right is the one being resolved.",
    ),
    "cyber": (
        "Cyber rate",
        "Both sides start at cyber rate 1. Climbing is a D4 against an access number: 1 to 2 needs a 3 or better, and every step after that needs a 4. Rate 4 ends the game at once. Victory points are not compared.",
        "The log shows the roll and the rate before and after. Many cyber cards also remove tokens equal to the rate you already have.",
    ),
    "kill": (
        "A kill and the score",
        "On Attrition, destroying an ordinary token is 1 point. A ship, bomber, ADA, or AEW token is 3. Destroying the squadron card is 2 more, and it also removes any aircraft still on that card. An air-to-air hit does this in one roll.",
        "The destroyed counter leaves the board. The victory-point track moves by the mission value, not by the number of hits.",
    ),
    "winchester": (
        "Winchester",
        "Ammo is the natural attack roll, before bonuses. Most aircraft go Winchester on a 1, 2, or 3. A 4 means they still have weapons. The damage die never decides ammo. At the start of that side's next turn, a Winchester aircraft flies home for free and re-arms next cycle.",
        "A token marked Winchester cannot take a voluntary move. The flight home is not your move action.",
    ),
    "score": (
        "Victory points",
        "Points come from the mission plus 1 for each enemy airbase box you fill. Boxes stay filled for the whole campaign and do not shut the base down. The higher total after the last ATO wins, unless someone has already hit cyber rate 4.",
        "The status line shows both totals. A change in the log is the points from what just happened.",
    ),
    "game_end": (
        "How this game ended",
        "There are two endings. The higher victory-point total wins after the last ATO. Or a side that reaches cyber rate 4 wins immediately, and the points are not compared.",
        "Check the cyber rates and the two point totals on the status line.",
    ),
    "between": (
        "Between decisions",
        "The board is the current truth: face-up tokens are identified, face-down tokens are not, and squadron cards on a base have not all launched.",
        "Your next choice shows up on the right as soon as it is your turn.",
    ),
    "opponent_draft": (
        "Their draft",
        "The other side also picks a posture, then squadrons and enablers, the same way you just did. You do not need to click through every one of their cards.",
        "When they finish, their squadrons and hand show on their side of the board.",
    ),
    "opponent_intel": (
        "Their intel",
        "Initiative lets a side peek at enemy cards. They may look at several cards in a row. You do not need to click Continue for every peek.",
        "When they finish, play continues with the next real choice.",
    ),
    "roll": (
        "The die",
        "A lot of this game is a four-sided die. Click it. The face it lands on is the whole result. Advantage rolls two dice and keeps the higher. Disadvantage keeps the lower.",
        "The number is hidden until you click.",
    ),
}

# One or two plain sentences: why the player is about to do this.
_WHY = {
    "mission": "You pick a mission because it is the only list of what scores points, and the higher total wins the campaign. Each side's list stays secret until the end.",
    "posture": "You pick a posture because it decides how many squadrons you may bring, and that is the size of the force you have to fight with.",
    "squadron_draft": "You pick these cards because they are the only aircraft you can launch. A card left in the deck never reaches the board.",
    "placement": "You pick a home for this squadron because that is where it launches from, and the card stays hidden until it does.",
    "enabler_draft": "You pick an enabler because one can be played on your turn for an effect the aircraft cannot do alone.",
    "initiative": "You roll because the higher result wins initiative. That winner peeks at enemy cards with an advantage and chooses who takes the first turn.",
    "first_player": "You choose who moves first because that side gets a squadron into the air before the other side can answer.",
    "intel": "You roll because the result is how many enemy cards you may see, and a card you see is one you can plan a kill around.",
    "turn": "This is your only chance to launch, move, spot, or shoot before the other side answers. A launch blocks move-acquire-shoot, but you may still play one enabler before you pass. Their full turn starts only after you choose Pass / end turn. The cycle ends only when both sides pass in a row.",
    "spawn": "You choose the band because the tokens appear there. After the launch you may still play one enabler, then pass. Where they start decides which targets they can reach.",
    "move": "You move one token because a shot is legal only when the shooter can reach the target, or when you need to step out of theirs.",
    "acquire": "You roll because that marker is face-down, and an air shot is illegal until this spot succeeds.",
    "shoot": "You roll because this is your one attack this turn. Meet the number on the counter and that token is destroyed.",
    "pass": "You choose Pass / end turn because that is what hands the turn to the other side. Until you do, they only answer mid-turn triggers — they do not take a full turn.",
    "missile_defense": "You are asked because this shot is crossing a weapon zone, and a worse attack roll can save the target. This is still the attacker's turn.",
    "response": "You are asked because the trigger is happening now, and waiting means the effect stands. This is still the current turn — not a handoff.",
    "damage": "You place each hit because where it lands is what scores. A point on a card that survives does not stay there.",
    "enabler_play": "You play this because a turn allows one enabler, and the text on the card happens now.",
    "cyber": "You roll because this is the climb toward an instant win. If the climb finishes, the points are not compared.",
    "kill": "That token left the board because the shot hit. The mission pays for what it was, and that payment is how the campaign is won.",
    "winchester": "The attack roll was low, so that aircraft is out of weapons and cannot choose its own move.",
    "score": "The score moved because the mission pays for what was just destroyed, plus 1 for each enemy airbase box you fill.",
    "game_end": "The game is over. Cyber rate 4 wins immediately. Otherwise the higher victory-point total wins.",
    "between": "The other side is taking its turn. Your choices come back as soon as it is done.",
    "opponent_draft": "They are building the force you will fight. One Continue skips ahead to when their whole draft is done.",
    "opponent_intel": "They are peeking at cards from the initiative intel roll. One Continue skips through every peek.",
    "roll": "You click the die because this result is random. The face it lands on is the whole answer.",
}


_NODE = {
    "MISSION_PICK": "mission",
    "POSTURE_PICK": "posture",
    "SQUADRON_PICK": "squadron_draft",
    "SQUADRON_BASE": "placement",
    "ENABLER_PICK": "enabler_draft",
    "BID_SACRIFICE": "initiative",
    "FIRST_PLAYER": "first_player",
    "INTEL_REVEAL": "intel",
    "SPAWN_BAND": "spawn",
    "ENABLER_BRANCH": "enabler_play",
    "MD_DECLARE": "missile_defense",
    "RESPONSE": "response",
    "ALLOC_POINT": "damage",
}

_KIND = {
    "activate": "spawn",
    "move": "move",
    "acquire": "acquire",
    "shoot_air": "shoot",
    "shoot_surface": "shoot",
    "pass": "pass",
    "play_enabler": "enabler_play",
}

# Longer names first so "F-35" does not steal a shorter match, and "Long Range"
# is tested before a generic "ADA".
_SLUGS = (
    ("Long Range ADA", "long-range-ada-prc"),
    ("Long-Range ADA", "long-range-ada-prc"),
    ("Mid-Range ADA", "mid-range-ada-prc"),
    ("Mid Range ADA", "mid-range-ada-prc"),
    ("F-35", "f-35a"),
    ("F-22", "f-22"),
    ("F-15E", "f-15e"),
    ("F-15C", "f-15c"),
    ("F-16", "f-16c"),
    ("B-52", "b-52"),
    ("EC-130", "ec-130"),
    ("Attack UAS", "attack-uas-us"),
    ("Recon UAS", "recon-uas-us"),
    ("J-20", "j-20b"),
    ("JH-7", "jh-7"),
    ("J-16", "j-16"),
    ("J-15", "j-15"),
    ("J-10", "j-10"),
    ("H-6", "h-6k"),
    ("DDG 115", "ddg-115"),
    ("DDG 81", "ddg-81"),
    ("Dalian", "dalian-105"),
    ("Nanning", "nanning-162"),
    ("Flotilla", "flotilla"),
    ("AEW", "aew-us"),
    ("ADA", "ada-us"),
)


def _slugs(text: str, side: str | None) -> list[str]:
    found: list[str] = []
    for needle, slug in _SLUGS:
        if needle in text and slug not in found:
            if slug == "aew-us" and side == "PRC":
                slug = "aew-prc"
            elif slug == "ada-us" and side == "PRC":
                slug = "mid-range-ada-prc"
            elif slug == "attack-uas-us" and side == "PRC":
                slug = "attack-uas-prc"
            elif slug == "recon-uas-us" and side == "PRC":
                slug = "recon-uas-prc"
            found.append(slug)
    return found[:3]


def _roll_concept(view: GameView) -> str:
    """Which idea a pending click-to-roll is teaching, without reading the faces."""
    blob = _roll_text(view)
    if "initiative" in blob:
        return "initiative"
    if "cyber" in blob:
        return "cyber"
    if "intel" in blob:
        return "intel"
    if "acquire" in blob:
        return "acquire"
    if any(word in blob for word in ("shoot", "attack", "strike", "bomb", "hit")):
        return "shoot"
    if "relaunch" in blob:
        return "turn"
    if "spawn" in blob or "enters play" in blob:
        return "spawn"
    return "roll"


def _roll_text(view: GameView) -> str:
    """Words that say what a pending roll is for.

    Action dice are often their own step, with a message like ``dice: D4=4``
    and the purpose stored on the roll (``acquire``, ``hit``) or on the
    decision just before it.
    """
    events = _latest_step(view)
    parts: list[str] = []
    for ev in events:
        parts.append(ev.message.lower())
        data = ev.data or {}
        label = data.get("label")
        if isinstance(label, str):
            parts.append(label.lower())
        kind = data.get("kind")
        if kind:
            parts.append(str(kind).lower())
        rolls = data.get("rolls") or []
        if isinstance(rolls, list):
            for roll in rolls:
                if isinstance(roll, dict) and roll.get("role"):
                    parts.append(str(roll["role"]).lower())
    if events and all(ev.type == "dice" for ev in events):
        step = events[0].step
        for ev in reversed(view.event_log):
            if ev.step >= step or ev.type != "decision":
                continue
            parts.append(ev.message.lower())
            kind = str((ev.data or {}).get("kind") or "")
            if kind:
                parts.append(kind.lower())
            break
    return " ".join(parts)


def _die_side(view: GameView) -> str | None:
    """Which side the pending die belongs to."""
    for ev in _latest_step(view):
        if ev.type == "dice" and ev.side:
            return ev.side
    return None


def _opponent_roll(view: GameView) -> str | None:
    roller = _die_side(view)
    if roller and view.viewer and roller != view.viewer:
        return roller
    return None


def _roll_suggest(view: GameView) -> str:
    roller = _opponent_roll(view)
    concept = _roll_concept(view)
    if roller and concept == "acquire":
        return (
            f"Click the die. {roller} is spotting one of your aircraft, "
            "and the face stays hidden until you do."
        )
    if roller and concept == "shoot":
        return (
            f"Click the die. {roller} is shooting, "
            "and the face stays hidden until you do."
        )
    return "Click the die. The face is the whole result, and it stays hidden until you do."


def _roll_why(view: GameView) -> str:
    blob = _roll_text(view)
    parts: list[str] = []
    if "initiative" in blob:
        parts.append(_WHY["initiative"])
    if "cyber" in blob:
        parts.append(_WHY["cyber"])
    if "intel" in blob and "initiative" not in blob:
        parts.append(_WHY["intel"])
    if parts:
        return " ".join(parts)
    roller = _opponent_roll(view)
    concept = _roll_concept(view)
    if roller and concept == "acquire":
        return (
            "They have to identify that aircraft before they are allowed to shoot it. "
            "This roll is only the spot."
        )
    if roller and concept == "shoot":
        return "This is their attack roll. The face it lands on decides whether the target is destroyed."
    return _WHY.get(concept, _WHY["roll"])


def _why(view: GameView, concept: str) -> str:
    if view.roll_pending:
        return _roll_why(view)
    return _WHY.get(concept, "You make this choice because it is the next legal step in the turn.")


def _concept(view: GameView) -> str:
    if view.roll_pending:
        return _roll_concept(view)
    if view.watch_pending and view.draft_skip_pending:
        if getattr(view, "watch_batch", "") == "intel":
            return "opponent_intel"
        return "opponent_draft"
    if view.watch_pending and _has_winchester(view):
        return "winchester"
    if view.watch_pending:
        for ev in reversed(_latest_step(view)):
            if ev.type != "decision":
                continue
            node_type = str(ev.data.get("node_type") or "")
            if node_type in _NODE:
                return _NODE[node_type]
            kind = str(ev.data.get("kind") or "")
            if kind in _KIND:
                return _KIND[kind]
            break
    if view.terminal:
        return "game_end"
    node = view.decision.node_type if view.decision else None
    if node in _NODE:
        return _NODE[node]
    step_events = _latest_step(view)
    types = {ev.type for ev in step_events}
    blob = " ".join(ev.message.lower() for ev in step_events)
    if "cyber_change" in types or "cyber raise" in blob or "cyber rate" in blob:
        return "cyber"
    if "token_destroyed" in types or "squadron_destroyed" in types:
        return "kill"
    if "token_winchester" in types or "winchester" in blob:
        return "winchester"
    if "squadron_damage" in types or "alloc" in blob:
        return "damage"
    if "vp_change" in types:
        return "score"
    for ev in reversed(step_events):
        if ev.type == "decision":
            kind = str(ev.data.get("kind") or "")
            if kind in _KIND:
                return _KIND[kind]
    if node == "TURN_ACTION":
        return "turn"
    return "between"


def _latest_step(view: GameView):
    if not view.event_log:
        return []
    step = max(ev.step for ev in view.event_log)
    return [ev for ev in view.event_log if ev.step == step]


def _has_winchester(view: GameView) -> bool:
    events = _latest_step(view)
    return any(ev.type == "token_winchester" or "winchester" in ev.message.lower()
               for ev in events)


def _watch_notice(view: GameView) -> str:
    """What just happened, held on screen until the player clicks Continue."""
    # Pass / end turn: freeze before the opponent's full turn so the handoff
    # is obvious (mid-turn responses are a different Continue).
    if view.watch_pending and not view.draft_skip_pending:
        for ev in reversed(_latest_step(view)):
            if ev.type != "decision":
                continue
            if (ev.data or {}).get("kind") != "pass":
                break
            if ev.side == view.viewer:
                return (
                    "You chose Pass / end turn. That hands the turn to the other side. "
                    "Click Continue to watch their turn."
                )
            who = ev.side or "The other side"
            return (
                f"{who} passed and ended their turn. "
                "Click Continue when you have seen it."
            )
    if view.draft_skip_pending:
        who = "PRC" if view.viewer == "US" else "US" if view.viewer == "PRC" else "The other side"
        batch = getattr(view, "watch_batch", "") or ""
        if batch == "intel":
            return (
                f"{who} is looking at intel cards now. "
                "Click Continue once to skip ahead to when they have finished every peek."
            )
        if batch == "posture":
            return (
                f"{who} is choosing a posture now. "
                "Click Continue once to let them finish that pick."
            )
        if batch == "squadrons":
            return (
                f"{who} is picking and placing squadron cards now. "
                "Click Continue once to skip ahead to when they have chosen them all."
            )
        if batch == "enablers":
            return (
                f"{who} is picking enabler cards now. "
                "Click Continue once to skip ahead to when their hand is full."
            )
        if batch == "bid":
            return (
                f"{who} is finishing setup (initiative bid) now. "
                "Click Continue once to let that resolve."
            )
        return (
            f"{who} is taking several setup picks now. "
            "Click Continue to skip ahead to when they have chosen everything."
        )
    events = _latest_step(view)
    parts: list[str] = []
    for ev in events:
        if ev.type == "token_winchester" or "winchester" in ev.message.lower():
            if ev.side == view.viewer:
                parts.append(
                    "Winchester. Your aircraft is out of weapons. It cannot move "
                    "on its own. At the start of your next turn it flies home and "
                    "re-arms next cycle."
                )
            else:
                who = ev.side or "The opponent"
                parts.append(
                    f"Winchester. {who}'s aircraft is out of weapons. It flies "
                    "home at the start of that side's next turn."
                )
            break
    # After a draft streak, initiative/cyber often share the last pick's step —
    # name the setup roll so it does not read like another single card Continue.
    if not parts:
        for ev in events:
            if ev.type != "dice":
                continue
            msg = (ev.message or "").lower()
            if "initiative" in msg:
                parts.append(
                    "Initiative is decided. "
                    + (ev.message or "").strip().rstrip(".")
                    + "."
                )
                break
            if "cyber" in msg:
                parts.append((ev.message or "").strip().rstrip(".") + ".")
                break
    # Moves: say so even when the log label is fogged, and point at the trail.
    if not parts:
        for ev in events:
            data = ev.data or {}
            is_move = (
                ev.type == "token_moved"
                or (ev.type == "decision" and data.get("kind") == "move")
            )
            if not is_move:
                continue
            who = ev.side or "The opponent"
            src = data.get("from_band")
            dst = data.get("to_band") or data.get("band")
            if isinstance(src, str) and isinstance(dst, str) and src and dst and src != dst:
                parts.append(
                    f"{who} moved a piece. Follow the yellow trail from "
                    f"{_band_short(src)} to {_band_short(dst)}."
                )
            else:
                parts.append(f"{who} moved a piece on the board.")
            break
    if not parts:
        for ev in reversed(events):
            if ev.type == "decision":
                parts.append(_plain(ev.message) + ".")
                break
    if not parts:
        parts.append("Look at what just changed on the board.")
    parts.append("Click Continue when you have seen it.")
    return " ".join(parts)


def _band_short(band: str) -> str:
    if band.startswith("BAND_") and len(band) == 6:
        return f"Band {band[-1]}"
    if band.endswith("_STANDOFF"):
        return "standoff"
    if band.endswith("_AIRBASE"):
        return "the airbase"
    if "CONTINGENCY" in band:
        return "the contingency location"
    return band.replace("_", " ").title()


def _now(view: GameView) -> str:
    if view.roll_pending:
        return "Click the die."
    if view.watch_pending:
        return ""
    if view.terminal:
        vp = view.status.vp
        cyber = view.status.cyber
        winner = view.winner or "Nobody"
        if view.winner and cyber.get(view.winner) == 4:
            how = f"{winner} reached cyber rate 4, so the game stopped before the points were compared."
        else:
            how = f"US {vp.get('US', 0)} to PRC {vp.get('PRC', 0)} on victory points."
        return f"{winner} wins. {how}"
    dec = view.decision
    if dec is None:
        return "The other side is moving. Your next choice comes up when they finish."
    who = "You are" if view.viewer == dec.side else f"{dec.side} is"
    labels = [c.label for c in dec.choices[:3]]
    extra = f" Choices include: {'; '.join(labels)}." if labels else ""
    return f"{who} choosing. {dec.prompt}.{extra}"


_PLAIN = {
    "MISSION_PICK": "picked a mission",
    "POSTURE_PICK": "picked a posture",
    "SQUADRON_PICK": "drafted a squadron",
    "SQUADRON_BASE": "placed a squadron",
    "ENABLER_PICK": "drafted an enabler",
    "BID_SACRIFICE": "bid for initiative",
    "FIRST_PLAYER": "chose who goes first",
    "INTEL_REVEAL": "looked at intel",
    "TURN_ACTION": "took a turn",
    "SPAWN_BAND": "launched into a band",
    "ENABLER_BRANCH": "played an enabler",
    "MD_DECLARE": "answered a missile-defense prompt",
    "RESPONSE": "answered a response",
    "ALLOC_POINT": "assigned damage",
}


def _plain(message: str) -> str:
    side, _, rest = message.partition(" ")
    if side not in ("US", "PRC") or ":" not in rest:
        return message
    node, _, label = rest.partition(": ")
    verb = _PLAIN.get(node)
    if not verb:
        return message
    return f"{side} {verb}: {label}"


def _just(view: GameView) -> str:
    if view.roll_pending or view.watch_pending:
        return ""
    events = _latest_step(view)
    if not events:
        return ""
    # Prefer a plain-language event over a raw dice blob.
    for ev in reversed(events):
        if ev.type != "dice":
            return _plain(ev.message)
    return events[-1].message


def _event_side(ev) -> str:
    """Best-effort side for a log event (decision, dice roll, or message prefix)."""
    if ev.side in ("US", "PRC"):
        return ev.side
    data = ev.data or {}
    for roll in data.get("rolls") or []:
        if isinstance(roll, dict) and roll.get("side") in ("US", "PRC"):
            return roll["side"]
    msg = ev.message or ""
    if msg.startswith("US ") or msg.startswith("US:"):
        return "US"
    if msg.startswith("PRC ") or msg.startswith("PRC:"):
        return "PRC"
    return ""


def _watch_focus(
    view: GameView,
) -> tuple[str, list[int], list[str], list[str], list[str], list[int], list[str]]:
    """Side + art + labels + bands + board uids + move trail for Continue.

    Works for both the human (US) and the AI (PRC): the yellow blink follows
    whoever just acted on the held step. Board token uids win over coach-strip art.
    """
    events = _latest_step(view)
    side = ""
    # Match the Continue banner: narrate the decision, not follow-on dice /
    # cyber diffs in the same step (those often tag the other side).
    for ev in reversed(events):
        if ev.type == "decision":
            side = _event_side(ev)
            if side:
                break
    if not side:
        for ev in reversed(events):
            side = _event_side(ev)
            if side:
                break
    if view.draft_skip_pending and view.viewer in ("US", "PRC"):
        # Hold is "they are drafting now" before any of their picks land.
        side = "PRC" if view.viewer == "US" else "US"
    cards: list[int] = []
    tokens: list[str] = []
    labels: list[str] = []
    bands: list[str] = []
    uids: list[int] = []
    trail: list[str] = []
    for ev in events:
        # Art/labels for the blink come from the acting side's decision only.
        if side and ev.type == "decision" and _event_side(ev) not in ("", side):
            continue
        data = ev.data or {}
        for key in ("uid", "actor_uid", "target_uid"):
            uid = data.get(key)
            if isinstance(uid, int) and uid not in uids:
                uids.append(uid)
        cid = data.get("card_id")
        if isinstance(cid, int) and cid not in cards:
            cards.append(cid)
        from_band = data.get("from_band")
        to_band = data.get("to_band") or data.get("band")
        if isinstance(from_band, str) and from_band and from_band not in bands:
            bands.append(from_band)
        if isinstance(to_band, str) and to_band and to_band not in bands:
            bands.append(to_band)
        # Prefer an explicit move decision / token_moved for the trail arrow.
        if not trail and isinstance(from_band, str) and isinstance(to_band, str) \
                and from_band and to_band and from_band != to_band:
            if ev.type == "token_moved" or (ev.type == "decision" and data.get("kind") == "move"):
                trail = [from_band, to_band]
        ev_side = _event_side(ev) or side
        if ev.type == "decision":
            # "PRC TURN_ACTION: Attrition" → label after ": "
            _, _, label = (ev.message or "").partition(": ")
            label = label.strip()
            if label and label not in labels:
                labels.append(label)
            tokens.extend(_slugs(label, ev_side))
        tokens.extend(_slugs(ev.message or "", ev_side))
    if not side:
        # Unlabeled result after your own roll → blink your column.
        side = view.viewer or ""
    # Activate / kills / damage often omit band on the decision. Prefer event
    # payload bands, then where focus uids still sit on the board, then airbase
    # when the log is about base boxes or squadron cards.
    if uids and view.board is not None:
        want = set(uids)
        for band_view in view.board.bands:
            for tok in band_view.tokens or []:
                if tok.uid in want and band_view.band not in bands:
                    bands.append(band_view.band)
    # Base / squadron-card hits: blink that side's airbase column.
    for ev in events:
        data = ev.data or {}
        msg = (ev.message or "").lower()
        home = ""
        if isinstance(data.get("band"), str) and data["band"].endswith("AIRBASE"):
            home = data["band"]
        elif ev.type in ("squadron_damage", "squadron_destroyed"):
            tag = ev.side or side
            if tag in ("US", "PRC"):
                home = f"{tag}_AIRBASE"
        elif ev.type == "decision" and (
            "airbase" in msg or "vp box" in msg
        ):
            tag = ev.side or side
            if tag in ("US", "PRC"):
                home = f"{tag}_AIRBASE"
        if home and home not in bands:
            bands.append(home)
    seen: list[str] = []
    for slug in tokens:
        if slug not in seen:
            seen.append(slug)
    return side, cards[:4], seen[:3], labels[:4], bands[:4], uids[:6], trail[:2]


def _art(view: GameView, concept: str) -> tuple[list[int], list[str]]:
    cards: list[int] = []
    tokens: list[str] = []
    if view.watch_pending:
        _side, cards, tokens, _labels, _bands, _uids, _trail = _watch_focus(view)
        return cards, tokens
    side = view.decision.side if view.decision else None
    if view.decision:
        for choice in view.decision.choices:
            if choice.card_id and choice.card_id not in cards:
                cards.append(choice.card_id)
            tokens.extend(_slugs(choice.label, side))
            if len(cards) >= 4:
                break
    if concept == "mission" and 51 not in cards:
        cards.insert(0, 51)
    if concept == "posture" and 49 not in cards:
        cards.insert(0, 49)
    blob = " ".join(ev.message for ev in _latest_step(view))
    tokens.extend(_slugs(blob, side))
    # Stable, short.
    seen: list[str] = []
    for slug in tokens:
        if slug not in seen:
            seen.append(slug)
    return cards[:4], seen[:3]


def _find(choices: list[ChoiceView], pred) -> ChoiceView | None:
    for choice in choices:
        if pred(choice):
            return choice
    return None


def _say(choice: ChoiceView, why: str) -> str:
    return f'Pick "{choice.label}". {why}'


def _squadron_token(card_id: int | None):
    if card_id is None:
        return None
    profile = SQUADRON_REGISTRY.get(card_id)
    if profile is None:
        return None
    return TOKEN_REGISTRY.get(profile.token_type)


def _drafted_names(view: GameView) -> list[str]:
    """Squadron names already taken in this cycle's draft.

    The roster is not on the board until the draft ends, so the panel is empty
    here. The player's own pick messages are on the log.
    """
    side = view.decision.side if view.decision else ""
    names: list[str] = []
    prefix = f"{side} SQUADRON_PICK: "
    for ev in view.event_log:
        if ev.type != "decision" or ev.side != side:
            continue
        data = ev.data or {}
        node_type = str(data.get("node_type") or "")
        if node_type == "POSTURE_PICK":
            names.clear()
            continue
        if node_type != "SQUADRON_PICK" or data.get("kind") != "pick":
            continue
        if ev.message.startswith(prefix):
            names.append(ev.message[len(prefix):])
    return names


def _drafted_scores(view: GameView) -> set[TokenScoreType]:
    names = set(_drafted_names(view))
    found: set[TokenScoreType] = set()
    for profile in SQUADRON_REGISTRY.values():
        if profile.name not in names:
            continue
        token = _squadron_token(profile.card_id)
        if token is not None:
            found.add(token.token_score_type)
    return found


_NUM = {1: "one", 2: "two", 3: "three", 4: "four"}


def _num(n: int) -> str:
    return _NUM.get(n, str(n))


def _squadron_reason(card_id: int | None) -> str:
    """What this squadron is, how a turn with it plays, and why it is in the draft."""
    token = _squadron_token(card_id)
    if token is None:
        return "This card is a squadron you can launch. A card left in the deck never reaches the board."
    kind = token.token_score_type
    n = _num(token.token_count)
    if kind == TokenScoreType.FIGHTER:
        stealth = token.acquisition_value >= 4
        opening = "This is a stealth fighter." if stealth else "This is a fighter."
        fight = "They move two bands, and one air-to-air hit destroys the target."
        if token.air_atk_thresh and token.air_atk_thresh != 2:
            fight = (
                f"They move two bands. An air-to-air shot needs a {token.air_atk_thresh} "
                "or better, and that one hit destroys the target."
            )
        extra = ""
        if token.surf_atk_range:
            extra = " It can also strike a surface target one band away."
        why = (
            f" The enemy needs a {token.acquisition_value} to spot one, so you take it "
            "to reach that shot while it is still face-down."
            if stealth else
            " You take it because those aircraft are how you shoot theirs down."
        )
        return (
            f"{opening} Launching it puts {n} aircraft on your front band "
            f"(you may still play one enabler before you pass). "
            f"{fight}{extra}{why}"
        )
    if kind == TokenScoreType.BOMBER:
        damage = " A hit there rolls extra damage, and you choose where those hits land." if token.surf_exploding_die else ""
        return (
            "This is a bomber. It launches as one aircraft, and it may start in standoff, "
            "behind your front line, from where it can still reach the enemy airbase."
            f"{damage} You take it because a base strike scores and does not need a spot first."
        )
    if kind == TokenScoreType.AEW:
        return (
            "This is an airborne radar. It launches as one aircraft, and it may start in standoff. "
            "It rolls the spot die twice and adds 2, which is how a stealth fighter gets flipped face-up. "
            "You take it because an air shot is illegal until that spot succeeds."
        )
    if kind == TokenScoreType.ADA:
        return (
            "This is air defense. It stays at your base, and it does not move. "
            "An attack that crosses its weapon zone rolls two dice and keeps the worse one, "
            "and that costs none of your turn. You take it so the base is harder to strike "
            "while your aircraft do the shooting."
        )
    if kind == TokenScoreType.UAS and token.surf_atk_range and not token.air_atk_range:
        shot = "They strike a surface target one band away."
        if token.surf_atk_thresh and token.surf_atk_thresh != 2:
            shot = (
                f"They strike a surface target one band away, and that shot needs a "
                f"{token.surf_atk_thresh} or better."
            )
        return (
            f"These are attack drones. Launching the card puts {n} of them "
            "in the air, and they may start on any of the five center bands. "
            f"{shot} You take the card so you can hit a base or a ship from a band your fighters "
            "do not launch from."
        )
    if kind == TokenScoreType.UAS and token.acquire_rolls > 1 and not token.air_atk_range and not token.surf_atk_range:
        return (
            f"These are recon drones. The card puts {n} of them up, and they may start on any center band. "
            "They roll the spot die twice, so they can identify a face-down token. "
            "You take the card because an air shot is illegal until someone spots the target."
        )
    if kind == TokenScoreType.UAS:
        return (
            f"These are drones. The card puts {n} of them up, and they may start on any of the five "
            "center bands. They move one band. You take them because that puts aircraft on a band "
            "your fighters do not launch from."
        )
    if kind == TokenScoreType.SHIP:
        return (
            "This is a ship. It enters on a center band, moves one band, and can shoot aircraft or ships. "
            "It can also defend a shot that crosses it, and that spends one of its air salvos. "
            "You take it because that defense can spoil an attack aimed at a token you want to keep."
        )
    if kind == TokenScoreType.EC_130:
        return (
            "This is a jammer. It sits on a center band, and a PRC attack made from that same band "
            "rolls two dice and keeps the worse one. You take it to spoil a shot your aircraft cannot stop."
        )
    return (
        f"This card puts {n} pieces on the board when you launch it. "
        "You take it because a card left in the deck never reaches the fight."
    )


def _enabler_reason(card_id: int | None) -> str:
    """The card's effect, when you are allowed to play it, and what happens to it after."""
    profile = ENABLER_REGISTRY.get(card_id) if card_id else None
    if profile is None or not (profile.effect_text or "").strip():
        return "This card is played from your hand for an effect the aircraft cannot do alone."
    effect = " ".join(profile.effect_text.split())
    cut = len(effect)
    for i, ch in enumerate(effect):
        if ch in ".!?" and i > 40:
            cut = i + 1
            break
    effect = effect[:cut]
    if not effect.endswith((".", "!", "?")):
        effect += "."
    if profile.is_response and not profile.is_not_response:
        timing = " You hold it until its trigger happens, which can be on the other side's turn."
    else:
        timing = " You play it on your own turn, once, and the effect happens then."
    if profile.single_use:
        stay = " After that it is gone for the campaign."
    elif profile.is_enduring:
        stay = " The effect then lasts the whole ATO."
    else:
        stay = ""
    return f"{effect}{timing}{stay}"


# Preferred US fighters for the tutorial "air control" lesson (F-22, F-35, F-15, F-16).
_AIR_FIGHTER_IDS = (5, 8, 6, 10)


def _best_fighter(choices: list[ChoiceView]) -> ChoiceView | None:
    for card_id in _AIR_FIGHTER_IDS:
        hit = _find(choices, lambda c, cid=card_id: c.card_id == cid)
        if hit is not None:
            return hit
    return _find(choices, lambda c: (
        _squadron_token(c.card_id) is not None
        and _squadron_token(c.card_id).token_score_type == TokenScoreType.FIGHTER
    ))


def _fighter_draft_count(view: GameView) -> int:
    n = 0
    for nm in _drafted_names(view):
        for cid, prof in SQUADRON_REGISTRY.items():
            if prof.name != nm:
                continue
            tok = _squadron_token(cid)
            if tok is not None and tok.token_score_type == TokenScoreType.FIGHTER:
                n += 1
            break
    return n


def _suggest_draft(view: GameView) -> str:
    """Tutorial draft: AEW + fighters so the student can launch and shoot,
    not a bomber stack that dies on the airbase to the first missile card."""
    choices = view.decision.choices
    owned = _drafted_scores(view)
    names = _drafted_names(view)
    # 1) Spotter first — air shots are illegal until something is acquired.
    if TokenScoreType.AEW not in owned:
        aew = _find(choices, lambda c: (
            _squadron_token(c.card_id) is not None
            and _squadron_token(c.card_id).token_score_type == TokenScoreType.AEW
        ))
        if aew is not None:
            return _say(aew, _squadron_reason(aew.card_id))
    # 2–3) Fighters so the roster can fight once it is up.
    if _fighter_draft_count(view) < 2:
        fighter = _best_fighter(choices)
        if fighter is not None:
            return _say(fighter, _squadron_reason(fighter.card_id))
    if len(names) < 4:
        fighter = _best_fighter(choices)
        if fighter is not None:
            return _say(fighter, _squadron_reason(fighter.card_id))
        bomber = _find(choices, lambda c: (
            _squadron_token(c.card_id) is not None
            and _squadron_token(c.card_id).token_score_type == TokenScoreType.BOMBER
        ))
        if bomber is not None:
            return _say(bomber, _squadron_reason(bomber.card_id))
    done = _find(choices, lambda c: c.kind == "done")
    if done is not None and len(names) >= 3:
        return _say(
            done,
            "You have a spotter and fighters. Stop here so you can learn to launch and shoot them.",
        )
    pick = next((c for c in choices if c.kind == "pick"), choices[0])
    return _say(pick, _squadron_reason(pick.card_id))


def _suggest_placement(view: GameView) -> str:
    choices = view.decision.choices
    card_id = next((c.card_id for c in choices if c.card_id is not None), None)
    token = _squadron_token(card_id)
    air = _find(choices, lambda c: bool(c.band) and c.band.endswith("AIRBASE"))
    cl = _find(choices, lambda c: bool(c.band) and "CONTINGENCY" in c.band)
    several = token is not None and token.token_count > 1
    if several and air is not None:
        return _say(air, "This card has more than one aircraft. The airbase launches all of them. The contingency location rolls a die and may leave some on the ground.")
    if cl is not None and not several:
        return _say(cl, "This card has one aircraft, so it still launches from the contingency location, and a strike there does not fill the airbase's point boxes.")
    if air is not None:
        return _say(air, "The airbase launches the whole card.")
    return _say(choices[0], "This is a legal home for the card.")


def _suggest_spawn(view: GameView) -> str:
    choices = view.decision.choices
    standoff = _find(choices, lambda c: bool(c.band) and c.band.endswith("STANDOFF"))
    if standoff is not None:
        return _say(standoff, "Standoff sits behind your front band. A bomber launched there can still reach the enemy airbase.")
    front = "BAND_A" if view.decision.side == "US" else "BAND_E"
    band = _find(choices, lambda c: c.band == front)
    if band is not None:
        return _say(band, "This is your front band. Fighters appear here, and it starts the tokens closest to the fight.")
    return _say(choices[0], "This is a legal band for this launch.")


def _suggest_turn(view: GameView) -> str:
    choices = view.decision.choices
    side = view.decision.side
    airborne = [
        token
        for band in view.board.bands
        for token in band.tokens
        if token.side == side and not token.grounded
    ]
    squadron_types: set[str] = set()
    for panel in view.squadrons:
        if panel.side != side:
            continue
        for squadron in panel.squadrons:
            token = _squadron_token(squadron.card_id)
            if token is not None:
                squadron_types.add(token.token_type.value)
    squadron_up = [token for token in airborne if token.type in squadron_types]
    launches = [c for c in choices if c.kind == "activate"]
    enablers = [c for c in choices if c.kind == "play_enabler"]
    played = 0
    for hand in view.hands:
        if hand.side == side:
            played = hand.spent_count
    # Get aircraft up before playing hand cards or bombers — cards left on the
    # airbase die to the first hypersonic / missile without teaching a launch.
    if launches and not squadron_up:
        def launch_score(choice: ChoiceView) -> int:
            tok = _squadron_token(choice.card_id)
            if tok is None:
                return 9
            if tok.token_score_type == TokenScoreType.AEW:
                return 0
            if tok.token_score_type == TokenScoreType.FIGHTER:
                return 1
            if tok.token_score_type == TokenScoreType.BOMBER:
                return 3
            return 2

        pick = min(launches, key=launch_score)
        why = (
            "Launch the spotter first so later air shots can flip a face-down target."
            if launch_score(pick) == 0 else
            "Get fighters in the air now. Cards left on the airbase can be destroyed by a missile before you ever launch them."
            if launch_score(pick) == 1 else
            "You have no aircraft in the air yet. Launching starts the fight; you can still play one enabler before you pass."
        )
        return _say(pick, why)
    if enablers and played == 0 and squadron_up:
        # Air-control hand cards after something is airborne.
        prefer = (19, 26, 27, 31, 12, 29)  # munitions, spoofing, def EW, space recon, recovery, decoy
        for cid in prefer:
            hit = _find(enablers, lambda c, i=cid: c.card_id == i)
            if hit is not None:
                return _say(hit, _enabler_reason(hit.card_id))
    bomber_launch = [
        c for c in launches
        if _squadron_token(c.card_id) is not None
        and _squadron_token(c.card_id).token_score_type == TokenScoreType.BOMBER
    ]
    bomber_up = [
        token for token in squadron_up
        if token.type and ("B-52" in token.type or "H-6" in token.type)
    ]
    if bomber_launch and not bomber_up and squadron_up:
        return _say(
            bomber_launch[0],
            "A bomber can strike the enemy airbase without a spot. That fills a point box and scores 1 victory point.",
        )
    surface = [c for c in choices if c.kind == "shoot_surface"]
    if surface:
        return _say(surface[0], "A base strike does not need a spot first. Filling an airbase box scores 1 victory point.")
    air = [c for c in choices if c.kind == "shoot_air"]
    if air:
        return _say(air[0], "The target is acquired, so this shot is legal.")
    spots = [c for c in choices if c.kind == "acquire"]
    if spots:
        return _say(spots[0], "That token is face-down. You cannot shoot an aircraft until this spot succeeds.")
    moves = [c for c in choices if c.kind == "move"]
    if moves:
        return _say(moves[0], "Moving one token can put a later shot in range, or step you out of theirs.")
    passed = _find(choices, lambda c: c.kind == "pass")
    if launches and passed is not None:
        fighter = next((
            c for c in launches
            if _squadron_token(c.card_id) is not None
            and _squadron_token(c.card_id).token_score_type == TokenScoreType.FIGHTER
        ), None)
        pick = fighter or launches[0]
        return _say(pick, "The aircraft already up cannot take a useful action. Launching the next card puts more of the roster in the fight.")
    if passed is not None:
        return _say(passed, "Nothing else this turn helps.")
    return _say(choices[0], "This is a legal action on your turn.")


def _suggest_enabler(view: GameView) -> str:
    choices = view.decision.choices
    side = view.decision.side
    held = 0
    for hand in view.hands:
        if hand.side == side:
            held = len(hand.cards)
    done = _find(choices, lambda c: c.kind == "done")
    # Keep a fuller air-control hand (munitions / spoofing / spotters), not just
    # two token-spawn cards that encourage sitting on the airbase.
    if held >= 4 and done is not None:
        return _say(done, "Four enablers is enough to learn the hand. You may play one of them on your turn.")

    def draft_pick(choice: ChoiceView) -> bool:
        profile = ENABLER_REGISTRY.get(choice.card_id) if choice.card_id else None
        return bool(profile is not None and choice.kind == "pick" and choice.label == profile.name)

    # Air-control picks first (match Example drafts → Air control).
    _AIR_ENABLER_IDS = (19, 26, 27, 31, 12, 29)

    def rank(choice: ChoiceView) -> tuple[int, int]:
        profile = ENABLER_REGISTRY.get(choice.card_id) if choice.card_id else None
        if profile is None:
            return (9, choice.card_id or 0)
        if choice.card_id in _AIR_ENABLER_IDS:
            return (0, _AIR_ENABLER_IDS.index(choice.card_id))
        if profile.is_not_response and profile.is_enduring:
            return (1, choice.card_id or 0)
        if profile.is_not_response and profile.generates_token is None:
            return (2, choice.card_id or 0)
        if profile.generates_token is not None and profile.is_not_response:
            return (3, choice.card_id or 0)
        return (4, choice.card_id or 0)

    picks = [c for c in choices if draft_pick(c)]
    if picks:
        placed = min(picks, key=rank)
        return _say(placed, _enabler_reason(placed.card_id))
    if done is not None:
        return _say(done, "You can stop the draft here.")
    pick = next((c for c in choices if c.kind == "pick"), choices[0])
    return _say(pick, _enabler_reason(pick.card_id))


def _suggest(view: GameView) -> str:
    """Name one legal button and the reason a student should take it."""
    if view.roll_pending:
        return _roll_suggest(view)
    if view.watch_pending:
        return _watch_notice(view)
    decision = view.decision
    if view.terminal or decision is None or not decision.choices:
        return ""
    choices = decision.choices
    node = decision.node_type
    if node == "MISSION_PICK":
        attrition = _find(choices, lambda c: "ATTRITION" in c.label.upper())
        pick = attrition or choices[0]
        return _say(pick, "This is your scoring list for the whole campaign.")
    if node == "POSTURE_PICK":
        standard = _find(choices, lambda c: "STANDARD" in c.label.upper())
        pick = standard or choices[0]
        return _say(pick, "Standard lets you bring 3 or 4 squadrons and 6 enabler cards. The US can still use the contingency location.")
    if node == "SQUADRON_PICK":
        return _suggest_draft(view)
    if node == "SQUADRON_BASE":
        return _suggest_placement(view)
    if node == "ENABLER_PICK":
        return _suggest_enabler(view)
    if node == "SPAWN_BAND":
        return _suggest_spawn(view)
    if node == "TURN_ACTION":
        return _suggest_turn(view)
    if node == "FIRST_PLAYER":
        own = _find(choices, lambda c: c.label.startswith(decision.side))
        pick = own or choices[0]
        return _say(pick, "Take the first turn so your launch happens before they have aircraft up.")
    if node == "ALLOC_POINT":
        box = _find(choices, lambda c: c.alloc_kind == "vp")
        if box is not None:
            return _say(box, "An airbase box scores 1 victory point and stays filled for the whole campaign.")
        card = _find(choices, lambda c: c.alloc_kind == "squadron")
        if card is not None:
            return _say(card, "A squadron card is destroyed at 2 hits, and aircraft still on it are lost with the card.")
        return _say(choices[0], "Place the hit on a target that can still take it.")
    if node == "MD_DECLARE":
        defense = _find(choices, lambda c: c.kind != "skip")
        if defense is not None:
            return _say(defense, "Missile defense makes the attack roll two dice and keep the worse one.")
        return _say(choices[0], "No defender is available for this shot.")
    if node == "RESPONSE":
        answer = _find(choices, lambda c: c.kind != "skip")
        if answer is not None:
            return _say(answer, "The trigger is happening now, and this card can cancel the effect.")
        return _say(choices[0], "There is no response card to play.")
    if node == "INTEL_REVEAL":
        return _say(choices[0], "You learn that this card is in their hand. At least one other card stays hidden.")
    if node == "BID_SACRIFICE":
        done = _find(choices, lambda c: c.kind == "done")
        if done is not None:
            return _say(done, "The dice decide initiative. You do not have to give up a card.")
    if node == "ENABLER_BRANCH":
        return _say(choices[0], "This is the branch the card resolves now.")
    return _say(choices[0], "This is a legal choice for the step in front of you.")


def explain(view: GameView) -> CoachNote:
    """Teaching note for whatever the spectator is looking at right now."""
    concept = _concept(view)
    title, lesson, look = _LESSONS[concept]
    cards, tokens = _art(view, concept)
    watch_side = ""
    watch_labels: list[str] = []
    watch_bands: list[str] = []
    watch_uids: list[int] = []
    watch_trail: list[str] = []
    if view.watch_pending:
        watch_side, w_cards, w_tokens, watch_labels, watch_bands, watch_uids, watch_trail = (
            _watch_focus(view)
        )
        if w_cards:
            cards = w_cards
        if w_tokens:
            tokens = w_tokens
    return CoachNote(
        revision=view.revision,
        concept=concept,
        title=title,
        lesson=lesson,
        now=_now(view),
        why=_why(view, concept),
        just=_just(view),
        look=look,
        suggest=_suggest(view),
        hold="watch" if view.watch_pending else "",
        cards=cards,
        tokens=tokens,
        watch_side=watch_side,
        watch_labels=watch_labels,
        watch_bands=watch_bands,
        watch_uids=watch_uids,
        watch_trail=watch_trail,
    )
