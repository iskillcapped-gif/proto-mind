from __future__ import annotations

import threading
from json import JSONDecodeError, dump, load
from dataclasses import dataclass
from datetime import datetime
from os import getenv
from pathlib import Path
from re import IGNORECASE, MULTILINE, search

from proto_mind.main import build_coordinator, process_interactive_input
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.session_log import SessionOperatorLogger

try:
    import tkinter as tk
    from tkinter import scrolledtext

    TKINTER_AVAILABLE = True
    TKINTER_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on local Python build.
    tk = None  # type: ignore[assignment]
    scrolledtext = None  # type: ignore[assignment]
    TKINTER_AVAILABLE = False
    TKINTER_IMPORT_ERROR = exc


QUICK_COMMANDS = {
    "Self-Check": "/session self-check",
    "Health": "/session health",
    "Doctor": "/session doctor",
    "Review": "/session review",
    "Log Status": "/session log status",
}


PANEL_COMMANDS = {
    "Check System": "/session self-check",
    "Refresh Status": "/session log status",
    "Health": "/session health",
    "Doctor": "/session doctor",
    "Review": "/session review",
    "Log Status": "/session log status",
    "Export Last 20": "/session log export --last 20",
}


START_MESSAGE = """Proto-Mind Desktop v0.3
Local-first chat shell.
Try:
- проверь свою систему
- /session self-check
- /session health
- /session doctor
"""


@dataclass
class DesktopRuntime:
    project_root: Path
    session_logger: SessionOperatorLogger
    coordinator: object
    hygiene: MemoryHygiene

    @property
    def backend_name(self) -> str:
        return str(getattr(self.coordinator.reasoner, "backend_name", "unknown"))

    @property
    def model_name(self) -> str | None:
        config = getattr(self.coordinator, "config", None)
        model = getattr(config, "ollama_model", None)
        return str(model) if model and self.backend_name == "ollama" else None

    @property
    def status_label(self) -> str:
        return format_backend_status(self.backend_name, self.model_name)

    def process(self, user_input: str) -> str | None:
        return process_interactive_input(
            user_input,
            coordinator=self.coordinator,
            session_logger=self.session_logger,
            project_root=self.project_root,
            hygiene=self.hygiene,
        )


@dataclass
class DesktopPreferences:
    debug_output: bool = False
    auto_self_check_on_startup: bool = False
    window_geometry: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "debug_output": self.debug_output,
            "auto_self_check_on_startup": self.auto_self_check_on_startup,
        }
        if self.window_geometry:
            data["window_geometry"] = self.window_geometry
        return data


def create_desktop_runtime(project_root: Path | None = None) -> DesktopRuntime:
    root = project_root or Path(__file__).resolve().parents[1]
    session_logger = SessionOperatorLogger.from_project_root(root)
    coordinator = build_coordinator(session_logger=session_logger)
    hygiene = MemoryHygiene(coordinator.memory_keeper.store)
    return DesktopRuntime(
        project_root=root,
        session_logger=session_logger,
        coordinator=coordinator,
        hygiene=hygiene,
    )


