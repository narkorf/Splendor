import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { cardAssetUrl, gemAssetUrl, nobleAssetUrl } from "../assets";
import {
  ALL_TOKEN_COLORS,
  COLOR_ABBREVIATIONS,
  TOKEN_STYLES,
  canAffordCard,
  countFromRecord,
  countsText,
  formatColor,
  missingTokensReason,
  playerStatuses,
} from "../gameUi";
import type { CardDef, GameState, StoredSession } from "../types";

type SelectedMarketCard = {
  tier: number;
  marketIndex: number;
  cardId: string;
} | null;

type BoardMode = "desktop" | "tablet" | "mobile-landscape" | "mobile-portrait";

export interface GameBoardProps {
  connected: boolean;
  connectionHint: string;
  error: string;
  feedback: string;
  onBankTokenClick: (color: typeof ALL_TOKEN_COLORS[number]) => void;
  onChooseNoble: (nobleId: string) => void;
  onCopyShareLink: () => void;
  onEndTurn: () => void;
  onLeaveRoom: () => void;
  onReservedCardClick: (reservedIndex: number) => void;
  onReserveTopDeck: (tier: number) => void;
  onSendMarketAction: (action: "buy" | "reserve", tier: number, marketIndex: number) => void;
  pendingDiscardSelection: Record<string, number>;
  pendingGemSelection: string[];
  session: StoredSession;
  state: GameState;
}

