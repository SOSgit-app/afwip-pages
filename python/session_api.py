"""
In-browser session API for the GitHub Pages build.

Mirrors the FastAPI routes in afwip.web.app so the existing frontend can keep
calling /api/... — a JS fetch shim forwards those calls here via Pyodide.
"""

from __future__ import annotations

import json
import secrets
import traceback
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from afwip.core.constants import CAMPAIGN_ATO_CYCLES, Side
from afwip.web.session import GameMode, GameSession, SessionError, StaleStateError
from afwip.web.coach import explain

# Pages MVP: single-device modes + random AI only (ONNX/GPT/LAN later).
PAGES_MODES = [
    GameMode.HUMAN_V_AGENT.value,
    GameMode.AGENT_V_AGENT.value,
    GameMode.HOTSEAT.value,
]
PAGES_AGENTS = ["random"]

_sessions: dict[str, GameSession] = {}


def _side(value: Optional[str]) -> Optional[Side]:
    if value is None or value == "":
        return None
    return Side(value)


def _dump(view: Any) -> Any:
    if hasattr(view, "model_dump"):
        return view.model_dump(mode="json")
    if hasattr(view, "dict"):
        return view.dict()
    return view


def _err(status: int, detail: str) -> dict:
    return {"status": status, "body": {"detail": detail}}


def _ok(body: Any, status: int = 200) -> dict:
    return {"status": status, "body": body}


def handle(method: str, url: str, body_text: str = "") -> str:
    """Entry point from JS. Returns a JSON string: {status, body}."""
    try:
        result = _dispatch(method.upper(), url, body_text or "")
    except Exception as exc:  # noqa: BLE001 — surface to the browser
        traceback.print_exc()
        result = _err(500, f"{type(exc).__name__}: {exc}")
    return json.dumps(result)


def _dispatch(method: str, url: str, body_text: str) -> dict:
    parsed = urlparse(url)
    path = parsed.path or ""
    # Strip optional Pages project prefix: /repo/api/... or /api/...
    if "/api/" in path:
        path = path[path.index("/api/") :]
    qs = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    body: dict[str, Any] = {}
    if body_text.strip():
        body = json.loads(body_text)

    if path == "/api/config" and method == "GET":
        return _ok({
            "campaigns": sorted(CAMPAIGN_ATO_CYCLES),
            "modes": list(PAGES_MODES),
            "sides": [s.value for s in Side],
            "agents": list(PAGES_AGENTS),
        })

    if path == "/api/games" and method == "POST":
        return _create(body)
    if path == "/api/games/restore" and method == "POST":
        return _restore(body)

    parts = [p for p in path.split("/") if p]
    # ["api", "games", "{id}", ...]
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "games":
        return _err(404, f"unknown route {method} {path}")

    game_id = parts[2]
    action = parts[3] if len(parts) > 3 else ""

    if not action and method == "GET":
        return _get(game_id, qs.get("viewer"))
    if not action and method == "DELETE":
        return _delete(game_id)
    if action == "save" and method == "GET":
        return _save(game_id)
    if action == "choices" and method == "POST":
        return _choices(game_id, body)
    if action == "step" and method == "POST":
        return _step(game_id)
    if action == "reveal" and method == "POST":
        return _reveal(game_id, qs.get("viewer"))
    if action == "handoff" and method == "POST":
        return _handoff(game_id)
    if action == "pace" and method == "POST":
        return _pace(game_id, body)
    if action == "watch" and method == "POST":
        return _watch(game_id, qs.get("viewer"))
    if action == "undo" and method == "POST":
        return _undo(game_id, qs.get("viewer"))
    if action == "coach" and method == "GET":
        return _coach(game_id)
    if action == "trajectory" and method == "POST":
        return _err(400, "trajectory export is disabled in the Pages build")

    return _err(404, f"unknown route {method} {path}")


def _create(body: dict) -> dict:
    mode_raw = body.get("mode", GameMode.HUMAN_V_AGENT.value)
    if mode_raw not in PAGES_MODES:
        return _err(422, f"mode '{mode_raw}' is not available in the Pages build")
    agent = body.get("agent") or "random"
    if agent not in PAGES_AGENTS:
        # Fall back rather than hard-fail if the UI still offers old labels.
        agent = "random"
    try:
        side = Side(body.get("human_side") or "US")
        mode = GameMode(mode_raw)
    except ValueError as exc:
        return _err(422, str(exc))
    game_id = secrets.token_hex(4)
    try:
        session = GameSession(
            game_id,
            campaign=int(body.get("campaign") or 2),
            mode=mode,
            human_side=side,
            seed=body.get("seed"),
            agent_name=agent,
            # Keep a decision tape so Save / Load works in the browser.
            record=True,
            openai_api_key=None,
        )
    except ValueError as exc:
        return _err(422, str(exc))
    _sessions[game_id] = session
    return _ok(_dump(session.state()))


def _restore(body: dict) -> dict:
    game_id = secrets.token_hex(4)
    try:
        session = GameSession.from_save(game_id, body.get("save") or {})
    except SessionError as exc:
        return _err(400, str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        return _err(400, f"invalid save: {exc}")
    _sessions[game_id] = session
    return _ok(_dump(session.state()))


def _save(game_id: str) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    try:
        return _ok(session.export_save())
    except SessionError as exc:
        return _err(404, str(exc))


def _get_session(game_id: str) -> GameSession:
    session = _sessions.get(game_id)
    if session is None:
        raise KeyError(game_id)
    return session


def _get(game_id: str, viewer: Optional[str]) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    return _ok(_dump(session.state(viewer_override=_side(viewer))))


def _delete(game_id: str) -> dict:
    if _sessions.pop(game_id, None) is None:
        return _err(404, f"no game '{game_id}'")
    return _ok({"deleted": game_id})


def _choices(game_id: str, body: dict) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    actor = _side(body.get("viewer"))
    try:
        session.apply_human(
            int(body["index"]),
            revision=body.get("revision"),
            node_id=body.get("node_id"),
            justification=body.get("justification"),
            actor_side=actor,
        )
    except StaleStateError as exc:
        return _err(409, str(exc))
    except SessionError as exc:
        return _err(400, str(exc))
    except KeyError as exc:
        return _err(422, f"missing field {exc}")
    return _ok(_dump(session.state(viewer_override=actor)))


def _step(game_id: str) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    try:
        session.step_once()
    except SessionError as exc:
        return _err(400, str(exc))
    return _ok(_dump(session.state()))


def _reveal(game_id: str, viewer: Optional[str]) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    session.reveal_roll()
    return _ok(_dump(session.state(viewer_override=_side(viewer))))


def _handoff(game_id: str) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    try:
        session.handoff()
    except SessionError as exc:
        return _err(400, str(exc))
    return _ok(_dump(session.state()))


def _pace(game_id: str, body: dict) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    session.paced = bool(body.get("on"))
    return _ok({"paced": session.paced})


def _watch(game_id: str, viewer: Optional[str]) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    try:
        session.continue_watch()
    except SessionError as exc:
        return _err(400, str(exc))
    return _ok(_dump(session.state(viewer_override=_side(viewer))))


def _undo(game_id: str, viewer: Optional[str]) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    try:
        _sessions[game_id] = session.undone()
    except SessionError as exc:
        return _err(400, str(exc))
    return _ok(_dump(_sessions[game_id].state(viewer_override=_side(viewer))))


def _coach(game_id: str) -> dict:
    try:
        session = _get_session(game_id)
    except KeyError:
        return _err(404, f"no game '{game_id}'")
    note = explain(session.state())
    return _ok(_dump(note))
