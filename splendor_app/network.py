"""Simple TCP host/join networking for the Splendor prototype."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .constants import PLAYER_COUNT
from .game_logic import GameError, SplendorGame

DISCOVERY_PORT = 34871
DISCOVERY_INTERVAL_SECONDS = 1.0
DISCOVERY_STALE_AFTER_SECONDS = 3.0


def _send_json(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload) + "\n").encode("utf-8")
    sock.sendall(data)


def get_local_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


@dataclass
class ServerClient:
    sock: socket.socket
    address: tuple[str, int]
    player_id: str | None = None
    name: str | None = None


@dataclass(slots=True)
class DiscoveryGame:
    host_name: str
    host: str
    port: int
    player_count: int
    joinable: bool
    status: str
    last_seen: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_name": self.host_name,
            "host": self.host,
            "port": self.port,
            "player_count": self.player_count,
            "joinable": self.joinable,
            "status": self.status,
            "last_seen": self.last_seen,
        }


class GameServer:
    """Threaded authoritative game server."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 0,
        seed: int | None = None,
        advertised_name: str = "Host",
        discovery_port: int = DISCOVERY_PORT,
        discovery_target: str = "255.255.255.255",
        discovery_interval: float = DISCOVERY_INTERVAL_SECONDS,
    ) -> None:
        self.host = host
        self.port = port
        self.game = SplendorGame(seed=seed)
        self.advertised_name = advertised_name.strip() or "Host"
        self.discovery_port = discovery_port
        self.discovery_target = discovery_target
        self.discovery_interval = discovery_interval
        self.server_socket: socket.socket | None = None
        self.accept_thread: threading.Thread | None = None
        self.discovery_thread: threading.Thread | None = None
        self.discovery_socket: socket.socket | None = None
        self.clients: dict[socket.socket, ServerClient] = {}
        self.lock = threading.RLock()
        self.running = False

    def start(self) -> tuple[str, int]:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.running = True
        self.host, self.port = self.server_socket.getsockname()[:2]
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
        return self.host, self.port

    def stop(self) -> None:
        self.running = False
        if self.discovery_socket is not None:
            try:
                self.discovery_socket.close()
            except OSError:
                pass
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass
        with self.lock:
            clients = list(self.clients.keys())
        for client_socket in clients:
            try:
                client_socket.close()
            except OSError:
                pass

    def connection_hint(self) -> str:
        return f"{get_local_ip()}:{self.port}"

    def discovery_snapshot(self) -> dict[str, Any]:
        with self.lock:
            host_name = self.advertised_name
            if self.game.players:
                host_name = self.game.players[0].name
            player_count = len(self.game.players)
        joinable = player_count < PLAYER_COUNT
        return {
            "type": "discovery",
            "host_name": host_name,
            "host": get_local_ip(),
            "port": self.port,
            "player_count": player_count,
            "joinable": joinable,
            "status": "Waiting" if joinable else "Full",
            "timestamp": time.time(),
        }

    def _accept_loop(self) -> None:
        assert self.server_socket is not None
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
            except OSError:
                break
            with self.lock:
                self.clients[client_socket] = ServerClient(sock=client_socket, address=address)
            thread = threading.Thread(target=self._client_loop, args=(client_socket,), daemon=True)
            thread.start()

    def _discovery_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket = sock
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            while self.running:
                try:
                    payload = json.dumps(self.discovery_snapshot()).encode("utf-8")
                    targets = [(self.discovery_target, self.discovery_port)]
                    # Loopback makes same-machine testing reliable even when the OS
                    # does not reflect LAN broadcasts back to local listeners.
                    if self.discovery_target != "127.0.0.1":
                        targets.append(("127.0.0.1", self.discovery_port))
                    for target in targets:
                        sock.sendto(payload, target)
                except OSError:
                    if not self.running:
                        break
                time.sleep(self.discovery_interval)
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self.discovery_socket = None

    def _client_loop(self, client_socket: socket.socket) -> None:
        file_obj = client_socket.makefile("r", encoding="utf-8")
        try:
            while self.running:
                line = file_obj.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                    self._handle_message(client_socket, message)
                except (json.JSONDecodeError, GameError, KeyError, ValueError) as exc:
                    self._send_error(client_socket, str(exc))
        finally:
            file_obj.close()
            self._handle_disconnect(client_socket)

    def _handle_message(self, client_socket: socket.socket, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "join":
            self._handle_join(client_socket, str(message.get("name", "")).strip() or "Player")
            return
        if message_type == "action":
            with self.lock:
                client = self.clients.get(client_socket)
                if client is None or client.player_id is None:
                    raise GameError("Join the room before sending actions.")
                result = self.game.apply_action(
                    client.player_id,
                    str(message["action"]),
                    dict(message.get("payload", {})),
                )
            self._broadcast_state(result.emitted_events)
            return
        raise GameError("Unknown network message.")

    def _handle_join(self, client_socket: socket.socket, name: str) -> None:
        with self.lock:
            client = self.clients[client_socket]
            if client.player_id is not None:
                raise GameError("You already joined this room.")
            player_id = self.game.add_player(name)
            client.player_id = player_id
            client.name = name
            _send_json(
                client_socket,
                {
                    "type": "joined",
                    "player_id": player_id,
                    "connection_hint": self.connection_hint(),
                },
            )
        self._broadcast_state([{"type": "join_game", "player_id": player_id, "name": name}])
        if self.game.phase == "active":
            self._broadcast_state([{"type": "start_game"}])

    def _handle_disconnect(self, client_socket: socket.socket) -> None:
        with self.lock:
            client = self.clients.pop(client_socket, None)
            if client and client.player_id:
                self.game.mark_disconnected(client.player_id)
                self._broadcast_state([{"type": "disconnect", "player_id": client.player_id}])
        try:
            client_socket.close()
        except OSError:
            pass

    def _broadcast_state(self, events: list[dict[str, Any]]) -> None:
        with self.lock:
            client_items = list(self.clients.items())
            payloads = [
                (
                    client_socket,
                    client.player_id,
                    {
                        "type": "state",
                        "state": self.game.player_view(client.player_id),
                        "events": list(events),
                    },
                )
                for client_socket, client in client_items
            ]
        stale: list[socket.socket] = []
        for client_socket, _, payload in payloads:
            try:
                _send_json(client_socket, payload)
            except OSError:
                stale.append(client_socket)
        for client_socket in stale:
            self._handle_disconnect(client_socket)

    def _send_error(self, client_socket: socket.socket, message: str) -> None:
        try:
            _send_json(client_socket, {"type": "error", "message": message})
        except OSError:
            self._handle_disconnect(client_socket)


class GameClient:
    """Background client connection for desktop UI or integration tests."""

    def __init__(self, on_message: Callable[[dict[str, Any]], None]) -> None:
        self.on_message = on_message
        self.socket: socket.socket | None = None
        self.read_thread: threading.Thread | None = None
        self.send_lock = threading.Lock()
        self.running = False

    def connect(self, host: str, port: int, name: str) -> None:
        self.socket = socket.create_connection((host, port), timeout=5.0)
        # The connect timeout is only for the initial handshake. The game
        # connection stays open indefinitely while waiting for turns/messages.
        self.socket.settimeout(None)
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
        self.send({"type": "join", "name": name})

    def send(self, payload: dict[str, Any]) -> None:
        if self.socket is None:
            raise RuntimeError("Client is not connected.")
        with self.send_lock:
            _send_json(self.socket, payload)

    def send_action(self, action: str, payload: dict[str, Any] | None = None) -> None:
        self.send({"type": "action", "action": action, "payload": payload or {}})

    def close(self) -> None:
        self.running = False
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass

    def _read_loop(self) -> None:
        assert self.socket is not None
        file_obj = self.socket.makefile("r", encoding="utf-8")
        try:
            while self.running:
                try:
                    line = file_obj.readline()
                except TimeoutError:
                    continue
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.on_message(message)
        finally:
            file_obj.close()
            self.running = False
            self.on_message({"type": "connection_closed"})


class GameDiscoveryClient:
    """Background LAN game discovery listener for the desktop UI."""

    def __init__(
        self,
        on_update: Callable[[list[dict[str, Any]]], None],
        discovery_port: int = DISCOVERY_PORT,
        bind_host: str = "",
        stale_after: float = DISCOVERY_STALE_AFTER_SECONDS,
        prune_interval: float = 0.25,
    ) -> None:
        self.on_update = on_update
        self.discovery_port = discovery_port
        self.bind_host = bind_host
        self.stale_after = stale_after
        self.prune_interval = prune_interval
        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.games: dict[tuple[str, int], DiscoveryGame] = {}
        self.lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        self.socket.bind((self.bind_host, self.discovery_port))
        self.socket.settimeout(self.prune_interval)
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.running = False
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass

    def _listen_loop(self) -> None:
        assert self.socket is not None
        while self.running:
            changed = False
            try:
                data, address = self.socket.recvfrom(4096)
            except socket.timeout:
                pass
            except OSError:
                break
            else:
                changed = self._handle_datagram(data, address)
            changed = self._prune_stale_games() or changed
            if changed:
                self._emit_snapshot()
        self._emit_snapshot()

    def _handle_datagram(self, data: bytes, address: tuple[str, int]) -> bool:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if payload.get("type") != "discovery":
            return False
        host = str(payload.get("host") or address[0])
        port = int(payload["port"])
        key = (host, port)
        game = DiscoveryGame(
            host_name=str(payload.get("host_name", "Host")),
            host=host,
            port=port,
            player_count=int(payload.get("player_count", 0)),
            joinable=bool(payload.get("joinable", False)),
            status=str(payload.get("status", "Waiting")),
            last_seen=time.time(),
        )
        with self.lock:
            previous = self.games.get(key)
            self.games[key] = game
        return previous != game

    def _prune_stale_games(self) -> bool:
        deadline = time.time() - self.stale_after
        removed = False
        with self.lock:
            stale_keys = [key for key, game in self.games.items() if game.last_seen < deadline]
            for key in stale_keys:
                self.games.pop(key, None)
                removed = True
        return removed

    def _emit_snapshot(self) -> None:
        with self.lock:
            snapshot = [game.to_dict() for game in self.games.values()]
        snapshot.sort(key=lambda game: (game["status"] != "Waiting", game["host_name"], game["host"], game["port"]))
        self.on_update(snapshot)
