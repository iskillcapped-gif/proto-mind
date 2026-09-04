"""Core flow checks: pyside."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    Path,
    TemporaryDirectory,
    build_local_capability_card_html,
    os,
    pyside_app,
)


class PysideFlowTests(unittest.TestCase):
    def test_pyside_app_imports_safely_and_exposes_optional_dependency_message(self) -> None:
        self.assertTrue(hasattr(pyside_app, "main"))
        self.assertEqual(pyside_app.PYSIDE_APP_VERSION, "v2.3.0")
        self.assertIn("Cognitive Control Room", pyside_app.PYSIDE_APP_TITLE)
        self.assertIn("Welcome back", pyside_app.START_MESSAGE)
        self.assertIn("PySide6 is not installed.", pyside_app.pyside_missing_message())
        self.assertIn("python3 -m pip install PySide6", pyside_app.pyside_missing_message())

    def test_pyside_panel_command_mapping_and_scripts(self) -> None:
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Start Brief"], "/session start-brief")
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Daily Brief"], "/daily brief")
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Next Work"], "/agenda next")
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Experience"], "/experience doctor")
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Skill State"], "/skills lifecycle-status")
        self.assertEqual(pyside_app.PYSIDE_PANEL_COMMANDS["Showcase"], "/showcase demo")
        self.assertEqual(len(pyside_app.PYSIDE_PANEL_COMMANDS), 12)
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        for command in pyside_app.PYSIDE_PANEL_COMMANDS.values():
            self.assertIn(command, registry)
            self.assertTrue(registry[command].read_only)
            self.assertEqual(registry[command].mutates, "none")
        self.assertEqual(
            [group for group, _ in pyside_app.PYSIDE_CONTROL_DECK_GROUPS],
            ["SESSION", "COGNITIVE STATE", "TRUST & EVIDENCE"],
        )
        self.assertEqual(len(pyside_app.PYSIDE_PROMPT_CHIPS), 4)
        self.assertEqual(
            pyside_app.pyside_registry_summary(),
            "387 commands / 41 capability families",
        )

        root = Path(__file__).resolve().parents[2]
        ollama_script = root / "scripts" / "run_pyside_ollama.sh"
        mock_script = root / "scripts" / "run_pyside_mock.sh"
        build_script = root / "scripts" / "build_macos_app_launcher.sh"
        open_script = root / "scripts" / "open_pyside_app.sh"
        shortcut_script = root / "scripts" / "install_macos_app_shortcut.sh"
        icon_source = root / "assets" / "proto_mind_icon.svg"
        self.assertTrue(ollama_script.exists())
        self.assertTrue(mock_script.exists())
        self.assertTrue(build_script.exists())
        self.assertTrue(open_script.exists())
        self.assertTrue(shortcut_script.exists())
        self.assertTrue(icon_source.exists())
        self.assertTrue(os.access(ollama_script, os.X_OK))
        self.assertTrue(os.access(mock_script, os.X_OK))
        self.assertTrue(os.access(build_script, os.X_OK))
        self.assertTrue(os.access(open_script, os.X_OK))
        self.assertTrue(os.access(shortcut_script, os.X_OK))
        self.assertIn("PROTO_MIND_REASONER=ollama", ollama_script.read_text(encoding="utf-8"))
        self.assertIn("PROTO_MIND_OLLAMA_MODEL", ollama_script.read_text(encoding="utf-8"))
        self.assertIn("PROTO_MIND_REASONER=mock", mock_script.read_text(encoding="utf-8"))

        build_text = build_script.read_text(encoding="utf-8")
        self.assertIn("dist/${APP_NAME}.app", build_text)
        self.assertIn("CFBundleName", build_text)
        self.assertIn("<string>Proto-Mind</string>", build_text)
        self.assertIn("CFBundleExecutable", build_text)
        self.assertIn("<string>2.3.0</string>", build_text)
        self.assertIn("CFBundleIconFile", build_text)
        self.assertIn("ProtoMind.icns", build_text)
        self.assertIn("iconutil -c icns", build_text)
        self.assertIn("local.proto-mind.pyside", build_text)
        self.assertIn("PROTO_MIND_REASONER=ollama", build_text)
        self.assertIn("PROTO_MIND_OLLAMA_MODEL", build_text)
        self.assertIn("proto_mind.pyside_app", build_text)
        self.assertIn("PYTHON_CANDIDATES=(", build_text)
        self.assertIn("for candidate in", build_text)
        self.assertIn("/opt/homebrew/opt/python@3.11/bin/python3", build_text)
        self.assertIn("/opt/homebrew/opt/python@3.11/bin/python3.11", build_text)
        self.assertIn("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3", build_text)
        self.assertIn('PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"', build_text)
        self.assertIn('PROJECT_DIR="$(CDPATH= cd -- "${APP_EXEC_DIR}/../../../.." && pwd)"', build_text)
        self.assertIn('sys.path.insert(0, os.environ["PROTO_MIND_PROJECT_DIR"])', build_text)
        self.assertNotIn("/Users/", build_text)
        self.assertIn("import proto_mind", build_text)
        self.assertIn("import PySide6", build_text)
        self.assertIn("Could not find a Python that can import Proto-Mind and PySide6.", build_text)
        self.assertIn("Candidates checked:", build_text)
        self.assertIn("/tmp/proto_mind_launcher.log", build_text)
        self.assertIn("Proto-Mind launcher started:", build_text)
        self.assertIn("Ollama check: OK", build_text)
        self.assertNotIn("PYTHON_BIN=\"${PROJECT_DIR}/.venv/bin/python\"", build_text)

        open_text = open_script.read_text(encoding="utf-8")
        self.assertIn("dist/Proto-Mind.app", open_text)
        self.assertIn("build_macos_app_launcher.sh", open_text)

        shortcut_text = shortcut_script.read_text(encoding="utf-8")
        self.assertIn("dist/Proto-Mind.app", shortcut_text)
        self.assertIn("${HOME}/Desktop", shortcut_text)
        self.assertIn("--applications", shortcut_text)
        self.assertIn("/Applications", shortcut_text)
        self.assertIn("ln -sfn", shortcut_text)

    def test_pyside_demo_runway_has_safe_ordered_steps(self) -> None:
        steps = pyside_app.PYSIDE_DEMO_DECK_STEPS
        self.assertEqual([step.number for step in steps], list(range(1, 13)))
        self.assertEqual(steps[0].payload, "/showcase status")
        self.assertEqual(steps[5].action, "normal_prompt")
        self.assertEqual(steps[8].payload, "/runner-exec dry-run /daily doctor")
        self.assertEqual(steps[-1].payload, "/experience stop")
        self.assertNotIn("/context injection", "\n".join(step.payload for step in steps))
        report = pyside_app.pyside_demo_deck_doctor()
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.step_count, 12)
        self.assertEqual(report.issues, [])

    def test_pyside_demo_runway_extracts_exact_experience_consent(self) -> None:
        command = (
            "/experience consent CONSENT EXPERIENCE PREVIEW FOR SESSION: "
            "experience-20260721-ab12"
        )
        output = f"Experience Preview\nExact consent command:\n{command}\n"
        self.assertEqual(
            pyside_app.extract_pyside_demo_command(
                output,
                "/experience consent CONSENT EXPERIENCE PREVIEW FOR SESSION:",
            ),
            command,
        )

    def test_pyside_demo_runway_extracts_exact_runner_usage(self) -> None:
        command = "/runner-exec run CONFIRM RUN READONLY: /daily doctor"
        output = f"Read-only Runner MVP Dry Run\nexact_usage: {command}\n"
        self.assertEqual(
            pyside_app.extract_pyside_demo_command(
                output,
                "/runner-exec run CONFIRM RUN READONLY:",
            ),
            command,
        )

    def test_pyside_demo_runway_extractor_refuses_unsafe_or_unknown_commands(self) -> None:
        runner_prefix = "/runner-exec run CONFIRM RUN READONLY:"
        self.assertIsNone(
            pyside_app.extract_pyside_demo_command(
                "exact_usage: /runner-exec run CONFIRM RUN READONLY: /daily doctor; /memory status",
                runner_prefix,
            )
        )
        self.assertIsNone(
            pyside_app.extract_pyside_demo_command(
                "/context injection enable true",
                "/context injection enable",
            )
        )
        self.assertIsNone(
            pyside_app.extract_pyside_demo_command(
                "/runner-exec run CONFIRM RUN READONLY:",
                runner_prefix,
            )
        )
        self.assertIsNone(
            pyside_app.extract_pyside_demo_command(
                "/runner-exec run CONFIRM RUN READONLY: /exports doctor",
                runner_prefix,
            )
        )

    def test_pyside_context_indicator_is_read_only_and_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = list(root.rglob("*"))
            missing = pyside_app.read_context_indicator(root)
            after = list(root.rglob("*"))
            settings_path = root / "proto_mind" / "data" / "context_injection.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text('{"enabled": true}', encoding="utf-8")
            enabled = pyside_app.read_context_indicator(root)
            settings_path.write_text('{"enabled": false}', encoding="utf-8")
            disabled = pyside_app.read_context_indicator(root)
            settings_path.write_text("not-json", encoding="utf-8")
            invalid = pyside_app.read_context_indicator(root)

        self.assertEqual(missing.state, "OFF")
        self.assertEqual(after, before)
        self.assertEqual(enabled.text, "CONTEXT ON")
        self.assertEqual(disabled.text, "CONTEXT OFF")
        self.assertEqual(invalid.state, "UNKNOWN")
        self.assertIn("no UI repair", invalid.detail)

    def test_pyside_enter_send_key_helpers_and_badge_styles(self) -> None:
        self.assertTrue(pyside_app.should_send_on_key("return"))
        self.assertTrue(pyside_app.should_send_on_key("enter"))
        self.assertTrue(pyside_app.should_send_on_key("return", {"ctrl"}))
        self.assertTrue(pyside_app.should_send_on_key("return", {"cmd"}))
        self.assertFalse(pyside_app.should_send_on_key("return", {"shift"}))
        self.assertFalse(pyside_app.should_send_on_key("space"))
        self.assertTrue(pyside_app.should_insert_newline_on_key("return", {"shift"}))
        self.assertFalse(pyside_app.should_insert_newline_on_key("return"))

        self.assertIn("#245a38", pyside_app.pyside_badge_style("OK"))
        self.assertIn("#7a5518", pyside_app.pyside_badge_style("WARN"))
        self.assertIn("#7a2d2d", pyside_app.pyside_badge_style("ERROR"))
        self.assertIn("#4a4d55", pyside_app.pyside_badge_style("UNKNOWN"))
        self.assertIn("#8ee3ce", pyside_app.pyside_context_style("OFF"))
        self.assertIn("#ffd18a", pyside_app.pyside_context_style("ON"))
        stylesheet = pyside_app.pyside_dark_stylesheet()
        self.assertIn("QFrame#brandCard", stylesheet)
        self.assertIn("QFrame#controlDeck", stylesheet)
        self.assertIn("QPushButton#primaryButton", stylesheet)

    def test_pyside_worker_helpers_and_optional_worker_class(self) -> None:
        self.assertTrue(pyside_app.can_start_pyside_worker(busy=False, text="hello"))
        self.assertFalse(pyside_app.can_start_pyside_worker(busy=True, text="hello"))
        self.assertFalse(pyside_app.can_start_pyside_worker(busy=False, text="   "))
        self.assertIn("System error:", pyside_app.format_worker_error(RuntimeError("boom")))
        self.assertIn("Worker error: boom", pyside_app.format_worker_error(RuntimeError("boom")))
        controller = pyside_app.CancelController()
        self.assertFalse(controller.is_cancel_requested())
        controller.request_cancel()
        self.assertTrue(controller.is_cancel_requested())
        if pyside_app.PYSIDE_AVAILABLE:
            self.assertTrue(hasattr(pyside_app, "InputWorker"))
            self.assertTrue(hasattr(pyside_app.InputWorker, "chunk"))
            self.assertTrue(hasattr(pyside_app.InputWorker, "cancel_requested"))

    def test_pyside_runtime_state_helpers(self) -> None:
        self.assertEqual(pyside_app.format_runtime_label("ready"), "Runtime: ready")
        self.assertEqual(pyside_app.format_runtime_label("thinking"), "Runtime: thinking...")
        self.assertEqual(pyside_app.format_runtime_label("stopping"), "Runtime: stopping...")
        self.assertEqual(pyside_app.format_runtime_label("error"), "Runtime: error")
        self.assertEqual(pyside_app.format_runtime_label("weird"), "Runtime: ready")

        self.assertIn("#1f4f35", pyside_app.runtime_style_for_state("ready"))
        self.assertIn("#21537a", pyside_app.runtime_style_for_state("thinking"))
        self.assertIn("#7a5518", pyside_app.runtime_style_for_state("stopping"))
        self.assertIn("#7a2d2d", pyside_app.runtime_style_for_state("error"))
        self.assertIn("#1f4f35", pyside_app.runtime_style_for_state("unknown"))

        self.assertEqual(pyside_app.pyside_send_button_text("ready"), "Send")
        self.assertEqual(pyside_app.pyside_send_button_text("thinking"), "Thinking...")
        self.assertEqual(pyside_app.pyside_send_button_text("error"), "Send")
        self.assertEqual(pyside_app.pyside_send_button_state("ready"), pyside_app.ButtonState(text="Send", enabled=True))
        self.assertEqual(
            pyside_app.pyside_send_button_state("thinking"),
            pyside_app.ButtonState(text="Thinking...", enabled=False),
        )
        self.assertEqual(
            pyside_app.pyside_send_button_state("stopping"),
            pyside_app.ButtonState(text="Send", enabled=False),
        )
        self.assertEqual(pyside_app.pyside_send_button_state("error"), pyside_app.ButtonState(text="Send", enabled=True))
        self.assertEqual(pyside_app.pyside_stop_button_state("ready"), pyside_app.ButtonState(text="Stop", enabled=False))
        self.assertEqual(pyside_app.pyside_stop_button_state("thinking"), pyside_app.ButtonState(text="Stop", enabled=True))
        self.assertEqual(
            pyside_app.pyside_stop_button_state("stopping"),
            pyside_app.ButtonState(text="Stopping...", enabled=False),
        )

        ready = pyside_app.pyside_status_line("ready", backend="ollama", model="qwen3:8b", debug_enabled=False)
        thinking = pyside_app.pyside_status_line("thinking", backend="mock", model=None, debug_enabled=True)
        stopping = pyside_app.pyside_status_line("stopping", backend="ollama", model="qwen3:8b", debug_enabled=True)
        self.assertEqual(ready, "Status: ready | Backend: ollama | Model: qwen3:8b | Debug: off")
        self.assertEqual(thinking, "Status: thinking... | Backend: mock | Debug: on")
        self.assertEqual(stopping, "Status: stopping... | Backend: ollama | Model: qwen3:8b | Debug: on")

    def test_pyside_message_html_escapes_and_formats_reports(self) -> None:
        message = pyside_app.pyside_message_html("User", "<hello>\nworld")
        self.assertIn("&lt;hello&gt;", message)
        self.assertIn("<p>&lt;hello&gt;<br>world</p>", message)
        self.assertNotIn("<hello>", message)

        plain = pyside_app.pyside_message_html("User", "**not bold**\n<script>x</script>", markdown=False)
        self.assertIn("**not bold**", plain)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", plain)
        self.assertNotIn("<strong>", plain)

        system = pyside_app.pyside_message_html("System", "Status: <OK>", markdown=False, muted=True)
        self.assertIn("class='system message'", system)
        self.assertIn("Status: &lt;OK&gt;", system)

        report = pyside_app.pyside_message_html("System report", "Status: <WARN>", report=True)
        self.assertIn("<pre>", report)
        self.assertIn("Status: &lt;WARN&gt;", report)

    def test_pyside_typed_capability_card_css_is_present(self) -> None:
        stylesheet = pyside_app.pyside_chat_document_css()
        card = build_local_capability_card_html(
            "/exports doctor",
            "Export Retention Doctor\nStatus: OK\nNo findings.",
        )

        self.assertIsNotNone(card)
        self.assertIn(".capability-card", stylesheet)
        self.assertIn(".capability-status-warn", stylesheet)
        self.assertIn("capability-card", card)
        self.assertIn("Check local exports", card)

    def test_pyside_message_blocks_are_isolated_after_numbered_lists(self) -> None:
        first = pyside_app.pyside_message_html("Proto-Mind", "1. one\n2. two")
        second = pyside_app.pyside_message_html("User", "thanks", markdown=False)
        combined = first + second

        self.assertIn("class='message-block'", first)
        self.assertIn("class='message-block'", second)
        self.assertIn("</ol>", first)
        self.assertLess(combined.index("</ol>"), combined.index("User"))
        self.assertIn("message-reset", pyside_app.pyside_message_reset_html())

    def test_pyside_operator_reports_stay_preformatted_after_list_content(self) -> None:
        report = pyside_app.pyside_message_html("System report", "1. one\n2. two", report=True)

        self.assertIn("<pre>", report)
        self.assertIn("1. one", report)
        self.assertNotIn("<ol>", report)

    def test_pyside_markdown_lite_renderer_escapes_and_formats_basic_markdown(self) -> None:
        rendered = pyside_app.render_markdown_lite(
            "# Heading\n"
            "## Smaller\n"
            "This is **bold** and `code`.\n\n"
            "Hello `<tag>`\n\n"
            "- one\n"
            "* two\n\n"
            "1. first\n"
            "2. second\n\n"
            "```python\n"
            "print('<hello>')\n"
            "```"
        )

        self.assertIn("<h1>Heading</h1>", rendered)
        self.assertIn("<h2>Smaller</h2>", rendered)
        self.assertIn("<strong>bold</strong>", rendered)
        self.assertIn("<p>Hello <code>&lt;tag&gt;</code></p>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<li>one</li>", rendered)
        self.assertIn("<li>two</li>", rendered)
        self.assertIn("<ol>", rendered)
        self.assertIn("<li>first</li>", rendered)
        self.assertIn("<li>second</li>", rendered)
        self.assertIn("<pre><code>print(&#x27;&lt;hello&gt;&#x27;)</code></pre>", rendered)
        self.assertNotIn("print('<hello>')", rendered)

    def test_pyside_markdown_lite_closes_lists_before_following_content(self) -> None:
        ordered = pyside_app.render_markdown_lite("1. one\n2. two\nAfter")
        unordered = pyside_app.render_markdown_lite("- one\n- two\nAfter")

        self.assertIn("</ol><p>After</p>", ordered)
        self.assertIn("</ul><p>After</p>", unordered)

    def test_pyside_markdown_lite_closes_blocks_at_boundaries(self) -> None:
        ordered = pyside_app.render_markdown_lite("1. one\n2. two")
        list_then_code = pyside_app.render_markdown_lite("1. one\n```python\nprint('x')\n```")
        code_then_list = pyside_app.render_markdown_lite("```python\nprint('x')\n```\n1. one")
        escaped = pyside_app.render_markdown_lite("<script>alert(1)</script>")

        self.assertTrue(ordered.endswith("</ol>"))
        self.assertIn("</ol><pre><code>", list_then_code)
        self.assertIn("</code></pre><ol>", code_then_list)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", escaped)
        self.assertNotIn("<script>", escaped)

    def test_pyside_geometry_encoding_uses_pyside_prefix(self) -> None:
        class FakeGeometry:
            def toBase64(self) -> bytes:
                return b"abc123"

        self.assertEqual(pyside_app.encode_pyside_geometry(FakeGeometry()), "pyside6:abc123")
