import type { CardDef, GameState, TokenColor } from "./types";

export const ALL_TOKEN_COLORS: TokenColor[] = ["white", "blue", "green", "red", "black", "gold"];

export const TOKEN_STYLES: Record<TokenColor, string> = {
  white: "#f2f2f2",
  blue: "#4c78dd",
  green: "#2a9d5b",
  red: "#d1495b",
  black: "#333333",
  gold: "#d9a404",
};

export const COLOR_ABBREVIATIONS: Record<TokenColor, string> = {
  white: "Wht",
  blue: "Blu",
  green: "Grn",
  red: "Red",
  black: "Blk",
  gold: "Gld",
};

export function formatColor(color: string): string {
  return color[0].toUpperCase() + color.slice(1);
}

export function countFromRecord(record: Record<string, number>): number {
  return Object.values(record).reduce((total, value) => total + value, 0);
}

export function countsText(counts: Record<string, number>): string {
  const parts = Object.entries(counts)
    .filter(([, count]) => count)
    .map(([color, count]) => `${color[0].toUpperCase()}:${count}`);
  return parts.length > 0 ? parts.join(", ") : "None";
}

export function formatCost(costs: Record<string, number>): string {
  const entries = Object.entries(costs).filter(([, amount]) => amount > 0);
  if (entries.length === 0) {
    return "Free";
  }
  return entries.map(([color, amount]) => `${amount} ${formatColor(color)}`).join(" • ");
}

export function canSubmitPendingGems(state: GameState | null, pendingGems: string[]): boolean {
  if (!state || state.phase !== "active") {
    return false;
  }
  const bank = state.bank_tokens;
  if (pendingGems.length === 1) {
    const color = pendingGems[0] as TokenColor;
    return color !== "gold" && ALL_TOKEN_COLORS.includes(color) && (bank[color] ?? 0) >= 4;
  }
  if (pendingGems.length === 3 && new Set(pendingGems).size === 3) {
    return pendingGems.every((color) => color !== "gold" && (bank[color] ?? 0) >= 1);
  }
  return false;
}

export function gemActionPayload(pendingGems: string[]): string[] {
  if (pendingGems.length === 1) {
    return [pendingGems[0], pendingGems[0]];
  }
  return [...pendingGems];
}

export function canAffordCard(card: CardDef, player: GameState["players"][number] | null): boolean {
  if (!player) {
    return false;
  }
  let goldNeeded = 0;
  for (const color of ALL_TOKEN_COLORS) {
    if (color === "gold") {
      continue;
    }
    const cost = Number(card.cost[color] ?? 0);
    const discount = Number(player.bonuses[color] ?? 0);
    const remaining = Math.max(0, cost - discount);
    const available = Number(player.tokens[color] ?? 0);
    goldNeeded += Math.max(0, remaining - available);
  }
  return goldNeeded <= Number(player.tokens.gold ?? 0);
}

export function missingTokensReason(card: CardDef, player: GameState["players"][number] | null): string {
  if (!player) {
    return "Waiting for your player state.";
  }
  let shortageTotal = 0;
  const shortages: string[] = [];
  for (const color of ALL_TOKEN_COLORS) {
    if (color === "gold") {
      continue;
    }
    const cost = Number(card.cost[color] ?? 0);
    const discount = Number(player.bonuses[color] ?? 0);
    const remaining = Math.max(0, cost - discount);
    const available = Number(player.tokens[color] ?? 0);
    const missing = Math.max(0, remaining - available);
    if (missing) {
      shortages.push(`${color} ${missing}`);
      shortageTotal += missing;
    }
  }
  const goldAvailable = Number(player.tokens.gold ?? 0);
  if (shortageTotal <= goldAvailable) {
    return "You can cover the remaining cost with gold.";
  }
  const stillMissing = shortageTotal - goldAvailable;
  if (shortages.length > 0) {
    return `Need ${stillMissing} more token(s): ${shortages.join(", ")}.`;
  }
  return "You do not have enough tokens.";
}

export function playerStatuses(
  player: GameState["players"][number],
  activePlayerId: string | null,
  localPlayerId: string | null,
): string[] {
  const statuses: string[] = [];
  if (player.id === activePlayerId) {
    statuses.push("Active");
  }
  if (player.id === localPlayerId) {
    statuses.push("You");
  }
  if (!player.connected) {
    statuses.push("Disconnected");
  }
  return statuses;
}