export function GameBoard({
  connected,
  connectionHint,
  error,
  feedback,
  onBankTokenClick,
  onChooseNoble,
  onCopyShareLink,
  onEndTurn,
  onLeaveRoom,
  onReservedCardClick,
  onReserveTopDeck,
  onSendMarketAction,
  pendingDiscardSelection,
  pendingGemSelection,
  session,
  state,
}: GameBoardProps) {
  const [selectedMarketCard, setSelectedMarketCard] = useState<SelectedMarketCard>(null);
  const [dismissedWinnerKey, setDismissedWinnerKey] = useState<string | null>(null);
  const boardMode = useBoardMode();
  const me = useMemo(() => state.players.find((player) => player.id === session.playerId) ?? null, [session.playerId, state.players]);
  const isMyTurn = state.active_player === session.playerId;
  const canEndTurn =
    isMyTurn &&
    ((state.phase === "active" && pendingGemSelection.length > 0) ||
      (state.phase === "awaiting_end_turn" && state.pending_turn.can_end_turn));
  const isMobileBoard = boardMode === "mobile-landscape" || boardMode === "mobile-portrait";
  const fullConnectionLabel = `Connected as ${session.playerId ?? "?"}. Active player: ${state.active_player ?? "n/a"}. Phase: ${state.phase}. Room detail: ${connectionHint}`;
  const compactConnectionLabel = `Room ${connectionHint} | You ${session.playerId ?? "?"} | Turn ${state.active_player ?? "n/a"}`;
  const connectionLabel = isMobileBoard ? compactConnectionLabel : fullConnectionLabel;
  const winnerKey =
    state.phase === "game_over" && state.winner_state
      ? `${state.winner_state.winner_ids.join("|")}:${state.winner_state.reason}:${state.message}`
      : null;
  const winnerModalVisible = winnerKey !== null && winnerKey !== dismissedWinnerKey;
  const discardModalVisible = state.phase === "discard" && isMyTurn;

  useEffect(() => {
    if (selectedMarketCard === null) {
      return;
    }
    if (state.phase !== "active" || state.active_player !== session.playerId) {
      setSelectedMarketCard(null);
      return;
    }
    const tierCards = state.market[String(selectedMarketCard.tier)] ?? [];
    const card = tierCards[selectedMarketCard.marketIndex];
    if (!card || card.id !== selectedMarketCard.cardId) {
      setSelectedMarketCard(null);
    }
  }, [selectedMarketCard, session.playerId, state.active_player, state.market, state.phase]);

  const selectedCardPayload = useMemo(() => {
    if (selectedMarketCard === null) {
      return null;
    }
    const tierCards = state.market[String(selectedMarketCard.tier)] ?? [];
    const card = tierCards[selectedMarketCard.marketIndex];
    if (!card || card.id !== selectedMarketCard.cardId) {
      return null;
    }
    return {
      tier: selectedMarketCard.tier,
      marketIndex: selectedMarketCard.marketIndex,
      card,
    };
  }, [selectedMarketCard, state.market]);

  useEffect(() => {
    const modalOpen = selectedCardPayload !== null || discardModalVisible || winnerModalVisible;
    if (!modalOpen) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [discardModalVisible, selectedCardPayload, winnerModalVisible]);

  useEffect(() => {
    if (winnerKey === null) {
      setDismissedWinnerKey(null);
    }
  }, [winnerKey]);

  const selectedCardCanBuy = selectedCardPayload ? canAffordCard(selectedCardPayload.card, me) : false;
  const selectedCardBuyHint = selectedCardPayload
    ? selectedCardCanBuy
      ? "You can buy this card now."
      : missingTokensReason(selectedCardPayload.card, me)
    : "";

  const bankPanel = (
    <BankPanel
      isMyTurn={isMyTurn}
      onBankTokenClick={onBankTokenClick}
      pendingDiscardSelection={pendingDiscardSelection}
      pendingGemSelection={pendingGemSelection}
      state={state}
    />
  );

  const noblesPanel = <NoblesPanel isMyTurn={isMyTurn} onChooseNoble={onChooseNoble} state={state} />;

  const marketPanel = (
    <MarketPanel
      canEndTurn={canEndTurn}
      compactCards={boardMode !== "desktop"}
      isMyTurn={isMyTurn}
      onEndTurn={onEndTurn}
      onReserveTopDeck={onReserveTopDeck}
      onSelectMarketCard={setSelectedMarketCard}
      state={state}
    />
  );

  const playersPanel = (
    <PlayersPanel
      boardStatusPanel={
        <BoardStatusPanel
          connected={connected}
          connectionLabel={connectionLabel}
          connectionLabelTitle={fullConnectionLabel}
          error={error}
          feedback={feedback}
          message={state.message}
          onCopyShareLink={onCopyShareLink}
          onLeaveRoom={onLeaveRoom}
        />
      }
      compact={boardMode !== "desktop"}
      isMobileBoard={isMobileBoard}
      isMyTurn={isMyTurn}
      onReservedCardClick={onReservedCardClick}
      session={session}
      state={state}
    />
  );

  return (
    <main className="game-screen" data-board-mode={boardMode} data-testid="game-screen">
      {isMobileBoard ? (
        <section className={`mobile-board ${boardMode}`}>
          <div className="mobile-primary-region">
            <div className="mobile-market-region">{marketPanel}</div>
            <div className="mobile-nobles-region">{noblesPanel}</div>
          </div>
          <div className={`mobile-secondary-region ${boardMode === "mobile-landscape" ? "mobile-secondary-landscape" : "mobile-secondary-portrait"}`}>
            <div className="mobile-bank-region">{bankPanel}</div>
            <section className="mobile-players-region" data-testid="players-section">
              {playersPanel}
            </section>
          </div>
        </section>
      ) : (
        <section className={`desktop-board ${boardMode === "tablet" ? "board-tablet" : "board-desktop"}`}>
          <aside className="left-column">
            {bankPanel}
            {noblesPanel}
          </aside>
          <section className="center-column">{marketPanel}</section>
          <aside className="right-column" data-testid="players-section">
            {playersPanel}
          </aside>
        </section>
      )}

      {selectedCardPayload ? (
        <div className="market-overlay" role="dialog" aria-modal="true">
          <div className="market-dialog">
            <div className="market-overlay-card">
              <CardFace card={selectedCardPayload.card} compact={boardMode !== "desktop"} />
            </div>
            <div className="overlay-actions">
              <button
                type="button"
                className={`market-buy-button ${selectedCardCanBuy ? "primary-action" : "market-buy-button-disabled"}`}
                onClick={() => {
                  onSendMarketAction("buy", selectedCardPayload.tier, selectedCardPayload.marketIndex);
                  setSelectedMarketCard(null);
                }}
                disabled={!selectedCardCanBuy}
                title={!selectedCardCanBuy ? selectedCardBuyHint : ""}
              >
                Buy
              </button>
              <button
                type="button"
                onClick={() => {
                  onSendMarketAction("reserve", selectedCardPayload.tier, selectedCardPayload.marketIndex);
                  setSelectedMarketCard(null);
                }}
                disabled={!canReserveCard(state, me, isMyTurn)}
                className="secondary-button"
              >
                Reserve
              </button>
              <button type="button" className="secondary-button" onClick={() => setSelectedMarketCard(null)}>
                Cancel
              </button>
            </div>
            <p className={`overlay-hint ${selectedCardCanBuy ? "ready" : "blocked"}`}>{selectedCardBuyHint}</p>
          </div>
        </div>
      ) : null}

      {discardModalVisible ? (
        <DiscardModal
          onBankTokenClick={onBankTokenClick}
          pendingDiscardSelection={pendingDiscardSelection}
          player={me}
          state={state}
        />
      ) : null}

      {winnerModalVisible && state.winner_state ? (
        <WinnerModal
          message={state.message}
          onClose={() => setDismissedWinnerKey(winnerKey)}
          onLeaveRoom={onLeaveRoom}
          players={state.players}
          winnerState={state.winner_state}
        />
      ) : null}
    </main>
  );
}

function BoardStatusPanel({
  connected,
  connectionLabel,
  connectionLabelTitle,
  error,
  feedback,
  message,
  onCopyShareLink,
  onLeaveRoom,
}: {
  connected: boolean;
  connectionLabel: string;
  connectionLabelTitle: string;
  error: string;
  feedback: string;
  message: string;
  onCopyShareLink: () => void;
  onLeaveRoom: () => void;
}) {
  return (
    <section className="panel board-status-panel" data-testid="board-status-panel">
      <div className="board-status-copy">
        <div className="board-status-message">{message}</div>
        <div className="board-status-connection" title={connectionLabelTitle}>
          {connectionLabel}
        </div>
        <div className="board-status-feedback">{feedback}</div>
        {error ? <div className="error-banner board-status-error">Error: {error}</div> : null}
      </div>

      <div className="board-status-actions">
        <span className={`status-pill ${connected ? "connected" : "disconnected"}`}>{connected ? "Connected" : "Offline"}</span>
        <button type="button" className="secondary-button" onClick={onCopyShareLink}>
          Copy Share Link
        </button>
        <button type="button" className="secondary-button" onClick={onLeaveRoom}>
          Leave Room
        </button>
      </div>
    </section>
  );
}

function BankPanel({
  isMyTurn,
  onBankTokenClick,
  pendingDiscardSelection,
  pendingGemSelection,
  state,
}: {
  isMyTurn: boolean;
  onBankTokenClick: (color: typeof ALL_TOKEN_COLORS[number]) => void;
  pendingDiscardSelection: Record<string, number>;
  pendingGemSelection: string[];
  state: GameState;
}) {
  return (
    <section className="panel bank-panel" data-testid="bank-section">
      <div className="panel-heading">
        <h2>Bank Tokens</h2>
        <p className="panel-caption">Tap to build a legal gem take or discard selection.</p>
      </div>
      <div className="bank-grid">
        {ALL_TOKEN_COLORS.map((color) => {
          const activePhase = state.phase === "active";
          const discardPhase = state.phase === "discard";
          const disabled =
            (!discardPhase && (!activePhase || !isMyTurn || color === "gold")) ||
            (discardPhase && !isMyTurn);
          const selectedCount = pendingGemSelection.filter((entry) => entry === color).length;
          const discardCount = pendingDiscardSelection[color] ?? 0;
          return (
            <button
              key={color}
              type="button"
              className={`bank-token ${selectedCount ? "selected" : ""}`}
              onClick={() => onBankTokenClick(color)}
              disabled={disabled}
              aria-label={`${formatColor(color)} token`}
            >
              <img src={gemAssetUrl(color)} alt="" />
              <span className="token-count-badge">{state.bank_tokens[color] ?? 0}</span>
              {discardCount > 0 ? <span className="token-selection-count">-{discardCount}</span> : null}
            </button>
          );
        })}
      </div>
      <div className="discard-status" data-testid="discard-status">
        {pendingStatusText(state, pendingGemSelection, pendingDiscardSelection)}
      </div>
    </section>
  );
}

function NoblesPanel({
  isMyTurn,
  onChooseNoble,
  state,
}: {
  isMyTurn: boolean;
  onChooseNoble: (nobleId: string) => void;
  state: GameState;
}) {
  return (
    <section className="panel nobles-panel" data-testid="nobles-section">
      <div className="panel-heading">
        <h2>Nobles</h2>
        <p className="panel-caption">Claim one when its requirement is highlighted.</p>
      </div>
      <div className="nobles-list">
        {state.nobles_remaining.length > 0 ? (
          state.nobles_remaining.map((noble) => {
            const eligible =
              state.phase === "choose_noble" &&
              isMyTurn &&
              state.pending_turn.eligible_nobles.includes(noble.id);
            return (
              <button
                key={noble.id}
                type="button"
                className={`noble-tile ${eligible ? "eligible" : ""}`}
                disabled={!eligible}
                onClick={() => onChooseNoble(noble.id)}
                aria-label={noble.placeholder_label}
              >
                {nobleAssetUrl(noble) ? <img src={nobleAssetUrl(noble)!} alt={noble.placeholder_label} /> : null}
                <span className="sr-only">
                  {noble.placeholder_label} {countsText(noble.requirements)}
                </span>
              </button>
            );
          })
        ) : (
          <p className="muted-copy">No nobles remaining.</p>
        )}
      </div>
    </section>
  );
}

function MarketPanel({
  canEndTurn,
  compactCards,
  isMyTurn,
  onEndTurn,
  onReserveTopDeck,
  onSelectMarketCard,
  state,
}: {
  canEndTurn: boolean;
  compactCards: boolean;
  isMyTurn: boolean;
  onEndTurn: () => void;
  onReserveTopDeck: (tier: number) => void;
  onSelectMarketCard: (selected: SelectedMarketCard) => void;
  state: GameState;
}) {
  return (
    <section className="panel market-panel" data-testid="market-section">
      <div className="panel-heading market-heading">
        <div>
          <h2>Market</h2>
          <p className="panel-caption">Tap a face-up card to buy or reserve it.</p>
        </div>
        <button type="button" className="primary-action market-end-turn" onClick={onEndTurn} disabled={!canEndTurn}>
          End Turn
        </button>
      </div>
      <div className="market-tiers">
        {[1, 2, 3].map((tier) => (
          <section key={tier} className="tier-panel">
            <div className="tier-header">
              <span>{`Tier ${tier}  |  Deck Remaining: ${state.deck_counts[String(tier)] ?? 0}`}</span>
              <button
                type="button"
                className="secondary-button tier-action"
                onClick={() => onReserveTopDeck(tier)}
                disabled={!isMyTurn || state.phase !== "active"}
              >
                Reserve Top Card
              </button>
            </div>
            <div className="tier-row">
              {(state.market[String(tier)] ?? []).map((card, marketIndex) => (
                <button
                  key={card.id}
                  type="button"
                  className="card-button"
                  onClick={() => onSelectMarketCard({ tier, marketIndex, cardId: card.id })}
                  disabled={!isMyTurn || state.phase !== "active"}
                  aria-label={cardButtonLabel(card)}
                >
                  <CardFace card={card} compact={compactCards} />
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function PlayersPanel({
  boardStatusPanel,
  compact,
  isMobileBoard,
  isMyTurn,
  onReservedCardClick,
  session,
  state,
}: {
  boardStatusPanel: ReactNode;
  compact: boolean;
  isMobileBoard: boolean;
  isMyTurn: boolean;
  onReservedCardClick: (reservedIndex: number) => void;
  session: StoredSession;
  state: GameState;
}) {
  return (
    <div className={`players-panel ${isMobileBoard ? "players-panel-mobile" : "players-panel-desktop"}`}>
      {state.players.map((player) => (
        <PlayerCard
          key={player.id}
          compact={compact}
          isMobileBoard={isMobileBoard}
          isMyTurn={isMyTurn}
          onReservedCardClick={onReservedCardClick}
          player={player}
          session={session}
          state={state}
        />
      ))}
      {boardStatusPanel}
    </div>
  );
}

function PlayerCard({
  compact,
  isMobileBoard,
  isMyTurn,
  onReservedCardClick,
  player,
  session,
  state,
}: {
  compact: boolean;
  isMobileBoard: boolean;
  isMyTurn: boolean;
  onReservedCardClick: (reservedIndex: number) => void;
  player: GameState["players"][number];
  session: StoredSession;
  state: GameState;
}) {
  const statuses = playerStatuses(player, state.active_player, session.playerId);
  const heldTokenCount = countFromRecord(player.tokens);
  const isOverflowing = player.id === state.active_player && state.phase === "discard";
  const discardCount = isOverflowing ? state.pending_turn.discard_count : 0;

  return (
    <section className={`player-shell ${compact ? "compact-player-shell" : ""}`}>
      <article
        className={`panel player-panel ${compact ? "player-panel-compact" : ""} ${!isMobileBoard ? "player-panel-split" : ""} ${
          isOverflowing ? "player-panel-warning" : ""
        }`}
      >
        <div className="player-header">
          <div className="player-header-copy">
            <span className="player-id">{player.id}</span>
            <h3>{player.name}</h3>
            <div className="player-statuses">
              {statuses.length > 0 ? (
                statuses.map((status) => (
                  <span key={status} className={`status-chip ${status.toLowerCase()}`}>
                    {status}
                  </span>
                ))
              ) : (
                <span className="muted-chip">Ready</span>
              )}
              <span className={`token-limit-pill ${isOverflowing ? "warning" : ""}`}>
                {isOverflowing ? `Discard ${discardCount}` : `Held ${heldTokenCount}/10`}
              </span>
            </div>
          </div>
          <div className="score-box">
            <strong>{player.score}</strong>
            <span>points</span>
          </div>
        </div>

        <div className={`player-sections ${!isMobileBoard ? "player-sections-side-by-side" : ""}`}>
          <div className="player-section-group">
            <SectionLabel text="Gems and Bonuses" />
            <div className="player-resource-grid">
              {ALL_TOKEN_COLORS.map((color) => (
                <ResourceLink
                  key={color}
                  bonusCount={color === "gold" ? null : Number(player.bonuses[color] ?? 0)}
                  color={color}
                  tokenCount={Number(player.tokens[color] ?? 0)}
                />
              ))}
            </div>
          </div>

          <div className="player-section-group">
            <SectionLabel text="Reserved Cards" />
            <div className="reserved-row">
              {player.reserved_cards.length > 0 ? (
                player.reserved_cards.map((card, index) => {
                  const canBuyReserved = player.id === session.playerId && !(card.masked ?? false) && isMyTurn && state.phase === "active";
                  return (
                    <button
                      key={`${player.id}-${index}`}
                      type="button"
                      className="reserved-card-button"
                      onClick={() => onReservedCardClick(index)}
                      disabled={!canBuyReserved}
                      aria-label={cardButtonLabel(card)}
                    >
                      <CardFace card={card} compact />
                    </button>
                  );
                })
              ) : (
                <p className="muted-copy">No reserved cards</p>
              )}
            </div>
          </div>
        </div>
        {isOverflowing ? <p className="player-warning-copy">Over the 10-gem limit. Discard before the turn can finish.</p> : null}
      </article>
    </section>
  );
}

function SectionLabel({ text }: { text: string }) {
  return <div className="section-label">{text}</div>;
}

function ResourceLink({
  bonusCount,
  color,
  tokenCount,
}: {
  bonusCount: number | null;
  color: typeof ALL_TOKEN_COLORS[number];
  tokenCount: number;
}) {
  const accentStyles =
    tokenCount || (bonusCount ?? 0)
      ? {
          borderColor: color === "white" ? "#d1d5db" : TOKEN_STYLES[color],
          boxShadow: `inset 0 0 0 1px ${color === "white" ? "#d1d5db" : TOKEN_STYLES[color]}`,
        }
      : undefined;

  return (
    <div className="resource-link" title={`${formatColor(color)} held ${tokenCount}${bonusCount === null ? "" : `, bonus ${bonusCount}`}`} style={accentStyles}>
      <div className="resource-link-header">
        <div className={`token-counter-icon ${tokenCount ? "active" : "inactive"}`}>
          <img src={gemAssetUrl(color)} alt="" className={tokenCount ? "" : "dimmed"} />
          {bonusCount !== null ? (
            <span
              className={`bonus-counter-badge ${bonusCount ? "active" : ""}`}
              style={
                bonusCount
                  ? {
                      backgroundColor: TOKEN_STYLES[color],
                      color: tokenTextColor(color),
                      borderColor: color === "white" ? "#d1d5db" : TOKEN_STYLES[color],
                    }
                  : undefined
              }
            >
              +{bonusCount}
            </span>
          ) : null}
          <span
            className={`token-counter-badge ${tokenCount ? "active" : ""}`}
            style={tokenCount ? { backgroundColor: TOKEN_STYLES[color], color: tokenTextColor(color) } : undefined}
          >
            {tokenCount}
          </span>
        </div>
      </div>
      <span className="sr-only">{COLOR_ABBREVIATIONS[color]}</span>
    </div>
  );
}

function CardFace({ card, compact }: { card: CardDef; compact: boolean }) {
  const assetUrl = cardAssetUrl(card);
  if (assetUrl) {
    return <img src={assetUrl} alt={card.placeholder_label} className={compact ? "card-art compact" : "card-art"} />;
  }
  return (
    <div className={`card-fallback ${compact ? "compact" : ""}`}>
      <strong>{card.placeholder_label}</strong>
      {card.masked ? null : (
        <>
          <span>{`Points: ${card.points}  Bonus: ${card.bonus_color}`}</span>
          <span>{`Cost: ${countsText(card.cost)}`}</span>
        </>
      )}
    </div>
  );
}

function canReserveCard(state: GameState, me: GameState["players"][number] | null, isMyTurn: boolean): boolean {
  if (!isMyTurn || state.phase !== "active" || me === null) {
    return false;
  }
  return me.reserved_cards.length < 3;
}

function DiscardModal({
  onBankTokenClick,
  pendingDiscardSelection,
  player,
  state,
}: {
  onBankTokenClick: (color: typeof ALL_TOKEN_COLORS[number]) => void;
  pendingDiscardSelection: Record<string, number>;
  player: GameState["players"][number] | null;
  state: GameState;
}) {
  const selectedCount = countFromRecord(pendingDiscardSelection);

  return (
    <div className="market-overlay" role="dialog" aria-modal="true" aria-labelledby="discard-modal-title">
      <div className="market-dialog modal-dialog discard-dialog">
        <div className="panel-heading">
          <h2 id="discard-modal-title">Discard excess gems</h2>
          <p className="panel-caption">
            You are holding too many gems. Select exactly {state.pending_turn.discard_count} to discard before your turn can end.
          </p>
        </div>
        <div className="discard-modal-grid">
          {ALL_TOKEN_COLORS.map((color) => {
            const available = Number(player?.tokens[color] ?? 0);
            const selected = pendingDiscardSelection[color] ?? 0;
            const disabled = available <= selected;
            return (
              <button
                key={color}
                type="button"
                className={`bank-token discard-choice ${selected ? "selected" : ""}`}
                onClick={() => onBankTokenClick(color)}
                disabled={disabled}
                aria-label={`Discard ${formatColor(color)} token`}
              >
                <img src={gemAssetUrl(color)} alt="" />
                <span className="token-count-badge">{available}</span>
                {selected > 0 ? <span className="token-selection-count">-{selected}</span> : null}
              </button>
            );
          })}
        </div>
        <p className="overlay-hint blocked">
          Discard selection: {selectedCount}/{state.pending_turn.discard_count}. The final click will submit automatically.
        </p>
      </div>
    </div>
  );
}

function WinnerModal({
  message,
  onClose,
  onLeaveRoom,
  players,
  winnerState,
}: {
  message: string;
  onClose: () => void;
  onLeaveRoom: () => void;
  players: GameState["players"];
  winnerState: NonNullable<GameState["winner_state"]>;
}) {
  const winnerNames = winnerState.winner_ids
    .map((winnerId) => players.find((player) => player.id === winnerId)?.name ?? winnerId)
    .join(", ");

  return (
    <div className="market-overlay" role="dialog" aria-modal="true" aria-labelledby="winner-modal-title">
      <div className="market-dialog modal-dialog winner-dialog">
        <div className="panel-heading">
          <h2 id="winner-modal-title">{winnerState.winner_ids.length === 1 ? `${winnerNames} wins` : "Game over"}</h2>
          <p className="panel-caption">{message}</p>
        </div>
        <div className="winner-summary">
          <div className="winner-pill">{winnerNames}</div>
          <p className="winner-reason">{winnerState.reason}</p>
        </div>
        <div className="overlay-actions">
          <button type="button" className="primary-action" onClick={onClose}>
            Close
          </button>
          <button type="button" className="secondary-button" onClick={onLeaveRoom}>
            Leave Room
          </button>
        </div>
      </div>
    </div>
  );
}

function cardButtonLabel(card: CardDef): string {
  if (card.masked) {
    return card.placeholder_label;
  }
  return `${card.placeholder_label}. Points ${card.points}. Bonus ${card.bonus_color}. Cost ${countsText(card.cost)}.`;
}

function pendingStatusText(
  state: GameState,
  pendingGemSelection: string[],
  pendingDiscardSelection: Record<string, number>,
): string {
  if (state.phase === "discard") {
    return `Discard required: ${countFromRecord(pendingDiscardSelection)}/${state.pending_turn.discard_count} selected. Pick tokens from the bank buttons.`;
  }
  if (pendingGemSelection.length > 0) {
    if (pendingGemSelection.length === 1 && (state.bank_tokens[pendingGemSelection[0]] ?? 0) >= 4) {
      return `Pending gems: ${pendingGemSelection[0]}. End Turn will take two ${pendingGemSelection[0]} gems.`;
    }
    return `Pending gems: ${pendingGemSelection.join(", ")}`;
  }
  if (state.phase === "choose_noble") {
    return "Choose one highlighted noble to finish the turn.";
  }
  if (state.phase === "awaiting_end_turn") {
    return "Your gem action is complete. Click End Turn to pass play.";
  }
  return "Click gems to build a legal take, then click End Turn. Click a market card to choose Buy or Reserve.";
}

function tokenTextColor(color: typeof ALL_TOKEN_COLORS[number]): string {
  return color === "white" || color === "gold" ? "#111827" : "#f8fafc";
}

function getBoardMode(width: number, height: number): BoardMode {
  if (width >= 1200) {
    return "desktop";
  }
  if (width >= 860) {
    return "tablet";
  }
  return width > height ? "mobile-landscape" : "mobile-portrait";
}

function useBoardMode(): BoardMode {
  const [boardMode, setBoardMode] = useState<BoardMode>(() => {
    if (typeof window === "undefined") {
      return "desktop";
    }
    return getBoardMode(window.innerWidth, window.innerHeight);
  });

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const handleResize = () => {
      setBoardMode(getBoardMode(window.innerWidth, window.innerHeight));
    };

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return boardMode;
}
