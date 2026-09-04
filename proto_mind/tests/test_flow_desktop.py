"""Core flow checks: desktop."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    LOCAL_CAPABILITY_CARD_BADGES,
    LOCAL_CAPABILITY_CONTRACTS,
    Path,
    SessionOperatorLogger,
    SimpleNamespace,
    TemporaryDirectory,
    build_local_capability_card_html,
    datetime,
    desktop_app,
    json,
    os,
    patch,
    project_local_capability_card,
    render_local_capability_card_html,
)


class DesktopFlowTests(unittest.TestCase):
    def test_desktop_app_module_imports_safely_and_exposes_quick_commands(self) -> None:
        self.assertIn("Self-Check", desktop_app.QUICK_COMMANDS)
        self.assertEqual(desktop_app.QUICK_COMMANDS["Self-Check"], "/session self-check")
        self.assertEqual(desktop_app.QUICK_COMMANDS["Health"], "/session health")
        self.assertEqual(desktop_app.QUICK_COMMANDS["Doctor"], "/session doctor")
        self.assertEqual(desktop_app.QUICK_COMMANDS["Review"], "/session review")
        self.assertEqual(desktop_app.QUICK_COMMANDS["Log Status"], "/session log status")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Check System"], "/session self-check")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Refresh Status"], "/session log status")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Health"], "/session health")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Doctor"], "/session doctor")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Review"], "/session review")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Log Status"], "/session log status")
        self.assertEqual(desktop_app.PANEL_COMMANDS["Export Last 20"], "/session log export --last 20")
        self.assertTrue(hasattr(desktop_app, "main"))

    def test_desktop_view_model_projects_only_exact_local_contract_commands(self) -> None:
        for contract in LOCAL_CAPABILITY_CONTRACTS:
            with self.subTest(command=contract.command):
                output = f"{contract.title}\nStatus: OK\nlocal report"
                view_model = project_local_capability_card(contract.command, output)

                self.assertIsNotNone(view_model)
                self.assertEqual(view_model.contract_name, contract.name)
                self.assertEqual(view_model.command, contract.command)
                self.assertEqual(view_model.status, "OK")
                self.assertEqual(view_model.body, output)
                self.assertEqual(view_model.badges, LOCAL_CAPABILITY_CARD_BADGES)
                self.assertTrue(view_model.local_only)
                self.assertTrue(view_model.read_only)
                self.assertEqual(view_model.transport, "none")

        for unsafe_input in (
            "daily_doctor",
            "/daily doctor --verbose",
            "/memory status",
            "run daily doctor",
            "",
        ):
            with self.subTest(unsafe_input=unsafe_input):
                self.assertIsNone(project_local_capability_card(unsafe_input, "Status: OK"))

    def test_desktop_view_model_renders_escaped_local_capability_card(self) -> None:
        output = "Daily Layer Doctor\nStatus: WARN\n<script>alert('x')</script>"
        view_model = project_local_capability_card("/daily doctor", output)

        self.assertIsNotNone(view_model)
        rendered = render_local_capability_card_html(view_model)

        self.assertIn("PROTO-MIND LOCAL CAPABILITY", rendered)
        self.assertIn("capability-status-warn", rendered)
        self.assertIn("/daily doctor", rendered)
        self.assertIn("LOCAL", rendered)
        self.assertIn("READ ONLY", rendered)
        self.assertIn("NO NETWORK", rendered)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>", rendered)

    def test_desktop_view_model_fails_closed_to_text_fallback(self) -> None:
        unsafe_envelope = {
            "structuredContent": {
                "command": "/daily doctor",
                "contract": "daily_doctor",
                "status": "OK",
                "summary": "Daily Layer Doctor",
                "read_only": True,
                "local_only": True,
            },
            "content": [{"type": "text", "text": "Daily Layer Doctor"}],
            "_meta": {
                "proto_mind": {
                    "local_only": False,
                    "transport": "network",
                    "network_access": True,
                    "store_mutation": False,
                    "external_exposure": True,
                }
            },
        }
        fake_result = SimpleNamespace(to_mcp_result=lambda: unsafe_envelope)
        with patch("proto_mind.desktop_view_model.build_local_capability_result", return_value=fake_result):
            self.assertIsNone(project_local_capability_card("/daily doctor", "Daily Layer Doctor"))
        with patch(
            "proto_mind.desktop_view_model.build_local_capability_result",
            side_effect=RuntimeError("presentation failure"),
        ):
            self.assertIsNone(build_local_capability_card_html("/daily doctor", "Daily Layer Doctor"))

    def test_desktop_backend_status_label_helpers(self) -> None:
        self.assertEqual(desktop_app.format_backend_status("mock"), "Backend: mock")
        self.assertEqual(
            desktop_app.format_backend_status("ollama", "qwen3:8b"),
            "Backend: ollama | Model: qwen3:8b",
        )
        self.assertEqual(
            desktop_app.format_status_line("ready", backend_status="Backend: mock", debug_enabled=False),
            "Status: ready | Backend: mock | Debug: off",
        )
        self.assertEqual(
            desktop_app.format_status_line(
                "thinking...",
                backend_status="Backend: ollama | Model: qwen3:8b",
                debug_enabled=True,
            ),
            "Status: thinking... | Backend: ollama | Model: qwen3:8b | Debug: on",
        )

    def test_desktop_system_panel_status_parsers(self) -> None:
        self.assertEqual(desktop_app.parse_overall_status("Session Self-Check\nOverall: OK"), "OK")
        self.assertEqual(desktop_app.parse_overall_status("Session Self-Check\nOverall: WARN"), "WARN")
        self.assertEqual(desktop_app.parse_overall_status("Session Self-Check\nOverall: ERROR"), "ERROR")
        self.assertEqual(desktop_app.parse_overall_status("Session Health\nStatus: OK"), "OK")
        self.assertEqual(desktop_app.parse_overall_status("Session Doctor\nStatus: WARN"), "WARN")
        self.assertEqual(desktop_app.parse_overall_status("Session Health\nStatus: ERROR"), "ERROR")
        self.assertEqual(desktop_app.parse_overall_status("No status here"), "UNKNOWN")

        self.assertEqual(desktop_app.parse_log_entries("Session log status\n  entries: 13"), 13)
        self.assertEqual(desktop_app.parse_log_entries("Log entries: 21"), 21)
        self.assertEqual(desktop_app.parse_log_entries("- total log entries: 34"), 34)
        self.assertIsNone(desktop_app.parse_log_entries("entries: unknown"))
        self.assertIsNone(desktop_app.parse_log_entries("No entries here"))

    def test_desktop_preferences_defaults_load_save_and_corrupt_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = desktop_app.desktop_preferences_path(root)

            defaults = desktop_app.DesktopPreferences()
            self.assertFalse(defaults.debug_output)
            self.assertFalse(defaults.auto_self_check_on_startup)
            self.assertIsNone(defaults.window_geometry)
            self.assertEqual(defaults.to_dict(), {"debug_output": False, "auto_self_check_on_startup": False})
            self.assertEqual(path, root / "desktop_prefs.json")
            self.assertEqual(desktop_app.load_desktop_preferences(path), defaults)

            valid = {
                "debug_output": True,
                "auto_self_check_on_startup": True,
                "window_geometry": "1100x700+1+2",
            }
            path.write_text(json.dumps(valid), encoding="utf-8")
            loaded = desktop_app.load_desktop_preferences(path)
            self.assertTrue(loaded.debug_output)
            self.assertTrue(loaded.auto_self_check_on_startup)
            self.assertEqual(loaded.window_geometry, "1100x700+1+2")

            saved_path = desktop_app.save_desktop_preferences(
                path,
                desktop_app.DesktopPreferences(debug_output=False, auto_self_check_on_startup=True),
            )
            self.assertEqual(saved_path, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["debug_output"], False)
            self.assertEqual(saved["auto_self_check_on_startup"], True)

            path.write_text("{not valid json", encoding="utf-8")
            fallback = desktop_app.load_desktop_preferences(path)
            self.assertFalse(fallback.debug_output)
            self.assertFalse(fallback.auto_self_check_on_startup)

    def test_desktop_runtime_status_label_uses_configured_ollama_model(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(
                os.environ,
                {
                    "PROTO_MIND_REASONER": "ollama",
                    "PROTO_MIND_OLLAMA_MODEL": "qwen3:8b",
                    "PROTO_MIND_OLLAMA_URL": "http://localhost:11434",
                },
                clear=False,
            ):
                runtime = desktop_app.create_desktop_runtime(root)

            self.assertEqual(runtime.backend_name, "ollama")
            self.assertEqual(runtime.model_name, "qwen3:8b")
            self.assertEqual(runtime.status_label, "Backend: ollama | Model: qwen3:8b")

    def test_desktop_compact_output_strips_debug_blocks_for_normal_turns(self) -> None:
        output = (
            "Proto-Mind: concise answer\n"
            "Observer: {'query_type': 'new_question'}\n"
            "Memory decision: {'should_store': False}\n"
            "Grounding audit:\n"
            "  status: not_needed\n"
            "Self-reflection:\n"
            "  warnings: none"
        )

        compact = desktop_app.compact_desktop_output(output)

        self.assertEqual(compact, "Proto-Mind: concise answer")
        self.assertNotIn("Observer:", compact)
        self.assertNotIn("Memory decision:", compact)
        self.assertEqual(desktop_app.format_desktop_response(output, debug=True), output)

    def test_desktop_compact_output_falls_back_for_unknown_format(self) -> None:
        output = "Unexpected output format\nObserver: maybe"
        self.assertEqual(desktop_app.compact_desktop_output(output), output)

    def test_desktop_compact_output_preserves_operator_and_natural_reports(self) -> None:
        operator_output = "Session Health\nStatus: OK\nChecks:\n- session log exists: OK"
        natural_output = "Natural command matched: /session self-check\n\nSession Self-Check\nOverall: OK"

        self.assertEqual(desktop_app.compact_desktop_output(operator_output), operator_output)
        self.assertEqual(desktop_app.compact_desktop_output(natural_output), natural_output)
        self.assertEqual(desktop_app.classify_desktop_output(operator_output), "report")
        self.assertEqual(desktop_app.classify_desktop_output(natural_output), "system")

    def test_desktop_chat_entry_and_transcript_path_helpers(self) -> None:
        timestamp = datetime(2026, 6, 16, 12, 34, 56)

        self.assertEqual(desktop_app.format_chat_entry("User", "hello"), "User:\nhello\n")
        self.assertEqual(
            desktop_app.transcript_filename(timestamp),
            "desktop_chat_transcript_2026-06-16_12-34-56.md",
        )
        self.assertEqual(
            desktop_app.transcript_path(Path("/tmp/proto"), timestamp),
            Path("/tmp/proto/exports/desktop_chat_transcript_2026-06-16_12-34-56.md"),
        )

    def test_desktop_save_transcript_writes_exports_only_when_explicitly_called(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_log = log_path.read_bytes()
            timestamp = datetime(2026, 6, 16, 12, 34, 56)

            path = desktop_app.save_transcript(root, "User:\nhello\n\nProto-Mind:\nhi", timestamp)

            self.assertTrue(path.exists())
            self.assertEqual(path.parent, root / "exports")
            self.assertIn("desktop_chat_transcript_2026-06-16_12-34-56.md", path.name)
            self.assertIn("Proto-Mind:\nhi", path.read_text(encoding="utf-8"))
            self.assertEqual(log_path.read_bytes(), before_log)
            self.assertEqual(logger.status().entry_count, 1)

    def test_desktop_clipboard_shortcut_helpers_bind_expected_sequences(self) -> None:
        class FakeWidget:
            def __init__(self) -> None:
                self.bindings: dict[str, object] = {}

            def bind(self, sequence: str, callback: object) -> None:
                self.bindings[sequence] = callback

        editable = FakeWidget()
        readonly = FakeWidget()

        desktop_app.bind_clipboard_shortcuts(editable, editable=True)
        desktop_app.bind_clipboard_shortcuts(readonly, editable=False)

        common_sequences = (
            "<Command-c>",
            "<Command-C>",
            "<Control-c>",
            "<Control-C>",
            "<<Copy>>",
            "<Command-a>",
            "<Command-A>",
            "<Control-a>",
            "<Control-A>",
            "<<SelectAll>>",
        )
        for sequence in common_sequences:
            self.assertIn(sequence, editable.bindings)
            self.assertIn(sequence, readonly.bindings)
        editable_sequences = (
            "<Command-v>",
            "<Command-V>",
            "<Control-v>",
            "<Control-V>",
            "<<Paste>>",
            "<Command-x>",
            "<Command-X>",
            "<Control-x>",
            "<Control-X>",
            "<<Cut>>",
        )
        for sequence in editable_sequences:
            self.assertIn(sequence, editable.bindings)
            self.assertNotIn(sequence, readonly.bindings)

    def test_desktop_clipboard_robust_app_helpers_exist(self) -> None:
        for name in (
            "_build_menus",
            "_bind_app_shortcuts",
            "_bind_context_menu",
            "get_focused_text_widget",
            "handle_copy_event",
            "handle_paste_event",
            "handle_cut_event",
            "handle_select_all_event",
        ):
            self.assertTrue(hasattr(desktop_app.ProtoMindDesktopApp, name))
        for name in (
            "copy_selection_from",
            "paste_into_input",
            "cut_from_input",
            "select_all_in",
        ):
            self.assertTrue(hasattr(desktop_app, name))

    def test_desktop_clipboard_helpers_copy_paste_cut_and_select_all(self) -> None:
        class FakeRoot:
            def __init__(self) -> None:
                self.clipboard = ""
                self.updated = False

            def clipboard_clear(self) -> None:
                self.clipboard = ""

            def clipboard_append(self, text: str) -> None:
                self.clipboard += text

            def clipboard_get(self) -> str:
                return self.clipboard

            def update(self) -> None:
                self.updated = True

        class FakeText:
            def __init__(self, text: str, root: FakeRoot) -> None:
                self.text = text
                self.root = root
                self.selection = (0, len(text))
                self.inserted: list[tuple[str, str]] = []
                self.tags: list[tuple[str, str, str]] = []
                self.mark: tuple[str, str] | None = None
                self.seen: str | None = None

            def winfo_toplevel(self) -> FakeRoot:
                return self.root

            def get(self, start: str, end: str) -> str:
                if (start, end) == ("sel.first", "sel.last"):
                    return self.text[self.selection[0] : self.selection[1]]
                return self.text

            def delete(self, start: str, end: str) -> None:
                if (start, end) == ("sel.first", "sel.last"):
                    left, right = self.selection
                    self.text = self.text[:left] + self.text[right:]
                    self.selection = (left, left)

            def insert(self, index: str, text: str) -> None:
                self.inserted.append((index, text))
                if index == "insert":
                    left, _right = self.selection
                    self.text = self.text[:left] + text + self.text[left:]

            def tag_add(self, tag: str, start: str, end: str) -> None:
                self.tags.append((tag, start, end))

            def mark_set(self, mark: str, index: str) -> None:
                self.mark = (mark, index)

            def see(self, index: str) -> None:
                self.seen = index

        root = FakeRoot()
        widget = FakeText("hello", root)

        self.assertEqual(desktop_app.copy_selection(widget), "break")
        self.assertEqual(root.clipboard, "hello")
        self.assertTrue(root.updated)

        widget.selection = (0, 2)
        root.updated = False
        self.assertEqual(desktop_app.cut_selection(widget), "break")
        self.assertEqual(root.clipboard, "he")
        self.assertEqual(widget.text, "llo")
        self.assertTrue(root.updated)

        root.clipboard = "yo"
        widget.selection = (0, 0)
        self.assertEqual(desktop_app.paste_into_widget(widget), "break")
        self.assertEqual(widget.text, "yollo")

        self.assertEqual(desktop_app.select_all(widget), "break")
        self.assertIn(("sel", "1.0", "end-1c"), widget.tags)
        self.assertEqual(widget.mark, ("insert", "1.0"))
        self.assertEqual(widget.seen, "insert")

    def test_desktop_clipboard_helpers_handle_missing_selection_cleanly(self) -> None:
        class NoSelectionWidget:
            def get(self, _start: str, _end: str) -> str:
                raise RuntimeError("no selection")

            def winfo_toplevel(self) -> object:
                raise AssertionError("clipboard should not be touched")

        widget = NoSelectionWidget()

        self.assertEqual(desktop_app.copy_selection_from(widget), "break")
        self.assertEqual(desktop_app.cut_from_input(widget), "break")
        self.assertEqual(desktop_app.copy_selection_from(None), "break")
        self.assertEqual(desktop_app.paste_into_input(None), "break")
        self.assertEqual(desktop_app.cut_from_input(None), "break")
        self.assertEqual(desktop_app.select_all_in(None), "break")

    def test_desktop_make_text_read_only_binds_edit_blockers(self) -> None:
        class FakeWidget:
            def __init__(self) -> None:
                self.bindings: dict[str, object] = {}

            def bind(self, sequence: str, callback: object) -> None:
                self.bindings[sequence] = callback

        widget = FakeWidget()
        desktop_app.make_text_read_only(widget)

        for sequence in (
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
        ):
            self.assertIn(sequence, widget.bindings)

    def test_desktop_launch_scripts_exist_and_set_expected_backends(self) -> None:
        root = Path(__file__).resolve().parents[2]
        ollama_script = root / "scripts" / "run_desktop_ollama.sh"
        mock_script = root / "scripts" / "run_desktop_mock.sh"

        self.assertTrue(ollama_script.exists())
        self.assertTrue(mock_script.exists())
        self.assertTrue(os.access(ollama_script, os.X_OK))
        self.assertTrue(os.access(mock_script, os.X_OK))
        self.assertIn("PROTO_MIND_REASONER=ollama", ollama_script.read_text(encoding="utf-8"))
        self.assertIn("PROTO_MIND_OLLAMA_MODEL", ollama_script.read_text(encoding="utf-8"))
        self.assertIn("PROTO_MIND_REASONER=mock", mock_script.read_text(encoding="utf-8"))

    def test_desktop_runtime_process_uses_same_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            runtime = desktop_app.create_desktop_runtime(root)

            output = runtime.process("/session log status")

            self.assertIn("Session operator log:", output)
            self.assertEqual(runtime.session_logger.status().entry_count, 0)
