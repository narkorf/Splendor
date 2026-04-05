"""PySide6 user interface for the Splendor prototype."""

from __future__ import annotations

from functools import partial
import time
from typing import Any

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .constants import ALL_TOKEN_COLORS, TIER_LEVELS
from .assets import load_asset_bytes
from .network import DISCOVERY_PORT, GameClient, GameDiscoveryClient, GameServer


TOKEN_STYLES = {
    "white": "#f2f2f2",
    "blue": "#4c78dd",
    "green": "#2a9d5b",
    "red": "#d1495b",
    "black": "#333333",
    "gold": "#d9a404",
}

GEM_ASSET_NAMES = {
    "white": "diamond",
    "green": "emerald",
    "gold": "gold",
    "black": "onyx",
    "red": "ruby",
    "blue": "sapphire",
}


COLOR_ABBREVIATIONS = {
    "white": "Wht",
    "blue": "Blu",
    "green": "Grn",
    "red": "Red",
    "black": "Blk",
    "gold": "Gld",
}


class QtClientBridge(QObject):
    message_received = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.client = GameClient(self._emit_message)

    def _emit_message(self, message: dict[str, Any]) -> None:
        self.message_received.emit(message)

    def connect_to(self, host: str, port: int, name: str) -> None:
        self.client.connect(host, port, name)

    def send_action(self, action: str, payload: dict[str, Any] | None = None) -> None:
        self.client.send_action(action, payload)

    def close(self) -> None:
        self.client.close()


