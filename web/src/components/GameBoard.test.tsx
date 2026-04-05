import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameBoard } from "./GameBoard";
import type { GameBoardProps } from "./GameBoard";
import type { GameState, StoredSession } from "../types";

function makeState(): GameState {
  return {
    connected_players: [
      { id: "P1", name: "Alice", connected: true },
      { id: "P2", name: "Bob", connected: true },
    ],
    active_player: "P1",
    bank_tokens: { white: 4, blue: 4, green: 4, red: 4, black: 4, gold: 5 },
    market: {
      "1": [
        {
          id: "card-1",
          tier: 1,
          cost: { white: 1, blue: 2 },
          bonus_color: "red",
          points: 0,
          placeholder_label: "Card One",
          asset_id: "level_one0",
        },
      ],
      "2": [],
      "3": [],
    },
    deck_counts: { "1": 39, "2": 30, "3": 20 },
    players: [
      {
        id: "P1",
        name: "Alice",
        tokens: { white: 0, blue: 0, green: 0, red: 0, black: 0, gold: 0 },
        purchased_cards: [],
        bonuses: { white: 0, blue: 0, green: 0, red: 0, black: 0 },
        reserved_cards: [],
        score: 0,
        claimed_nobles: [],
        purchased_card_count: 0,
        connected: true,
      },
      {
        id: "P2",
        name: "Bob",
        tokens: { white: 0, blue: 0, green: 0, red: 0, black: 0, gold: 0 },
        purchased_cards: [],
        bonuses: { white: 0, blue: 0, green: 0, red: 0, black: 0 },
        reserved_cards: [],
        score: 0,
        claimed_nobles: [],
        purchased_card_count: 0,
        connected: true,
      },
    ],
    nobles_remaining: [
      {
        id: "noble-1",
        requirements: { white: 3, blue: 3 },
        points: 3,
        placeholder_label: "Noble One",
        asset_id: "noble0",
      },
    ],
    nobles_claimed: { P1: [], P2: [] },
    endgame_triggered: false,
    winner_state: null,
    phase: "active",
    pending_turn: {
      discard_count: 0,
      eligible_nobles: [],
      manual_end_turn: false,
      can_end_turn: false,
    },
    message: "Alice starts the game.",
  };
}

function makeProps(overrides: Partial<GameBoardProps> = {}): GameBoardProps {
  const session: StoredSession = {
    roomCode: "ABC123",
    playerId: "P1",
    playerName: "Alice",
    playerToken: "token-1",
  };

  return {
    connected: true,
    connectionHint: "ABC123",
    error: "",
    feedback: "Ready",
    onBankTokenClick: vi.fn(),
    onChooseNoble: vi.fn(),
    onCopyShareLink: vi.fn(),
    onEndTurn: vi.fn(),
    onLeaveRoom: vi.fn(),
    onReservedCardClick: vi.fn(),
    onReserveTopDeck: vi.fn(),
    onSendMarketAction: vi.fn(),
    pendingDiscardSelection: {},
    pendingGemSelection: [],
    session,
    state: makeState(),
    ...overrides,
  };
}

function setViewport(width: number, height: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: height,
  });
}

beforeEach(() => {
  setViewport(1440, 900);
});

afterEach(() => {
  cleanup();
  window.dispatchEvent(new Event("resize"));
});

