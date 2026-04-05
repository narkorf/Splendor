from __future__ import annotations

import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path

from splendor_app.assets import load_asset_bytes, load_json_asset
from splendor_app.data import build_card_definitions, build_noble_definitions
from splendor_app.game_logic import GameError, SplendorGame
from splendor_app.model import CardDef, NobleDef, ReservedCard
from splendor_app.network import GameClient, GameDiscoveryClient, GameServer


def make_started_game(seed: int = 7) -> SplendorGame:
    game = SplendorGame(seed=seed)
    game.add_player("Alice")
    game.add_player("Bob")
    return game


class SplendorRulesTest(unittest.TestCase):
    def test_manifest_backed_card_definitions_match_expected_counts(self) -> None:
        cards = build_card_definitions()
        self.assertEqual(len(cards), 90)
        self.assertEqual(sum(1 for card in cards if card.tier == 1), 40)
        self.assertEqual(sum(1 for card in cards if card.tier == 2), 30)
        self.assertEqual(sum(1 for card in cards if card.tier == 3), 20)
        self.assertTrue(all(card.asset_id for card in cards))

    def test_manifest_backed_noble_definitions_match_expected_count(self) -> None:
        nobles = build_noble_definitions()
        self.assertEqual(len(nobles), 10)
        self.assertTrue(all(noble.asset_id for noble in nobles))
        self.assertTrue(all(noble.points == 3 for noble in nobles))

    def test_initial_setup_matches_two_player_layout(self) -> None:
        game = make_started_game()
        self.assertEqual(game.phase, "active")
        self.assertEqual(game.bank_tokens["gold"], 5)
        for color in ("white", "blue", "green", "red", "black"):
            self.assertEqual(game.bank_tokens[color], 4)
        self.assertEqual(len(game.nobles_remaining), 3)
        self.assertEqual(len(game.market[1]), 4)
        self.assertEqual(len(game.market[2]), 4)
        self.assertEqual(len(game.market[3]), 4)
        self.assertEqual(len(game.decks[1]), 36)
        self.assertEqual(len(game.decks[2]), 26)
        self.assertEqual(len(game.decks[3]), 16)

    def test_take_three_different_gems(self) -> None:
        game = make_started_game()
        game.apply_action("P1", "take_gems", {"colors": ["white", "blue", "green"]})
        player = game.players[0]
        self.assertEqual(player.tokens["white"], 1)
        self.assertEqual(player.tokens["blue"], 1)
        self.assertEqual(player.tokens["green"], 1)
        self.assertEqual(game.bank_tokens["white"], 3)
        self.assertEqual(game.phase, "awaiting_end_turn")
        self.assertEqual(game.active_player_id(), "P1")
        game.apply_action("P1", "end_turn", {})
        self.assertEqual(game.active_player_id(), "P2")

    def test_take_two_same_requires_four_in_bank_before_take(self) -> None:
        game = make_started_game()
        game.bank_tokens["white"] = 3
        with self.assertRaises(GameError):
            game.apply_action("P1", "take_gems", {"colors": ["white", "white"]})
        game.bank_tokens["white"] = 4
        game.apply_action("P1", "take_gems", {"colors": ["white", "white"]})
        self.assertEqual(game.players[0].tokens["white"], 2)
        self.assertEqual(game.bank_tokens["white"], 2)
        self.assertEqual(game.phase, "awaiting_end_turn")

    def test_reserving_face_up_card_moves_it_and_grants_gold_if_available(self) -> None:
        game = make_started_game()
        previous_market_ids = [card.id for card in game.market[1]]
        game.apply_action("P1", "reserve_card", {"tier": 1, "market_index": 0, "top_deck": False})
        player = game.players[0]
        self.assertEqual(len(player.reserved_cards), 1)
        self.assertEqual(player.tokens["gold"], 1)
        self.assertEqual(game.bank_tokens["gold"], 4)
        self.assertEqual(len(game.market[1]), 4)
        self.assertNotEqual(previous_market_ids, [card.id for card in game.market[1]])

    def test_buying_card_uses_bonuses_and_gold(self) -> None:
        game = make_started_game()
        card = CardDef(
            id="test-card",
            tier=1,
            cost={"white": 2, "blue": 2, "green": 1},
            bonus_color="red",
            points=1,
            placeholder_label="Test Card",
        )
        game.market[1] = [card]
        player = game.players[0]
        player.tokens.update({"white": 1, "blue": 2, "green": 0, "gold": 1, "red": 0, "black": 0})
        player.bonuses["white"] = 1
        game.apply_action("P1", "buy_face_up_card", {"tier": 1, "market_index": 0})
        self.assertEqual(player.score, 1)
        self.assertEqual(player.bonuses["red"], 1)
        self.assertEqual(len(player.purchased_cards), 1)
        self.assertEqual(player.tokens["gold"], 0)
        self.assertEqual(game.bank_tokens["gold"], 6)

    def test_out_of_turn_action_is_rejected(self) -> None:
        game = make_started_game()
        with self.assertRaises(GameError):
            game.apply_action("P2", "take_gems", {"colors": ["white", "blue", "green"]})

    def test_discard_flow_blocks_turn_finish_above_token_limit(self) -> None:
        game = make_started_game()
        player = game.players[0]
        player.tokens.update({"white": 2, "blue": 2, "green": 2, "red": 2, "black": 2, "gold": 0})
        game.apply_action("P1", "reserve_card", {"tier": 1, "market_index": 0, "top_deck": False})
        self.assertEqual(game.phase, "discard")
        self.assertEqual(game.pending_turn.discard_count, 1)
        self.assertEqual(game.active_player_id(), "P1")
        game.apply_action("P1", "discard_excess_tokens", {"tokens": {"gold": 1}})
        self.assertEqual(game.phase, "active")
        self.assertEqual(game.active_player_id(), "P2")

    def test_noble_claim_happens_at_end_of_turn(self) -> None:
        game = make_started_game()
        noble = NobleDef(
            id="test-noble",
            requirements={"white": 3, "blue": 3},
            points=3,
            placeholder_label="Test Noble",
        )
        game.nobles_remaining = [noble]
        player = game.players[0]
        player.bonuses["white"] = 3
        player.bonuses["blue"] = 3
        game.apply_action("P1", "take_gems", {"colors": ["white", "green", "red"]})
        self.assertEqual(len(player.claimed_nobles), 1)
        self.assertEqual(player.score, 3)
        self.assertEqual(game.phase, "awaiting_end_turn")
        game.apply_action("P1", "end_turn", {})
        self.assertEqual(game.active_player_id(), "P2")

    def test_cannot_end_turn_before_gem_action_completes(self) -> None:
        game = make_started_game()
        with self.assertRaises(GameError):
            game.apply_action("P1", "end_turn", {})

    def test_endgame_finishes_after_equal_turns_and_uses_tiebreaker(self) -> None:
        game = make_started_game()
        finishing_card = CardDef(
            id="finisher",
            tier=1,
            cost={"white": 1},
            bonus_color="green",
            points=1,
            placeholder_label="Finisher",
        )
        game.market[1] = [finishing_card]
        p1 = game.players[0]
        p2 = game.players[1]
        p1.score = 14
        p1.tokens["white"] = 1
        p1.purchased_cards = [
            CardDef("a", 1, {}, "white", 0, "A"),
            CardDef("b", 1, {}, "blue", 0, "B"),
        ]
        p2.score = 15
        p2.purchased_cards = [CardDef("c", 1, {}, "red", 0, "C")]
        game.apply_action("P1", "buy_face_up_card", {"tier": 1, "market_index": 0})
        self.assertTrue(game.endgame_triggered)
        self.assertEqual(game.endgame_target_turns, 1)
        self.assertEqual(game.phase, "active")
        game.apply_action("P2", "take_gems", {"colors": ["white", "blue", "green"]})
        self.assertEqual(game.phase, "awaiting_end_turn")
        game.apply_action("P2", "end_turn", {})
        self.assertEqual(game.phase, "game_over")
        self.assertEqual(game.winner_state.winner_ids, ["P2"])

    def test_opponent_view_hides_all_reserved_card_details(self) -> None:
        game = make_started_game()
        top_deck_reserved = ReservedCard(
            card=CardDef(
                id="masked-top-deck-card",
                tier=2,
                cost={"white": 1},
                bonus_color="blue",
                points=1,
                placeholder_label="Masked Top Deck Card",
                asset_id="masked_top_deck_card",
            ),
            is_top_deck_reservation=True,
        )
        face_up_reserved = ReservedCard(
            card=CardDef(
                id="masked-face-up-card",
                tier=1,
                cost={"green": 2},
                bonus_color="red",
                points=0,
                placeholder_label="Masked Face Up Card",
                asset_id="masked_face_up_card",
            ),
            is_top_deck_reservation=False,
        )
        game.players[0].reserved_cards.extend([top_deck_reserved, face_up_reserved])

        owner_view = game.player_view("P1")
        opponent_view = game.player_view("P2")

        self.assertEqual(owner_view["players"][0]["reserved_cards"][0]["asset_id"], "masked_top_deck_card")
        self.assertEqual(owner_view["players"][0]["reserved_cards"][1]["asset_id"], "masked_face_up_card")

        top_deck_opponent_card = opponent_view["players"][0]["reserved_cards"][0]
        face_up_opponent_card = opponent_view["players"][0]["reserved_cards"][1]

        self.assertIsNone(top_deck_opponent_card["asset_id"])
        self.assertIsNone(top_deck_opponent_card["card_back_asset_id"])
        self.assertTrue(top_deck_opponent_card["masked"])
        self.assertEqual(top_deck_opponent_card["placeholder_label"], "Hidden")
        self.assertIsNone(top_deck_opponent_card["tier"])
        self.assertEqual(top_deck_opponent_card["cost"], {})
        self.assertEqual(top_deck_opponent_card["bonus_color"], "hidden")

        self.assertIsNone(face_up_opponent_card["asset_id"])
        self.assertIsNone(face_up_opponent_card["card_back_asset_id"])
        self.assertTrue(face_up_opponent_card["masked"])
        self.assertEqual(face_up_opponent_card["placeholder_label"], "Hidden")
        self.assertIsNone(face_up_opponent_card["tier"])
        self.assertEqual(face_up_opponent_card["cost"], {})
        self.assertEqual(face_up_opponent_card["bonus_color"], "hidden")


