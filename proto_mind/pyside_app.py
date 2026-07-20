from __future__ import annotations

from datetime import datetime
from html import escape
import json
from os import getenv
from pathlib import Path
from traceback import print_exc
from dataclasses import dataclass
from re import match

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.desktop_app import (
    DesktopRuntime,
    classify_desktop_output,
    compact_desktop_output,
    create_desktop_runtime,
    desktop_preferences_path,
    format_desktop_response,
    load_desktop_preferences,
    parse_log_entries,
    parse_overall_status,
    save_desktop_preferences,
    save_transcript,
)

try:
    from PySide6.QtCore import QByteArray, QObject, Qt, QThread, QTimer, Signal, Slot
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QSizePolicy,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE_AVAILABLE = True
    PYSIDE_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - depends on optional dependency.
    QApplication = None  # type: ignore[assignment]
    QByteArray = None  # type: ignore[assignment]
    QObject = object  # type: ignore[assignment,misc]
    QCheckBox = None  # type: ignore[assignment]
    QFrame = None  # type: ignore[assignment]
    QGridLayout = None  # type: ignore[assignment]
    QHBoxLayout = None  # type: ignore[assignment]
    QLabel = None  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment,misc]
    QPlainTextEdit = None  # type: ignore[assignment]
    QPushButton = None  # type: ignore[assignment]
    QSizePolicy = None  # type: ignore[assignment]
    QSplitter = None  # type: ignore[assignment]
    QTextEdit = None  # type: ignore[assignment]
    QTextCursor = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]
    QThread = None  # type: ignore[assignment]
    QTimer = None  # type: ignore[assignment]
    Signal = None  # type: ignore[assignment]
    Slot = None  # type: ignore[assignment]
    QVBoxLayout = None  # type: ignore[assignment]
    QWidget = None  # type: ignore[assignment]
    PYSIDE_AVAILABLE = False
    PYSIDE_IMPORT_ERROR = exc


PYSIDE_APP_VERSION = "v2.0.0"
PYSIDE_APP_TITLE = f"Proto-Mind Cognitive Control Room {PYSIDE_APP_VERSION}"
PYSIDE_COMMAND_COUNT = len(COMMAND_REGISTRY)
PYSIDE_CATEGORY_COUNT = len({entry.category for entry in COMMAND_REGISTRY})

PYSIDE_CONTROL_DECK_GROUPS = (
    (
        "SESSION",
        (
            ("Start Brief", "/session start-brief"),
            ("Daily Brief", "/daily brief"),
            ("Next Work", "/agenda next"),
            ("Handoff", "/session handoff-brief"),
        ),
    ),
    (
        "COGNITIVE STATE",
        (
            ("System Status", "/proto status"),
            ("Experience", "/experience doctor"),
            ("Memory Card", "/memory-card short"),
            ("Skill State", "/skills lifecycle-status"),
        ),
    ),
    (
        "TRUST & EVIDENCE",
        (
            ("Full Doctor", "/proto doctor"),
            ("Warnings", "/warnings status"),
            ("Snapshot Diff", "/proto snapshot-diff-status"),
            ("Showcase", "/showcase demo"),
        ),
    ),
)
PYSIDE_PANEL_COMMANDS = {
    label: command
    for _, actions in PYSIDE_CONTROL_DECK_GROUPS
    for label, command in actions
}
PYSIDE_PROMPT_CHIPS = (
    ("DAILY", "/daily brief"),
    ("NEXT", "/agenda next"),
    ("DOCTOR", "/proto doctor"),
    ("SHOWCASE", "/showcase demo"),
)

START_MESSAGE = """# Welcome back
**Proto-Mind is local, inspectable, and operator-guided.**

Use the Control Deck for a safe system view, or continue the conversation below.
Start with `Daily Brief`, `Next Work`, or `Showcase`.
"""


def pyside_missing_message() -> str:
    return "PySide6 is not installed.\nInstall with:\n  python3 -m pip install PySide6"


def format_worker_error(exc: Exception) -> str:
    return f"System error:\nWorker error: {exc}"


def can_start_pyside_worker(*, busy: bool, text: str) -> bool:
    return (not busy) and bool(text.strip())


@dataclass
class ButtonState:
    text: str
    enabled: bool


@dataclass(frozen=True)
class ContextIndicator:
    state: str
    text: str
    detail: str


def pyside_registry_summary() -> str:
    return f"{PYSIDE_COMMAND_COUNT} commands / {PYSIDE_CATEGORY_COUNT} capability families"


