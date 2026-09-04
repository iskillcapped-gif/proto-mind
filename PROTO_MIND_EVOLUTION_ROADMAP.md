# Proto-Mind: Current Direction

Updated: 2026-09-05. Current release: Native **0.46.0 (53)**.

Proto-Mind is a personal macOS assistant. The immediate goal is a dependable, approachable application that can support the operator's planned expansion. The next agreed stage is to make the interface less developer-oriented.

This is the current priority map. [AGENTS.md](AGENTS.md) describes how to work in the project; [Native releases](NATIVE_MACOS_ROADMAP.md) preserve delivered contracts and verification; [Architect Ledger](PROTO_MIND_ARCHITECT_LEDGER.md) preserves architectural evidence. Earlier versions of this document remain in Git history. Historical EV/P2 numbering and imported blueprints do not determine the next task.

## Foundation Completed

| Area | Current behavior | Practical boundary |
| --- | --- | --- |
| Dialog persistence | Each dialog has an immutable object; a small atomic manifest selects the current versions. Saves reuse unchanged dialogs. Competing app processes cannot silently overwrite each other. | Up to 10,000 dialogs; each object below 50 MiB. Startup still reads the complete archive into memory. |
| Recovery | Failed saves retain visible replies and drafts. The app offers verified export/import, the last 20 automatic snapshots, a pinned original-format copy and copies before recovery. | These are dialog copies. Core memory, the separate work journal, provider sessions and original attachment files need their own backup. |
| Work journal | New independent turns have no global 500-run ceiling. The journal pages through older records and opens a message's exact run directly. | Page listing and continuation validation still scan the journal; the detached archive audit has a separate 500-record input budget. |
| Memory | Full core-memory mutations use cooperative transactions. Project notes have explicit scope, source evidence and bounded local RU/UK/EN recall. | The legacy shared core is not fully project-isolated; matching is deterministic, with finite vocabulary. |
| Execution | Codex Chat and explicit Full Mac have separate durable sessions; local Ollama and Mock remain available. Public work evidence, Stop and manual acceptance are distinct. | Full Mac has broad user-level authority. Finished model output does not prove task success or undo side effects. |
| Continuity and learning | Brother Persona, reviewed notes/lessons/skills, exact Turn Lineage and the confirmed single-turn Session Spine writer are implemented. | General automatic learning, multi-turn Spine ingestion and background work are not implemented. |
| Code structure | Dialogs, turn execution, work history, Spine and persistence have separate Native model files. Python history routes are isolated. The original 1,193 flow checks are split across 21 topic modules with a stable aggregate command. | Other large modules can be split when their next change benefits; no rewrite is required before interface work. |

Release 0.46.0 closes the agreed storage, recovery, code-structure and current-roadmap batch. Its detailed limits and verification are in the [release contract](NATIVE_MACOS_ROADMAP.md#dialog-storage-and-recovery--native-0460).

## Next: Everyday Interface

Improve the real app around the most frequent paths: open a conversation, choose a model, attach context, send, understand progress, inspect a result and recover from a failure.

- Give the conversation and composer a clear visual hierarchy, consistent spacing and predictable keyboard behavior.
- Use plain Russian for everyday labels and status messages. Keep protocol names, hashes and milestone terminology in expandable technical details where they help inspection.
- Organize model, access, memory and project controls so their current state and effect are easy to understand.
- Make settings, empty states, warnings and recovery actions consistent. Preserve useful evidence and access controls while reducing the amount presented at once.

Acceptance is an end-to-end check in the running app, including a small window, a long conversation, streaming/Stop, an interrupted request and recovery. Existing conversations, drafts and permissions must survive the update. These are product outcomes, not a fixed visual specification.

## Later Candidates

The operator plans a substantial functional expansion and will supply its scope after interface work. Keep these options available without starting all of them now:

- Better practical memory correction, scope and retrieval quality, supported by ordinary-task evidence.
- Continuity across tasks and sessions, with stronger recovery for linked history and work records.
- Richer document/artifact handling, voice input and provider capability parity.
- Narrower tool modes, reviewed procedures and useful background/parallel work with visible limits.
- A complete private-state backup/restore flow and simpler local runtime packaging when needed.

Choose the next increment from actual usage and the operator's direction. Broad architecture proposals, historical design gates and old test counts are context, not a substitute for inspecting the current implementation.
