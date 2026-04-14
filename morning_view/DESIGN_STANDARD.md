# Morning View TUI Design Standard

**Version:** 1.0
**Date:** 2025-10-30
**Philosophy:** Keyboard-first, compact, consistent

---

## Core Principles

1. **Keyboard-First Design**
   - Hotkeys over buttons
   - Tab navigation between sections
   - Arrow keys for table navigation
   - Enter/Space for activation

2. **Compact & Scannable**
   - Minimize vertical scrolling
   - Group related controls
   - Use tabs for mode switching
   - Clear visual hierarchy

3. **Consistent Patterns**
   - All admin screens follow same layout structure
   - Standardized hotkey conventions
   - Uniform styling and spacing

---

## Standard Screen Layout

### Template Structure (Admin Screens)

```
┌─────────────────────────────────────────┐
│ MorningViewApp                          │  ← Header (built-in)
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ ADMIN MODE - Screen Name            │ │  ← Red border (admin-mode class)
│ │                                     │ │
│ │  Content built as string            │ │  ← Single Static widget
│ │  with keyboard hints included       │ │
│ │                                     │ │
│ │  [1] Option 1                       │ │
│ │  [2] Option 2                       │ │
│ │                                     │ │
│ │  ESC=Back | Q=Quit                  │ │  ← Hints inline in content
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ q Quit | esc Back                       │  ← Footer with global keys only
└─────────────────────────────────────────┘
```

### Layout Implementation (RECOMMENDED)

**Simple Static Widget Pattern** - Build content as strings, single Static widget:

```python
def compose(self) -> ComposeResult:
    """Single Static widget - simple and works"""
    yield Header()
    with VerticalScroll(id="admin-container"):
        yield Static(self._build_content(), id="admin-content", classes="admin-mode")
    yield Footer()

def _build_content(self) -> str:
    """Build screen content as string"""
    lines = [
        "[bold red]ADMIN MODE - Screen Name[/bold red]",
        "[yellow]Screen description[/yellow]",
        "",
        "[bold][1][/bold] Option 1",
        "[bold][2][/bold] Option 2",
        "",
        "[dim]1-2=Select | ESC=Back | Q=Quit[/dim]"
    ]
    return "\n".join(lines)

def _refresh_display(self):
    """Update display when state changes"""
    content = self._build_content()
    static = self.query_one("#admin-content", Static)
    static.update(content)
```

**Benefits of this approach:**
- Content scrolls naturally - no CSS tricks needed
- Hints are always visible in the content
- Simple to understand and maintain
- Proven to work (see pipeline_control.py)

### Components

1. **Header** (Textual built-in)
   - App title centered
   - Automatically displays clock/title

2. **VerticalScroll Container** (`#admin-container`)
   - Wraps all content
   - Enables automatic scrolling when content exceeds viewport
   - CSS: `height: 100%; padding: 1 2;`

3. **Single Static Widget** (`classes="admin-mode"`)
   - **Red border** around entire content
   - Contains ALL screen content as formatted string
   - Updated via `.update(new_content_string)` when state changes
   - CSS class: `.admin-mode { border: solid $error; }`

4. **Content Structure** (built as strings)
   - Admin header line: `"[bold red]ADMIN MODE - Screen Name[/bold red]"`
   - Yellow descriptions: `"[yellow]Description text[/yellow]"`
   - Menu options with keys: `"[bold][1][/bold] Option text"`
   - Inline hints at bottom: `"[dim]1-2=Select | ESC=Back[/dim]"`
   - All built in `_build_content()` method

5. **Footer** (Textual built-in)
   - **Shows ONLY global keybindings**: Q=Quit, ESC=Back
   - All other keys handled via `on_key()` event handler
   - Footer is the same everywhere - simple and uncluttered

---

## Hotkey Conventions

### Universal Keys (All Screens) - MANDATORY
- **Q**: Quit app (exit to shell)
- **ESC**: Go back to previous screen/step (context-aware navigation)
- **Ctrl+C**: Emergency quit (built-in Textual behavior - use sparingly)
- **Tab**: Navigate between input fields or tabs (when TabbedContent present)
- **Shift+Tab**: Navigate backwards between fields/tabs

### Common Actions
- **L**: Lookup/Load/List (context-dependent)
- **A**: Add/Append new item
- **E**: Edit selected item
- **O**: Overwrite (when replacing existing data)
- **D**: Delete selected item (with confirmation)
- **R**: Refresh/Reload data
- **S**: Save/Submit form
- **C**: Create new item
- **X**: Execute/Run (for operations like sync, archive)

### Form Controls
- **Space**: Toggle switches/checkboxes
- **Enter**: Submit form or activate focused item
- **Arrow Keys**: Navigate between RadioButtons in RadioSet

### DataTable Navigation
- **Arrow Keys**: Navigate DataTable rows/columns
- **Home/End**: Jump to first/last row
- **Page Up/Down**: Scroll DataTable by page

### Context-Specific Keys
- **F**: Filter (when filtering makes sense)
- **T**: Test mode (for dry-run operations)
- **1-9**: Number keys for quick selection (pipeline controls, menus)

### Key Convention Notes
1. **Q vs ESC distinction**: Q always quits the app entirely. ESC navigates back (to parent form, previous screen, or admin menu).
2. **ESC should be context-aware**: If in a sub-form, ESC returns to parent form. If at top level, ESC exits screen back to menu.
3. **Keep verbs consistent**: L=Lookup (not "Find" or "Search"), S=Save (not "Submit"), A=Add (not "New")
4. **Single letter preferred**: Avoid multi-key combos unless absolutely necessary (exception: Ctrl+C, Shift+Tab)
5. **Number keys for selection**: When showing numbered lists (1-9 max), allow direct selection via number
6. **Both Q and ESC in BINDINGS**: Always include both so footer shows "q Quit | escape Back"
7. **ENTER key philosophy**:
   - Input fields: ENTER submits naturally (via `on_input_submitted`)
   - Select/other widgets: Use letter hotkeys (S=Save, E=Estimate, etc.)
   - **Never** hack context-aware Enter routing - that's fighting the framework
   - Show "ENTER or L" in hints for Input fields, just "S" for other actions