def read_context_indicator(project_root: Path) -> ContextIndicator:
    settings_path = Path(project_root) / "proto_mind" / "data" / "context_injection.json"
    if not settings_path.exists():
        return ContextIndicator(
            state="OFF",
            text="CONTEXT OFF",
            detail="Disabled by default; settings file is absent.",
        )
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ContextIndicator(
            state="UNKNOWN",
            text="CONTEXT UNKNOWN",
            detail="Context settings are unreadable; no UI repair was attempted.",
        )
    if not isinstance(payload, dict):
        return ContextIndicator(
            state="UNKNOWN",
            text="CONTEXT UNKNOWN",
            detail="Context settings have an invalid root type.",
        )
    enabled = payload.get("enabled") is True
    return ContextIndicator(
        state="ON" if enabled else "OFF",
        text="CONTEXT ON" if enabled else "CONTEXT OFF",
        detail=(
            "Preview-safe context injection is enabled for normal prompts."
            if enabled
            else "Preview-safe context injection is disabled."
        ),
    )


def pyside_context_style(state: str) -> str:
    colors = {
        "OFF": ("#163b37", "#8ee3ce", "#285f57"),
        "ON": ("#493718", "#ffd18a", "#7d5c26"),
        "UNKNOWN": ("#3b3030", "#f2b8b5", "#684545"),
    }
    background, foreground, border = colors.get(state.upper(), colors["UNKNOWN"])
    return (
        f"background: {background}; color: {foreground}; border: 1px solid {border}; "
        "border-radius: 9px; padding: 6px 10px; font-weight: 700;"
    )


class CancelController:
    def __init__(self) -> None:
        self.cancel_requested = False

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def is_cancel_requested(self) -> bool:
        return self.cancel_requested


def _normalise_modifiers(modifiers: object) -> set[str]:
    if isinstance(modifiers, set):
        return {str(value).lower() for value in modifiers}
    if isinstance(modifiers, (list, tuple)):
        return {str(value).lower() for value in modifiers}
    return {str(modifiers).lower()} if modifiers else set()


def should_send_on_key(key: str, modifiers: object = None) -> bool:
    key_name = str(key).lower()
    mods = _normalise_modifiers(modifiers)
    if key_name not in {"return", "enter"}:
        return False
    return "shift" not in mods


def should_insert_newline_on_key(key: str, modifiers: object = None) -> bool:
    key_name = str(key).lower()
    mods = _normalise_modifiers(modifiers)
    return key_name in {"return", "enter"} and "shift" in mods


def pyside_badge_style(status: str) -> str:
    colors = {
        "UNKNOWN": ("#4a4d55", "#d8dee9"),
        "OK": ("#245a38", "#dff7e8"),
        "WARN": ("#7a5518", "#ffe8a3"),
        "ERROR": ("#7a2d2d", "#ffd6d6"),
    }
    background, foreground = colors.get(status.upper(), colors["UNKNOWN"])
    return (
        f"background-color: {background}; color: {foreground}; border: 1px solid {background}; "
        "border-radius: 8px; padding: 8px; font-weight: bold;"
    )


def format_runtime_label(state: str) -> str:
    state_name = state.lower()
    if state_name == "thinking":
        return "Runtime: thinking..."
    if state_name == "stopping":
        return "Runtime: stopping..."
    if state_name == "error":
        return "Runtime: error"
    return "Runtime: ready"


def runtime_style_for_state(state: str) -> str:
    colors = {
        "ready": ("#1f4f35", "#dff7e8"),
        "thinking": ("#21537a", "#d9ecff"),
        "stopping": ("#7a5518", "#ffe8a3"),
        "error": ("#7a2d2d", "#ffd6d6"),
    }
    background, foreground = colors.get(state.lower(), colors["ready"])
    return (
        f"background-color: {background}; color: {foreground}; border: 1px solid {background}; "
        "border-radius: 8px; padding: 8px; font-weight: bold;"
    )


def pyside_send_button_text(state: str) -> str:
    return "Thinking..." if state.lower() == "thinking" else "Send"


def pyside_send_button_state(state: str) -> ButtonState:
    state_name = state.lower()
    return ButtonState(text=pyside_send_button_text(state_name), enabled=state_name not in {"thinking", "stopping"})


def pyside_stop_button_state(state: str) -> ButtonState:
    state_name = state.lower()
    if state_name == "thinking":
        return ButtonState(text="Stop", enabled=True)
    if state_name == "stopping":
        return ButtonState(text="Stopping...", enabled=False)
    return ButtonState(text="Stop", enabled=False)


def pyside_status_line(state: str, *, backend: str, model: str | None, debug_enabled: bool) -> str:
    state_name = state.lower()
    if state_name == "thinking":
        state_text = "thinking..."
    elif state_name == "stopping":
        state_text = "stopping..."
    else:
        state_text = "ready"
    debug = "on" if debug_enabled else "off"
    model_text = f" | Model: {model}" if model else ""
    return f"Status: {state_text} | Backend: {backend}{model_text} | Debug: {debug}"


