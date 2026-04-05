"""In-memory room management for the hosted Splendor API."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from splendor_core import GameError, PLAYER_COUNT, SplendorGame


ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits
DEFAULT_ACTIVE_ROOM_TTL_SECONDS = 2 * 60 * 60
DEFAULT_EMPTY_ROOM_TTL_SECONDS = 15 * 60
DEFAULT_CLEANUP_INTERVAL_SECONDS = 30


class RoomServiceError(Exception):
    """Raised for recoverable room-service failures."""

    def __init__(self, message: str, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class RoomSeat:
    player_id: str
    player_token: str


@dataclass(slots=True)
class RoomSession:
    room_code: str
    game: SplendorGame
    seats: dict[str, RoomSeat] = field(default_factory=dict)
    sockets: dict[str, set[Any]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_activity_at = time.time()

    def has_connected_clients(self) -> bool:
        return any(self.sockets.get(player_id) for player_id in self.seats)

    def state_for(self, player_id: str | None) -> dict[str, Any]:
        return self.game.player_view(player_id)

    def connected_players(self) -> list[dict[str, Any]]:
        return self.game.player_view(None)["connected_players"]

    def metadata(self, player_id: str | None = None) -> dict[str, Any]:
        return {
            "room_code": self.room_code,
            "phase": self.game.phase,
            "player_count": len(self.game.players),
            "max_players": PLAYER_COUNT,
            "joinable": len(self.game.players) < PLAYER_COUNT,
            "player_id": player_id,
            "connected_players": self.connected_players(),
            "state": self.state_for(player_id) if player_id else None,
        }

    def ttl_seconds(self, active_ttl: int, empty_ttl: int) -> int:
        if len(self.game.players) >= PLAYER_COUNT or self.game.phase != "lobby" or self.has_connected_clients():
            return active_ttl
        return empty_ttl

    def expired(self, active_ttl: int, empty_ttl: int, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now - self.last_activity_at > self.ttl_seconds(active_ttl, empty_ttl)


class RoomManager:
    """Owns room creation, join flow, reconnect tokens, and cleanup."""

    def __init__(
        self,
        *,
        active_room_ttl_seconds: int = DEFAULT_ACTIVE_ROOM_TTL_SECONDS,
        empty_room_ttl_seconds: int = DEFAULT_EMPTY_ROOM_TTL_SECONDS,
        cleanup_interval_seconds: int = DEFAULT_CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        self.active_room_ttl_seconds = active_room_ttl_seconds
        self.empty_room_ttl_seconds = empty_room_ttl_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.rooms: dict[str, RoomSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
        async with self._lock:
            rooms = list(self.rooms.values())
            self.rooms.clear()
        await asyncio.gather(*(self._close_room(room, "Room closed.") for room in rooms), return_exceptions=True)

    async def create_room(self, player_name: str) -> tuple[RoomSession, RoomSeat]:
        async with self._lock:
            room_code = self._generate_room_code()
            game = SplendorGame()
            player_id = game.add_player(player_name)
            seat = RoomSeat(player_id=player_id, player_token=self._generate_player_token())
            room = RoomSession(room_code=room_code, game=game)
            room.seats[player_id] = seat
            room.touch()
            self.rooms[room_code] = room
            return room, seat

    async def join_room(self, room_code: str, player_name: str) -> tuple[RoomSession, RoomSeat]:
        async with self._lock:
            room = self._get_room_locked(room_code)
            if len(room.game.players) >= PLAYER_COUNT:
                raise RoomServiceError("That room is already full.", "room_full", 409)
            player_id = room.game.add_player(player_name)
            seat = RoomSeat(player_id=player_id, player_token=self._generate_player_token())
            room.seats[player_id] = seat
            room.touch()
            return room, seat

    async def get_room(self, room_code: str, player_token: str | None = None) -> tuple[RoomSession, str | None]:
        async with self._lock:
            room = self._get_room_locked(room_code)
            player_id = self._player_id_for_token(room, player_token) if player_token else None
            room.touch()
            return room, player_id

    async def connect_player(self, room_code: str, player_token: str, websocket: Any) -> tuple[RoomSession, RoomSeat]:
        async with self._lock:
            room = self._get_room_locked(room_code)
            player_id = self._player_id_for_token(room, player_token)
            assert player_id is not None
            seat = room.seats[player_id]
            room.sockets.setdefault(player_id, set()).add(websocket)
            room.game.mark_connected(player_id)
            room.touch()
            return room, seat

    async def disconnect_player(self, room_code: str, player_token: str, websocket: Any) -> RoomSession | None:
        async with self._lock:
            room = self.rooms.get(room_code)
            if room is None:
                return None
            player_id = self._player_id_for_token(room, player_token, raise_on_missing=False)
            if player_id is None:
                return room
            sockets = room.sockets.get(player_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    room.sockets.pop(player_id, None)
                    room.game.mark_disconnected(player_id)
            room.touch()
            return room

    async def apply_action(
        self,
        room_code: str,
        player_token: str,
        action: str,
        payload: dict[str, Any] | None,
    ) -> tuple[RoomSession, list[dict[str, Any]]]:
        async with self._lock:
            room = self._get_room_locked(room_code)
            player_id = self._player_id_for_token(room, player_token)
            assert player_id is not None
            try:
                result = room.game.apply_action(player_id, action, payload or {})
            except GameError as exc:
                raise RoomServiceError(str(exc), "illegal_action", 400) from exc
            room.touch()
            return room, result.emitted_events

    async def snapshot(self, room_code: str, player_token: str | None) -> dict[str, Any]:
        room, player_id = await self.get_room(room_code, player_token)
        return room.metadata(player_id)

    async def emit_presence(self, room: RoomSession) -> None:
        await self._broadcast(room, {"type": "presence", "connected_players": room.connected_players()})

    async def emit_state(self, room: RoomSession, events: list[dict[str, Any]] | None = None) -> None:
        await self._broadcast_state(room, events or [])

    async def close_expired_rooms(self) -> None:
        async with self._lock:
            expired_codes = [
                room_code
                for room_code, room in self.rooms.items()
                if room.expired(self.active_room_ttl_seconds, self.empty_room_ttl_seconds)
            ]
            rooms = [self.rooms.pop(room_code) for room_code in expired_codes]
        await asyncio.gather(
            *(self._close_room(room, "Room expired due to inactivity.") for room in rooms),
            return_exceptions=True,
        )

    def _generate_room_code(self) -> str:
        while True:
            room_code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))
            if room_code not in self.rooms:
                return room_code

    @staticmethod
    def _generate_player_token() -> str:
        return secrets.token_urlsafe(24)

    def _get_room_locked(self, room_code: str) -> RoomSession:
        room = self.rooms.get(room_code.upper())
        if room is None:
            raise RoomServiceError("That room does not exist.", "room_not_found", 404)
        return room

    @staticmethod
    def _player_id_for_token(
        room: RoomSession,
        player_token: str | None,
        *,
        raise_on_missing: bool = True,
    ) -> str | None:
        if not player_token:
            if raise_on_missing:
                raise RoomServiceError("A player token is required.", "invalid_player_token", 401)
            return None
        for player_id, seat in room.seats.items():
            if secrets.compare_digest(seat.player_token, player_token):
                return player_id
        if raise_on_missing:
            raise RoomServiceError("That player token is invalid.", "invalid_player_token", 401)
        return None

    async def _broadcast_state(self, room: RoomSession, events: list[dict[str, Any]]) -> None:
        coroutines = []
        for player_id, seat in room.seats.items():
            payload = {
                "type": "state",
                "state": room.state_for(player_id),
                "events": list(events),
            }
            for websocket in list(room.sockets.get(player_id, ())):
                coroutines.append(self._send_safe(websocket, payload))
        if coroutines:
            await asyncio.gather(*coroutines, return_exceptions=True)

    async def _broadcast(self, room: RoomSession, payload: dict[str, Any]) -> None:
        coroutines = []
        for sockets in room.sockets.values():
            for websocket in list(sockets):
                coroutines.append(self._send_safe(websocket, payload))
        if coroutines:
            await asyncio.gather(*coroutines, return_exceptions=True)

    async def _close_room(self, room: RoomSession, message: str) -> None:
        await self._broadcast(room, {"type": "room_closed", "message": message})
        coroutines = []
        for sockets in room.sockets.values():
            for websocket in list(sockets):
                coroutines.append(self._close_socket_safe(websocket))
        if coroutines:
            await asyncio.gather(*coroutines, return_exceptions=True)

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self.close_expired_rooms()
        except asyncio.CancelledError:
            raise

    @staticmethod
    async def _send_safe(websocket: Any, payload: dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            return

    @staticmethod
    async def _close_socket_safe(websocket: Any) -> None:
        with contextlib.suppress(Exception):
            await websocket.close()