class NetworkSyncTest(unittest.TestCase):
    def test_client_connection_switches_to_blocking_mode_after_connect(self) -> None:
        server = GameServer(port=0, seed=3)
        server.start()
        collector = queue.Queue()
        client = GameClient(collector.put)
        try:
            client.connect("127.0.0.1", server.port, "Host")
            self.assertIsNotNone(client.socket)
            assert client.socket is not None
            self.assertIsNone(client.socket.gettimeout())
        finally:
            client.close()
            server.stop()

    def test_host_join_and_state_sync(self) -> None:
        server = GameServer(port=0, seed=5)
        server.start()
        collector_one = queue.Queue()
        collector_two = queue.Queue()
        client_one = GameClient(collector_one.put)
        client_two = GameClient(collector_two.put)
        try:
            client_one.connect("127.0.0.1", server.port, "Host")
            client_two.connect("127.0.0.1", server.port, "Guest")
            state_one = self._wait_for_state(collector_one, lambda state: state["phase"] == "active")
            state_two = self._wait_for_state(collector_two, lambda state: state["phase"] == "active")
            self.assertEqual(state_one["active_player"], state_two["active_player"])
            active_player = state_one["active_player"]
            actor = client_one if active_player == "P1" else client_two
            actor.send_action("take_gems", {"colors": ["white", "blue", "green"]})
            synced_one = self._wait_for_state(collector_one, lambda state: state["players"][0]["tokens"]["white"] == 1)
            synced_two = self._wait_for_state(collector_two, lambda state: state["players"][0]["tokens"]["white"] == 1)
            self.assertEqual(synced_one["bank_tokens"], synced_two["bank_tokens"])
            self.assertEqual(synced_one["players"][0]["tokens"], synced_two["players"][0]["tokens"])
            self.assertEqual(synced_one["phase"], "awaiting_end_turn")
            actor.send_action("end_turn", {})
            ended_one = self._wait_for_state(collector_one, lambda state: state["active_player"] != active_player)
            ended_two = self._wait_for_state(collector_two, lambda state: state["active_player"] != active_player)
            self.assertEqual(ended_one["active_player"], ended_two["active_player"])
        finally:
            client_one.close()
            client_two.close()
            server.stop()

    def _wait_for_state(self, collector: queue.Queue, predicate, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        latest_state = None
        while time.time() < deadline:
            remaining = max(0.01, deadline - time.time())
            try:
                message = collector.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("type") == "state":
                latest_state = message["state"]
                if predicate(latest_state):
                    return latest_state
        raise AssertionError(f"Timed out waiting for state. Latest: {latest_state}")


class NetworkDiscoveryTest(unittest.TestCase):
    def test_discovery_lists_waiting_and_full_games(self) -> None:
        discovery_port = 34971
        discovered = queue.Queue()
        listener = GameDiscoveryClient(
            discovered.put,
            discovery_port=discovery_port,
            bind_host="127.0.0.1",
            stale_after=0.5,
            prune_interval=0.05,
        )
        server = GameServer(
            host="127.0.0.1",
            port=0,
            seed=9,
            advertised_name="Host",
            discovery_port=discovery_port,
            discovery_target="127.0.0.1",
            discovery_interval=0.05,
        )
        listener.start()
        server.start()
        host_client = GameClient(lambda _: None)
        guest_client = GameClient(lambda _: None)
        try:
            host_client.connect("127.0.0.1", server.port, "Host")
            waiting_game = self._wait_for_games(
                discovered,
                lambda games: games and games[0]["status"] == "Waiting" and games[0]["player_count"] == 1,
            )
            self.assertEqual(waiting_game[0]["host_name"], "Host")
            self.assertEqual(waiting_game[0]["player_count"], 1)
            self.assertTrue(waiting_game[0]["joinable"])

            guest_client.connect("127.0.0.1", server.port, "Guest")
            full_game = self._wait_for_games(discovered, lambda games: games and games[0]["status"] == "Full")
            self.assertEqual(full_game[0]["player_count"], 2)
            self.assertFalse(full_game[0]["joinable"])
        finally:
            host_client.close()
            guest_client.close()
            listener.close()
            server.stop()

    def test_discovery_entries_expire_after_host_stops(self) -> None:
        discovery_port = 34972
        discovered = queue.Queue()
        listener = GameDiscoveryClient(
            discovered.put,
            discovery_port=discovery_port,
            bind_host="127.0.0.1",
            stale_after=0.2,
            prune_interval=0.05,
        )
        server = GameServer(
            host="127.0.0.1",
            port=0,
            seed=11,
            advertised_name="Host",
            discovery_port=discovery_port,
            discovery_target="127.0.0.1",
            discovery_interval=0.05,
        )
        listener.start()
        server.start()
        host_client = GameClient(lambda _: None)
        try:
            host_client.connect("127.0.0.1", server.port, "Host")
            self._wait_for_games(discovered, lambda games: len(games) == 1)
            server.stop()
            host_client.close()
            empty_snapshot = self._wait_for_games(discovered, lambda games: games == [])
            self.assertEqual(empty_snapshot, [])
        finally:
            listener.close()
            server.stop()
            host_client.close()

    def _wait_for_games(self, collector: queue.Queue, predicate, timeout: float = 5.0) -> list[dict]:
        deadline = time.time() + timeout
        latest_games: list[dict] = []
        while time.time() < deadline:
            remaining = max(0.01, deadline - time.time())
            try:
                latest_games = collector.get(timeout=remaining)
            except queue.Empty:
                continue
            if predicate(latest_games):
                return latest_games
        raise AssertionError(f"Timed out waiting for discovery update. Latest: {latest_games}")


class AssetHelperTest(unittest.TestCase):
    def test_missing_asset_returns_none(self) -> None:
        self.assertIsNone(load_asset_bytes("cards", "missing.png"))

    def test_frozen_build_asset_lookup_uses_meipass(self) -> None:
        original_frozen = getattr(sys, "frozen", None)
        original_meipass = getattr(sys, "_MEIPASS", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_root = Path(temp_dir) / "splendor_app" / "assets" / "manifests"
            asset_root.mkdir(parents=True)
            (asset_root / "sample.json").write_text('{"ok": true}', encoding="utf-8")
            sys.frozen = True
            sys._MEIPASS = temp_dir
            try:
                self.assertEqual(load_json_asset("manifests", "sample.json"), {"ok": True})
            finally:
                if original_frozen is None:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = original_frozen
                if original_meipass is None:
                    delattr(sys, "_MEIPASS")
                else:
                    sys._MEIPASS = original_meipass


if __name__ == "__main__":
    unittest.main()