def _render_bold_lite(text: str) -> str:
    rendered: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("**", index)
        if start == -1:
            rendered.append(escape(text[index:]))
            break
        end = text.find("**", start + 2)
        if end == -1:
            rendered.append(escape(text[index:]))
            break
        rendered.append(escape(text[index:start]))
        rendered.append(f"<strong>{escape(text[start + 2:end])}</strong>")
        index = end + 2
    return "".join(rendered)


def render_inline_markdown_lite(text: str) -> str:
    parts = text.split("`")
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            rendered.append(f"<code>{escape(part)}</code>")
        else:
            rendered.append(_render_bold_lite(part))
    return "".join(rendered)


def render_markdown_lite(text: str) -> str:
    lines = text.strip().splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            rendered = "<br>".join(render_inline_markdown_lite(line) for line in paragraph)
            output.append(f"<p>{rendered}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    def ensure_list(kind: str) -> None:
        nonlocal list_type
        flush_paragraph()
        if list_type and list_type != kind:
            close_list()
        if not list_type:
            list_type = kind
            output.append(f"<{kind}>")

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                output.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
                code_lines = []
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        heading = match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{render_inline_markdown_lite(heading.group(2).strip())}</h{level}>")
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            ensure_list("ul")
            output.append(f"<li>{render_inline_markdown_lite(stripped[2:].strip())}</li>")
            continue
        numbered = match(r"^(\d+)\.\s+(.*)$", stripped)
        if numbered:
            ensure_list("ol")
            output.append(f"<li>{render_inline_markdown_lite(numbered.group(2).strip())}</li>")
            continue
        close_list()
        paragraph.append(stripped)

    if in_code:
        output.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return "".join(output)


def render_plain_text_html(text: str) -> str:
    return escape(text.strip()).replace("\n", "<br>")


def pyside_message_html(
    speaker: str,
    text: str,
    *,
    report: bool = False,
    markdown: bool = True,
    muted: bool = False,
) -> str:
    speaker_html = escape(speaker)
    if report:
        text_html = escape(text.strip())
        body = f"<pre>{text_html}</pre>"
        klass = "report"
    elif markdown:
        body = f"<div class='body'>{render_markdown_lite(text)}</div>"
        klass = "message"
    else:
        body = f"<div class='body'><p>{render_plain_text_html(text)}</p></div>"
        klass = "system message" if muted else "message"
    return f"<div class='message-block'><div class='{klass}'><div class='speaker'>{speaker_html}</div>{body}</div></div>"


def pyside_message_reset_html() -> str:
    return "<div class='message-reset'>&nbsp;</div>"


def pyside_dark_stylesheet() -> str:
    return """
    QMainWindow, QWidget {
        background: #0b1016;
        color: #eee9df;
        font-family: "Avenir Next", "Helvetica Neue";
        font-size: 13px;
    }
    QFrame#brandCard {
        background: #111923;
        border: 1px solid #253344;
        border-left: 3px solid #d7a75b;
        border-radius: 14px;
    }
    QLabel#brandMark {
        background: #d7a75b;
        color: #111923;
        border-radius: 17px;
        font-size: 14px;
        font-weight: 800;
        padding: 8px;
    }
    QLabel#brandTitle {
        color: #fff7e8;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }
    QLabel#brandSubtitle, QLabel#mutedLabel {
        color: #8e9bad;
        font-size: 11px;
    }
    QLabel#localBadge {
        background: #182b2a;
        color: #84d8c5;
        border: 1px solid #2a5b54;
        border-radius: 9px;
        padding: 6px 10px;
        font-weight: 700;
    }
    QFrame#controlDeck {
        background: #101720;
        border: 1px solid #253344;
        border-radius: 14px;
    }
    QLabel#deckTitle {
        color: #fff7e8;
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 0.6px;
    }
    QLabel#sectionTitle, QLabel#inputLabel {
        color: #d7a75b;
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 1.2px;
    }
    QFrame#composer {
        background: #101720;
        border: 1px solid #253344;
        border-radius: 13px;
    }
    QTextEdit, QPlainTextEdit {
        background: #0d131a;
        color: #eee9df;
        border: 1px solid #263545;
        border-radius: 10px;
        padding: 10px;
        selection-background-color: #376c67;
        selection-color: #ffffff;
    }
    QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #4f8f86;
    }
    QPushButton {
        background: #1a2430;
        color: #eee9df;
        border: 1px solid #304052;
        border-radius: 8px;
        padding: 8px 10px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #243241;
        border-color: #4c657e;
    }
    QPushButton#primaryButton {
        background: #d7a75b;
        color: #111923;
        border: 1px solid #edc47f;
        min-width: 72px;
        font-weight: 800;
    }
    QPushButton#primaryButton:hover {
        background: #e6b96f;
    }
    QPushButton#dangerButton {
        background: #251b1c;
        color: #e5a7a3;
        border-color: #5e3537;
        min-width: 64px;
    }
    QPushButton#quickActionButton {
        background: #151f29;
        color: #d9e0e7;
        border-color: #2b3b4c;
        text-align: left;
        padding: 9px 10px;
    }
    QPushButton#quickActionButton:hover {
        background: #1b302f;
        color: #a7eadb;
        border-color: #35655f;
    }
    QPushButton#chipButton {
        background: transparent;
        color: #aeb9c6;
        border: 1px solid #2c3b4b;
        border-radius: 10px;
        padding: 5px 10px;
        font-size: 10px;
        font-weight: 800;
    }
    QPushButton#chipButton:hover {
        color: #ffd18a;
        border-color: #7d6034;
    }
    QPushButton:disabled {
        background: #121922;
        color: #596472;
        border-color: #202b37;
    }
    QCheckBox {
        spacing: 8px;
        color: #aeb9c6;
    }
    QLabel {
        color: #d9e0e7;
    }
    QSplitter::handle {
        background: #111923;
        width: 4px;
    }
    """


def pyside_chat_document_css() -> str:
    return """
    body { background: #0d131a; color: #eee9df; font-family: "Avenir Next", "Helvetica Neue", sans-serif; }
    .message-block { margin: 0 0 20px 0; }
    .message-reset { margin: 0; padding: 0; height: 1px; line-height: 1px; }
    .message, .report { margin: 0 0 18px 0; }
    .speaker { color: #7fd8c4; font-weight: 700; margin-bottom: 7px; letter-spacing: 0.4px; }
    .system .speaker { color: #8390a0; }
    .system .body { color: #9ca7b5; }
    .body { white-space: normal; line-height: 1.5; }
    h1, h2, h3 { color: #ffd18a; margin: 10px 0 7px 0; }
    h1 { font-size: 20px; }
    h2 { font-size: 17px; }
    h3 { font-size: 15px; }
    strong { color: #ffffff; font-weight: 700; }
    ul, ol { margin-top: 6px; margin-bottom: 10px; padding-left: 24px; }
    li { margin: 3px 0; }
    code {
        background: #17212b;
        border: 1px solid #304052;
        border-radius: 4px;
        color: #ffd18a;
        font-family: Menlo, Monaco, Consolas, monospace;
        padding: 1px 4px;
    }
    pre {
        background: #0a1016;
        border: 1px solid #263545;
        border-radius: 8px;
        color: #d9e0e7;
        font-family: Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        line-height: 1.35;
        padding: 10px;
        white-space: pre-wrap;
    }
    """


def encode_pyside_geometry(raw_geometry: object) -> str:
    data = bytes(raw_geometry.toBase64()).decode("ascii")
    return f"pyside6:{data}"


if PYSIDE_AVAILABLE:

    class InputWorker(QObject):
        started = Signal()
        chunk = Signal(str)
        error = Signal(str)
        cancel_requested = Signal()
        finished = Signal(object)

        def __init__(self, runtime: DesktopRuntime, text: str) -> None:
            super().__init__()
            self.runtime = runtime
            self.text = text
            self.cancel_controller = CancelController()

        def request_cancel(self) -> None:
            self.cancel_controller.request_cancel()
            self.cancel_requested.emit()

        def is_cancel_requested(self) -> bool:
            return self.cancel_controller.is_cancel_requested()

        @Slot()
        def run(self) -> None:
            self.started.emit()
            if self.is_cancel_requested():
                self.finished.emit({"input": self.text, "response": None, "cancelled": True})
                return
            try:
                response = self.runtime.process(self.text)
            except Exception as exc:  # pragma: no cover - defensive worker boundary.
                if getenv("PROTO_MIND_DESKTOP_DEBUG") == "1":
                    print_exc()
                response = format_worker_error(exc)
                self.error.emit(response)
            self.finished.emit(
                {
                    "input": self.text,
                    "response": response,
                    "cancel_requested": self.is_cancel_requested(),
                }
            )


    class ChatInput(QPlainTextEdit):
        def __init__(self, send_callback: object) -> None:
            super().__init__()
            self._send_callback = send_callback

        def keyPressEvent(self, event: object) -> None:
            key_name = "return" if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) else str(event.key())
            modifiers: set[str] = set()
            event_modifiers = event.modifiers()
            if event_modifiers & Qt.KeyboardModifier.ShiftModifier:
                modifiers.add("shift")
            if event_modifiers & Qt.KeyboardModifier.ControlModifier:
                modifiers.add("ctrl")
            if event_modifiers & Qt.KeyboardModifier.MetaModifier:
                modifiers.add("cmd")
            if should_insert_newline_on_key(key_name, modifiers):
                super().keyPressEvent(event)
                return
            if should_send_on_key(key_name, modifiers):
                self._send_callback()
                event.accept()
                return
            super().keyPressEvent(event)


    class ProtoMindPySideApp(QMainWindow):
        def __init__(self, runtime: DesktopRuntime) -> None:
            super().__init__()
            self.runtime = runtime
            self.preferences_path = desktop_preferences_path(runtime.project_root)
            self.preferences = load_desktop_preferences(self.preferences_path)
            self.overall_status = "UNKNOWN"
            self.runtime_state = "ready"
            self.last_check = "never"
            self.log_entries: int | None = None
            self.busy = False
            self.current_worker_thread: QThread | None = None
            self.current_worker: InputWorker | None = None
            self.current_display_mode = "normal"
            self.cancel_requested_for_current_worker = False
            self.active_stream_speaker: str | None = None
            self.panel_buttons: list[QPushButton] = []

            self.setWindowTitle(PYSIDE_APP_TITLE)
            self.setMinimumSize(1040, 700)
            self.resize(1280, 820)
            self._build_ui()
            self._restore_geometry()
            self.append_assistant_message(START_MESSAGE.strip())
            self._refresh_panel()
            QTimer.singleShot(100, self._startup_status_refresh)

        def _build_ui(self) -> None:
            self.setStyleSheet(pyside_dark_stylesheet())
            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QHBoxLayout(central)
            root_layout.setContentsMargins(16, 16, 16, 14)
            root_layout.setSpacing(14)

            splitter = QSplitter(Qt.Orientation.Horizontal)
            root_layout.addWidget(splitter)

            left = QWidget()
            left_layout = QVBoxLayout(left)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(11)
            splitter.addWidget(left)

            right = QFrame()
            right.setObjectName("controlDeck")
            right.setMinimumWidth(330)
            right.setMaximumWidth(390)
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(14, 14, 14, 14)
            right_layout.setSpacing(9)
            splitter.addWidget(right)
            splitter.setSizes([900, 350])

            brand = QFrame()
            brand.setObjectName("brandCard")
            brand_layout = QHBoxLayout(brand)
            brand_layout.setContentsMargins(14, 10, 14, 10)
            brand_layout.setSpacing(12)

            brand_mark = QLabel("PM")
            brand_mark.setObjectName("brandMark")
            brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            brand_mark.setFixedSize(38, 38)
            brand_layout.addWidget(brand_mark)

            brand_copy = QVBoxLayout()
            brand_copy.setSpacing(1)
            brand_title = QLabel("PROTO-MIND")
            brand_title.setObjectName("brandTitle")
            brand_subtitle = QLabel(
                f"CONTROL ROOM {PYSIDE_APP_VERSION} / LOCAL-FIRST"
            )
            brand_subtitle.setObjectName("brandSubtitle")
            brand_copy.addWidget(brand_title)
            brand_copy.addWidget(brand_subtitle)
            brand_layout.addLayout(brand_copy, stretch=1)

            local_badge = QLabel("LOCAL / PRIVATE")
            local_badge.setObjectName("localBadge")
            local_badge.setToolTip("Proto-Mind uses the local project and local reasoner configuration.")
            brand_layout.addWidget(local_badge)
            self.header_context_label = QLabel("CONTEXT OFF")
            brand_layout.addWidget(self.header_context_label)
            left_layout.addWidget(brand)

            self.chat = QTextEdit()
            self.chat.setReadOnly(True)
            self.chat.setObjectName("conversationView")
            self.chat.document().setDefaultStyleSheet(pyside_chat_document_css())
            left_layout.addWidget(self.chat, stretch=1)

            controls = QHBoxLayout()
            controls.setSpacing(8)
            self.debug_checkbox = QCheckBox("Debug output")
            self.debug_checkbox.setChecked(self.preferences.debug_output)
            self.debug_checkbox.stateChanged.connect(self._on_debug_toggle)
            controls.addWidget(self.debug_checkbox)
            controls.addStretch(1)

            copy_all = QPushButton("Copy All")
            copy_all.clicked.connect(self._copy_all)
            controls.addWidget(copy_all)

            save_button = QPushButton("Save Transcript")
            save_button.clicked.connect(self._save_transcript)
            controls.addWidget(save_button)

            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(self.chat.clear)
            controls.addWidget(clear_button)
            left_layout.addLayout(controls)

            chip_row = QHBoxLayout()
            chip_row.setSpacing(7)
            chip_label = QLabel("QUICK RUN")
            chip_label.setObjectName("inputLabel")
            chip_row.addWidget(chip_label)
            for label, command in PYSIDE_PROMPT_CHIPS:
                chip_row.addWidget(
                    self._make_command_button(
                        label,
                        command,
                        object_name="chipButton",
                        announce=True,
                    )
                )
            chip_row.addStretch(1)
            left_layout.addLayout(chip_row)

            composer = QFrame()
            composer.setObjectName("composer")
            composer_layout = QVBoxLayout(composer)
            composer_layout.setContentsMargins(11, 9, 11, 10)
            composer_layout.setSpacing(6)
            input_heading = QHBoxLayout()
            input_label = QLabel("OPERATOR INPUT")
            input_label.setObjectName("inputLabel")
            input_hint = QLabel("ENTER TO SEND / SHIFT+ENTER FOR NEW LINE")
            input_hint.setObjectName("mutedLabel")
            input_heading.addWidget(input_label)
            input_heading.addStretch(1)
            input_heading.addWidget(input_hint)
            composer_layout.addLayout(input_heading)

            input_row = QHBoxLayout()
            input_row.setSpacing(8)
            self.input_box = ChatInput(self._send_from_input)
            self.input_box.setMinimumHeight(76)
            self.input_box.setMaximumHeight(118)
            self.input_box.setPlaceholderText(
                "Ask Proto-Mind, continue the current goal, or enter an exact command..."
            )
            input_row.addWidget(self.input_box, stretch=1)

            self.send_button = QPushButton("Send")
            self.send_button.setObjectName("primaryButton")
            self.send_button.setMinimumHeight(42)
            self.send_button.clicked.connect(self._send_from_input)
            input_row.addWidget(self.send_button)

            self.stop_button = QPushButton("Stop")
            self.stop_button.setObjectName("dangerButton")
            self.stop_button.setMinimumHeight(42)
            self.stop_button.clicked.connect(self._request_stop)
            input_row.addWidget(self.stop_button)
            composer_layout.addLayout(input_row)
            left_layout.addWidget(composer)

            self.status_label = QLabel("Status: ready")
            self.status_label.setObjectName("mutedLabel")
            self.status_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            left_layout.addWidget(self.status_label)

            deck_title = QLabel("CONTROL DECK")
            deck_title.setObjectName("deckTitle")
            right_layout.addWidget(deck_title)
            deck_subtitle = QLabel("Safe views over the cognitive stack")
            deck_subtitle.setObjectName("mutedLabel")
            right_layout.addWidget(deck_subtitle)

            self.overall_label = QLabel("Overall: UNKNOWN")
            self.overall_label.setFrameStyle(QLabel.Shape.Box)
            right_layout.addWidget(self.overall_label)

            self.runtime_label = QLabel("Runtime: ready")
            self.runtime_label.setFrameStyle(QLabel.Shape.Box)
            right_layout.addWidget(self.runtime_label)

            self.context_label = QLabel("CONTEXT OFF")
            right_layout.addWidget(self.context_label)

            self.backend_label = QLabel()
            self.model_label = QLabel()
            self.capability_label = QLabel()
            self.log_entries_label = QLabel()
            self.last_check_label = QLabel()
            self.debug_label = QLabel()
            for label in (
                self.backend_label,
                self.model_label,
                self.capability_label,
                self.log_entries_label,
                self.last_check_label,
                self.debug_label,
            ):
                label.setObjectName("mutedLabel")
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                right_layout.addWidget(label)

            self.auto_self_check = QCheckBox("Auto self-check on startup")
            self.auto_self_check.setChecked(self.preferences.auto_self_check_on_startup)
            self.auto_self_check.stateChanged.connect(self._on_auto_self_check_toggle)
            right_layout.addWidget(self.auto_self_check)

            for group_name, actions in PYSIDE_CONTROL_DECK_GROUPS:
                section = QLabel(group_name)
                section.setObjectName("sectionTitle")
                right_layout.addWidget(section)
                grid = QGridLayout()
                grid.setHorizontalSpacing(7)
                grid.setVerticalSpacing(7)
                for index, (label, command) in enumerate(actions):
                    grid.addWidget(
                        self._make_command_button(
                            label,
                            command,
                            object_name="quickActionButton",
                            announce=True,
                        ),
                        index // 2,
                        index % 2,
                    )
                grid.setColumnStretch(0, 1)
                grid.setColumnStretch(1, 1)
                right_layout.addLayout(grid)

            right_layout.addStretch(1)

        def _make_command_button(
            self,
            label: str,
            command: str,
            *,
            object_name: str,
            announce: bool,
        ) -> QPushButton:
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.setToolTip(command)
            button.setAccessibleName(f"Run {command}")
            button.clicked.connect(
                lambda _checked=False, value=command, show=announce: self._send(
                    value,
                    append_user=False,
                    announce=show,
                )
            )
            self.panel_buttons.append(button)
            return button

        def _set_busy(self, busy: bool) -> None:
            self.busy = busy
            if busy:
                self.runtime_state = "thinking"
            elif self.runtime_state != "error":
                self.runtime_state = "ready"
            for button in self.panel_buttons:
                button.setEnabled(not busy)
            self._refresh_panel()
            QApplication.processEvents()

        def _send_from_input(self) -> None:
            text = self.input_box.toPlainText().strip()
            if not text:
                return
            self.input_box.clear()
            self._send(text, append_user=True)

        def _send(
            self,
            text: str,
            *,
            append_user: bool = True,
            display_mode: str = "normal",
            announce: bool = False,
        ) -> None:
            if not can_start_pyside_worker(busy=self.busy, text=text):
                return
            self.cancel_requested_for_current_worker = False
            self._set_busy(True)
            self.current_display_mode = display_mode
            if append_user:
                self.append_user_message(text)
            elif announce:
                self.append_system_message(f"Running {text}")
            self._start_worker(text)

        def _start_worker(self, text: str) -> None:
            thread = QThread(self)
            worker = InputWorker(self.runtime, text)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.chunk.connect(self.append_assistant_chunk)
            worker.cancel_requested.connect(self._mark_stop_requested)
            worker.finished.connect(self._finish_worker_response)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._clear_worker_refs)
            self.current_worker_thread = thread
            self.current_worker = worker
            thread.start()

        def _clear_worker_refs(self) -> None:
            self.current_worker_thread = None
            self.current_worker = None

        def _finish_worker_response(self, result: object) -> None:
            response = result.get("response") if isinstance(result, dict) else None
            cancel_requested = bool(result.get("cancel_requested")) if isinstance(result, dict) else False
            self._finish_response(response, cancel_requested=cancel_requested)

        def _finish_response(self, response: str | None, *, cancel_requested: bool = False) -> None:
            was_cancel_requested = cancel_requested or self.cancel_requested_for_current_worker
            self._set_busy(False)
            if response is None:
                self.close()
                return
            display_mode = self.current_display_mode
            self.current_display_mode = "normal"
            if display_mode == "status_refresh":
                self._finish_status_refresh_response(response)
                if was_cancel_requested:
                    self.append_system_message("Operation finished after stop request.")
                    self.cancel_requested_for_current_worker = False
                return
            display = format_desktop_response(response, debug=self.debug_checkbox.isChecked())
            kind = classify_desktop_output(response)
            if kind == "system":
                self.append_system_message(display)
            elif kind == "report":
                self.append_report_message(display)
            else:
                self.append_assistant_message(display)
            self._update_panel_from_output(response)
            if response.startswith("System error:"):
                self.runtime_state = "error"
                self._refresh_panel()
            if was_cancel_requested:
                self.append_system_message("Operation finished after stop request.")
                self.cancel_requested_for_current_worker = False
            self.input_box.setFocus()

        def _finish_status_refresh_response(self, response: str) -> None:
            self._update_panel_from_output(response, update_last_check=True)
            if response.startswith("System error:"):
                self.append_system_message(response)
                self.runtime_state = "error"
                self._refresh_panel()
            else:
                entries = parse_log_entries(response)
                value = str(entries) if entries is not None else "unknown"
                self.append_system_message(f"Status refreshed. Log entries: {value}")
            self.input_box.setFocus()

        def _request_stop(self) -> None:
            if not self.busy or self.current_worker is None:
                return
            self._mark_stop_requested()
            self.current_worker.request_cancel()

        def _mark_stop_requested(self) -> None:
            if self.cancel_requested_for_current_worker:
                return
            self.cancel_requested_for_current_worker = True
            self.runtime_state = "stopping"
            self.append_system_message("Stop requested. Waiting for current operation to finish.")
            self._refresh_panel()

        def start_assistant_stream_block(self, speaker: str = "Proto-Mind") -> None:
            self.active_stream_speaker = speaker
            self.append_assistant_message("")

        def append_assistant_chunk(self, text: str) -> None:
            if text:
                self.chat.insertPlainText(text)
                scrollbar = self.chat.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

        def finish_assistant_stream_block(self) -> None:
            self.active_stream_speaker = None

        def _startup_status_refresh(self) -> None:
            try:
                response = self.runtime.process("/session log status")
            except Exception as exc:  # pragma: no cover - defensive UI boundary.
                response = f"System error:\nStartup status refresh failed: {exc}"
            self._update_panel_from_output(response, update_last_check=True)
            if response.startswith("System error:"):
                self.append_system_message(response)
            if self.preferences.auto_self_check_on_startup:
                QTimer.singleShot(100, lambda: self._send("/session self-check", append_user=False, announce=True))

        def _update_panel_from_output(self, output: str, *, update_last_check: bool = False) -> None:
            status = parse_overall_status(output)
            entries = parse_log_entries(output)
            if status != "UNKNOWN":
                self.overall_status = status
                update_last_check = True
            if entries is not None:
                self.log_entries = entries
            if update_last_check:
                self.last_check = datetime.now().strftime("%H:%M:%S")
            self._refresh_panel()

        def _refresh_panel(self) -> None:
            self.overall_label.setText(f"Overall: {self.overall_status}")
            self.overall_label.setStyleSheet(pyside_badge_style(self.overall_status))
            self.runtime_label.setText(format_runtime_label(self.runtime_state))
            self.runtime_label.setStyleSheet(runtime_style_for_state(self.runtime_state))
            context = read_context_indicator(self.runtime.project_root)
            context_style = pyside_context_style(context.state)
            self.context_label.setText(context.text)
            self.context_label.setStyleSheet(context_style)
            self.context_label.setToolTip(context.detail)
            self.header_context_label.setText(context.text)
            self.header_context_label.setStyleSheet(context_style)
            self.header_context_label.setToolTip(context.detail)
            send_state = pyside_send_button_state(self.runtime_state)
            stop_state = pyside_stop_button_state(self.runtime_state)
            self.send_button.setText(send_state.text)
            self.send_button.setEnabled(send_state.enabled and not self.busy)
            self.stop_button.setText(stop_state.text)
            self.stop_button.setEnabled(stop_state.enabled and self.busy)
            self.backend_label.setText(f"Backend: {self.runtime.backend_name}")
            self.model_label.setText(f"Model: {self.runtime.model_name or 'none'}")
            self.capability_label.setText(pyside_registry_summary())
            entries = str(self.log_entries) if self.log_entries is not None else "unknown"
            self.log_entries_label.setText(f"Log entries: {entries}")
            self.last_check_label.setText(f"Last check: {self.last_check}")
            debug = "on" if self.debug_checkbox.isChecked() else "off"
            self.debug_label.setText(f"Debug: {debug}")
            self.status_label.setText(
                pyside_status_line(
                    self.runtime_state,
                    backend=self.runtime.backend_name,
                    model=self.runtime.model_name,
                    debug_enabled=self.debug_checkbox.isChecked(),
                )
            )

        def _on_debug_toggle(self) -> None:
            self.preferences.debug_output = self.debug_checkbox.isChecked()
            save_desktop_preferences(self.preferences_path, self.preferences)
            self._refresh_panel()

        def _on_auto_self_check_toggle(self) -> None:
            self.preferences.auto_self_check_on_startup = self.auto_self_check.isChecked()
            save_desktop_preferences(self.preferences_path, self.preferences)

        def _copy_all(self) -> None:
            QApplication.clipboard().setText(self.chat.toPlainText())
            self.append_system_message("Transcript copied to clipboard.")

        def _save_transcript(self) -> None:
            try:
                path = save_transcript(self.runtime.project_root, self.chat.toPlainText())
                self.append_system_message(f"Transcript saved: {path}")
            except Exception as exc:  # pragma: no cover - defensive UI boundary.
                self.append_system_message(f"Transcript save failed: {exc}")

        def append_user_message(self, text: str) -> None:
            self._append("User", text, markdown=False)

        def append_assistant_message(self, text: str) -> None:
            self._append("Proto-Mind", text, markdown=True)

        def append_system_message(self, text: str) -> None:
            self._append("System", text, markdown=False, muted=True)

        def append_report_message(self, text: str) -> None:
            self._append("Proto-Mind / System report", text, report=True)

        def _append(
            self,
            speaker: str,
            text: str,
            *,
            report: bool = False,
            markdown: bool = True,
            muted: bool = False,
        ) -> None:
            cursor = self.chat.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(pyside_message_html(speaker, text, report=report, markdown=markdown, muted=muted))
            cursor.insertHtml(pyside_message_reset_html())
            cursor.insertBlock()
            self.chat.setTextCursor(cursor)
            scrollbar = self.chat.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _restore_geometry(self) -> None:
            geometry = self.preferences.window_geometry
            if not geometry or not geometry.startswith("pyside6:"):
                return
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.removeprefix("pyside6:").encode("ascii")))
            except Exception:
                self.resize(1280, 820)

        def closeEvent(self, event: object) -> None:
            self.preferences.window_geometry = encode_pyside_geometry(self.saveGeometry())
            save_desktop_preferences(self.preferences_path, self.preferences)
            super().closeEvent(event)


def main() -> None:
    if not PYSIDE_AVAILABLE:
        print(pyside_missing_message())
        raise SystemExit(1)
    app = QApplication.instance() or QApplication([])
    window = ProtoMindPySideApp(create_desktop_runtime())
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
