"""Serializable data models for cards, players, and game state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .constants import ALL_TOKEN_COLORS, TOKEN_COLORS


def empty_token_counts() -> dict[str, int]:
    return {color: 0 for color in ALL_TOKEN_COLORS}


def empty_bonus_counts() -> dict[str, int]:
    return {color: 0 for color in TOKEN_COLORS}


@dataclass(slots=True)
class CardDef:
    id: str
    tier: int
    cost: dict[str, int]
    bonus_color: str
    points: int
    placeholder_label: str
    asset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CardDef":
        return cls(**payload)


@dataclass(slots=True)
class ReservedCard:
    card: CardDef
    is_top_deck_reservation: bool = False

    def to_dict(self, masked: bool = False) -> dict[str, Any]:
        if masked:
            return {
                "id": "hidden-reserved-card",
                "tier": None,
                "cost": {},
                "bonus_color": "hidden",
                "points": 0,
                "placeholder_label": "Hidden",
                "asset_id": None,
                "card_back_asset_id": None,
                "masked": True,
                "is_top_deck_reservation": False,
            }
        payload = self.card.to_dict()
        payload["masked"] = False
        payload["is_top_deck_reservation"] = self.is_top_deck_reservation
        return payload


@dataclass(slots=True)
class NobleDef:
    id: str
    requirements: dict[str, int]
    points: int
    placeholder_label: str
    asset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NobleDef":
        return cls(**payload)


@dataclass(slots=True)
class PlayerState:
    id: str
    name: str
    tokens: dict[str, int] = field(default_factory=empty_token_counts)
    bonuses: dict[str, int] = field(default_factory=empty_bonus_counts)
    purchased_cards: list[CardDef] = field(default_factory=list)
    reserved_cards: list[ReservedCard] = field(default_factory=list)
    claimed_nobles: list[NobleDef] = field(default_factory=list)
    score: int = 0
    turns_taken: int = 0
    connected: bool = True

    def total_tokens(self) -> int:
        return sum(self.tokens.values())

    def purchased_card_count(self) -> int:
        return len(self.purchased_cards)


@dataclass(slots=True)
class PendingTurnState:
    discard_count: int = 0
    eligible_nobles: list[str] = field(default_factory=list)
    manual_end_turn: bool = False
    can_end_turn: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "discard_count": self.discard_count,
            "eligible_nobles": list(self.eligible_nobles),
            "manual_end_turn": self.manual_end_turn,
            "can_end_turn": self.can_end_turn,
        }


@dataclass(slots=True)
class WinnerState:
    winner_ids: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner_ids": list(self.winner_ids),
            "reason": self.reason,
        }


@dataclass(slots=True)
class GameState:
    connected_players: list[dict[str, Any]]
    active_player: str | None
    bank_tokens: dict[str, int]
    market: dict[str, list[dict[str, Any]]]
    deck_counts: dict[str, int]
    players: list[dict[str, Any]]
    nobles_remaining: list[dict[str, Any]]
    nobles_claimed: dict[str, list[dict[str, Any]]]
    endgame_triggered: bool
    winner_state: dict[str, Any] | None
    phase: str
    pending_turn: dict[str, Any]
    message: str
