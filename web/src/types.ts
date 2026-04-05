export type TokenColor = "white" | "blue" | "green" | "red" | "black" | "gold";

export interface PlayerConnection {
  id: string;
  name: string;
  connected: boolean;
}

export interface CardDef {
  id: string;
  tier: number | null;
  cost: Record<string, number>;
  bonus_color: string;
  points: number;
  placeholder_label: string;
  asset_id?: string | null;
  masked?: boolean;
  is_top_deck_reservation?: boolean;
}

export interface NobleDef {
  id: string;
  requirements: Record<string, number>;
  points: number;
  placeholder_label: string;
  asset_id?: string | null;
}

export interface PendingTurn {
  discard_count: number;
  eligible_nobles: string[];
  manual_end_turn: boolean;
  can_end_turn: boolean;
}

export interface GameState {
  connected_players: PlayerConnection[];
  active_player: string | null;
  bank_tokens: Record<string, number>;
  market: Record<string, CardDef[]>;
  deck_counts: Record<string, number>;
  players: Array<{
    id: string;
    name: string;
    tokens: Record<string, number>;
    purchased_cards: CardDef[];
    bonuses: Record<string, number>;
    reserved_cards: CardDef[];
    score: number;
    claimed_nobles: NobleDef[];
    purchased_card_count: number;
    connected: boolean;
  }>;
  nobles_remaining: NobleDef[];
  nobles_claimed: Record<string, NobleDef[]>;
  endgame_triggered: boolean;
  winner_state: { winner_ids: string[]; reason: string } | null;
  phase: string;
  pending_turn: PendingTurn;
  message: string;
}

export interface JoinedPayload {
  type: "joined";
  room_code: string;
  player_id: string;
  player_token: string;
}

export interface RoomSnapshot {
  room_code: string;
  phase: string;
  player_count: number;
  max_players: number;
  joinable: boolean;
  player_id: string | null;
  connected_players: PlayerConnection[];
  state: GameState | null;
}

export interface ErrorPayload {
  type: "error";
  message: string;
  code: string;
}

export interface PresencePayload {
  type: "presence";
  connected_players: PlayerConnection[];
}

export interface RoomClosedPayload {
  type: "room_closed";
  message: string;
}

export interface StatePayload {
  type: "state";
  state: GameState;
  events: Array<Record<string, unknown>>;
}

export type ServerMessage =
  | JoinedPayload
  | ErrorPayload
  | PresencePayload
  | RoomClosedPayload
  | StatePayload;

export interface StoredSession {
  roomCode: string;
  playerToken: string;
  playerId: string | null;
  playerName: string;
}
