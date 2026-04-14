"""Settings Screen - Edit config.json and planner_config.json"""

import json
import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Static, Input, Button
from textual.screen import Screen
from textual.binding import Binding
from textual.validation import Number

logger = logging.getLogger(__name__)

# Config file paths
CONFIG_DIR = Path(__file__).parent.parent
MAIN_CONFIG_FILE = CONFIG_DIR / "config.json"
PLANNER_CONFIG_FILE = CONFIG_DIR / "planner_config.json"


class SettingsScreen(Screen):
    """Settings screen for editing TUI and planner configuration"""

    CSS = """
    SettingsScreen {
        background: $surface;
    }

    #settings-container {
        height: 100%;
        padding: 1 2;
    }

    #settings-content {
        border: solid $primary;
        background: $surface-darken-1;
        padding: 1 2;
        width: 100%;
        height: auto;
    }

    .settings-section {
        margin: 0;
        padding: 0;
    }

    .settings-section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }

    .settings-row {
        height: auto;
        margin: 0;
    }

    .settings-label {
        width: 30;
        padding: 0 2 0 0;
        content-align: right middle;
    }

    .settings-input {
        width: 15;
        margin: 0 2 0 0;
    }

    Input {
        height: 3;
    }

    .settings-hint {
        color: $text-muted;
        padding: 0 0 0 1;
    }

    #button-container {
        margin-top: 2;
        padding: 1 0;
        height: auto;
    }

    Button {
        margin: 0 2 0 0;
    }

    .error-message {
        color: $error;
        text-style: bold;
        margin: 1 0;
    }

    .success-message {
        color: $success;
        text-style: bold;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("s", "save", "Save Changes", show=True),
        Binding("r", "reset", "Reset Defaults", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.original_main_config = {}
        self.original_planner_config = {}
        self.input_fields = {}

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with VerticalScroll(id="settings-container"):
            with Container(id="settings-content"):
                yield Static("[bold cyan]Settings[/bold cyan]\n", id="settings-title")

                # Load configs
                self.original_main_config = self._load_main_config()
                self.original_planner_config = self._load_planner_config()

                # Discovery Filters section
                yield Static("\n[Discovery Filters] (config.json)", classes="settings-section-title")
                yield from self._build_section("discovery", [
                    ("max_symbol_price", "Max Symbol Price:", self.original_main_config["filters"]["max_symbol_price"], "$"),
                    ("min_liquidity_oi", "Min Liquidity (OI):", self.original_main_config["filters"]["min_liquidity_oi"], ""),
                    ("dte_min", "DTE Range Min:", self.original_main_config["filters"]["dte_range"]["min"], "days"),
                    ("dte_max", "DTE Range Max:", self.original_main_config["filters"]["dte_range"]["max"], "days"),
                ])

                # Capital Planner section
                yield Static("\n[Capital Planner] (planner_config.json)", classes="settings-section-title")
                yield from self._build_section("planner", [
                    ("total_capital", "Total Capital:", self.original_planner_config["capital"]["total_capital"], "$"),
                    ("target_position_size", "Target Position Size:", self.original_planner_config["capital"]["target_position_size"], "$"),
                    ("warning_threshold", "Warning Threshold:", self.original_planner_config["capital"]["warning_threshold_pct"], "% of total"),
                    ("default_entry_days", "Default Entry (days):", self.original_planner_config["defaults"]["default_entry_days_before"], "days before earnings"),
                    ("default_exit_days", "Default Exit (days):", self.original_planner_config["defaults"]["default_exit_days_before"], "days before earnings"),
                ])

                # Confluence Scoring section
                yield Static("\n[Confluence Scoring] (config.json)", classes="settings-section-title")
                weights = self.original_main_config["confluence_scoring"]["weights"]
                yield from self._build_section("confluence", [
                    ("has_flow_alert", "Has Flow Alert:", weights["has_flow_alert"], ""),
                    ("volume_surge", "Volume Surge:", weights["volume_surge"], ""),
                    ("earnings_catalyst", "Earnings Catalyst:", weights["earnings_catalyst"], ""),
                    ("news_sentiment_strong", "News Sentiment Strong:", weights["news_sentiment_strong"], ""),
                    ("oi_conviction_high", "OI Conviction High:", weights["oi_conviction_high"], ""),
                    ("min_confluence_score", "Min Confluence Score:", self.original_main_config["confluence_scoring"]["min_confluence_score"], ""),
                ])

                # Display section
                yield Static("\n[Display] (config.json)", classes="settings-section-title")
                yield from self._build_section("display", [
                    ("watchlist_limit", "Watchlist Limit:", self.original_main_config["display"]["watchlist_limit"], ""),
                ])

                # Buttons and status
                yield Static("\n", id="status-message")

                with Horizontal(id="button-container"):
                    yield Button("Save Changes [S]", id="save-button", variant="success")
                    yield Button("Reset to Defaults [R]", id="reset-button", variant="warning")
                    yield Button("Cancel [ESC]", id="cancel-button")

        yield Footer()

    def on_mount(self) -> None:
        """Set input field values after mount"""
        # Use set_timer to ensure widgets are fully mounted before setting values
        self.set_timer(0.05, self._populate_fields)

    def _populate_fields(self) -> None:
        """Populate input fields with config values"""
        try:
            # Set discovery filter values using query_one
            self.query_one("#discovery_max_symbol_price", Input).value = str(self.original_main_config["filters"]["max_symbol_price"])
            self.query_one("#discovery_min_liquidity_oi", Input).value = str(self.original_main_config["filters"]["min_liquidity_oi"])
            self.query_one("#discovery_dte_min", Input).value = str(self.original_main_config["filters"]["dte_range"]["min"])
            self.query_one("#discovery_dte_max", Input).value = str(self.original_main_config["filters"]["dte_range"]["max"])

            # Set planner values
            self.query_one("#planner_total_capital", Input).value = str(self.original_planner_config["capital"]["total_capital"])
            self.query_one("#planner_target_position_size", Input).value = str(self.original_planner_config["capital"]["target_position_size"])
            self.query_one("#planner_warning_threshold", Input).value = str(self.original_planner_config["capital"]["warning_threshold_pct"])
            self.query_one("#planner_default_entry_days", Input).value = str(self.original_planner_config["defaults"]["default_entry_days_before"])
            self.query_one("#planner_default_exit_days", Input).value = str(self.original_planner_config["defaults"]["default_exit_days_before"])

            # Set confluence weights
            weights = self.original_main_config["confluence_scoring"]["weights"]
            self.query_one("#confluence_has_flow_alert", Input).value = str(weights["has_flow_alert"])
            self.query_one("#confluence_volume_surge", Input).value = str(weights["volume_surge"])
            self.query_one("#confluence_earnings_catalyst", Input).value = str(weights["earnings_catalyst"])
            self.query_one("#confluence_news_sentiment_strong", Input).value = str(weights["news_sentiment_strong"])
            self.query_one("#confluence_oi_conviction_high", Input).value = str(weights["oi_conviction_high"])
            self.query_one("#confluence_min_confluence_score", Input).value = str(self.original_main_config["confluence_scoring"]["min_confluence_score"])

            # Set display values
            self.query_one("#display_watchlist_limit", Input).value = str(self.original_main_config["display"]["watchlist_limit"])

            logger.info("Settings fields populated successfully")
        except Exception as e:
            logger.error(f"Error populating settings fields: {e}")
            self.notify(f"Error loading settings values: {str(e)}", severity="error")

    def _build_section(self, section_prefix: str, fields: list) -> ComposeResult:
        """Build a section of settings fields.

        Args:
            section_prefix: Prefix for field IDs
            fields: List of (id_suffix, label, default_value, hint) tuples
        """
        for field_id, label, default_value, hint in fields:
            full_id = f"{section_prefix}_{field_id}"

            with Horizontal(classes="settings-row"):
                yield Static(label, classes="settings-label")
                input_widget = Input(
                    value=str(default_value),
                    id=full_id,
                    classes="settings-input"
                )
                self.input_fields[full_id] = input_widget
                yield input_widget
                if hint:
                    yield Static(hint, classes="settings-hint")

    def _load_main_config(self) -> dict:
        """Load main config.json"""
        try:
            with open(MAIN_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading main config: {e}")
            self.notify("Failed to load config.json", severity="error")
            return self._get_default_main_config()

    def _load_planner_config(self) -> dict:
        """Load planner_config.json"""
        try:
            with open(PLANNER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading planner config: {e}")
            self.notify("Failed to load planner_config.json", severity="error")
            return self._get_default_planner_config()

    def _get_default_main_config(self) -> dict:
        """Get default main config structure"""
        return {
            "filters": {
                "max_symbol_price": 60,
                "min_liquidity_oi": 500,
                "dte_range": {"min": 7, "max": 60}
            },
            "confluence_scoring": {
                "weights": {
                    "has_flow_alert": 1,
                    "volume_surge": 1,
                    "earnings_catalyst": 1,
                    "news_sentiment_strong": 1,
                    "oi_conviction_high": 1
                },
                "min_confluence_score": 2,
                "news_lookback_days": 5
            },
            "display": {"watchlist_limit": 10, "detail_top_strikes": 5},
            "database": {"path": "data/datalake_query.db"}
        }

    def _get_default_planner_config(self) -> dict:
        """Get default planner config structure"""
        return {
            "capital": {
                "total_capital": 3000,
                "target_position_size": 300,
                "warning_threshold_pct": 80
            },
            "defaults": {
                "default_entry_days_before": 14,
                "default_exit_days_before": 2
            },
            "archival": {
                "auto_archive_closed": False,
                "archive_after_days": 7
            }
        }

    def _validate_fields(self) -> tuple[bool, str]:
        """Validate all input fields.

        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            for field_id, input_widget in self.input_fields.items():
                value_str = input_widget.value.strip()

                # Check if numeric
                try:
                    value = float(value_str)
                except ValueError:
                    return False, f"{field_id}: Must be a number"

                # Check if positive
                if value < 0:
                    return False, f"{field_id}: Must be positive"

                # Specific field validations
                if "threshold" in field_id and value > 100:
                    return False, f"{field_id}: Threshold must be <= 100%"

            return True, ""

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _save_configs(self) -> bool:
        """Save all settings to config files.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update main config
            main_config = self.original_main_config.copy()
            main_config["filters"]["max_symbol_price"] = int(self.input_fields["discovery_max_symbol_price"].value)
            main_config["filters"]["min_liquidity_oi"] = int(self.input_fields["discovery_min_liquidity_oi"].value)
            main_config["filters"]["dte_range"]["min"] = int(self.input_fields["discovery_dte_min"].value)
            main_config["filters"]["dte_range"]["max"] = int(self.input_fields["discovery_dte_max"].value)

            main_config["confluence_scoring"]["weights"]["has_flow_alert"] = int(self.input_fields["confluence_has_flow_alert"].value)
            main_config["confluence_scoring"]["weights"]["volume_surge"] = int(self.input_fields["confluence_volume_surge"].value)
            main_config["confluence_scoring"]["weights"]["earnings_catalyst"] = int(self.input_fields["confluence_earnings_catalyst"].value)
            main_config["confluence_scoring"]["weights"]["news_sentiment_strong"] = int(self.input_fields["confluence_news_sentiment_strong"].value)
            main_config["confluence_scoring"]["weights"]["oi_conviction_high"] = int(self.input_fields["confluence_oi_conviction_high"].value)
            main_config["confluence_scoring"]["min_confluence_score"] = int(self.input_fields["confluence_min_confluence_score"].value)

            main_config["display"]["watchlist_limit"] = int(self.input_fields["display_watchlist_limit"].value)

            # Update planner config
            planner_config = self.original_planner_config.copy()
            planner_config["capital"]["total_capital"] = int(self.input_fields["planner_total_capital"].value)
            planner_config["capital"]["target_position_size"] = int(self.input_fields["planner_target_position_size"].value)
            planner_config["capital"]["warning_threshold_pct"] = int(self.input_fields["planner_warning_threshold"].value)
            planner_config["defaults"]["default_entry_days_before"] = int(self.input_fields["planner_default_entry_days"].value)
            planner_config["defaults"]["default_exit_days_before"] = int(self.input_fields["planner_default_exit_days"].value)

            # Write to files
            with open(MAIN_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(main_config, f, indent=2, ensure_ascii=False)

            with open(PLANNER_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(planner_config, f, indent=2, ensure_ascii=False)

            logger.info("Settings saved successfully")
            return True

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            self.notify(f"Failed to save settings: {str(e)}", severity="error")
            return False

    def action_save(self) -> None:
        """Save settings action"""
        # Validate
        is_valid, error_msg = self._validate_fields()
        if not is_valid:
            self.notify(f"Validation failed: {error_msg}", severity="error")
            return

        # Save
        if self._save_configs():
            self.notify("✓ Settings saved successfully", severity="information", timeout=3)
            # Close screen after brief delay
            self.app.pop_screen()

    def action_reset(self) -> None:
        """Reset to defaults action"""
        # Confirmation via notification
        self.notify("Resetting to defaults...", severity="warning", timeout=2)

        # Get defaults
        default_main = self._get_default_main_config()
        default_planner = self._get_default_planner_config()

        # Update input fields
        self.input_fields["discovery_max_symbol_price"].value = str(default_main["filters"]["max_symbol_price"])
        self.input_fields["discovery_min_liquidity_oi"].value = str(default_main["filters"]["min_liquidity_oi"])
        self.input_fields["discovery_dte_min"].value = str(default_main["filters"]["dte_range"]["min"])
        self.input_fields["discovery_dte_max"].value = str(default_main["filters"]["dte_range"]["max"])

        self.input_fields["planner_total_capital"].value = str(default_planner["capital"]["total_capital"])
        self.input_fields["planner_target_position_size"].value = str(default_planner["capital"]["target_position_size"])
        self.input_fields["planner_warning_threshold"].value = str(default_planner["capital"]["warning_threshold_pct"])
        self.input_fields["planner_default_entry_days"].value = str(default_planner["defaults"]["default_entry_days_before"])
        self.input_fields["planner_default_exit_days"].value = str(default_planner["defaults"]["default_exit_days_before"])

        self.input_fields["confluence_has_flow_alert"].value = str(default_main["confluence_scoring"]["weights"]["has_flow_alert"])
        self.input_fields["confluence_volume_surge"].value = str(default_main["confluence_scoring"]["weights"]["volume_surge"])
        self.input_fields["confluence_earnings_catalyst"].value = str(default_main["confluence_scoring"]["weights"]["earnings_catalyst"])
        self.input_fields["confluence_news_sentiment_strong"].value = str(default_main["confluence_scoring"]["weights"]["news_sentiment_strong"])
        self.input_fields["confluence_oi_conviction_high"].value = str(default_main["confluence_scoring"]["weights"]["oi_conviction_high"])
        self.input_fields["confluence_min_confluence_score"].value = str(default_main["confluence_scoring"]["min_confluence_score"])

        self.input_fields["display_watchlist_limit"].value = str(default_main["display"]["watchlist_limit"])

        self.notify("✓ Reset to defaults (not saved yet)", severity="information")

    def action_cancel(self) -> None:
        """Cancel action - discard changes"""
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "save-button":
            self.action_save()
        elif event.button.id == "reset-button":
            self.action_reset()
        elif event.button.id == "cancel-button":
            self.action_cancel()
