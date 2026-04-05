import { FormEvent, useEffect, useState } from "react";

import { createRoom, fetchRoomSnapshot, joinRoom, wsBaseUrl } from "./api";
import { GameBoard } from "./components/GameBoard";
import { ALL_TOKEN_COLORS, canSubmitPendingGems, gemActionPayload } from "./gameUi";
import type { GameState, JoinedPayload, ServerMessage, StoredSession, TokenColor } from "./types";

const STORAGE_KEY = "splendor-web-session";

function loadStoredSession(): StoredSession | null {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

function saveStoredSession(session: StoredSession | null): void {
  if (session === null) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function App() {
  const [playerName, setPlayerName] = useState("Player");
  const [roomCodeInput, setRoomCodeInput] = useState(() => new URLSearchParams(window.location.search).get("room") ?? "");
  const [session, setSession] = useState<StoredSession | null>(() => loadStoredSession());
  const [state, setState] = useState<GameState | null>(null);
  const [feedback, setFeedback] = useState("Create a room or join an existing one.");
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [connectionHint, setConnectionHint] = useState("");
  const [pendingGemSelection, setPendingGemSelection] = useState<string[]>([]);
  const [pendingDiscardSelection, setPendingDiscardSelection] = useState<Record<string, number>>({});
  const [pendingEndAfterGemSubmit, setPendingEndAfterGemSubmit] = useState(false);
  const [socket, setSocket] = useState<WebSocket | null>(null);

  useEffect(() => {
    if (session === null) {
      saveStoredSession(null);
      const search = new URLSearchParams(window.location.search);
      search.delete("room");
      const query = search.toString();
      window.history.replaceState({}, "", query ? `${window.location.pathname}?${query}` : window.location.pathname);
      return;
    }
    saveStoredSession(session);
    const search = new URLSearchParams(window.location.search);
    search.set("room", session.roomCode);
    window.history.replaceState({}, "", `${window.location.pathname}?${search.toString()}`);
  }, [session]);

  useEffect(() => {
    const stored = loadStoredSession();
    if (!stored) {
      return;
    }
    setPlayerName(stored.playerName);
    fetchRoomSnapshot(stored)
      .then((snapshot) => {
        if (snapshot.player_id === null || snapshot.state === null) {
          throw new Error("Could not restore that game session.");
        }
        setSession({
          roomCode: snapshot.room_code,
          playerToken: stored.playerToken,
          playerId: snapshot.player_id,
          playerName: stored.playerName,
        });
        setState(snapshot.state);
        setConnectionHint(snapshot.room_code);
        setFeedback(`Restored room ${snapshot.room_code}.`);
      })
      .catch(() => {
        setSession(null);
      });
  }, []);

  useEffect(() => {
    setPendingGemSelection([]);
    setPendingDiscardSelection({});
  }, [state?.phase, state?.active_player, session?.roomCode]);

  useEffect(() => {
    if (session === null) {
      socket?.close();
      setSocket(null);
      return;
    }
    const nextSocket = new WebSocket(`${wsBaseUrl()}/ws/rooms/${session.roomCode}?player_token=${encodeURIComponent(session.playerToken)}`);
    setSocket(nextSocket);
    setConnected(false);
    setError("");

    nextSocket.onopen = () => {
      setConnected(true);
      setConnectionHint(session.roomCode);
      setFeedback(`Connected to room ${session.roomCode}.`);
    };

    nextSocket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ServerMessage;
      if (payload.type === "joined") {
        setSession((current) =>
          current
            ? {
                ...current,
                roomCode: payload.room_code,
                playerId: payload.player_id,
                playerToken: payload.player_token,
              }
            : current,
        );
        setConnectionHint(payload.room_code);
        return;
      }
      if (payload.type === "presence") {
        setState((current) => (current ? { ...current, connected_players: payload.connected_players } : current));
        return;
      }
      if (payload.type === "room_closed") {
        setError(payload.message);
        setConnected(false);
        setSession(null);
        setState(null);
        return;
      }
      if (payload.type === "error") {
        setError(payload.message);
        setFeedback(payload.message);
        return;
      }
      if (payload.type === "state") {
        setState(payload.state);
        setFeedback(payload.state.message);
      }
    };

    nextSocket.onclose = () => {
      setConnected(false);
    };

    return () => {
      nextSocket.close();
      setSocket(null);
    };
  }, [session?.roomCode, session?.playerToken]);

  useEffect(() => {
    if (
      pendingEndAfterGemSubmit &&
      state &&
      session &&
      state.active_player === session.playerId &&
      state.phase === "awaiting_end_turn" &&
      state.pending_turn.can_end_turn
    ) {
      setPendingEndAfterGemSubmit(false);
      sendAction("end_turn", {});
    }
  }, [pendingEndAfterGemSubmit, session, state]);

  async function handleCreateRoom(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const joined = await createRoom(playerName);
      applyJoinResult(joined);
      setFeedback(`Room ${joined.room_code} created. Share the link with your friend.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create a room.");
    }
  }

  async function handleJoinRoom(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const joined = await joinRoom(roomCodeInput.toUpperCase(), playerName);
      applyJoinResult(joined);
      setFeedback(`Joined room ${joined.room_code}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join the room.");
    }
  }

  function applyJoinResult(joined: JoinedPayload) {
    const nextSession = {
      roomCode: joined.room_code,
      playerToken: joined.player_token,
      playerId: joined.player_id,
      playerName,
    };
    setSession(nextSession);
    saveStoredSession(nextSession);
    setRoomCodeInput(joined.room_code);
    setConnectionHint(joined.room_code);
  }

  function sendAction(action: string, payload: Record<string, unknown>) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("The game connection is not ready yet.");
      return;
    }
    setPendingGemSelection([]);
    socket.send(JSON.stringify({ type: "action", action, payload }));
  }

  function localPlayer(): GameState["players"][number] | null {
    if (!state || !session?.playerId) {
      return null;
    }
    return state.players.find((player) => player.id === session.playerId) ?? null;
  }

  function handleBankTokenClick(color: TokenColor) {
    if (!state || !session) {
      return;
    }
    if (state.phase === "discard") {
      addDiscardSelection(color);
      return;
    }
    if (state.phase !== "active") {
      setFeedback("Gem selection is only available during an active turn.");
      return;
    }
    if (state.active_player !== session.playerId) {
      setFeedback("Only the active player can take gems.");
      return;
    }
    if ((state.bank_tokens[color] ?? 0) <= 0) {
      setFeedback(`No ${color} gems remain in the bank.`);
      return;
    }
    if (color === "gold") {
      setFeedback("Gold cannot be taken directly from the bank.");
      return;
    }
    if (pendingGemSelection.includes(color)) {
      const next = pendingGemSelection.filter((entry) => entry !== color);
      setPendingGemSelection(next);
      setFeedback(next.length ? `Pending gems: ${next.join(", ")}.` : "Gem selection cleared.");
      return;
    }
    if (pendingGemSelection.length >= 3) {
      setFeedback("You can only have up to three different gem colors selected.");
      return;
    }
    const next = [...pendingGemSelection, color];
    setPendingGemSelection(next);
    if (next.length === 1) {
      if ((state.bank_tokens[color] ?? 0) >= 4) {
        setFeedback(`Selected ${color}. Click End Turn to take two ${color} gems, or pick different colors for a three-gem take.`);
      } else {
        setFeedback(`Selected ${color}. Pick two different colors, or re-click ${color} to clear it.`);
      }
      return;
    }
    if (next.length === 2) {
      setFeedback(`Selected ${next.join(", ")}. Pick one more different gem.`);
      return;
    }
    setFeedback(`Selected ${next.join(", ")}. Click End Turn to take them.`);
  }

  function addDiscardSelection(color: TokenColor) {
    if (!state || !session) {
      return;
    }
    if (state.active_player !== session.playerId) {
      setFeedback("Only the active player can discard.");
      return;
    }
    const target = Number(state.pending_turn.discard_count ?? 0);
    const me = localPlayer();
    if (!me) {
      return;
    }
    const selected = pendingDiscardSelection[color] ?? 0;
    if (selected >= Number(me.tokens[color] ?? 0)) {
      setFeedback(`You do not have more ${color} tokens to discard.`);
      return;
    }
    const totalSelected = Object.values(pendingDiscardSelection).reduce((total, value) => total + value, 0);
    if (totalSelected >= target) {
      setFeedback("Discard selection already meets the required total.");
      return;
    }
    const next = { ...pendingDiscardSelection, [color]: selected + 1 };
    setPendingDiscardSelection(next);
    const nextTotal = Object.values(next).reduce((total, value) => total + value, 0);
    if (nextTotal === target) {
      sendAction("discard_excess_tokens", { tokens: next });
      setPendingDiscardSelection({});
    }
  }

  function handleEndTurn() {
    if (!state) {
      return;
    }
    if (state.phase === "active") {
      if (pendingGemSelection.length === 0) {
        setFeedback("Select gems first.");
        return;
      }
      if (!canSubmitPendingGems(state, pendingGemSelection)) {
        setFeedback("Finish selecting a legal gem take, or reset your gem picks.");
        return;
      }
      setPendingEndAfterGemSubmit(true);
      sendAction("take_gems", { colors: gemActionPayload(pendingGemSelection) });
      setPendingGemSelection([]);
      return;
    }
    if (state.phase !== "awaiting_end_turn") {
      setFeedback("End Turn is only available after selecting gems or completing a gem-taking turn.");
      return;
    }
    sendAction("end_turn", {});
  }

  function handleChooseNoble(nobleId: string) {
    sendAction("choose_noble", { noble_id: nobleId });
  }

  function handleReservedCardClick(index: number) {
    if (!state || !session) {
      return;
    }
    if (state.active_player !== session.playerId) {
      setFeedback("Only the active player can buy reserved cards.");
      return;
    }
    if (state.phase !== "active") {
      setFeedback("Reserved cards can only be bought during the active phase.");
      return;
    }
    sendAction("buy_reserved_card", { reserved_index: index });
  }

  function handleReserveTopDeck(tier: number) {
    if (!state || !session) {
      return;
    }
    if (state.active_player !== session.playerId) {
      setFeedback("Only the active player can reserve cards.");
      return;
    }
    if (state.phase !== "active") {
      setFeedback("Top-deck reservation is only available during the active phase.");
      return;
    }
    sendAction("reserve_card", { tier, top_deck: true });
  }

  function handleSendMarketAction(action: "buy" | "reserve", tier: number, marketIndex: number) {
    if (action === "buy") {
      sendAction("buy_face_up_card", { tier, market_index: marketIndex });
      return;
    }
    sendAction("reserve_card", { tier, market_index: marketIndex, top_deck: false });
  }

  function shareLink(): string {
    if (session === null) {
      return "";
    }
    const url = new URL(window.location.href);
    url.searchParams.set("room", session.roomCode);
    return url.toString();
  }

  async function copyShareLink() {
    try {
      await navigator.clipboard.writeText(shareLink());
      setFeedback("Share link copied.");
    } catch {
      setFeedback(`Room link: ${shareLink()}`);
    }
  }

  function leaveRoom() {
    setSession(null);
    setState(null);
    setConnected(false);
    setConnectionHint("");
    setPendingGemSelection([]);
    setPendingDiscardSelection({});
  }

  return (
    <div className="app-shell">
      {session === null || state === null ? (
        <>
          <header className="hero">
            <div>
              <p className="eyebrow">Hosted Splendor</p>
              <h1>Play from a link instead of a DMG.</h1>
              <p className="hero-copy">
                Create a room, send a share link, and keep playing from phone or desktop with automatic reconnect.
              </p>
            </div>
            <div className="hero-status">
              <p>{feedback}</p>
              {error ? <p className="error-banner">{error}</p> : null}
            </div>
          </header>

          <main className="landing-grid">
            <section className="panel">
              <h2>Create a room</h2>
              <form className="form-stack" onSubmit={handleCreateRoom}>
                <label>
                  <span>Your name</span>
                  <input value={playerName} onChange={(event) => setPlayerName(event.target.value)} maxLength={40} />
                </label>
                <button type="submit">Create Room</button>
              </form>
            </section>
            <section className="panel">
              <h2>Join a room</h2>
              <form className="form-stack" onSubmit={handleJoinRoom}>
                <label>
                  <span>Your name</span>
                  <input value={playerName} onChange={(event) => setPlayerName(event.target.value)} maxLength={40} />
                </label>
                <label>
                  <span>Room code</span>
                  <input
                    value={roomCodeInput}
                    onChange={(event) => setRoomCodeInput(event.target.value.toUpperCase())}
                    maxLength={6}
                  />
                </label>
                <button type="submit">Join Room</button>
              </form>
            </section>
          </main>
        </>
      ) : (
        <GameBoard
          connected={connected}
          connectionHint={connectionHint}
          error={error}
          feedback={feedback}
          onBankTokenClick={handleBankTokenClick}
          onChooseNoble={handleChooseNoble}
          onCopyShareLink={copyShareLink}
          onEndTurn={handleEndTurn}
          onLeaveRoom={leaveRoom}
          onReservedCardClick={handleReservedCardClick}
          onReserveTopDeck={handleReserveTopDeck}
          onSendMarketAction={handleSendMarketAction}
          pendingDiscardSelection={pendingDiscardSelection}
          pendingGemSelection={pendingGemSelection}
          session={session}
          state={state}
        />
      )}
    </div>
  );
}

export default App;