class ProtoMindDesktopApp:
    def __init__(self, root: object, runtime: DesktopRuntime) -> None:
        if not TKINTER_AVAILABLE:
            raise RuntimeError(_tkinter_unavailable_message())
        self.root = root
        self.runtime = runtime
        self.preferences_path = desktop_preferences_path(runtime.project_root)
        self.preferences = load_desktop_preferences(self.preferences_path)
        self.busy = False
        self.overall_status = "UNKNOWN"
        self.last_check = "never"
        self.log_entries: int | None = None
        self.panel_buttons: list[object] = []
        self.root.title("Proto-Mind Desktop v0.4")
        geometry = self.preferences.window_geometry
        self.root.geometry(geometry if geometry and not geometry.startswith("pyside6:") else "1050x680")
        self._build_ui()
        self._build_menus()
        self._bind_app_shortcuts()
        self.append_system_message(START_MESSAGE.strip())
        self._refresh_system_panel()
        self._set_status("ready")
        self.input_box.focus_set()
        self.root.after(100, self._startup_status_refresh)

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        chat_frame = tk.Frame(main_frame)
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        panel_frame = tk.Frame(main_frame, width=230, borderwidth=1, relief=tk.GROOVE)
        panel_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        panel_frame.pack_propagate(False)

        self.history = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD)
        self.history.tag_configure("heading_user", font=("TkDefaultFont", 10, "bold"))
        self.history.tag_configure("heading_assistant", font=("TkDefaultFont", 10, "bold"))
        self.history.tag_configure("heading_system", font=("TkDefaultFont", 10, "bold"))
        self.history.tag_configure("system", foreground="#4d4d4d")
        self.history.tag_configure("warning", foreground="#9a5b00")
        self.history.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 6))
        make_text_read_only(self.history)
        bind_clipboard_shortcuts(self.history, editable=False)
        self._bind_context_menu(self.history, editable=False)

        button_frame = tk.Frame(chat_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 6))
        self.debug_output = tk.BooleanVar(value=self.preferences.debug_output)
        debug_checkbox = tk.Checkbutton(
            button_frame,
            text="Debug output",
            variable=self.debug_output,
            command=self._on_debug_toggle,
        )
        debug_checkbox.pack(side=tk.LEFT, padx=(8, 0))
        copy_button = tk.Button(button_frame, text="Copy All", command=self._copy_all)
        copy_button.pack(side=tk.RIGHT, padx=(6, 0))
        save_button = tk.Button(button_frame, text="Save Transcript", command=self._save_transcript)
        save_button.pack(side=tk.RIGHT, padx=(6, 0))
        clear_button = tk.Button(button_frame, text="Clear", command=self._clear_history)
        clear_button.pack(side=tk.RIGHT)

        input_frame = tk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 6))
        self.input_box = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        bind_clipboard_shortcuts(self.input_box, editable=True)
        self._bind_context_menu(self.input_box, editable=True)
        self.input_box.bind("<Shift-Return>", self._on_shift_enter)
        self.input_box.bind("<Return>", self._on_enter)
        self.send_button = tk.Button(input_frame, text="Send", command=self._send_from_input)
        self.send_button.pack(side=tk.LEFT, padx=(8, 0), fill=tk.Y)

        self.status = tk.Label(chat_frame, anchor="w")
        self.status.pack(fill=tk.X, padx=10, pady=(0, 8))
        self._build_system_panel(panel_frame)

    def _build_system_panel(self, parent: object) -> None:
        title = tk.Label(parent, text="System", font=("TkDefaultFont", 12, "bold"), anchor="w")
        title.pack(fill=tk.X, padx=10, pady=(10, 8))

        self.overall_label = tk.Label(parent, anchor="w", text="Overall: UNKNOWN", relief=tk.RIDGE)
        self.overall_label.pack(fill=tk.X, padx=10, pady=(0, 8))

        self.backend_label = tk.Label(parent, anchor="w", justify=tk.LEFT)
        self.backend_label.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.model_label = tk.Label(parent, anchor="w", justify=tk.LEFT)
        self.model_label.pack(fill=tk.X, padx=10, pady=(0, 8))

        self.log_entries_label = tk.Label(parent, anchor="w")
        self.log_entries_label.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.last_check_label = tk.Label(parent, anchor="w")
        self.last_check_label.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.debug_label = tk.Label(parent, anchor="w")
        self.debug_label.pack(fill=tk.X, padx=10, pady=(0, 12))

        self.auto_self_check = tk.BooleanVar(value=self.preferences.auto_self_check_on_startup)
        auto_self_check = tk.Checkbutton(
            parent,
            text="Auto self-check on startup",
            variable=self.auto_self_check,
            command=self._on_auto_self_check_toggle,
            anchor="w",
            justify=tk.LEFT,
        )
        auto_self_check.pack(fill=tk.X, padx=10, pady=(0, 12))

        for label, command in PANEL_COMMANDS.items():
            if label == "Refresh Status":
                button = tk.Button(parent, text=label, command=self._refresh_status_from_button)
            else:
                button = tk.Button(parent, text=label, command=lambda value=command: self._send(value))
            button.pack(fill=tk.X, padx=10, pady=(0, 6))
            self.panel_buttons.append(button)

    def _build_menus(self) -> None:
        menubar = tk.Menu(self.root)
        edit = tk.Menu(menubar, tearoff=False)
        edit.add_command(label="Cut", accelerator="⌘X", command=self.handle_cut_event)
        edit.add_command(label="Copy", accelerator="⌘C", command=self.handle_copy_event)
        edit.add_command(label="Paste", accelerator="⌘V", command=self.handle_paste_event)
        edit.add_separator()
        edit.add_command(label="Select All", accelerator="⌘A", command=self.handle_select_all_event)
        menubar.add_cascade(label="Edit", menu=edit)
        self.root.configure(menu=menubar)

    def _bind_app_shortcuts(self) -> None:
        bindings = {
            "<Command-c>": self.handle_copy_event,
            "<Command-C>": self.handle_copy_event,
            "<Control-c>": self.handle_copy_event,
            "<Control-C>": self.handle_copy_event,
            "<Command-v>": self.handle_paste_event,
            "<Command-V>": self.handle_paste_event,
            "<Control-v>": self.handle_paste_event,
            "<Control-V>": self.handle_paste_event,
            "<Command-x>": self.handle_cut_event,
            "<Command-X>": self.handle_cut_event,
            "<Control-x>": self.handle_cut_event,
            "<Control-X>": self.handle_cut_event,
            "<Command-a>": self.handle_select_all_event,
            "<Command-A>": self.handle_select_all_event,
            "<Control-a>": self.handle_select_all_event,
            "<Control-A>": self.handle_select_all_event,
            "<<Copy>>": self.handle_copy_event,
            "<<Paste>>": self.handle_paste_event,
            "<<Cut>>": self.handle_cut_event,
            "<<SelectAll>>": self.handle_select_all_event,
        }
        for sequence, callback in bindings.items():
            self.root.bind_all(sequence, callback)
        if getenv("PROTO_MIND_DESKTOP_KEY_DEBUG") == "1":
            self.root.bind_all("<Key>", self._debug_key_event, add="+")

    def _bind_context_menu(self, widget: object, *, editable: bool) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        if editable:
            menu.add_command(label="Cut", command=lambda: self.handle_cut_event())
        menu.add_command(label="Copy", command=lambda: self.handle_copy_event())
        if editable:
            menu.add_command(label="Paste", command=lambda: self.handle_paste_event())
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self.handle_select_all_event())
        if not editable:
            menu.add_command(label="Copy All", command=self._copy_all)

        def popup(event: object) -> str:
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
            return "break"

        widget.bind("<Button-2>", popup)
        widget.bind("<Button-3>", popup)
        widget.bind("<Control-Button-1>", popup)

    def _debug_key_event(self, event: object) -> None:
        print(
            "Proto-Mind desktop key event: "
            f"keysym={getattr(event, 'keysym', None)} "
            f"keycode={getattr(event, 'keycode', None)} "
            f"state={getattr(event, 'state', None)} "
            f"widget={getattr(event, 'widget', None)}"
        )

    def _on_enter(self, _event: object) -> str:
        self._send_from_input()
        return "break"

    def _on_shift_enter(self, _event: object) -> str:
        self.input_box.insert(tk.INSERT, "\n")
        return "break"

    def _send_from_input(self) -> None:
        text = self.input_box.get("1.0", tk.END).strip()
        if not text:
            return
        self.input_box.delete("1.0", tk.END)
        self._send(text)

    def _send(self, text: str, *, append_user: bool = True, display_mode: str = "normal") -> None:
        if self.busy:
            return
        self.busy = True
        self.pending_display_mode = display_mode
        self._set_controls_busy(True)
        self._set_status("thinking...")
        if append_user:
            self.append_user_message(text)
        thread = threading.Thread(target=self._process_worker, args=(text,), daemon=True)
        thread.start()

    def _process_worker(self, text: str) -> None:
        try:
            response = self.runtime.process(text)
        except Exception as exc:  # pragma: no cover - defensive UI boundary.
            response = f"System error:\nDesktop processing error: {exc}"
        self._call_on_ui_thread(self._finish_response, response)

    def _call_on_ui_thread(self, callback: object, *args: object) -> None:
        try:
            self.root.after(0, callback, *args)
        except RuntimeError:
            callback(*args)

    def _finish_response(self, response: str | None) -> None:
        self.busy = False
        self._set_controls_busy(False)
        if response is None:
            self.root.destroy()
            return
        display_mode = getattr(self, "pending_display_mode", "normal")
        self.pending_display_mode = "normal"
        if display_mode == "status_refresh":
            self._finish_status_refresh_response(response)
            return
        display_response = format_desktop_response(response, debug=self.debug_output.get())
        kind = classify_desktop_output(response)
        if kind == "system":
            self.append_system_message(display_response)
        elif kind == "report":
            self.append_assistant_message(display_response, heading="Proto-Mind / System report")
        else:
            self.append_assistant_message(display_response)
        self._update_panel_from_output(response)
        self._set_status("ready")
        self.input_box.focus_set()

    def _finish_status_refresh_response(self, response: str) -> None:
        self._update_panel_from_output(response, update_last_check=True)
        if response.startswith("System error:"):
            self.append_system_message(response)
        else:
            entries = parse_log_entries(response)
            value = str(entries) if entries is not None else "unknown"
            self.append_system_message(f"Status refreshed. Log entries: {value}")
        self._set_status("ready")
        self.input_box.focus_set()

    def _set_controls_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.send_button.configure(state=state)
        for button in self.panel_buttons:
            button.configure(state=state)

    def _on_debug_toggle(self) -> None:
        self.preferences.debug_output = bool(self.debug_output.get())
        self._save_preferences()
        self._refresh_system_panel()
        self._set_status("ready" if not self.busy else "thinking...")

    def _on_auto_self_check_toggle(self) -> None:
        self.preferences.auto_self_check_on_startup = bool(self.auto_self_check.get())
        self._save_preferences()
        self._refresh_system_panel()

    def _save_preferences(self) -> None:
        save_desktop_preferences(self.preferences_path, self.preferences)

    def _startup_status_refresh(self) -> None:
        try:
            response = self.runtime.process("/session log status")
        except Exception as exc:  # pragma: no cover - defensive UI boundary.
            response = f"System error:\nStartup status refresh failed: {exc}"
        self._finish_startup_status_refresh(response)

    def _finish_startup_status_refresh(self, response: str | None) -> None:
        if response is None:
            return
        self._update_panel_from_output(response, update_last_check=True)
        if response.startswith("System error:"):
            self.append_system_message(response)
        if self.preferences.auto_self_check_on_startup:
            self.root.after(100, lambda: self._send("/session self-check", append_user=False))

    def _refresh_status_from_button(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_controls_busy(True)
        self._set_status("thinking...")
        try:
            response = self.runtime.process("/session log status")
        except Exception as exc:  # pragma: no cover - defensive UI boundary.
            response = f"System error:\nStatus refresh failed: {exc}"
        self.busy = False
        self._set_controls_busy(False)
        self._finish_status_refresh_response(response)

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
        self._refresh_system_panel()

    def _refresh_system_panel(self) -> None:
        colors = {
            "UNKNOWN": "#e6e6e6",
            "OK": "#cdeccd",
            "WARN": "#ffe3a3",
            "ERROR": "#f4b4b4",
        }
        self.overall_label.configure(
            text=f"Overall: {self.overall_status}",
            background=colors.get(self.overall_status, colors["UNKNOWN"]),
        )
        self.backend_label.configure(text=f"Backend: {self.runtime.backend_name}")
        model = self.runtime.model_name or "none"
        self.model_label.configure(text=f"Model: {model}")
        entries = str(self.log_entries) if self.log_entries is not None else "unknown"
        self.log_entries_label.configure(text=f"Log entries: {entries}")
        self.last_check_label.configure(text=f"Last check: {self.last_check}")
        debug = "on" if self.debug_output.get() else "off"
        self.debug_label.configure(text=f"Debug: {debug}")

    def append_user_message(self, text: str) -> None:
        self._append("User", text, heading_tag="heading_user")

    def append_assistant_message(self, text: str, *, heading: str = "Proto-Mind") -> None:
        self._append(heading, text, heading_tag="heading_assistant")

    def append_system_message(self, text: str) -> None:
        self._append("System", text, heading_tag="heading_system", body_tag="system")

    def _append(self, speaker: str, text: str, *, heading_tag: str, body_tag: str | None = None) -> None:
        self.history.insert(tk.END, f"{speaker}:\n", heading_tag)
        tag = "warning" if "WARN" in text or "error" in text.lower() else body_tag
        if tag:
            self.history.insert(tk.END, f"{text}\n\n", tag)
        else:
            self.history.insert(tk.END, f"{text}\n\n")
        self.history.see(tk.END)

    def _clear_history(self) -> None:
        self.history.delete("1.0", tk.END)

    def _copy_all(self) -> None:
        transcript = self._history_text()
        self.root.clipboard_clear()
        self.root.clipboard_append(transcript)
        try:
            self.root.update()
        except Exception:
            pass
        self.append_system_message("Transcript copied to clipboard.")

    def _save_transcript(self) -> None:
        try:
            path = save_transcript(self.runtime.project_root, self._history_text())
            self.append_system_message(f"Transcript saved: {path}")
        except Exception as exc:  # pragma: no cover - defensive UI boundary.
            self.append_system_message(f"Transcript save failed: {exc}")

    def _history_text(self) -> str:
        return self.history.get("1.0", tk.END).strip()

    def _set_status(self, state: str) -> None:
        self.status.configure(
            text=format_status_line(
                state,
                backend_status=self.runtime.status_label,
                debug_enabled=self.debug_output.get(),
            )
        )

    def get_focused_text_widget(self) -> object | None:
        widget = self.root.focus_get()
        return widget if self.is_input_widget(widget) or self.is_history_widget(widget) else None

    def is_input_widget(self, widget: object) -> bool:
        return widget is self.input_box

    def is_history_widget(self, widget: object) -> bool:
        return widget is self.history

    def handle_copy_event(self, event: object | None = None) -> str:
        widget = getattr(event, "widget", None) if event is not None else self.get_focused_text_widget()
        if not (self.is_input_widget(widget) or self.is_history_widget(widget)):
            widget = self.get_focused_text_widget()
        return copy_selection_from(widget) if widget is not None else "break"

    def handle_paste_event(self, event: object | None = None) -> str:
        widget = getattr(event, "widget", None) if event is not None else self.get_focused_text_widget()
        target = widget if self.is_input_widget(widget) else self.input_box
        return paste_into_input(target)

    def handle_cut_event(self, event: object | None = None) -> str:
        widget = getattr(event, "widget", None) if event is not None else self.get_focused_text_widget()
        return cut_from_input(widget) if self.is_input_widget(widget) else "break"

    def handle_select_all_event(self, event: object | None = None) -> str:
        widget = getattr(event, "widget", None) if event is not None else self.get_focused_text_widget()
        if self.is_input_widget(widget) or self.is_history_widget(widget):
            return select_all_in(widget)
        return "break"


def _tkinter_unavailable_message() -> str:
    detail = f" ({TKINTER_IMPORT_ERROR})" if TKINTER_IMPORT_ERROR else ""
    return f"tkinter is not available in this Python environment{detail}."


def format_backend_status(backend_name: str, model_name: str | None = None) -> str:
    if backend_name == "ollama" and model_name:
        return f"Backend: ollama | Model: {model_name}"
    return f"Backend: {backend_name}"


def format_status_line(state: str, *, backend_status: str, debug_enabled: bool) -> str:
    debug = "on" if debug_enabled else "off"
    return f"Status: {state} | {backend_status} | Debug: {debug}"


def parse_overall_status(text: str) -> str:
    for label in ("Overall", "Status"):
        match = search(rf"^\s*{label}\s*:\s*(OK|WARN|ERROR)\b", text, IGNORECASE | MULTILINE)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def parse_log_entries(text: str) -> int | None:
    patterns = (
        r"^\s*entries\s*:\s*(\d+)\b",
        r"^\s*Log entries\s*:\s*(\d+)\b",
        r"^\s*-\s*total log entries\s*:\s*(\d+)\b",
    )
    for pattern in patterns:
        match = search(pattern, text, IGNORECASE | MULTILINE)
        if match:
            return int(match.group(1))
    return None


def format_chat_entry(speaker: str, text: str) -> str:
    return f"{speaker}:\n{text.strip()}\n"


def transcript_filename(timestamp: datetime | None = None) -> str:
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    return f"desktop_chat_transcript_{stamp}.md"


def transcript_path(project_root: Path, timestamp: datetime | None = None) -> Path:
    return project_root / "exports" / transcript_filename(timestamp)


def save_transcript(project_root: Path, transcript_text: str, timestamp: datetime | None = None) -> Path:
    destination = transcript_path(project_root, timestamp)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(transcript_text.rstrip() + "\n", encoding="utf-8")
    return destination


def desktop_preferences_path(project_root: Path) -> Path:
    return project_root / "desktop_prefs.json"


def load_desktop_preferences(path: Path) -> DesktopPreferences:
    if not path.exists():
        return DesktopPreferences()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = load(handle)
    except (OSError, JSONDecodeError, TypeError, ValueError):
        return DesktopPreferences()
    if not isinstance(data, dict):
        return DesktopPreferences()
    geometry = data.get("window_geometry")
    return DesktopPreferences(
        debug_output=bool(data.get("debug_output", False)),
        auto_self_check_on_startup=bool(data.get("auto_self_check_on_startup", False)),
        window_geometry=str(geometry) if geometry else None,
    )


def save_desktop_preferences(path: Path, preferences: DesktopPreferences) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        dump(preferences.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def bind_clipboard_shortcuts(widget: object, *, editable: bool) -> None:
    for sequence in ("<Command-c>", "<Command-C>", "<Control-c>", "<Control-C>", "<<Copy>>"):
        widget.bind(sequence, lambda event: copy_selection_from(widget))
    for sequence in ("<Command-a>", "<Command-A>", "<Control-a>", "<Control-A>", "<<SelectAll>>"):
        widget.bind(sequence, lambda event: select_all_in(widget))
    if editable:
        for sequence in ("<Command-v>", "<Command-V>", "<Control-v>", "<Control-V>", "<<Paste>>"):
            widget.bind(sequence, lambda event: paste_into_input(widget))
        for sequence in ("<Command-x>", "<Command-X>", "<Control-x>", "<Control-X>", "<<Cut>>"):
            widget.bind(sequence, lambda event: cut_from_input(widget))


def make_text_read_only(widget: object) -> None:
    blocked = (
        "<Key>",
        "<BackSpace>",
        "<Delete>",
        "<Command-v>",
        "<Command-V>",
        "<Control-v>",
        "<Control-V>",
        "<Command-x>",
        "<Command-X>",
        "<Control-x>",
        "<Control-X>",
        "<<Paste>>",
        "<<Cut>>",
    )
    for sequence in blocked:
        widget.bind(sequence, lambda _event: "break")


def copy_selection_from(widget: object | None) -> str:
    if widget is None:
        return "break"
    try:
        text = widget.get("sel.first", "sel.last")
    except Exception:
        return "break"
    root = widget.winfo_toplevel()
    root.clipboard_clear()
    root.clipboard_append(text)
    try:
        root.update()
    except Exception:
        pass
    return "break"


def paste_into_input(widget: object | None) -> str:
    if widget is None:
        return "break"
    try:
        text = widget.winfo_toplevel().clipboard_get()
    except Exception:
        return "break"
    try:
        widget.delete("sel.first", "sel.last")
    except Exception:
        pass
    widget.insert("insert", text)
    return "break"


def cut_from_input(widget: object | None) -> str:
    if widget is None:
        return "break"
    try:
        text = widget.get("sel.first", "sel.last")
    except Exception:
        return "break"
    root = widget.winfo_toplevel()
    root.clipboard_clear()
    root.clipboard_append(text)
    try:
        root.update()
    except Exception:
        pass
    widget.delete("sel.first", "sel.last")
    return "break"


def select_all_in(widget: object | None) -> str:
    if widget is None:
        return "break"
    widget.tag_add("sel", "1.0", "end-1c")
    widget.mark_set("insert", "1.0")
    widget.see("insert")
    return "break"


copy_selection = copy_selection_from
paste_into_widget = paste_into_input
cut_selection = cut_from_input
select_all = select_all_in


def is_operator_or_natural_output(output: str) -> bool:
    if output.startswith("Natural command matched:"):
        return True
    return not output.startswith("Proto-Mind:")


def classify_desktop_output(output: str) -> str:
    if output.startswith("Natural command matched:") or output.startswith("System error:"):
        return "system"
    if is_operator_or_natural_output(output):
        return "report"
    return "assistant"


def compact_desktop_output(output: str) -> str:
    if is_operator_or_natural_output(output):
        return output
    markers = [
        "\nObserver:",
        "\nMemory used:",
        "\nRetrieval trace:",
        "\nMemory decision:",
        "\nGrounding audit:",
        "\nSelf-reflection:",
    ]
    cut_at = min((output.find(marker) for marker in markers if output.find(marker) != -1), default=-1)
    if cut_at == -1:
        return output
    answer = output[:cut_at].strip()
    return answer or output


def format_desktop_response(output: str, *, debug: bool = False) -> str:
    if debug:
        return output
    return compact_desktop_output(output)


def main() -> None:
    if not TKINTER_AVAILABLE:
        print(_tkinter_unavailable_message())
        raise SystemExit(1)
    runtime = create_desktop_runtime()
    try:
        root = tk.Tk()
    except Exception as exc:
        print(f"Unable to open Proto-Mind Desktop v0.1 window: {exc}")
        raise SystemExit(1)
    ProtoMindDesktopApp(root, runtime)
    root.mainloop()


if __name__ == "__main__":
    main()
