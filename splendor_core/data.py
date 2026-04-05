"""Manifest-backed card and noble definitions."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from .assets import load_json_asset
from .constants import PLAYER_COUNT, POINTS_BY_NOBLE, TOKEN_COLORS
from .model import CardDef, NobleDef


EXPECTED_CARD_COUNTS = {
    1: 40,
    2: 30,
    3: 20,
}
EXPECTED_NOBLE_COUNT = 10


def _validate_card_record(
    record: object,
    index: int,
    seen_ids: set[str],
    seen_asset_ids: set[str],
) -> CardDef:
    if not isinstance(record, dict):
        raise ValueError(f"Card record {index} must be an object.")
    required_fields = {"id", "tier", "bonus_color", "points", "cost", "placeholder_label"}
    missing_fields = sorted(required_fields - set(record))
    if missing_fields:
        raise ValueError(f"Card record {index} is missing required fields: {', '.join(missing_fields)}.")
    card_id = str(record["id"])
    if card_id in seen_ids:
        raise ValueError(f"Duplicate card id: {card_id}.")
    seen_ids.add(card_id)

    tier = int(record["tier"])
    if tier not in EXPECTED_CARD_COUNTS:
        raise ValueError(f"Card {card_id} has invalid tier {tier}.")

    bonus_color = str(record["bonus_color"])
    if bonus_color not in TOKEN_COLORS:
        raise ValueError(f"Card {card_id} has invalid bonus color {bonus_color}.")

    points = int(record["points"])
    if points < 0:
        raise ValueError(f"Card {card_id} has negative points.")

    raw_cost = record["cost"]
    if not isinstance(raw_cost, dict):
        raise ValueError(f"Card {card_id} cost must be an object.")
    cost: dict[str, int] = {}
    for color, raw_amount in raw_cost.items():
        if color not in TOKEN_COLORS:
            raise ValueError(f"Card {card_id} uses invalid cost color {color}.")
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError(f"Card {card_id} has negative cost for {color}.")
        if amount:
            cost[color] = amount

    raw_asset_id = record.get("asset_id")
    asset_id = None if raw_asset_id is None else str(raw_asset_id)
    if asset_id:
        if asset_id in seen_asset_ids:
            raise ValueError(f"Duplicate asset id: {asset_id}.")
        seen_asset_ids.add(asset_id)

    return CardDef(
        id=card_id,
        tier=tier,
        cost=cost,
        bonus_color=bonus_color,
        points=points,
        placeholder_label=str(record["placeholder_label"]),
        asset_id=asset_id,
    )


def _validate_noble_record(
    record: object,
    index: int,
    seen_ids: set[str],
    seen_asset_ids: set[str],
) -> NobleDef:
    if not isinstance(record, dict):
        raise ValueError(f"Noble record {index} must be an object.")
    required_fields = {"id", "requirements", "points", "placeholder_label"}
    missing_fields = sorted(required_fields - set(record))
    if missing_fields:
        raise ValueError(f"Noble record {index} is missing required fields: {', '.join(missing_fields)}.")

    noble_id = str(record["id"])
    if noble_id in seen_ids:
        raise ValueError(f"Duplicate noble id: {noble_id}.")
    seen_ids.add(noble_id)

    raw_requirements = record["requirements"]
    if not isinstance(raw_requirements, dict):
        raise ValueError(f"Noble {noble_id} requirements must be an object.")
    requirements: dict[str, int] = {}
    for color, raw_amount in raw_requirements.items():
        if color not in TOKEN_COLORS:
            raise ValueError(f"Noble {noble_id} uses invalid requirement color {color}.")
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError(f"Noble {noble_id} has negative requirement for {color}.")
        if amount:
            requirements[color] = amount

    points = int(record["points"])
    if points != POINTS_BY_NOBLE:
        raise ValueError(f"Noble {noble_id} must be worth {POINTS_BY_NOBLE} points.")

    raw_asset_id = record.get("asset_id")
    asset_id = None if raw_asset_id is None else str(raw_asset_id)
    if asset_id:
        if asset_id in seen_asset_ids:
            raise ValueError(f"Duplicate noble asset id: {asset_id}.")
        seen_asset_ids.add(asset_id)

    return NobleDef(
        id=noble_id,
        requirements=requirements,
        points=points,
        placeholder_label=str(record["placeholder_label"]),
        asset_id=asset_id,
    )


@lru_cache(maxsize=1)
def _load_cards_from_manifest() -> tuple[CardDef, ...]:
    payload = load_json_asset("manifests", "cards.json")
    if not isinstance(payload, list):
        raise ValueError("cards.json must contain a list of card records.")

    seen_ids: set[str] = set()
    seen_asset_ids: set[str] = set()
    cards = [
        _validate_card_record(record, index, seen_ids, seen_asset_ids)
        for index, record in enumerate(payload, start=1)
    ]
    tier_counts = Counter(card.tier for card in cards)
    for tier, expected_count in EXPECTED_CARD_COUNTS.items():
        actual_count = tier_counts.get(tier, 0)
        if actual_count != expected_count:
            raise ValueError(
                f"Tier {tier} must have {expected_count} cards in cards.json, found {actual_count}."
            )
    return tuple(cards)


@lru_cache(maxsize=1)
def _load_nobles_from_manifest() -> tuple[NobleDef, ...]:
    payload = load_json_asset("manifests", "nobles.json")
    if not isinstance(payload, list):
        raise ValueError("nobles.json must contain a list of noble records.")

    seen_ids: set[str] = set()
    seen_asset_ids: set[str] = set()
    nobles = [
        _validate_noble_record(record, index, seen_ids, seen_asset_ids)
        for index, record in enumerate(payload, start=1)
    ]
    if len(nobles) != EXPECTED_NOBLE_COUNT:
        raise ValueError(
            f"nobles.json must contain {EXPECTED_NOBLE_COUNT} nobles, found {len(nobles)}."
        )
    return tuple(nobles)


def build_card_definitions() -> list[CardDef]:
    return [CardDef.from_dict(card.to_dict()) for card in _load_cards_from_manifest()]


def build_noble_definitions() -> list[NobleDef]:
    return [NobleDef.from_dict(noble.to_dict()) for noble in _load_nobles_from_manifest()]


def default_setup_summary() -> dict[str, int]:
    return {
        "players": PLAYER_COUNT,
        "cards": len(build_card_definitions()),
        "nobles": len(build_noble_definitions()),
    }