class QtDiscoveryBridge(QObject):
    games_updated = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.discovery_client = GameDiscoveryClient(self._emit_games)
        self.discovery_client.start()

    def _emit_games(self, games: list[dict[str, Any]]) -> None:
        self.games_updated.emit(games)

    def close(self) -> None:
        self.discovery_client.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Splendor Desktop Prototype")
        self.resize(1400, 900)

        self.server: GameServer | None = None
        self.client_bridge: QtClientBridge | None = None
        self.discovery_bridge: QtDiscoveryBridge | None = None
        self.player_id: str | None = None
        self.connection_hint = ""
        self.state: dict[str, Any] | None = None
        self.discovered_games: list[dict[str, Any]] = []
        self.pending_gems: list[str] = []
        self.pending_discard: dict[str, int] = {}
        self.pending_end_after_gem_submit = False
        self.selected_market_card: dict[str, Any] | None = None
        self.market_action_popover_visible = False
        self._pixmap_cache: dict[tuple[str, ...], QPixmap | None] = {}

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._build_start_page()
        self._build_browse_page()
        self._build_game_page()
        self.discovery_bridge = QtDiscoveryBridge()
        self.discovery_bridge.games_updated.connect(self.handle_discovered_games)
        self.stack.setCurrentWidget(self.start_page)

    def _build_start_page(self) -> None:
        self.start_page = QWidget()
        layout = QVBoxLayout(self.start_page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)

        title = QLabel("Splendor 2-Player Desktop Prototype")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel("Host a room or browse games available on your local network.")
        subtitle.setWordWrap(True)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Player name")
        self.name_input.setText("Player")

        host_box = QGroupBox("Host Game")
        host_form = QFormLayout(host_box)
        self.host_port_input = QSpinBox()
        self.host_port_input.setRange(0, 65535)
        self.host_port_input.setValue(5000)
        self.host_button = QPushButton("Host Game")
        self.host_button.clicked.connect(self.host_game)
        host_form.addRow("Your name", self.name_input)
        host_form.addRow("Port", self.host_port_input)
        host_form.addRow(self.host_button)

        browse_box = QGroupBox("Browse Games")
        browse_form = QFormLayout(browse_box)
        browse_description = QLabel("Find LAN games automatically instead of entering an IP and port.")
        browse_description.setWordWrap(True)
        self.browse_button = QPushButton("Browse Games")
        self.browse_button.clicked.connect(self.show_browse_games)
        browse_form.addRow(browse_description)
        browse_form.addRow(self.browse_button)

        self.host_debug_label = QLabel(f"LAN discovery uses UDP {DISCOVERY_PORT}.")
        self.host_debug_label.setWordWrap(True)
        self.host_debug_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")

        self.start_status = QLabel("Choose Host Game or Browse Games.")
        self.start_status.setWordWrap(True)
        self.start_status.setStyleSheet(
            "padding: 8px; background: #f4f0e8; color: #111827; border: 1px solid #b8a88d;"
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(host_box)
        layout.addWidget(browse_box)
        layout.addWidget(self.host_debug_label)
        layout.addWidget(self.start_status)
        layout.addStretch(1)
        self.stack.addWidget(self.start_page)

    def _build_browse_page(self) -> None:
        self.browse_page = QWidget()
        layout = QVBoxLayout(self.browse_page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)

        header_row = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.show_start_page)
        header_row.addWidget(back_button)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        title = QLabel("Browse LAN Games")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel("Games on your local network appear automatically below.")
        subtitle.setWordWrap(True)

        self.browse_name_input = QLineEdit()
        self.browse_name_input.setPlaceholderText("Player name")
        self.browse_name_input.setText("Player")

        name_box = QGroupBox("Join As")
        name_form = QFormLayout(name_box)
        name_form.addRow("Your name", self.browse_name_input)

        games_box = QGroupBox("Available Games")
        games_layout = QVBoxLayout(games_box)
        self.browse_scroll = QScrollArea()
        self.browse_scroll.setWidgetResizable(True)
        browse_content = QWidget()
        self.browse_games_layout = QVBoxLayout(browse_content)
        self.browse_scroll.setWidget(browse_content)
        games_layout.addWidget(self.browse_scroll)

        self.browse_status = QLabel("Listening for games on your local network...")
        self.browse_status.setWordWrap(True)
        self.browse_status.setStyleSheet(
            "padding: 8px; background: #f4f0e8; color: #111827; border: 1px solid #b8a88d;"
        )
        self.browse_debug_label = QLabel(f"Listening on UDP {DISCOVERY_PORT}. Last packet: none yet.")
        self.browse_debug_label.setWordWrap(True)
        self.browse_debug_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(name_box)
        layout.addWidget(games_box, 1)
        layout.addWidget(self.browse_debug_label)
        layout.addWidget(self.browse_status)
        self.stack.addWidget(self.browse_page)

    def _build_game_page(self) -> None:
        self.game_page = QScrollArea()
        self.game_page.setWidgetResizable(True)
        game_content = QWidget()
        self.game_content = game_content
        self.game_page.setWidget(game_content)
        root = QVBoxLayout(game_content)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.banner_label = QLabel("Waiting for connection.")
        self.banner_label.setWordWrap(True)
        self.banner_label.setStyleSheet("padding: 10px; background: #1f2937; color: white; border-radius: 6px;")
        self.connection_label = QLabel("")
        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet(
            "padding: 8px; background: #fff4d6; color: #111827; border: 1px solid #d4b466;"
        )

        root.addWidget(self.banner_label)
        root.addWidget(self.connection_label)
        root.addWidget(self.feedback_label)

        control_row = QHBoxLayout()
        self.end_turn_button = QPushButton("End Turn")
        self.end_turn_button.clicked.connect(self.end_turn)
        self.end_turn_button.setEnabled(False)
        control_row.addWidget(self.end_turn_button)
        control_row.addStretch(1)
        root.addLayout(control_row)

        content_row = QHBoxLayout()

        left_column = QVBoxLayout()
        self.bank_group = QGroupBox("Bank Tokens")
        bank_layout = QGridLayout(self.bank_group)
        self.bank_buttons: dict[str, QPushButton] = {}
        for index, color in enumerate(ALL_TOKEN_COLORS):
            button = QPushButton()
            button.setMinimumHeight(60)
            button.clicked.connect(partial(self.on_bank_token_clicked, color))
            self.bank_buttons[color] = button
            bank_layout.addWidget(button, index // 2, index % 2)
        left_column.addWidget(self.bank_group)

        self.discard_status = QLabel("")
        self.discard_status.setWordWrap(True)
        left_column.addWidget(self.discard_status)

        self.nobles_group = QGroupBox("Nobles")
        self.nobles_layout = QVBoxLayout(self.nobles_group)
        left_column.addWidget(self.nobles_group)
        left_column.addStretch(1)

        center_column = QVBoxLayout()
        self.market_group = QGroupBox("Market")
        self.market_layout = QVBoxLayout(self.market_group)
        center_column.addWidget(self.market_group)

        players_container = QWidget()
        self.players_layout = QVBoxLayout(players_container)

        content_row.addLayout(left_column, 1)
        content_row.addLayout(center_column, 2)
        content_row.addWidget(players_container, 2)
        root.addLayout(content_row)

        self.market_action_overlay = QWidget(self.game_page.viewport())
        self.market_action_overlay.hide()
        self.market_action_overlay.setStyleSheet("background: rgba(0, 0, 0, 170);")
        overlay_layout = QVBoxLayout(self.market_action_overlay)
        overlay_layout.setContentsMargins(32, 32, 32, 32)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.market_action_dialog = QFrame()
        self.market_action_dialog.setStyleSheet(
            "background: #323232;"
            "border-radius: 16px;"
        )
        self.market_action_dialog_layout = QVBoxLayout(self.market_action_dialog)
        self.market_action_dialog_layout.setContentsMargins(18, 18, 18, 18)
        self.market_action_dialog_layout.setSpacing(12)
        overlay_layout.addWidget(self.market_action_dialog, 0, Qt.AlignmentFlag.AlignCenter)
        self._update_market_action_overlay_geometry()
        self.stack.addWidget(self.game_page)

    def host_game(self) -> None:
        name = self.name_input.text().strip() or "Host"
        self.server = GameServer(port=self.host_port_input.value(), advertised_name=name)
        try:
            _, port = self.server.start()
        except OSError as exc:
            self.server = None
            self.start_status.setText(f"Unable to host: {exc}")
            self.host_debug_label.setText(f"Host broadcast inactive. UDP {DISCOVERY_PORT} could not start.")
            return
        self.start_status.setText(f"Hosting on {self.server.connection_hint()}. Connecting local client...")
        self.host_debug_label.setText(
            f"Broadcasting LAN discovery on UDP {DISCOVERY_PORT} for TCP {port}."
        )
        self._connect_client("127.0.0.1", port, name)

    def show_browse_games(self) -> None:
        self.browse_name_input.setText(self.name_input.text().strip() or "Player")
        self._render_discovered_games()
        self.stack.setCurrentWidget(self.browse_page)

    def show_start_page(self) -> None:
        self.name_input.setText(self.browse_name_input.text().strip() or "Player")
        self.stack.setCurrentWidget(self.start_page)

    def _connect_client(self, host: str, port: int, name: str) -> None:
        try:
            if self.client_bridge is not None:
                self.client_bridge.close()
            self.client_bridge = QtClientBridge()
            self.client_bridge.message_received.connect(self.handle_network_message)
            self.client_bridge.connect_to(host, port, name)
            self.stack.setCurrentWidget(self.game_page)
            self.feedback_label.setText("Connecting...")
        except OSError as exc:
            self.set_feedback(f"Connection failed: {exc}")

    def handle_network_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "joined":
            self.player_id = message.get("player_id")
            self.connection_hint = str(message.get("connection_hint", ""))
            self.connection_label.setText(f"Connected as {self.player_id}. Room detail: {self.connection_hint}")
            self.feedback_label.setText("Connected. Waiting for synchronized state.")
            return
        if message_type == "state":
            self.state = dict(message["state"])
            self.banner_label.setText(self.state.get("message", ""))
            self.render_state()
            return
        if message_type == "error":
            self.set_feedback(str(message.get("message", "Unknown error.")))
            return
        if message_type == "connection_closed":
            self.set_feedback("Connection closed.")

    def handle_discovered_games(self, games: list[dict[str, Any]]) -> None:
        self.discovered_games = list(games)
        self._render_discovered_games()

    def _render_discovered_games(self) -> None:
        if not hasattr(self, "browse_games_layout"):
            return
        self._clear_layout(self.browse_games_layout)
        if not self.discovered_games:
            empty_label = QLabel("No LAN games found yet.")
            empty_label.setStyleSheet("color: #667085;")
            self.browse_games_layout.addWidget(empty_label)
            self.browse_games_layout.addStretch(1)
            self.browse_status.setText("Listening for games on your local network...")
            self.browse_debug_label.setText(f"Listening on UDP {DISCOVERY_PORT}. Last packet: none yet.")
            return
        waiting_count = sum(1 for game in self.discovered_games if game["joinable"])
        self.browse_status.setText(
            f"Found {len(self.discovered_games)} game(s) on your network. {waiting_count} ready to join."
        )
        latest_game = max(self.discovered_games, key=lambda game: float(game.get("last_seen", 0.0)))
        seen_at = time.strftime("%H:%M:%S", time.localtime(float(latest_game.get("last_seen", 0.0))))
        self.browse_debug_label.setText(
            "Listening on UDP "
            f"{DISCOVERY_PORT}. Last packet: {latest_game['host_name']} at "
            f"{latest_game['host']}:{latest_game['port']} ({latest_game['status']}) at {seen_at}."
        )
        for game in self.discovered_games:
            self.browse_games_layout.addWidget(self._make_discovered_game_widget(game))
        self.browse_games_layout.addStretch(1)

    def _make_discovered_game_widget(self, game: dict[str, Any]) -> QWidget:
        box = QGroupBox()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        details = QVBoxLayout()
        host_name = QLabel(game["host_name"])
        host_name.setStyleSheet("font-size: 16px; font-weight: 700;")
        details.addWidget(host_name)
        details.addWidget(QLabel(f"Address: {game['host']}:{game['port']}"))
        details.addWidget(QLabel(f"Players: {game['player_count']}/{2}"))
        status_label = QLabel(f"Status: {game['status']}")
        status_label.setStyleSheet(
            f"color: {'#1d4ed8' if game['joinable'] else '#6b7280'}; font-weight: 700;"
        )
        details.addWidget(status_label)
        layout.addLayout(details, 1)

        join_button = QPushButton("Join")
        join_button.setMinimumHeight(38)
        join_button.setEnabled(bool(game["joinable"]))
        join_button.clicked.connect(partial(self.join_discovered_game, game["host"], int(game["port"])))
        layout.addWidget(join_button)
        return box

    def join_discovered_game(self, host: str, port: int) -> None:
        name = self.browse_name_input.text().strip() or "Player"
        self._connect_client(host, port, name)

    def render_state(self) -> None:
        if self.state is None:
            return
        active_player = self.state.get("active_player")
        phase = self.state.get("phase")
        is_my_turn = self.player_id == active_player
        self._sync_market_card_selection()
        self._refresh_market_action_overlay()
        self.connection_label.setText(
            f"Connected as {self.player_id}. Active player: {active_player or 'n/a'}. "
            f"Phase: {phase}. Room detail: {self.connection_hint}"
        )
        self._update_local_controls()
        self.discard_status.setText(self._pending_text())
        self._render_bank()
        self._render_market()
        self._render_players()
        self._render_nobles()
        pending_turn = self.state.get("pending_turn", {})
        if (
            self.pending_end_after_gem_submit
            and self.player_id == active_player
            and phase == "awaiting_end_turn"
            and pending_turn.get("can_end_turn", False)
        ):
            self.pending_end_after_gem_submit = False
            self.send_action("end_turn", {})
            return
        if not is_my_turn and phase not in {"lobby", "game_over"}:
            self.feedback_label.setText("Waiting for the active player.")
        elif phase == "game_over":
            winner_state = self.state.get("winner_state") or {}
            winners = ", ".join(winner_state.get("winner_ids", []))
            self.feedback_label.setText(f"Match finished. Winner state: {winners}.")
        elif phase == "active" and not self.pending_gems:
            self.pending_end_after_gem_submit = False

    def _render_bank(self) -> None:
        assert self.state is not None
        bank = self.state["bank_tokens"]
        for color, button in self.bank_buttons.items():
            count = bank.get(color, 0)
            selected_count = self.pending_gems.count(color)
            gem_asset_name = GEM_ASSET_NAMES.get(color, color)
            gem_pixmap = self._load_pixmap("gems", f"{gem_asset_name}.png")
            self._apply_button_pixmap(button, gem_pixmap, QSize(56, 56))
            text_color = "white"
            border_width = 4 if selected_count else 1
            border_color = "#facc15" if selected_count else "#444"
            if gem_pixmap is not None:
                button.setText(str(count))
                button.setStyleSheet(
                    f"background: transparent; color: {text_color}; font-size: 18px; font-weight: 800; "
                    f"border: {border_width}px solid {border_color}; text-align: bottom right; padding: 8px;"
                )
            else:
                button.setText(f"{color.title()}\n{count}")
                button.setStyleSheet(
                    "background: "
                    f"{TOKEN_STYLES[color]}; color: {text_color}; font-weight: 700; "
                    f"border: {border_width}px solid {border_color}; text-align: left; padding: 8px;"
                )
            button.setEnabled(color != "gold")

    def _render_market(self) -> None:
        self._clear_layout(self.market_layout)
        assert self.state is not None
        deck_counts = self.state["deck_counts"]
        for tier in TIER_LEVELS:
            tier_box = QGroupBox()
            tier_layout = QVBoxLayout(tier_box)
            header_row = QHBoxLayout()
            header_row.addWidget(QLabel(f"Tier {tier}  |  Deck Remaining: {deck_counts[str(tier)]}"))
            reserve_top_button = QPushButton("Reserve Top Card")
            reserve_top_button.clicked.connect(partial(self.reserve_top_deck, tier))
            tier_is_active = self.state.get("active_player") == self.player_id and self.state.get("phase") == "active"
            reserve_top_button.setEnabled(tier_is_active)
            header_row.addWidget(reserve_top_button)
            header_row.addStretch(1)
            row = QHBoxLayout()
            for index, card in enumerate(self.state["market"][str(tier)]):
                button = self._make_card_button(card)
                button.clicked.connect(partial(self.on_market_card_clicked, tier, index))
                row.addWidget(button)
            tier_layout.addLayout(header_row)
            tier_layout.addLayout(row)
            self.market_layout.addWidget(tier_box)
        self.market_layout.addStretch(1)

    def _render_players(self) -> None:
        self._clear_layout(self.players_layout)
        assert self.state is not None
        for player in self.state["players"]:
            box = QGroupBox()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(12)
            layout.addLayout(self._make_player_header_layout(player))
            layout.addWidget(self._make_section_label("Held Gems"))
            layout.addLayout(self._make_token_summary_layout(player["tokens"]))
            layout.addWidget(self._make_section_label("Bonuses"))
            layout.addLayout(self._make_bonus_summary_layout(player["bonuses"]))
            layout.addLayout(self._make_player_meta_layout(player))
            layout.addWidget(self._make_section_label("Reserved Cards"))
            reserved_row = QHBoxLayout()
            reserved_row.setSpacing(8)
            if player["reserved_cards"]:
                for index, card in enumerate(player["reserved_cards"]):
                    button = self._make_card_button(card, compact=True)
                    is_local = player["id"] == self.player_id
                    if is_local:
                        button.clicked.connect(partial(self.on_reserved_card_clicked, index))
                    else:
                        button.setEnabled(False)
                    reserved_row.addWidget(button)
            else:
                empty_reserved = QLabel("No reserved cards")
                empty_reserved.setStyleSheet(f"color: {self._panel_muted_text()}; font-size: 12px;")
                reserved_row.addWidget(empty_reserved)
            reserved_row.addStretch(1)
            layout.addLayout(reserved_row)
            self.players_layout.addWidget(box)
        self.players_layout.addStretch(1)

    def _render_nobles(self) -> None:
        self._clear_layout(self.nobles_layout)
        assert self.state is not None
        eligible = set(self.state["pending_turn"].get("eligible_nobles", []))
        phase = self.state.get("phase")
        for noble in self.state["nobles_remaining"]:
            button = self._make_noble_button(noble)
            if phase == "choose_noble" and noble["id"] in eligible and self.state["active_player"] == self.player_id:
                button.clicked.connect(partial(self.choose_noble, noble["id"]))
            else:
                button.setEnabled(False)
            self.nobles_layout.addWidget(button)
        if not self.state["nobles_remaining"]:
            self.nobles_layout.addWidget(QLabel("No nobles remaining."))
        self.nobles_layout.addStretch(1)

    def on_bank_token_clicked(self, color: str) -> None:
        if self.state is None:
            return
        phase = self.state.get("phase")
        if phase == "discard":
            self.add_discard_selection(color)
            return
        if phase != "active":
            self.set_feedback("Gem selection is only available during an active turn.")
            return
        if self.state.get("active_player") != self.player_id:
            self.set_feedback("Only the active player can take gems.")
            return
        bank = self.state["bank_tokens"]
        if bank.get(color, 0) <= 0:
            self.set_feedback(f"No {color} gems remain in the bank.")
            return
        if color in self.pending_gems:
            self.pending_gems.remove(color)
            self._render_bank()
            self._update_local_controls()
            self.discard_status.setText(self._pending_text())
            if self.pending_gems:
                self.set_feedback(f"Removed {color}. Pending gems: {', '.join(self.pending_gems)}.")
            else:
                self.set_feedback("Gem selection cleared.")
            return
        if len(self.pending_gems) >= 3:
            self.set_feedback("You can only have up to three different gem colors selected.")
            return
        self.pending_gems.append(color)
        self._render_bank()
        self._update_local_controls()
        if len(self.pending_gems) == 1:
            if bank.get(color, 0) >= 4:
                self.set_feedback(
                    f"Selected {color}. Click End Turn to take two {color} gems, or pick different colors for a three-gem take."
                )
            else:
                self.set_feedback(
                    f"Selected {color}. Pick two different colors, or re-click {color} to clear it."
                )
        elif len(self.pending_gems) == 2:
            self.set_feedback(f"Selected {', '.join(self.pending_gems)}. Pick one more different gem.")
        else:
            self.set_feedback(f"Selected {', '.join(self.pending_gems)}. Click End Turn to take them.")
        self.discard_status.setText(self._pending_text())

    def on_market_card_clicked(self, tier: int, market_index: int) -> None:
        if self.state is None:
            return
        if self.state.get("active_player") != self.player_id:
            self.set_feedback("Only the active player can act.")
            return
        if self.state.get("phase") != "active":
            self.set_feedback("Cards can only be used during the active phase.")
            return
        card = self.state["market"][str(tier)][market_index]
        self.selected_market_card = {
            "tier": tier,
            "market_index": market_index,
            "card_id": card["id"],
        }
        self._show_market_action_overlay()

    def on_reserved_card_clicked(self, reserved_index: int) -> None:
        if self.state is None:
            return
        if self.state.get("active_player") != self.player_id:
            self.set_feedback("Only the active player can buy reserved cards.")
            return
        if self.state.get("phase") != "active":
            self.set_feedback("Reserved cards can only be bought during the active phase.")
            return
        self.send_action("buy_reserved_card", {"reserved_index": reserved_index})

    def reserve_top_deck(self, tier: int) -> None:
        if self.state is None:
            return
        if self.state.get("active_player") != self.player_id:
            self.set_feedback("Only the active player can reserve cards.")
            return
        if self.state.get("phase") != "active":
            self.set_feedback("Top-deck reservation is only available during the active phase.")
            return
        self._clear_market_card_selection()
        self._hide_market_action_overlay()
        self.send_action("reserve_card", {"tier": tier, "top_deck": True})

    def add_discard_selection(self, color: str) -> None:
        assert self.state is not None
        if self.state.get("active_player") != self.player_id:
            self.set_feedback("Only the active player can discard.")
            return
        target = int(self.state["pending_turn"].get("discard_count", 0))
        local_player = self.local_player()
        if local_player is None:
            return
        selected = self.pending_discard.get(color, 0)
        if selected >= local_player["tokens"].get(color, 0):
            self.set_feedback(f"You do not have more {color} tokens to discard.")
            return
        if sum(self.pending_discard.values()) >= target:
            self.set_feedback("Discard selection already meets the required total.")
            return
        self.pending_discard[color] = selected + 1
        self.discard_status.setText(self._pending_text())
        if sum(self.pending_discard.values()) == target:
            self.send_action("discard_excess_tokens", {"tokens": dict(self.pending_discard)})
            self.pending_discard = {}

    def choose_noble(self, noble_id: str) -> None:
        self.send_action("choose_noble", {"noble_id": noble_id})

    def end_turn(self) -> None:
        if self.state is None:
            return
        phase = self.state.get("phase")
        if phase == "active":
            if not self.pending_gems:
                self.set_feedback("Select gems first.")
                return
            if not self._can_submit_pending_gems():
                self.set_feedback("Finish selecting a legal gem take, or reset your gem picks.")
                return
            self.pending_end_after_gem_submit = True
            self.send_action("take_gems", {"colors": self._gem_action_payload()})
            self.pending_gems = []
            self._render_bank()
            self._update_local_controls()
            self.discard_status.setText(self._pending_text())
            return
        if phase != "awaiting_end_turn":
            self.set_feedback("End Turn is only available after selecting gems or completing a gem-taking turn.")
            return
        self.send_action("end_turn", {})

    def send_action(self, action: str, payload: dict[str, Any]) -> None:
        if self.client_bridge is None:
            return
        self.pending_gems = []
        self.client_bridge.send_action(action, payload)

    def local_player(self) -> dict[str, Any] | None:
        if self.state is None or self.player_id is None:
            return None
        for player in self.state["players"]:
            if player["id"] == self.player_id:
                return player
        return None

    def set_feedback(self, message: str) -> None:
        self.feedback_label.setText(message)
        self.start_status.setText(message)
        self.browse_status.setText(message)

    def _pending_text(self) -> str:
        if self.state is None:
            return ""
        phase = self.state.get("phase")
        if phase == "discard":
            target = int(self.state["pending_turn"].get("discard_count", 0))
            return f"Discard required: {sum(self.pending_discard.values())}/{target} selected. Pick tokens from the bank buttons."
        if self.pending_gems:
            if len(self.pending_gems) == 1:
                color = self.pending_gems[0]
                if self.state["bank_tokens"].get(color, 0) >= 4:
                    return f"Pending gems: {color}. End Turn will take two {color} gems."
            return f"Pending gems: {', '.join(self.pending_gems)}"
        if phase == "choose_noble":
            return "Choose one highlighted noble to finish the turn."
        if phase == "awaiting_end_turn":
            return "Your gem action is complete. Click End Turn to pass play."
        return "Click gems to build a legal take, then click End Turn. Click a market card to choose Buy or Reserve."

    def _make_card_button(self, card: dict[str, Any], compact: bool = False) -> QPushButton:
        label = card["placeholder_label"]
        is_masked = bool(card.get("masked"))
        if not is_masked:
            label = (
                f"{label}\n"
                f"Points: {card['points']}  Bonus: {card['bonus_color']}\n"
                f"Cost: {self._counts_text(card['cost'])}"
            )
        button = QPushButton(label)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setMinimumWidth(120 if compact else 165)
        button.setMinimumHeight(180 if compact else 250)
        button.setStyleSheet(
            "background: #f8fafc; color: #111827; border: 1px solid #445; "
            f"text-align: {'center' if is_masked else 'left'}; padding: 8px; font-weight: 600;"
        )
        button.setToolTip(label)
        asset_id = None
        if card.get("masked"):
            asset_id = card.get("card_back_asset_id")
        else:
            asset_id = card.get("asset_id")
        if asset_id:
            pixmap = self._load_pixmap("cards", f"{asset_id}.png")
            if pixmap is not None:
                image_size = QSize(120, 170) if compact else QSize(170, 240)
                self._apply_button_pixmap(button, pixmap, image_size)
                button.setStyleSheet("background: transparent; border: none; padding: 0;")
                button.setText("")
        return button

    def _make_noble_button(self, noble: dict[str, Any]) -> QPushButton:
        label = (
            f"{noble['placeholder_label']}\n"
            f"Points: {noble['points']}\n"
            f"Needs: {self._counts_text(noble['requirements'])}"
        )
        button = QPushButton(label)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setMinimumWidth(165)
        button.setMinimumHeight(220)
        button.setStyleSheet(
            "background: #f8fafc; color: #111827; border: 1px solid #445; "
            "text-align: left; padding: 8px; font-weight: 600;"
        )
        button.setToolTip(label)
        asset_id = noble.get("asset_id")
        if asset_id:
            pixmap = self._load_pixmap("nobles", f"{asset_id}.png")
            if pixmap is not None:
                self._apply_button_pixmap(button, pixmap, QSize(170, 170))
                button.setStyleSheet("background: transparent; border: none; padding: 0;")
                button.setText("")
        return button

    def _can_afford_card(self, card: dict[str, Any]) -> bool:
        local_player = self.local_player()
        if local_player is None:
            return False
        gold_needed = 0
        for color in TOKEN_STYLES:
            if color == "gold":
                continue
            cost = int(card["cost"].get(color, 0))
            discount = int(local_player["bonuses"].get(color, 0))
            remaining = max(0, cost - discount)
            available = int(local_player["tokens"].get(color, 0))
            gold_needed += max(0, remaining - available)
        return gold_needed <= int(local_player["tokens"].get("gold", 0))

    def _can_submit_pending_gems(self) -> bool:
        if self.state is None:
            return False
        if self.state.get("phase") != "active":
            return False
        bank = self.state["bank_tokens"]
        if len(self.pending_gems) == 1:
            color = self.pending_gems[0]
            return color in ALL_TOKEN_COLORS and color != "gold" and bank.get(color, 0) >= 4
        if len(self.pending_gems) == 3 and len(set(self.pending_gems)) == 3:
            return all(color in ALL_TOKEN_COLORS and color != "gold" and bank.get(color, 0) >= 1 for color in self.pending_gems)
        return False

    def _gem_action_payload(self) -> list[str]:
        if len(self.pending_gems) == 1:
            return [self.pending_gems[0], self.pending_gems[0]]
        return list(self.pending_gems)

    def _update_local_controls(self) -> None:
        if self.state is None:
            self.end_turn_button.setEnabled(False)
            return
        active_player = self.state.get("active_player")
        phase = self.state.get("phase")
        pending_turn = self.state.get("pending_turn", {})
        has_started_gem_pick = bool(self.pending_gems)
        self.end_turn_button.setEnabled(
            self.player_id == active_player
            and (
                (phase == "active" and has_started_gem_pick)
                or (phase == "awaiting_end_turn" and pending_turn.get("can_end_turn", False))
            )
        )

    @staticmethod
    def _counts_text(counts: dict[str, int]) -> str:
        parts = [f"{color[0].upper()}:{count}" for color, count in counts.items() if count]
        return ", ".join(parts) if parts else "None"

    def _sync_market_card_selection(self) -> None:
        if self.state is None or self.selected_market_card is None:
            return
        if self.state.get("phase") != "active" or self.state.get("active_player") != self.player_id:
            self._clear_market_card_selection()
            self._hide_market_action_overlay()
            return
        tier = int(self.selected_market_card["tier"])
        market_cards = self.state["market"].get(str(tier), [])
        market_index = int(self.selected_market_card["market_index"])
        if market_index < 0 or market_index >= len(market_cards):
            self._clear_market_card_selection()
            self._hide_market_action_overlay()
            return
        if market_cards[market_index]["id"] != self.selected_market_card["card_id"]:
            self._clear_market_card_selection()
            self._hide_market_action_overlay()

    def _clear_market_card_selection(self) -> None:
        self.selected_market_card = None
        self.market_action_popover_visible = False

    def _show_market_action_overlay(self) -> None:
        self.market_action_popover_visible = True
        self._refresh_market_action_overlay()
        self._update_market_action_overlay_geometry()
        self.market_action_overlay.show()
        self.market_action_overlay.raise_()

    def _hide_market_action_overlay(self) -> None:
        self.market_action_overlay.hide()

    def _refresh_market_action_overlay(self) -> None:
        self._clear_layout(self.market_action_dialog_layout)
        if not self.market_action_popover_visible:
            self.market_action_overlay.hide()
            return
        selected = self._selected_market_card_payload()
        if selected is None:
            self.market_action_overlay.hide()
            return
        tier, market_index, card = selected
        self.market_action_dialog_layout.addWidget(self._make_market_action_overlay_content(tier, market_index, card))
        self.market_action_overlay.show()
        self.market_action_overlay.raise_()

    def _selected_market_card_payload(self) -> tuple[int, int, dict[str, Any]] | None:
        if not self.market_action_popover_visible or self.selected_market_card is None or self.state is None:
            return None
        tier = int(self.selected_market_card["tier"])
        market_cards = self.state["market"].get(str(tier), [])
        market_index = int(self.selected_market_card["market_index"])
        if market_index < 0 or market_index >= len(market_cards):
            return None
        card = market_cards[market_index]
        if card["id"] != self.selected_market_card["card_id"]:
            return None
        return tier, market_index, card

    def _make_market_action_overlay_content(self, tier: int, market_index: int, card: dict[str, Any]) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card_button = self._make_card_button(card)
        card_button.setEnabled(False)
        layout.addWidget(card_button, 0, Qt.AlignmentFlag.AlignCenter)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        buy_button = QPushButton("Buy")
        reserve_button = QPushButton("Reserve")
        cancel_button = QPushButton("Cancel")
        for button in (buy_button, reserve_button, cancel_button):
            button.setMinimumHeight(40)
            button.setMinimumWidth(110)
            button.setStyleSheet(
                "QPushButton {"
                "background: #444444;"
                "color: #f3f4f6;"
                "border: 1px solid #696969;"
                "border-radius: 10px;"
                "padding: 8px 14px;"
                "font-weight: 700;"
                "}"
                "QPushButton:disabled {"
                "color: #9ca3af;"
                "border-color: #4b5563;"
                "background: #2a2a2a;"
                "}"
            )
        button_row.addStretch(1)
        button_row.addWidget(buy_button)
        button_row.addWidget(reserve_button)
        button_row.addWidget(cancel_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        buy_enabled, buy_reason = self._market_buy_action_state(card)
        reserve_enabled, reserve_reason = self._market_reserve_action_state()
        buy_button.setEnabled(buy_enabled)
        reserve_button.setEnabled(reserve_enabled)
        if buy_enabled:
            buy_button.clicked.connect(partial(self._buy_selected_market_card, tier, market_index))
        if reserve_enabled:
            reserve_button.clicked.connect(partial(self._reserve_selected_market_card, tier, market_index))
        cancel_button.clicked.connect(self._cancel_selected_market_card)

        return content

    def _market_buy_action_state(self, card: dict[str, Any]) -> tuple[bool, str]:
        if self.state is None or self.state.get("phase") != "active" or self.state.get("active_player") != self.player_id:
            return False, "Only available during your active turn."
        if self._can_afford_card(card):
            return True, ""
        return False, self._missing_tokens_reason(card)

    def _market_reserve_action_state(self) -> tuple[bool, str]:
        if self.state is None or self.state.get("phase") != "active" or self.state.get("active_player") != self.player_id:
            return False, "Only available during your active turn."
        local_player = self.local_player()
        if local_player is None:
            return False, "Waiting for your player state."
        if len(local_player["reserved_cards"]) >= 3:
            return False, "You already have 3 reserved cards."
        return True, ""

    def _missing_tokens_reason(self, card: dict[str, Any]) -> str:
        local_player = self.local_player()
        if local_player is None:
            return "Waiting for your player state."
        shortage_total = 0
        shortages: list[str] = []
        for color in TOKEN_STYLES:
            if color == "gold":
                continue
            cost = int(card["cost"].get(color, 0))
            discount = int(local_player["bonuses"].get(color, 0))
            remaining = max(0, cost - discount)
            available = int(local_player["tokens"].get(color, 0))
            missing = max(0, remaining - available)
            if missing:
                shortages.append(f"{color} {missing}")
                shortage_total += missing
        gold_available = int(local_player["tokens"].get("gold", 0))
        if shortage_total <= gold_available:
            return "You can cover the remaining cost with gold."
        still_missing = shortage_total - gold_available
        if shortages:
            return f"Need {still_missing} more token(s): {', '.join(shortages)}."
        return "You do not have enough tokens."

    def _buy_selected_market_card(self, tier: int, market_index: int) -> None:
        self._clear_market_card_selection()
        self._hide_market_action_overlay()
        self.send_action("buy_face_up_card", {"tier": tier, "market_index": market_index})

    def _reserve_selected_market_card(self, tier: int, market_index: int) -> None:
        self._clear_market_card_selection()
        self._hide_market_action_overlay()
        self.send_action("reserve_card", {"tier": tier, "market_index": market_index, "top_deck": False})

    def _cancel_selected_market_card(self) -> None:
        self._clear_market_card_selection()
        self._hide_market_action_overlay()
        self.set_feedback("Card action cancelled.")

    def _make_player_header_layout(self, player: dict[str, Any]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        identity_column = QVBoxLayout()
        identity_column.setSpacing(4)

        player_id_label = QLabel(player["id"])
        player_id_label.setStyleSheet(
            f"color: {self._panel_muted_text()}; "
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
        )
        identity_column.addWidget(player_id_label)

        player_name_label = QLabel(player["name"])
        player_name_label.setStyleSheet(f"color: {self._panel_primary_text()}; font-size: 20px; font-weight: 700;")
        identity_column.addWidget(player_name_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        statuses = self._player_statuses(player)
        if statuses:
            for status in statuses:
                status_row.addWidget(self._make_status_chip(status))
            status_row.addStretch(1)
        else:
            spacer = QLabel("Ready")
            spacer.setStyleSheet(f"color: {self._panel_muted_text()}; font-size: 11px;")
            status_row.addWidget(spacer)
        identity_column.addLayout(status_row)

        row.addLayout(identity_column, 1)

        score_box = QLabel(f"{player['score']}\npoints")
        score_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_box.setMinimumWidth(84)
        score_box.setStyleSheet(
            f"background: {self._panel_surface()};"
            f"color: {self._panel_primary_text()};"
            f"border: 1px solid {self._player_score_border(player)};"
            "border-radius: 12px;"
            "padding: 8px 10px;"
            "font-size: 22px;"
            "font-weight: 800;"
        )
        row.addWidget(score_box)
        return row

    def _make_token_summary_layout(self, tokens: dict[str, int]) -> QGridLayout:
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        for index, color in enumerate(ALL_TOKEN_COLORS):
            layout.addWidget(self._make_token_counter_widget(color, int(tokens.get(color, 0))), index // 3, index % 3)
        return layout

    def _make_bonus_summary_layout(self, bonuses: dict[str, int]) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for color in ALL_TOKEN_COLORS:
            if color == "gold":
                continue
            layout.addWidget(self._make_bonus_chip(color, int(bonuses.get(color, 0))))
        layout.addStretch(1)
        return layout

    def _make_player_meta_layout(self, player: dict[str, Any]) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._make_meta_card("Purchased", str(player["purchased_card_count"])))
        layout.addWidget(self._make_meta_card("Nobles", str(len(player["claimed_nobles"]))))
        layout.addWidget(self._make_meta_card("Held", str(sum(int(value) for value in player["tokens"].values()))))
        return layout

    def _make_token_counter_widget(self, color: str, count: int) -> QWidget:
        container = QWidget()
        container.setToolTip(f"{color.title()}: {count}")
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(54, 54)
        icon_label.setStyleSheet(
            f"background: {self._panel_surface() if count else self._panel_surface_alt()};"
            f"border: 1px solid {self._panel_border()};"
            "border-radius: 14px;"
        )
        gem_asset_name = GEM_ASSET_NAMES.get(color, color)
        gem_pixmap = self._load_pixmap("gems", f"{gem_asset_name}.png")
        display_pixmap = self._scaled_pixmap(gem_pixmap, QSize(30, 30), 1.0 if count else 0.35)
        if display_pixmap is not None:
            icon_label.setPixmap(display_pixmap)
        else:
            icon_label.setText(COLOR_ABBREVIATIONS[color])
            icon_label.setStyleSheet(
                icon_label.styleSheet()
                + f"color: {self._text_color_for(color)}; font-size: 11px; font-weight: 700;"
            )
        layout.addWidget(icon_label, 0, 0, Qt.AlignmentFlag.AlignCenter)

        badge = QLabel(str(count))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(22, 22)
        badge.setStyleSheet(
            f"background: {TOKEN_STYLES[color] if count else self._panel_border()};"
            f"color: {self._text_color_for(color) if count else self._panel_primary_text()};"
            f"border: 2px solid {self._panel_background()};"
            "border-radius: 11px;"
            "font-size: 11px;"
            "font-weight: 800;"
        )
        layout.addWidget(
            badge,
            0,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        return container

    def _make_bonus_chip(self, color: str, count: int) -> QLabel:
        chip = QLabel(str(count))
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setMinimumHeight(28)
        chip.setMinimumWidth(38)
        chip.setToolTip(f"{color.title()} bonus: {count}")
        chip.setStyleSheet(
            f"background: {self._bonus_chip_background(color, count)};"
            f"color: {self._bonus_chip_foreground(color, count)};"
            f"border: 1px solid {self._bonus_chip_border(color, count)};"
            "border-radius: 14px;"
            "padding: 4px 8px;"
            "font-size: 12px;"
            "font-weight: 700;"
        )
        return chip

    def _make_meta_card(self, label: str, value: str) -> QLabel:
        widget = QLabel(f"{value}\n{label}")
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        widget.setStyleSheet(
            f"background: {self._panel_surface()};"
            f"color: {self._panel_primary_text()};"
            f"border: 1px solid {self._panel_border()};"
            "border-radius: 10px;"
            "padding: 8px 10px;"
            "font-size: 12px;"
            "font-weight: 700;"
        )
        return widget

    def _make_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {self._panel_muted_text()}; "
            "font-size: 11px; font-weight: 700; letter-spacing: 0.08em;"
        )
        return label

    def _make_status_chip(self, text: str) -> QLabel:
        palette = {
            "Active": (self._panel_surface_alt(), self._panel_primary_text(), self._panel_border()),
            "You": (self._panel_surface_alt(), self._panel_primary_text(), self._panel_border()),
            "Disconnected": ("#4b2323", "#f3d0d0", "#734040"),
        }
        background, foreground, border = palette.get(
            text,
            (
                self._panel_surface_alt(),
                self._panel_primary_text(),
                self._panel_border(),
            ),
        )
        chip = QLabel(text)
        chip.setStyleSheet(
            f"background: {background};"
            f"color: {foreground};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "padding: 3px 8px;"
            "font-size: 11px;"
            "font-weight: 700;"
        )
        return chip

    def _player_statuses(self, player: dict[str, Any]) -> list[str]:
        assert self.state is not None
        statuses: list[str] = []
        if player["id"] == self.state.get("active_player"):
            statuses.append("Active")
        if player["id"] == self.player_id:
            statuses.append("You")
        if not player.get("connected", True):
            statuses.append("Disconnected")
        return statuses

    def _bonus_chip_foreground(self, color: str, count: int) -> str:
        if not count:
            return self._panel_muted_text()
        return self._text_color_for(color)

    def _bonus_chip_background(self, color: str, count: int) -> str:
        if not count:
            return self._panel_surface_alt()
        return TOKEN_STYLES[color]

    def _bonus_chip_border(self, color: str, count: int) -> str:
        if not count:
            return self._panel_border()
        if color == "white":
            return "#d1d5db"
        return TOKEN_STYLES[color]

    def _player_score_border(self, player: dict[str, Any]) -> str:
        return self._panel_border()

    @staticmethod
    def _panel_background() -> str:
        return "#2d2d2d"

    @staticmethod
    def _panel_surface() -> str:
        return "#3a3a3a"

    @staticmethod
    def _panel_surface_alt() -> str:
        return "#323232"

    @staticmethod
    def _panel_border() -> str:
        return "#5b5b5b"

    @staticmethod
    def _panel_primary_text() -> str:
        return "#f3f4f6"

    @staticmethod
    def _panel_muted_text() -> str:
        return "#c7cad1"

    @staticmethod
    def _text_color_for(color: str) -> str:
        return "#111827" if color in {"white", "gold"} else "#f8fafc"

    def _load_pixmap(self, *parts: str) -> QPixmap | None:
        cache_key = tuple(parts)
        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]
        data = load_asset_bytes(*parts)
        if data is None:
            self._pixmap_cache[cache_key] = None
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._pixmap_cache[cache_key] = None
            return None
        self._pixmap_cache[cache_key] = pixmap
        return pixmap

    @staticmethod
    def _apply_button_pixmap(button: QPushButton, pixmap: QPixmap | None, size: QSize) -> None:
        if pixmap is None:
            button.setIcon(QIcon())
            return
        button.setIcon(QIcon(pixmap))
        button.setIconSize(size)

    @staticmethod
    def _scaled_pixmap(pixmap: QPixmap | None, size: QSize, opacity: float = 1.0) -> QPixmap | None:
        if pixmap is None:
            return None
        scaled = pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if opacity >= 0.999:
            return scaled
        faded = QPixmap(scaled.size())
        faded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(faded)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return faded

    def _update_market_action_overlay_geometry(self) -> None:
        self.market_action_overlay.setGeometry(self.game_page.viewport().rect())

    def resizeEvent(self, event) -> None:
        self._update_market_action_overlay_geometry()
        super().resizeEvent(event)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                MainWindow._clear_layout(child_layout)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.client_bridge is not None:
            self.client_bridge.close()
        if self.discovery_bridge is not None:
            self.discovery_bridge.close()
        if self.server is not None:
            self.server.stop()
        super().closeEvent(event)


def run() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
