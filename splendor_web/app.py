"""FastAPI application for the hosted Splendor experience."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from splendor_core.assets import asset_root

from .rooms import RoomManager, RoomServiceError


def _cors_origins_from_env() -> list[str]:
    raw_origins = os.getenv("SPLENDOR_WEB_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class JoinRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class JoinedResponse(BaseModel):
    type: str = "joined"
    room_code: str
    player_id: str
    player_token: str


class RoomSnapshotResponse(BaseModel):
    room_code: str
    phase: str
    player_count: int
    max_players: int
    joinable: bool
    player_id: str | None
    connected_players: list[dict[str, Any]]
    state: dict[str, Any] | None


def create_app() -> FastAPI:
    manager = RoomManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(title="Splendor Web API", version="0.1.0", lifespan=lifespan)
    app.state.room_manager = manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/assets", StaticFiles(directory=Path(asset_root())), name="assets")

    @app.post("/api/rooms", response_model=JoinedResponse)
    async def create_room(request: CreateRoomRequest) -> JoinedResponse:
        try:
            room, seat = await manager.create_room(request.name)
        except RoomServiceError as exc:
            raise _http_error(exc) from exc
        return JoinedResponse(room_code=room.room_code, player_id=seat.player_id, player_token=seat.player_token)

    @app.post("/api/rooms/{room_code}/join", response_model=JoinedResponse)
    async def join_room(room_code: str, request: JoinRoomRequest) -> JoinedResponse:
        try:
            room, seat = await manager.join_room(room_code.upper(), request.name)
        except RoomServiceError as exc:
            raise _http_error(exc) from exc
        return JoinedResponse(room_code=room.room_code, player_id=seat.player_id, player_token=seat.player_token)

    @app.get("/api/rooms/{room_code}", response_model=RoomSnapshotResponse)
    async def get_room(
        room_code: str,
        player_token: str | None = Query(default=None),
    ) -> RoomSnapshotResponse:
        try:
            snapshot = await manager.snapshot(room_code.upper(), player_token)
        except RoomServiceError as exc:
            raise _http_error(exc) from exc
        return RoomSnapshotResponse(**snapshot)

    @app.websocket("/ws/rooms/{room_code}")
    async def room_socket(websocket: WebSocket, room_code: str, player_token: str = Query(...)) -> None:
        await websocket.accept()
        try:
            room, seat = await manager.connect_player(room_code.upper(), player_token, websocket)
        except RoomServiceError as exc:
            await websocket.send_json({"type": "error", "message": exc.message, "code": exc.code})
            await websocket.close(code=1008)
            return

        await websocket.send_json(
            {
                "type": "joined",
                "room_code": room.room_code,
                "player_id": seat.player_id,
                "player_token": seat.player_token,
            }
        )
        await manager.emit_presence(room)
        await manager.emit_state(room, [{"type": "player_connected", "player_id": seat.player_id}])

        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") != "action":
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Unsupported message type.",
                            "code": "unsupported_message",
                        }
                    )
                    continue
                action = str(message.get("action", ""))
                payload = dict(message.get("payload", {}))
                try:
                    room, events = await manager.apply_action(room.room_code, player_token, action, payload)
                except RoomServiceError as exc:
                    await websocket.send_json({"type": "error", "message": exc.message, "code": exc.code})
                    continue
                await manager.emit_state(room, events)
        except WebSocketDisconnect:
            pass
        finally:
            room = await manager.disconnect_player(room_code.upper(), player_token, websocket)
            if room is not None:
                await manager.emit_presence(room)
                await manager.emit_state(room, [{"type": "player_disconnected"}])

    return app


def _http_error(error: RoomServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail={"message": error.message, "code": error.code})


def main() -> int:
    import uvicorn

    uvicorn.run(
        "splendor_web.app:create_app",
        factory=True,
        host=os.getenv("SPLENDOR_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("SPLENDOR_WEB_PORT", "8000")),
        reload=os.getenv("SPLENDOR_WEB_RELOAD", "0") == "1",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
