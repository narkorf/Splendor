"""Authoritative Splendor game logic."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .constants import (
    ALL_TOKEN_COLORS,
    MARKET_SIZE,
    MAX_RESERVED_CARDS,
    NOBLES_BY_PLAYER_COUNT,
    PLAYER_COUNT,
    TOKEN_LIMIT,
    TOKENS_BY_PLAYER_COUNT,
    TOKEN_COLORS,
    TIER_LEVELS,
    WINNING_SCORE,
)
from .data import build_card_definitions, build_noble_definitions
from .model import CardDef, NobleDef, PendingTurnState, PlayerState, ReservedCard, WinnerState


class GameError(Exception):
    """Raised for illegal game actions."""


@dataclass(slots=True)
class ActionResult:
    message: str
    emitted_events: list[dict[str, Any]]


class SplendorGame:
    """Core state machine for a 2-player Splendor match."""

    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed)
        self.card_defs = build_card_definitions()
        self.noble_defs = build_noble_definitions()
        self.players: list[PlayerState] = []
        self.player_index: dict[str, int] = {}
        self.bank_tokens = TOKENS_BY_PLAYER_COUNT[PLAYER_COUNT].copy()
        self.market: dict[int, list[CardDef]] = {tier: [] for tier in TIER_LEVELS}
        self.decks: dict[int, list[CardDef]] = {tier: [] for tier in TIER_LEVELS}
        self.nobles_remaining: list[NobleDef] = []
        self.active_player_index = 0
        self.phase = "lobby"
        self.pending_turn = PendingTurnState()
        self.endgame_triggered = False
        self.endgame_target_turns: int | None = None
        self.winner_state: WinnerState | None = None
        self.message = "Waiting for players."
        self._prepare_decks()

    def _prepare_decks(self) -> None:
        cards_by_tier: dict[int, list[CardDef]] = {tier: [] for tier in TIER_LEVELS}
        for card in self.card_defs:
            cards_by_tier[card.tier].append(card)
        for tier in TIER_LEVELS:
            deck = list(cards_by_tier[tier])
            self.random.shuffle(deck)
            self.decks[tier] = deck

    def _player(self, player_id: str) -> PlayerState:
        return self.players[self.player_index[player_id]]

    def add_player(self, name: str) -> str:
        if len(self.players) >= PLAYER_COUNT:
            raise GameError("The room is already full.")
        player_id = f"P{len(self.players) + 1}"
        player = PlayerState(id=player_id, name=name.strip() or player_id)
        self.player_index[player_id] = len(self.players)
        self.players.append(player)
        self.message = f"{player.name} joined the room."
        if len(self.players) == PLAYER_COUNT:
            self.start_game()
        return player_id

    def rename_player(self, player_id: str, name: str) -> None:
        player = self._player(player_id)
        player.name = name.strip() or player.id

    def mark_disconnected(self, player_id: str) -> None:
        if player_id in self.player_index:
            player = self._player(player_id)
            player.connected = False
            self.message = f"{player.name} disconnected."

    def mark_connected(self, player_id: str) -> None:
        if player_id in self.player_index:
            player = self._player(player_id)
            player.connected = True
            self.message = f"{player.name} connected."

    def start_game(self) -> None:
        if len(self.players) != PLAYER_COUNT:
            raise GameError("Need exactly two players to start.")
        if self.phase != "lobby":
            raise GameError("Game already started.")
        noble_pool = list(self.noble_defs)
        self.random.shuffle(noble_pool)
        self.nobles_remaining = noble_pool[: NOBLES_BY_PLAYER_COUNT[PLAYER_COUNT]]
        for tier in TIER_LEVELS:
            while len(self.market[tier]) < MARKET_SIZE and self.decks[tier]:
                self.market[tier].append(self.decks[tier].pop())
        self.phase = "active"
        self.active_player_index = 0
        self.message = f"{self.players[0].name} starts the game."

    def active_player_id(self) -> str | None:
        if not self.players:
            return None
        return self.players[self.active_player_index].id

    def apply_action(self, player_id: str, action: str, payload: dict[str, Any]) -> ActionResult:
        if self.phase == "game_over":
            raise GameError("The match is already finished.")
        if player_id not in self.player_index:
            raise GameError("Unknown player.")
        if len(self.players) < PLAYER_COUNT:
            raise GameError("Waiting for the second player.")
        if self.phase in {"active", "discard", "choose_noble", "awaiting_end_turn"} and player_id != self.active_player_id():
            raise GameError("It is not your turn.")

        emitted_events: list[dict[str, Any]] = []
        if action == "take_gems":
            self._require_phase("active")
            colors = payload.get("colors", [])
            self._take_gems(player_id, colors)
            self.pending_turn.manual_end_turn = True
            emitted_events.append({"type": "take_gems", "player_id": player_id, "colors": list(colors)})
            self._post_action_resolution(emitted_events)
        elif action == "reserve_card":
            self._require_phase("active")
            self._reserve_card(player_id, payload)
            emitted_events.append({"type": "reserve_card", "player_id": player_id, "payload": dict(payload)})
            self._post_action_resolution(emitted_events)
        elif action == "buy_face_up_card":
            self._require_phase("active")
            self._buy_face_up(player_id, int(payload["tier"]), int(payload["market_index"]))
            emitted_events.append({"type": "buy_face_up_card", "player_id": player_id, "payload": dict(payload)})
            self._post_action_resolution(emitted_events)
        elif action == "buy_reserved_card":
            self._require_phase("active")
            self._buy_reserved(player_id, int(payload["reserved_index"]))
            emitted_events.append({"type": "buy_reserved_card", "player_id": player_id, "payload": dict(payload)})
            self._post_action_resolution(emitted_events)
        elif action == "discard_excess_tokens":
            self._require_phase("discard")
            self._discard_tokens(player_id, payload.get("tokens", {}))
            emitted_events.append({"type": "discard_excess_tokens", "player_id": player_id, "payload": dict(payload)})
            self._post_discard_resolution(emitted_events)
        elif action == "choose_noble":
            self._require_phase("choose_noble")
            noble_id = payload.get("noble_id", "")
            self._claim_noble(player_id, noble_id)
            emitted_events.append({"type": "auto_claim_noble", "player_id": player_id, "noble_id": noble_id})
            if self.pending_turn.manual_end_turn:
                self._await_end_turn()
            else:
                self._finish_turn(emitted_events)
        elif action == "end_turn":
            self._require_phase("awaiting_end_turn")
            if not self.pending_turn.can_end_turn:
                raise GameError("You cannot end the turn yet.")
            self._finish_turn(emitted_events)
        else:
            raise GameError(f"Unknown action: {action}")
        return ActionResult(message=self.message, emitted_events=emitted_events)

    def _require_phase(self, expected: str) -> None:
        if self.phase != expected:
            raise GameError(f"This action is only valid during {expected}.")

    def _take_gems(self, player_id: str, colors: list[str]) -> None:
        player = self._player(player_id)
        if not colors:
            raise GameError("Select gems before confirming.")
        if any(color not in TOKEN_COLORS for color in colors):
            raise GameError("Only colored gem tokens can be taken.")
        unique_colors = set(colors)
        if len(colors) == 3 and len(unique_colors) == 3:
            for color in colors:
                if self.bank_tokens[color] < 1:
                    raise GameError(f"There are no {color} tokens left in the bank.")
            for color in colors:
                self.bank_tokens[color] -= 1
                player.tokens[color] += 1
            self.message = f"{player.name} took three different gems."
            return
        if len(colors) == 2 and len(unique_colors) == 1:
            color = colors[0]
            if self.bank_tokens[color] < 4:
                raise GameError("You can only take two of one color if the bank had at least four before taking.")
            self.bank_tokens[color] -= 2
            player.tokens[color] += 2
            self.message = f"{player.name} took two {color} gems."
            return
        raise GameError("Take exactly three different gems or two of the same color.")

    def _reserve_card(self, player_id: str, payload: dict[str, Any]) -> None:
        player = self._player(player_id)
        if len(player.reserved_cards) >= MAX_RESERVED_CARDS:
            raise GameError("You cannot reserve more than three cards.")
        tier = int(payload["tier"])
        top_deck = bool(payload.get("top_deck", False))
        if tier not in TIER_LEVELS:
            raise GameError("Invalid tier.")
        reserved: ReservedCard
        if top_deck:
            if not self.decks[tier]:
                raise GameError("That deck is empty.")
            reserved = ReservedCard(card=self.decks[tier].pop(), is_top_deck_reservation=True)
            self.message = f"{player.name} reserved a top-deck tier {tier} card."
        else:
            market_index = int(payload["market_index"])
            if market_index < 0 or market_index >= len(self.market[tier]):
                raise GameError("No face-up card exists in that slot.")
            card = self.market[tier].pop(market_index)
            reserved = ReservedCard(card=card, is_top_deck_reservation=False)
            self._refill_market_slot(tier)
            self.message = f"{player.name} reserved a face-up tier {tier} card."
        player.reserved_cards.append(reserved)
        if self.bank_tokens["gold"] > 0:
            self.bank_tokens["gold"] -= 1
            player.tokens["gold"] += 1
            self.message += " They also took a gold token."

    def _buy_face_up(self, player_id: str, tier: int, market_index: int) -> None:
        if tier not in TIER_LEVELS:
            raise GameError("Invalid tier.")
        if market_index < 0 or market_index >= len(self.market[tier]):
            raise GameError("No card exists in that market slot.")
        player = self._player(player_id)
        card = self.market[tier][market_index]
        spend = self._spend_plan(player, card)
        self.market[tier].pop(market_index)
        self._complete_purchase(player, card, spend)
        self._refill_market_slot(tier)
        self.message = f"{player.name} bought {card.placeholder_label}."

    def _buy_reserved(self, player_id: str, reserved_index: int) -> None:
        player = self._player(player_id)
        if reserved_index < 0 or reserved_index >= len(player.reserved_cards):
            raise GameError("No reserved card exists in that slot.")
        reserved = player.reserved_cards[reserved_index]
        spend = self._spend_plan(player, reserved.card)
        player.reserved_cards.pop(reserved_index)
        self._complete_purchase(player, reserved.card, spend)
        self.message = f"{player.name} bought a reserved card."

    def _spend_plan(self, player: PlayerState, card: CardDef) -> dict[str, int]:
        spend = {color: 0 for color in ALL_TOKEN_COLORS}
        gold_needed = 0
        for color in TOKEN_COLORS:
            discounted_cost = max(0, card.cost.get(color, 0) - player.bonuses[color])
            colored_spend = min(player.tokens[color], discounted_cost)
            spend[color] = colored_spend
            gold_needed += discounted_cost - colored_spend
        if gold_needed > player.tokens["gold"]:
            raise GameError("You cannot afford that card.")
        spend["gold"] = gold_needed
        return spend

    def _complete_purchase(self, player: PlayerState, card: CardDef, spend: dict[str, int]) -> None:
        for color, amount in spend.items():
            if amount:
                player.tokens[color] -= amount
                self.bank_tokens[color] += amount
        player.purchased_cards.append(card)
        player.bonuses[card.bonus_color] += 1
        player.score += card.points

    def _discard_tokens(self, player_id: str, tokens: dict[str, int]) -> None:
        player = self._player(player_id)
        if not tokens:
            raise GameError("Select tokens to discard.")
        discard_total = sum(int(value) for value in tokens.values())
        if discard_total != self.pending_turn.discard_count:
            raise GameError(f"You must discard exactly {self.pending_turn.discard_count} token(s).")
        for color, raw_amount in tokens.items():
            amount = int(raw_amount)
            if color not in ALL_TOKEN_COLORS or amount < 0:
                raise GameError("Invalid discard selection.")
            if player.tokens[color] < amount:
                raise GameError(f"You do not have enough {color} tokens to discard.")
        for color, raw_amount in tokens.items():
            amount = int(raw_amount)
            if amount:
                player.tokens[color] -= amount
                self.bank_tokens[color] += amount
        self.pending_turn.discard_count = 0
        self.message = f"{player.name} discarded down to the token limit."

    def _post_action_resolution(self, emitted_events: list[dict[str, Any]]) -> None:
        active = self.players[self.active_player_index]
        overflow = active.total_tokens() - TOKEN_LIMIT
        if overflow > 0:
            self.phase = "discard"
            self.pending_turn.discard_count = overflow
            self.pending_turn.can_end_turn = False
            self.pending_turn.eligible_nobles = []
            self.message += f" Discard {overflow} token(s) to end the turn."
            return
        self._resolve_nobles_or_progress(emitted_events)

    def _post_discard_resolution(self, emitted_events: list[dict[str, Any]]) -> None:
        if self.players[self.active_player_index].total_tokens() > TOKEN_LIMIT:
            remaining = self.players[self.active_player_index].total_tokens() - TOKEN_LIMIT
            self.pending_turn.discard_count = remaining
            self.pending_turn.can_end_turn = False
            self.message += f" Discard {remaining} more token(s)."
            return
        self._resolve_nobles_or_progress(emitted_events)

    def _resolve_nobles_or_progress(self, emitted_events: list[dict[str, Any]]) -> None:
        player = self.players[self.active_player_index]
        eligible = [
            noble.id
            for noble in self.nobles_remaining
            if all(player.bonuses[color] >= required for color, required in noble.requirements.items())
        ]
        self.pending_turn.eligible_nobles = eligible
        if not eligible:
            self.pending_turn.discard_count = 0
            if self.pending_turn.manual_end_turn:
                self._await_end_turn()
            else:
                self._finish_turn(emitted_events)
            return
        if len(eligible) == 1:
            self._claim_noble(player.id, eligible[0])
            emitted_events.append({"type": "auto_claim_noble", "player_id": player.id, "noble_id": eligible[0]})
            if self.pending_turn.manual_end_turn:
                self._await_end_turn()
            else:
                self._finish_turn(emitted_events)
            return
        self.phase = "choose_noble"
        self.pending_turn.discard_count = 0
        self.pending_turn.can_end_turn = False
        self.message += " Choose one eligible noble."

    def _await_end_turn(self) -> None:
        self.phase = "awaiting_end_turn"
        self.pending_turn.discard_count = 0
        self.pending_turn.eligible_nobles = []
        self.pending_turn.can_end_turn = True
        self.message += " Click End Turn to pass play."

    def _claim_noble(self, player_id: str, noble_id: str) -> None:
        player = self._player(player_id)
        if noble_id not in self.pending_turn.eligible_nobles:
            raise GameError("That noble is not available to claim.")
        for index, noble in enumerate(self.nobles_remaining):
            if noble.id == noble_id:
                claimed = self.nobles_remaining.pop(index)
                player.claimed_nobles.append(claimed)
                player.score += claimed.points
                self.message = f"{player.name} claimed {claimed.placeholder_label}."
                self.pending_turn.eligible_nobles = []
                return
        raise GameError("That noble is no longer available.")

    def _finish_turn(self, emitted_events: list[dict[str, Any]]) -> None:
        current = self.players[self.active_player_index]
        current.turns_taken += 1
        if not self.endgame_triggered and current.score >= WINNING_SCORE:
            self.endgame_triggered = True
            self.endgame_target_turns = current.turns_taken
            self.message += " Final round triggered."
        if self.endgame_triggered and self.endgame_target_turns is not None:
            if all(player.turns_taken >= self.endgame_target_turns for player in self.players):
                self._set_winner()
                emitted_events.append({"type": "end_turn", "player_id": current.id})
                return
        self.active_player_index = (self.active_player_index + 1) % len(self.players)
        self.phase = "active"
        self.pending_turn = PendingTurnState()
        self.message += f" {self.players[self.active_player_index].name}'s turn."
        emitted_events.append({"type": "end_turn", "player_id": current.id})

    def _set_winner(self) -> None:
        best_score = max(player.score for player in self.players)
        score_leaders = [player for player in self.players if player.score == best_score]
        fewest_cards = min(player.purchased_card_count() for player in score_leaders)
        winners = [player.id for player in score_leaders if player.purchased_card_count() == fewest_cards]
        self.phase = "game_over"
        if len(winners) == 1:
            winner_name = self._player(winners[0]).name
            self.message = f"{winner_name} wins with {best_score} points."
            reason = "highest score, then fewest purchased development cards"
        else:
            winner_names = ", ".join(self._player(player_id).name for player_id in winners)
            self.message = f"Tie between {winner_names} after applying the tiebreak."
            reason = "shared win after score and purchased-card tiebreaker"
        self.winner_state = WinnerState(winner_ids=winners, reason=reason)

    def _refill_market_slot(self, tier: int) -> None:
        if self.decks[tier]:
            self.market[tier].append(self.decks[tier].pop())

    def player_view(self, viewer_id: str | None = None) -> dict[str, Any]:
        players_payload: list[dict[str, Any]] = []
        nobles_claimed: dict[str, list[dict[str, Any]]] = {}
        connected_players = []
        for player in self.players:
            connected_players.append(
                {"id": player.id, "name": player.name, "connected": player.connected}
            )
            nobles_claimed[player.id] = [noble.to_dict() for noble in player.claimed_nobles]
            reserved_cards = [
                reserved.to_dict(masked=viewer_id != player.id)
                for reserved in player.reserved_cards
            ]
            players_payload.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "tokens": dict(player.tokens),
                    "purchased_cards": [card.to_dict() for card in player.purchased_cards],
                    "bonuses": dict(player.bonuses),
                    "reserved_cards": reserved_cards,
                    "score": player.score,
                    "claimed_nobles": [noble.to_dict() for noble in player.claimed_nobles],
                    "purchased_card_count": player.purchased_card_count(),
                    "connected": player.connected,
                }
            )
        return {
            "connected_players": connected_players,
            "active_player": self.active_player_id(),
            "bank_tokens": dict(self.bank_tokens),
            "market": {str(tier): [card.to_dict() for card in self.market[tier]] for tier in TIER_LEVELS},
            "deck_counts": {str(tier): len(self.decks[tier]) for tier in TIER_LEVELS},
            "players": players_payload,
            "nobles_remaining": [noble.to_dict() for noble in self.nobles_remaining],
            "nobles_claimed": nobles_claimed,
            "endgame_triggered": self.endgame_triggered,
            "winner_state": self.winner_state.to_dict() if self.winner_state else None,
            "phase": self.phase,
            "pending_turn": self.pending_turn.to_dict(),
            "message": self.message,
        }
