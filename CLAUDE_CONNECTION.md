# Claude in Proto-Mind

Development release: **0.74.10 (114)**. This local integration runs Anthropic's
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

Each PM conversation now resumes its exact saved Claude session, including tool
history, across worker/app restarts. PM uses the SDK's explicit session UUID,
never the most recent session in a directory. This removes the inherited
12-message / 2000-character-per-message restriction from continuing Claude chats.
The provider still owns its context window and compaction; PM does not promise
unlimited model context. [Official SDK session contract](https://code.claude.com/docs/en/agent-sdk/sessions).

Only a **new** session bootstraps from local PM messages: up to 300,000 Unicode
characters across 2,000 messages, without a per-message cap. Omitted older text
is marked, and the context inspector shows whether a session continues or starts
fresh. Old image bytes and PDF excerpts are not reattached from local history.
A request that failed or was stopped stays in local history with a marker: it has
no confirmed answer, and its actions are not repeated unless the current request
asks. Failed answers are not replayed. This applies to every provider's history.
The 4 MiB bridge request envelope accommodates this history including UTF-8 and
JSON escapes. Explicitly selected context is sent with each turn.

Claude Code keeps a session's first system prompt when it resumes, so PM's
system prompt holds only session-stable rules. Each turn's Observer labels,
selected core memory and correction hints travel in a `<proto_mind_turn_context>`
block inside that turn's message; a long memory record is truncated with a
marker there instead of failing the turn. A changed PM system prompt, for example
after an update, starts a new session from local history.

An exclusive per-conversation lease rechecks the binding before sending. A
confirmed result must name the expected session before PM saves continuation.
Bindings include public account identity, login epoch, exact workspace identity,
access/tool mode, PM's system prompt and private-restore generation. Resume also
requires the latest local answer to match the saved result and the provider
transcript to exist. After Stop, a usage limit, a crash or a transient error, the
next user-initiated turn from the same local position continues that session with
an explicit interruption notice; nothing is replayed or retried automatically. A
resumed session that fails before any output for an unknown reason is not offered
again. API logins without a public email bootstrap fresh.
Changing a provider or project can therefore start a new session; this release
does not add cross-provider context-transfer features.

Messages typed while Claude works reach the running turn as updates (0.74.4). With Full Mac, Claude can also see the screen and operate apps with the mouse and keyboard through PM (0.74.9), once macOS allows Proto-Mind Screen Recording and Accessibility. Claude reset actions and multiple Claude logins are not implemented.
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

Each completed Claude answer adds one content-free line to **About this response
→ Response notes** («Об ответе → Примечания к ответу»): model requests (including subagents), the largest context sent, and
tokens read from cache, written to cache, uncached and output (with thinking).
The worker counts each request by its message ID. It does not use the result
message's totals: Claude Code saves a session's accumulated cost state, so after
a resume they can include earlier turns. On 2026-09-25 local transcripts showed
what two long tool-heavy turns consumed; the first ended at the five-hour limit.
They made 113 and 154 requests, each re-reading a cached context of up to 366K
tokens: 24–32M cache-read tokens per turn against 0.3M cache writes and
0.14–0.17M output tokens (64–75% of them thinking).
The CLI's auto-compaction window stays on its model-tuned `auto` setting, which
it recommends for cost. On 2026-09-27 a live 1M-context session compacted at
968K tokens in 93 seconds and continued the same turn from a 35K-token context;
from 0.74.10 PM's work log shows each compaction with its token counts.

## Ownership and packaging

The CLI owns authentication under `<native profile>/claude-profile` and its
normal credential facilities. PM reads only public `auth status` fields; it
does not implement OAuth, ask for a password, extract tokens or proxy sessions.
The auth terminal is not copied into chats, work journals or exports. This
profile and the `claude_sessions` binding registry are excluded from private
backups. Restore generations invalidate saved continuation without deleting old
provider transcripts. Sign-in/out waits until
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

Release 0.74.2 verification on 2026-09-25: **2417 Python tests and 1988 Native
checks passed**, with the synthetic SDK and no model request. They cover the
session-stable system prompt, current per-turn context after resume, the prompt
hash in the binding, bounded long memory, and failed requests that survive both
resume and a fresh bootstrap. Earlier, in the running 0.74.0 app, a live
subscription session showed that `--resume` works and that the CLI kept the
first turn's `append`; this release addresses that. A live check of 0.74.2 itself
is still pending.

Release 0.74.0 verification on 2026-09-25: **2402 Python tests and 1982 Native
checks passed**. After table layout refinements, the 46 focused workspace checks
also passed; wide and narrow table renders were visually inspected. The long
Claude bootstrap passed through the actual Native/Python bridge with Unicode
history larger than the old 512 KiB envelope. Exact resume and interrupted-session
recovery were tested with the synthetic SDK. The installed official SDK accepted
the explicit session UUID in a disposable signed-out profile without a model
query. A live multi-turn subscription task was not part of this verification.
The local 0.74.0 (104) bundle was installed without restarting the running app;
its previous executable was preserved. The Apple Silicon DMG passed clean-profile
bridge bootstrap, bundled document-runtime checks, signature verification and
checksum verification. All 206 packaged Python source files and 157 Native
source hashes match commit `05c6538`; the Claude CLI remains byte-identical to
the original Anthropic-signed binary. Packaging evidence is stored beside the
local DMG in `dist/portable-0.74.0/verification.json`.

Offline tests exercise the actual PM worker pipe with a synthetic SDK, including
async SDK input, streaming, tool round trips, errors, cancellation, access
gates, long-history bootstrap, exact session resume, context, recall and durable
turn receipts. Separate tests cover lease contention, account/project/restore
changes, interrupted sessions and late tool replies. Known timed-out replies
cannot terminate unrelated pending calls. Authentication, quota and service
failures have distinct content-free messages. These tests never use live credentials.
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
