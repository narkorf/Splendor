from __future__ import annotations

import asyncio
import unittest

from splendor_web.rooms import RoomManager, RoomServiceError

try:
    from fastapi.testclient import TestClient
    from splendor_web.app import create_app

    FASTAPI_TESTING_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_TESTING_AVAILABLE = False


class StubWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.closed = False

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)

    async def close(self) -> None:
        self.closed = True


class RoomManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_join_and_reconnect_flow(self) -> None:
        manager = RoomManager(cleanup_interval_seconds=3600)
        room, host_seat = await manager.create_room("Alice")
        _, guest_seat = await manager.join_room(room.room_code, "Bob")

        host_socket = StubWebSocket()
        guest_socket = StubWebSocket()
        await manager.connect_player(room.room_code, host_seat.player_token, host_socket)
        await manager.connect_player(room.room_code, guest_seat.player_token, guest_socket)

        await manager.emit_presence(room)
        await manager.emit_state(room, [])
        self.assertTrue(host_socket.messages)
        self.assertTrue(guest_socket.messages)
        self.assertTrue(all(player["connected"] for player in room.connected_players()))

        await manager.disconnect_player(room.room_code, guest_seat.player_token, guest_socket)
        self.assertFalse(room.game.players[1].connected)

        reconnect_socket = StubWebSocket()
        await manager.connect_player(room.room_code, guest_seat.player_token, reconnect_socket)
        self.assertTrue(room.game.players[1].connected)

    async def test_rejects_invalid_token_and_full_room(self) -> None:
        manager = RoomManager(cleanup_interval_seconds=3600)
        room, _ = await manager.create_room("Alice")
        await manager.join_room(room.room_code, "Bob")

        with self.assertRaises(RoomServiceError) as full_error:
            await manager.join_room(room.room_code, "Charlie")
        self.assertEqual(full_error.exception.code, "room_full")

        with self.assertRaises(RoomServiceError) as token_error:
            await manager.snapshot(room.room_code, "bad-token")
        self.assertEqual(token_error.exception.code, "invalid_player_token")

    async def test_apply_action_and_invalid_action_error(self) -> None:
        manager = RoomManager(cleanup_interval_seconds=3600)
        room, host_seat = await manager.create_room("Alice")
        _, guest_seat = await manager.join_room(room.room_code, "Bob")
        host_socket = StubWebSocket()
        guest_socket = StubWebSocket()
        await manager.connect_player(room.room_code, host_seat.player_token, host_socket)
        await manager.connect_player(room.room_code, guest_seat.player_token, guest_socket)

        room, events = await manager.apply_action(
            room.room_code,
            host_seat.player_token,
            "take_gems",
            {"colors": ["white", "blue", "green"]},
        )
        self.assertEqual(events[0]["type"], "take_gems")
        self.assertEqual(room.game.phase, "awaiting_end_turn")

        with self.assertRaises(RoomServiceError) as invalid_action:
            await manager.apply_action(room.room_code, guest_seat.player_token, "end_turn", {})
        self.assertEqual(invalid_action.exception.code, "illegal_action")

    async def test_room_expiry_closes_connected_sockets(self) -> None:
        manager = RoomManager(
            active_room_ttl_seconds=1,
            empty_room_ttl_seconds=1,
            cleanup_interval_seconds=3600,
        )
        room, host_seat = await manager.create_room("Alice")
        host_socket = StubWebSocket()
        await manager.connect_player(room.room_code, host_seat.player_token, host_socket)

        room.last_activity_at -= 5
        await manager.close_expired_rooms()

        self.assertNotIn(room.room_code, manager.rooms)
        self.assertTrue(host_socket.closed)
        self.assertEqual(host_socket.messages[-1]["type"], "room_closed")


@unittest.skipUnless(FASTAPI_TESTING_AVAILABLE, "FastAPI test dependencies are not installed.")
class WebApiTest(unittest.TestCase):
    def test_asset_routes_serve_shared_desktop_assets(self) -> None:
        client = TestClient(create_app())

        response = client.get("/assets/gems/diamond.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")

    def test_create_join_and_play_round_trip(self) -> None:
        client = TestClient(create_app())

        create_response = client.post("/api/rooms", json={"name": "Alice"})
        self.assertEqual(create_response.status_code, 200)
        joined_payload = create_response.json()
        room_code = joined_payload["room_code"]
        host_token = joined_payload["player_token"]

        join_response = client.post(f"/api/rooms/{room_code}/join", json={"name": "Bob"})
        self.assertEqual(join_response.status_code, 200)
        guest_token = join_response.json()["player_token"]

        room_response = client.get(f"/api/rooms/{room_code}", params={"player_token": host_token})
        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.json()["player_id"], "P1")

        with client.websocket_connect(f"/ws/rooms/{room_code}?player_token={host_token}") as host_ws:
            with client.websocket_connect(f"/ws/rooms/{room_code}?player_token={guest_token}") as guest_ws:
                host_joined = host_ws.receive_json()
                guest_joined = guest_ws.receive_json()
                self.assertEqual(host_joined["type"], "joined")
                self.assertEqual(guest_joined["type"], "joined")

                host_ws.receive_json()
                host_state = host_ws.receive_json()
                guest_ws.receive_json()
                guest_state = guest_ws.receive_json()
                self.assertEqual(host_state["type"], "state")
                self.assertEqual(guest_state["type"], "state")

                host_ws.send_json(
                    {
                        "type": "action",
                        "action": "take_gems",
                        "payload": {"colors": ["white", "blue", "green"]},
                    }
                )
                updated_state = self._wait_for_state(host_ws, lambda payload: payload["state"]["phase"] == "awaiting_end_turn")
                self.assertEqual(updated_state["state"]["phase"], "awaiting_end_turn")

    def test_invalid_room_code_and_invalid_token(self) -> None:
        client = TestClient(create_app())

        missing = client.post("/api/rooms/NOPE12/join", json={"name": "Bob"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "room_not_found")

        create_response = client.post("/api/rooms", json={"name": "Alice"})
        room_code = create_response.json()["room_code"]
        room_response = client.get(f"/api/rooms/{room_code}", params={"player_token": "bad-token"})
        self.assertEqual(room_response.status_code, 401)
        self.assertEqual(room_response.json()["detail"]["code"], "invalid_player_token")

    @staticmethod
    def _wait_for_state(websocket, predicate) -> dict:
        for _ in range(10):
            message = websocket.receive_json()
            if message.get("type") == "state" and predicate(message):
                return message
        raise AssertionError("Timed out waiting for websocket state.")


if __name__ == "__main__":
    unittest.main()
