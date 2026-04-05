"""Framework-agnostic Splendor game core."""

from .constants import (
    ALL_TOKEN_COLORS,
    MARKET_SIZE,
    MAX_RESERVED_CARDS,
    NOBLES_BY_PLAYER_COUNT,
    PLAYER_COUNT,
    POINTS_BY_NOBLE,
    TOKEN_COLORS,
    TOKEN_LIMIT,
    TOKENS_BY_PLAYER_COUNT,
    TIER_LEVELS,
    WINNING_SCORE,
)
from .data import build_card_definitions, build_noble_definitions, default_setup_summary
from .game_logic import ActionResult, GameError, SplendorGame
from .model import (
    CardDef,
    GameState,
    NobleDef,
    PendingTurnState,
    PlayerState,
    ReservedCard,
    WinnerState,
    empty_bonus_counts,
    empty_token_counts,
)

__all__ = [
    "ALL_TOKEN_COLORS",
    "ActionResult",
    "CardDef",
    "GameError",
    "GameState",
    "MARKET_SIZE",
    "MAX_RESERVED_CARDS",
    "NOBLES_BY_PLAYER_COUNT",
    "NobleDef",
    "PLAYER_COUNT",
    "POINTS_BY_NOBLE",
    "PendingTurnState",
    "PlayerState",
    "ReservedCard",
    "SplendorGame",
    "TOKEN_COLORS",
    "TOKEN_LIMIT",
    "TOKENS_BY_PLAYER_COUNT",
    "TIER_LEVELS",
    "WINNING_SCORE",
    "WinnerState",
    "build_card_definitions",
    "build_noble_definitions",
    "default_setup_summary",
    "empty_bonus_counts",
    "empty_token_counts",
]
