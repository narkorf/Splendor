import { apiBaseUrl } from "./api";
import type { CardDef, NobleDef, TokenColor } from "./types";

export const GEM_ASSET_NAMES: Record<TokenColor, string> = {
  white: "diamond",
  blue: "sapphire",
  green: "emerald",
  red: "ruby",
  black: "onyx",
  gold: "gold",
};

export function buildAssetUrl(path: string, baseUrl = apiBaseUrl()): string {
  return new URL(path, baseUrl).toString();
}

export function gemAssetUrl(color: TokenColor, baseUrl?: string): string {
  return buildAssetUrl(`/assets/gems/${GEM_ASSET_NAMES[color]}.png`, baseUrl);
}

export function cardAssetUrl(card: Pick<CardDef, "asset_id" | "masked">, baseUrl?: string): string | null {
  if (card.masked || !card.asset_id) {
    return null;
  }
  return buildAssetUrl(`/assets/cards/${card.asset_id}.png`, baseUrl);
}

export function nobleAssetUrl(noble: Pick<NobleDef, "asset_id">, baseUrl?: string): string | null {
  if (!noble.asset_id) {
    return null;
  }
  return buildAssetUrl(`/assets/nobles/${noble.asset_id}.png`, baseUrl);
}
