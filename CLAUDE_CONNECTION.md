# Claude in Proto-Mind

Development release: **0.73.1 (103)**. This local integration runs Anthropic's
official **Claude Agent SDK 0.2.159 / Claude Code 2.1.281**. PM is an independent
application, not an Anthropic product. No account is included.

## Connect

1. Open **Settings → Connections → Claude · Claude Code**.
2. Choose **Sign in to Claude**. The embedded terminal runs the unmodified
   `claude auth login`; follow its official browser sign-in. Choose a Claude
   subscription with Claude Code access, such as Pro or Max. Console/API login
   is also available in Claude Code and has separate API billing.
3. Return to PM. Status refreshes when the CLI finishes, or use **Refresh**.
4. In any main or side chat, select **Model source → Claude · Claude Code**.
   Allow cloud processing. Choose the account default or a version from the live Claude Code catalog.
   Version choices store the exact model ID. A custom ID remains available under
   the advanced model field; its availability is not inferred from its spelling.
5. Enable **Mac access** separately for that conversation when you want tools.
   Start with a disposable project when checking real task execution.

Free Claude accounts are not equivalent to a Claude Code subscription.
Subscription/SDK rules are external and can change. Checked on 2026-09-25:
[Claude Code authentication](https://code.claude.com/docs/en/authentication),
[Pro/Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan),
[SDK subscription usage](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan),
[unmodified Claude Code in integrations](https://code.claude.com/docs/en/legal-and-compliance).
The SDK billing-change article explicitly says the June 15 change is paused;
the canceled announcement below that notice is not the current rule.

## What is shared

Claude uses PM's normal editor, attachments, core memory, project recall,
explicit skill/context selection, criteria, work journal and response history.
Each conversation owns its process, stream and Stop. Changing provider clears
its Mac access. Stop does not roll back changes or stop independently accepted
tasks. Hiding a window does not stop a task.

Plain chat has no built-in or PM tools. Full Mac enables Claude Code's normal
file/command/network tools plus PM's exact-turn task, question, browser,
document and explicitly enabled MCP tools. The initial directory is not a
sandbox. OpenAI's Computer Use helper is not supplied to Claude.

For this first route, each request starts a new provider session with PM's
bounded recent history (12 messages, up to 2000 characters each), selected
context and current memory. Full provider-session continuation, live steering,
Claude reset actions and multiple Claude logins are not implemented.
Brother Persona and automatic skill selection remain Codex/Ollama-specific;
Claude still gets core memory and explicit selected skill guidance. The sidebar and Limits page separate Codex and Claude subscriptions. No automatic provider fallback or
PM retry is performed after failure.

## Model catalog and subscription limits

From 0.73.1, the model menu uses Claude Code's initialization catalog, including
its resolved model IDs and supported effort levels. Existing `opus`/`sonnet`
aliases keep their behavior but show the version returned by the CLI. Selecting
a version pins its exact ID. Account-default selection remains automatic. The
menu preserves upstream model descriptions, including separate usage-credit
requirements; listing a model is not a promise it is included in the plan.

The sidebar and Limits page have Codex/Claude tabs. Both show remaining quota;
the full page also shows used percentage and reset times. Only returned periods
are shown, with a visible unavailable/stale state after a failure. Missing
percentages never mean zero use or 100% remaining. Claude's `get_usage` control
response uses percentages, unlike the fractional stream RateLimitEvent.

A short-lived metadata worker runs the unmodified CLI without a model query or
tools. It reads initialization data and the pinned CLI's `get_usage` control
command; Python's SDK currently has no public wrapper for that command. The
adapter fails visibly if it changes. No OAuth token, HTTP credential client,
extra-usage purchase or reset mechanism is added. Account identity is rechecked
after each read. Polling is throttled, quotas stay in memory, and auth/restore
invalidate pending updates. Metadata has its own bridge queue and observable
UI model; it never marks a conversation busy or replaces the editor.

## Ownership and packaging

The CLI owns authentication under `<native profile>/claude-profile` and its
normal credential facilities. PM reads only public `auth status` fields; it
does not implement OAuth, ask for a password, extract tokens or proxy sessions.
The auth terminal is not copied into chats, work journals or exports. This
profile is excluded by the private backup allowlist. Sign-in/out waits until
all Claude tasks are idle; an active login blocks new Claude turns.

The SDK runs in a separate `python -S` worker with a restricted inherited
environment. Inherited API keys, tokens, alternate endpoints and provider
switches are omitted. PM does not force a paid API route. The user may choose
one explicitly through Claude Code's own login.

`requirements-claude.txt` pins all wheels by hash. Development builds prepare
`dist/claude-runtime-<Python version>`; portable builds install fresh wheels in
`Contents/Resources/core/claude_packages`. They include no user profile.
Anthropic's binary and Developer ID signature are preserved during packaging.
The rest of the app retains its existing signing/distribution status.

## Verification

Offline tests exercise the actual PM worker pipe with a synthetic SDK, including
async SDK input, streaming, tool round trips, errors, cancellation, access
gates, context, recall and durable turn receipts. They never use live credentials.
The installed official SDK/CLI also completed initialization in a disposable
signed-out profile without submitting a model query. On 2026-09-25 the operator
signed in with Pro; a read-only live check then confirmed the CLI catalog and
five-hour/weekly quotas, with no model query. Real coding-task acceptance remains
a separate check.

Release 0.73.0 verification on 2026-09-25: **2372 Python tests and 1952 Native checks
passed**. The local app and Apple Silicon portable DMG were built. The portable
Python/SDK/CLI also initialized with all 26 PM tool definitions in a disposable,
signed-out profile, without a model query or tool invocation. Its Claude binary
matches the original SDK binary byte for byte and retains Anthropic's verified
Developer ID signature. This verifies packaging and initialization, not a live
subscription login or real Claude task.

Release 0.73.1 verification on 2026-09-25: **2379 Python tests and 1966 Native
checks passed**. The versioned model menu and Claude quota page were rendered
with disposable fixtures and visually inspected. The combined subscription
page and the standalone Codex page both passed small-window layout checks.
The local app was rebuilt and installed without restarting the running app;
live Pro metadata was verified as described above. The 0.73.1 Apple Silicon
portable DMG passed clean-profile bridge bootstrap and bundled document-runtime
checks. Its metadata module matches the checked source, and its Claude CLI
still matches the original signed binary.