8. **Context-aware actions**: Action handlers must check context (e.g., numbered menu keys only work on main menu)
9. **Footer philosophy - Global keys only**:
   - Set `show=True` ONLY for Q (Quit) and ESC (Back)
   - All other bindings default to `show=False` (hidden from footer)
   - This keeps footer clean and consistent across all screens
   - Context-specific keys are documented in status bar hints instead
10. **Status bar reinforces context hotkeys**: Show relevant keys for each screen (e.g., "S=Save | ESC=Cancel", "ENTER or L=Lookup | ESC=Back")

---

## DataTable Standards

### Display
- **Border**: `rounded` style
- **Cursor Type**: `row` (highlight full row)
- **Zebra Stripes**: Enabled for readability
- **Header Style**: Bold, distinct background

### Interaction
- Arrow keys for navigation
- Enter to select/activate row
- Context-specific hotkeys displayed in footer

### Columns
- **Width**: Auto-size based on content, with max widths
- **Alignment**: Numbers right-aligned, text left-aligned
- **Dates**: Use consistent format (YYYY-MM-DD HH:MM)

---

## Form Controls

### Layout
- Use `Horizontal` containers for compact grouping
- Label + Control in same container
- Related controls grouped together

### Control Types
- **Switch**: For on/off toggles (e.g., enable/disable features)
- **Input**: For text entry (dates, symbols, text)
- **Button**: Only when hotkey isn't sufficient (rare)
- **Select**: For dropdowns (if needed)

### Styling
- Consistent spacing between controls
- Clear labels above or beside controls
- Validation feedback near input

---

## Status Messages

### Format
```css
Status: [Icon] Message text
```

### Types
- ✓ Success: Green text, confirms action completed
- ✗ Error: Red text, explains what failed
- ⚠ Warning: Yellow text, alerts to issue
- ℹ Info: Default text, general feedback

### Duration
- Errors: Persistent until next action
- Success: Can be temporary (3-5 seconds) or persistent
- Use `self.notify()` for temporary toasts

---

## Color Scheme

### Standard Colors (from theme)
- **Primary**: Blue accents
- **Success**: Green (#00FF00)
- **Error**: Red (#FF0000)
- **Warning**: Yellow (#FFFF00)
- **Muted**: Gray for secondary text
- **Background**: Dark theme default

### Usage
- Minimal color usage - only for status and highlights
- Don't overuse - preserve visual calm
- Color should enhance, not distract

---

## CSS Classes

### Standard Classes to Define
```css
.compact-table {
    /* DataTable with minimal padding */
}

.status-success {
    color: $success;
}

.status-error {
    color: $error;
}

.status-warning {
    color: $warning;
}

.hotkey-footer {
    /* Footer styling for hotkey guide */
    dock: bottom;
    height: 1;
    background: $surface;
}

.form-group {
    /* Horizontal container for form controls */
    height: auto;
    padding: 1;
}
```

---

## Migration Checklist

To bring existing screens up to standard:

### Trading Journal Screen
- [x] Convert action buttons to hotkeys (A=Add, E=Edit, D=Delete)
- [x] Move filters to TabbedContent if needed
- [x] Add footer with global hotkeys (Q, ESC)
- [x] Standardize status message format
- [x] Remove mouse-focused buttons

### Symbol Metadata & Archives Screen
- [x] Convert Edit/Refresh buttons to E/R hotkeys
- [x] Add footer with global hotkeys (Q, ESC)
- [x] Compact form layout using Horizontal containers
- [x] Standardize status messages
- [x] Context-specific keys hidden from footer
- [x] NavigationStack for screen hierarchy tracking

---

## Example Implementation

See `morning_view/admin_screens/pipeline_control.py` as the reference implementation.

Key patterns:
```python
# Simple bindings - only global keys
BINDINGS = [
    Binding("q", "request_quit", "Quit", show=True),
    Binding("escape", "back", "Back", show=True),
]

# Single Static widget compose
def compose(self) -> ComposeResult:
    yield Header()
    with VerticalScroll(id="admin-container"):
        yield Static(self._build_content(), id="admin-content", classes="admin-mode")
    yield Footer()

# Build content as string
def _build_menu(self) -> str:
    lines = [
        "[bold red]ADMIN MODE - Screen Name[/bold red]",
        "[yellow]Select an option:[/yellow]",
        "",
        "[bold][1][/bold] First Option",
        "    [dim]Description of first option[/dim]",
        "",
        "[bold][2][/bold] Second Option",
        "    [dim]Description of second option[/dim]",
        "",
        "[dim]1-2=Select | ESC=Back | Q=Quit[/dim]"
    ]
    return "\n".join(lines)

# Update display when needed
def _refresh_display(self):
    content = self._build_content()
    static = self.query_one("#admin-content", Static)
    static.update(content)

# Handle keys directly
def on_key(self, event: events.Key) -> None:
    if self.current_screen == "main_menu":
        if event.key == "1":
            self.current_screen = "option_1"
            self._refresh_display()
        elif event.key == "2":
            self.current_screen = "option_2"
            self._refresh_display()
```

---

## Questions?

This is a living document. As we refine the design language, update this file to reflect new patterns and decisions.