describe("GameBoard", () => {
  it("renders board sections in desktop order and uses shared asset urls", () => {
    const { getByTestId } = render(<GameBoard {...makeProps()} />);

    const gameScreen = getByTestId("game-screen");
    const bankSection = getByTestId("bank-section");
    const noblesSection = getByTestId("nobles-section");
    const marketSection = getByTestId("market-section");
    const playersSection = getByTestId("players-section");

    expect(gameScreen).toHaveAttribute("data-board-mode", "desktop");
    expect(bankSection.compareDocumentPosition(noblesSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(noblesSection.compareDocumentPosition(marketSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(marketSection.compareDocumentPosition(playersSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const images = Array.from(document.querySelectorAll("img"));
    expect(images.some((image) => image.getAttribute("src")?.includes("/assets/gems/diamond.png"))).toBe(true);
    expect(images.some((image) => image.getAttribute("src")?.includes("/assets/cards/level_one0.png"))).toBe(true);
    expect(images.some((image) => image.getAttribute("src")?.includes("/assets/nobles/noble0.png"))).toBe(true);
  });

  it("places the board status panel after both player cards in the players column", () => {
    render(<GameBoard {...makeProps()} />);

    const playersSection = screen.getByTestId("players-section");
    const statusPanel = within(playersSection).getByTestId("board-status-panel");
    const aliceHeading = within(playersSection).getByText("Alice");
    const bobHeading = within(playersSection).getByText("Bob");

    expect(aliceHeading.compareDocumentPosition(statusPanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(bobHeading.compareDocumentPosition(statusPanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText(/Connected as P1\. Active player:/i)).toBeInTheDocument();
    expect(within(statusPanel).queryByRole("button", { name: "End Turn" })).not.toBeInTheDocument();
  });

  it("switches to tablet mode at mid-size widths", () => {
    setViewport(1000, 820);

    render(<GameBoard {...makeProps()} />);

    expect(screen.getByTestId("game-screen")).toHaveAttribute("data-board-mode", "tablet");
    expect(screen.getAllByRole("button", { name: "Reserve Top Card" })).toHaveLength(3);
  });

  it("uses the landscape mobile layout and keeps core actions reachable", () => {
    setViewport(740, 360);
    const onBankTokenClick = vi.fn();

    const { getByTestId } = render(<GameBoard {...makeProps({ onBankTokenClick })} />);

    const gameScreen = getByTestId("game-screen");
    const bankSection = getByTestId("bank-section");
    const marketSection = getByTestId("market-section");
    const noblesSection = getByTestId("nobles-section");
    const playersSection = getByTestId("players-section");

    expect(gameScreen).toHaveAttribute("data-board-mode", "mobile-landscape");
    expect(marketSection.compareDocumentPosition(noblesSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(noblesSection.compareDocumentPosition(bankSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(bankSection.compareDocumentPosition(playersSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/Room ABC123 \| You P1 \| Turn P1/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /white token/i }));
    expect(onBankTokenClick).toHaveBeenCalledWith("white");

    expect(within(marketSection).getByRole("button", { name: "End Turn" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Share Link" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Leave Room" })).toBeInTheDocument();
  });

  it("supports the portrait fallback without removing gameplay sections", () => {
    setViewport(390, 844);

    render(<GameBoard {...makeProps()} />);

    expect(screen.getByTestId("game-screen")).toHaveAttribute("data-board-mode", "mobile-portrait");
    expect(screen.getByTestId("market-section")).toBeInTheDocument();
    expect(screen.getByTestId("bank-section")).toBeInTheDocument();
    expect(screen.getByTestId("nobles-section")).toBeInTheDocument();
    expect(screen.getByTestId("players-section")).toBeInTheDocument();
  });

  it("opens and closes the market overlay from a market card click", () => {
    render(<GameBoard {...makeProps()} />);

    fireEvent.click(screen.getAllByRole("button", { name: /Card One/i })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buy" })).toBeDisabled();
    expect(screen.getByText(/Need 3 more token\(s\): white 1, blue 2\./i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("styles buy as a real primary action when the local player can afford the card", () => {
    const affordableState = makeState();
    affordableState.players[0].tokens = { white: 1, blue: 2, green: 0, red: 0, black: 0, gold: 0 };

    render(<GameBoard {...makeProps({ state: affordableState })} />);

    fireEvent.click(screen.getAllByRole("button", { name: /Card One/i })[0]);

    expect(screen.getByRole("button", { name: "Buy" })).toBeEnabled();
    expect(screen.getByText("You can buy this card now.")).toBeInTheDocument();
  });

  it("shows a blocking discard modal when the active local player is over the gem limit", () => {
    const discardState = makeState();
    discardState.phase = "discard";
    discardState.pending_turn.discard_count = 2;
    discardState.players[0].tokens = { white: 2, blue: 3, green: 2, red: 2, black: 1, gold: 1 };

    render(<GameBoard {...makeProps({ state: discardState })} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Discard excess gems")).toBeInTheDocument();
    expect(screen.getByText(/Select exactly 2 to discard/i)).toBeInTheDocument();
    expect(screen.getByText("Discard 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Discard White token/i })).toBeInTheDocument();
  });

  it("shows a winner modal as soon as the game ends", () => {
    const winnerState = makeState();
    winnerState.phase = "game_over";
    winnerState.message = "Alice wins with 15 points.";
    winnerState.winner_state = {
      winner_ids: ["P1"],
      reason: "highest score, then fewest purchased development cards",
    };

    render(<GameBoard {...makeProps({ state: winnerState })} />);

    const modal = screen.getByRole("dialog");
    expect(modal).toBeInTheDocument();
    expect(within(modal).getByText("Alice wins")).toBeInTheDocument();
    expect(within(modal).getByText("Alice wins with 15 points.")).toBeInTheDocument();
    expect(within(modal).getByText(/highest score, then fewest purchased development cards/i)).toBeInTheDocument();
    expect(within(modal).getByRole("button", { name: "Leave Room" })).toBeInTheDocument();
  });

  it("keeps both player cards and reserved cards visible after the compact player panel redesign", () => {
    const panelState = makeState();
    panelState.players[0].reserved_cards = [
      {
        id: "reserved-1",
        tier: 1,
        cost: { red: 2 },
        bonus_color: "blue",
        points: 1,
        placeholder_label: "Reserved One",
        asset_id: "level_one0",
      },
    ];

    render(<GameBoard {...makeProps({ state: panelState })} />);

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getAllByText("Gems and Bonuses")).toHaveLength(2);
    expect(screen.getAllByText("Held 0/10")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Reserved One/i })).toBeInTheDocument();
  });
});
