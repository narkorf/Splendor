import type { JoinedPayload, RoomSnapshot, StoredSession } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

function buildUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export function apiBaseUrl(): string {
  return API_BASE_URL || window.location.origin;
}

export function wsBaseUrl(): string {
  const base = apiBaseUrl();
  if (base.startsWith("https://")) {
    return base.replace("https://", "wss://");
  }
  if (base.startsWith("http://")) {
    return base.replace("http://", "ws://");
  }
  return window.location.origin.replace(/^http/, "ws");
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail ?? payload;
    const message = detail.message ?? "Request failed.";
    throw new Error(message);
  }
  return payload as T;
}

export async function createRoom(name: string): Promise<JoinedPayload> {
  const response = await fetch(buildUrl("/api/rooms"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return parseResponse<JoinedPayload>(response);
}

export async function joinRoom(roomCode: string, name: string): Promise<JoinedPayload> {
  const response = await fetch(buildUrl(`/api/rooms/${roomCode}/join`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return parseResponse<JoinedPayload>(response);
}

export async function fetchRoomSnapshot(session: StoredSession): Promise<RoomSnapshot> {
  const query = new URLSearchParams({ player_token: session.playerToken });
  const response = await fetch(buildUrl(`/api/rooms/${session.roomCode}?${query.toString()}`));
  return parseResponse<RoomSnapshot>(response);
}
