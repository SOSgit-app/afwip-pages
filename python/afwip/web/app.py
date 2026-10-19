"""
app.py — FastAPI application: session lifecycle + static frontend hosting.

Plain HTTP (no WebSocket): the browser polls / posts and always receives the
full fogged GameView. Sessions live in memory keyed by game_id; a lock per
process keeps concurrent requests from interleaving env steps.

    POST   /api/games                create {campaign, mode, human_side, seed}
    GET    /api/games/{id}           current fogged view
    POST   /api/games/{id}/choices   {index, revision, node_id} -> new view
    POST   /api/games/{id}/step      advance one decision (spectator)
    POST   /api/games/{id}/handoff   hotseat pass-the-device confirmation
    DELETE /api/games/{id}
    GET    /api/config               campaigns / modes / agents

Stale submissions (revision or node_id mismatch) return 409 Conflict. If a
built frontend exists at web/dist it is served at / with SPA fallback.
"""

from __future__ import annotations

import secrets
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from afwip.core.constants import CAMPAIGN_ATO_CYCLES, Side
from afwip.view.models import GameView
from afwip.web.agents import AGENT_REGISTRY
from afwip.web.coach import CoachNote, explain
from afwip.web.session import GameMode, GameSession, SessionError, StaleStateError

def _frontend_dist() -> Path:
    """Locate the built frontend. When frozen by PyInstaller the `web/dist`
    tree is bundled and extracted under `sys._MEIPASS`; from source it sits at
    the repo root."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return base / "web" / "dist"
    return Path(__file__).resolve().parents[2] / "web" / "dist"


FRONTEND_DIST = _frontend_dist()


class CreateGameRequest(BaseModel):
    campaign: int = Field(default=2, ge=1, le=5)
    mode: GameMode = GameMode.HUMAN_V_AGENT
    human_side: str = "US"                 # human_v_agent only
    seed: Optional[int] = None
    agent: str = "random"
    # Capture a replayable training trajectory. None -> default (record hotseat
    # games, the hand-curation mode); pass false to opt a hotseat game out.
    record: Optional[bool] = None
    # A user-supplied OpenAI key for the "gpt" agent (local app; kept only in
    # session memory, never logged or returned).
    openai_api_key: Optional[str] = None


class PaceRequest(BaseModel):
    on: bool = True


class ChoiceRequest(BaseModel):
    index: int = Field(ge=0)
    revision: Optional[int] = None
    node_id: Optional[str] = None
    # Optional doctrine rationale for this move, stored on the trajectory step.
    justification: Optional[str] = None
    # Two-device play: which side this device is acting as.
    viewer: Optional[str] = None


def _side(value: Optional[str]) -> Optional[Side]:
    if value is None:
        return None
    try:
        return Side(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="viewer must be US or PRC")


def create_app() -> FastAPI:
    app = FastAPI(title="AFWIP", docs_url="/api/docs", openapi_url="/api/openapi.json")
    sessions: dict[str, GameSession] = {}
    lock = threading.Lock()

    def get_session(game_id: str) -> GameSession:
        session = sessions.get(game_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"no game '{game_id}'")
        return session

    @app.post("/api/games", response_model=GameView)
    def create_game(req: CreateGameRequest) -> GameView:
        try:
            side = Side(req.human_side)
        except ValueError:
            raise HTTPException(status_code=422, detail="human_side must be US or PRC")
        game_id = secrets.token_hex(4)
        try:
            session = GameSession(game_id, campaign=req.campaign, mode=req.mode,
                                  human_side=side, seed=req.seed,
                                  agent_name=req.agent, record=req.record,
                                  openai_api_key=req.openai_api_key)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        with lock:
            sessions[game_id] = session
        return session.state()

    @app.get("/api/games/{game_id}", response_model=GameView)
    def get_game(game_id: str, viewer: Optional[str] = None) -> GameView:
        return get_session(game_id).state(viewer_override=_side(viewer))

    @app.get("/api/games/{game_id}/coach", response_model=CoachNote)
    def get_coach(game_id: str) -> CoachNote:
        """What the live tutorial should say about the current decision."""
        return explain(get_session(game_id).state())

    @app.post("/api/games/{game_id}/choices", response_model=GameView)
    def post_choice(game_id: str, req: ChoiceRequest) -> GameView:
        session = get_session(game_id)
        actor = _side(req.viewer)
        with lock:
            try:
                session.apply_human(req.index, revision=req.revision,
                                    node_id=req.node_id,
                                    justification=req.justification,
                                    actor_side=actor)
            except StaleStateError as e:
                raise HTTPException(status_code=409, detail=str(e))
            except SessionError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return session.state(viewer_override=actor)

    @app.post("/api/games/{game_id}/pace")
    def post_pace(game_id: str, req: PaceRequest) -> dict:
        """Live tutorial: reveal the opponent one decision at a time."""
        session = get_session(game_id)
        with lock:
            session.paced = req.on
        return {"paced": session.paced}

    @app.post("/api/games/{game_id}/watch", response_model=GameView)
    def post_watch(game_id: str, viewer: Optional[str] = None) -> GameView:
        """Leave the tutorial hold and show the next opponent decision."""
        session = get_session(game_id)
        with lock:
            try:
                session.continue_watch()
            except SessionError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return session.state(viewer_override=_side(viewer))

    @app.post("/api/games/{game_id}/undo", response_model=GameView)
    def post_undo(game_id: str, viewer: Optional[str] = None) -> GameView:
        """Drop the last card the player chose and return to that decision."""
        session = get_session(game_id)
        with lock:
            try:
                sessions[game_id] = session.undone()
            except SessionError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return sessions[game_id].state(viewer_override=_side(viewer))

    @app.post("/api/games/{game_id}/reveal", response_model=GameView)
    def post_reveal(game_id: str, viewer: Optional[str] = None) -> GameView:
        """Client finished the die screen; clear the pending roll. In
        human-v-agent that also lets the agent continue; in Watch Agents the
        spectator steps again afterward."""
        session = get_session(game_id)
        with lock:
            session.reveal_roll()
        return session.state(viewer_override=_side(viewer))

    @app.post("/api/games/{game_id}/step", response_model=GameView)
    def post_step(game_id: str) -> GameView:
        session = get_session(game_id)
        with lock:
            try:
                session.step_once()
            except SessionError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return session.state()

    @app.post("/api/games/{game_id}/handoff", response_model=GameView)
    def post_handoff(game_id: str) -> GameView:
        session = get_session(game_id)
        with lock:
            try:
                session.handoff()
            except SessionError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return session.state()

    @app.delete("/api/games/{game_id}")
    def delete_game(game_id: str) -> dict:
        with lock:
            if sessions.pop(game_id, None) is None:
                raise HTTPException(status_code=404, detail=f"no game '{game_id}'")
        return {"deleted": game_id}

    @app.get("/api/config")
    def get_config() -> dict:
        return {
            "campaigns": sorted(CAMPAIGN_ATO_CYCLES),
            "modes": [m.value for m in GameMode],
            "sides": [s.value for s in Side],
            "agents": sorted(AGENT_REGISTRY),
        }

    # Built frontend (web/dist) with SPA fallback; API keeps working without it.
    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = FRONTEND_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
