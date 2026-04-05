"""Shared constants for the Splendor game core."""

TOKEN_COLORS = ("white", "blue", "green", "red", "black")
ALL_TOKEN_COLORS = TOKEN_COLORS + ("gold",)
TIER_LEVELS = (1, 2, 3)
MARKET_SIZE = 4
MAX_RESERVED_CARDS = 3
TOKEN_LIMIT = 10
WINNING_SCORE = 15
PLAYER_COUNT = 2
TOKENS_BY_PLAYER_COUNT = {
    2: {"white": 4, "blue": 4, "green": 4, "red": 4, "black": 4, "gold": 5},
}
NOBLES_BY_PLAYER_COUNT = {
    2: 3,
}
POINTS_BY_NOBLE = 3
