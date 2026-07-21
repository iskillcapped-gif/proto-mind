# Proto-Mind — OpenAI Build Week Submission Draft

This file is a copy-ready submission handoff. Replace the YouTube placeholder after the upload finishes, then submit through <https://openai.devpost.com/> before July 21, 2026 at 5:00 PM Pacific Time.

## Submission Fields

- **Project name:** Proto-Mind
- **Tagline:** A local-first cognitive operating system with inspectable memory, consented experience, supervised learning, and bounded action.
- **Recommended track:** Apps for Your Life
- **Code repository:** <https://github.com/iskillcapped-gif/proto-mind>
- **Demo video:** `ADD_PUBLIC_YOUTUBE_URL_HERE`
- **Primary Codex /feedback Session ID:** `019d73be-1d7e-7401-8efe-f5e165736db4`
- **License:** Apache License 2.0

## Short Description

Proto-Mind is a local-first personal cognitive system that preserves continuity across sessions, separates facts from inference, turns operator-consented turns into inspectable evidence, learns only through supervised promotion, and keeps executable capabilities behind deterministic safety gates.

## Full Description

Most assistants either forget the user or hide how their memory and actions work. Proto-Mind explores a different model: a local cognitive operating system where identity, goals, memory, tasks, experiments, predictions, reflections, and procedural skills remain visible and operator-controlled.

The live cognitive path can recall relevant local context and answer a normal question. With exact process-session consent, the same turn can become a bounded sequence of typed Experience events. A read-only episode view then connects Observe, Interpret, Recall, Respond, Memory decision, Reflect, and Verify to exact source-event IDs. Learning candidates are derived from that evidence, but memory and skill promotion require separate, explicit, current-state-bound confirmations. Nothing is silently learned.

Proto-Mind also demonstrates bounded action. Its active runner exposes only four fixed, read-only internal callbacks. Every run requires a command-specific exact phrase, checks Registry and Policy metadata, records bounded in-memory evidence, and refuses shell commands, arbitrary dispatch, background execution, network actions, or persistent approval.

The PySide Cognitive Control Room presents this architecture through a twelve-step Demo Runway. Two gate buttons unlock only after their preceding preview produces the exact safe command, letting the operator demonstrate consent and execution without bypassing the underlying safety state machines.

## What Was Built During Build Week

Proto-Mind was an existing project and is disclosed as such. The pre-contest July 11 checkpoint already contained the local CLI/UI foundation, explicit stores, diagnostics, Command Registry, safety policy, and an early fixed read-only runner.

During Build Week, Codex/GPT-5.6 meaningfully extended it with:

- bilingual cognitive continuity and grounding hardening;
- pure memory retrieval plus explicit telemetry and compact writes;
- typed, provenance-linked Experience events and deterministic redaction;
- exact session consent, bounded in-memory live capture, and fail-closed activation checks;
- an explainable Observe-to-Verify cognitive episode;
- operator-reviewed learning candidates and exact-token memory lesson promotion;
- durable lesson provenance, recall, outcome review, lifecycle transition, and audit;
- supervised procedural skill authoring, apply, outcome, lifecycle, archive, restore, and post-restore readiness layers;
- a judge-facing Showcase and PySide Demo Runway;
- 480 additional unit-test methods and reproducible baseline/current SHA-256 manifests.

See [`BUILD_WEEK_PROVENANCE.md`](BUILD_WEEK_PROVENANCE.md) for the full distinction and machine-readable evidence under [`contest/provenance/`](contest/provenance/).

## How Codex And GPT-5.6 Were Used

The operator defined the product vision and retained authority over scope, privacy, safety, and milestone approval. Codex/GPT-5.6 inspected the local architecture, proposed bounded next steps, implemented source and regression tests, diagnosed failures, verified protected-store hashes, and maintained the documentation/provenance trail.

The collaboration deliberately avoided opaque self-modification. Codex helped turn broad goals into inspectable contracts and fail-closed gates; the operator decided which tradeoffs and capabilities were acceptable. Detailed evidence is in [`CODEX_COLLABORATION.md`](CODEX_COLLABORATION.md).

## Technologies

- Python 3.11
- PySide6 desktop UI with tkinter fallback
- Local Ollama integration with deterministic mock fallback
- JSON/JSONL local stores with atomic writes where mutation is allowed
- Standard-library hashing, provenance, validation, redaction, and test infrastructure
- Codex and GPT-5.6 for Build Week development

## Testing Instructions For Judges

No cloud account, API key, database, or package build is required for the deterministic CLI path.

```bash
git clone https://github.com/iskillcapped-gif/proto-mind.git
cd proto-mind
scripts/which_python.sh
scripts/run_tests.sh
scripts/run_cli.sh
```

Inside the CLI:

```text
/showcase status
/showcase demo
/showcase doctor
/experience preview
/runner-exec dry-run /daily doctor
/exit
```

Expected results:

- the Showcase reports continuity, Experience, governance, and bounded action;
- Context Injection is disabled;
- Experience preview prints a process-session-specific consent command but captures nothing yet;
- runner dry-run prints an exact command but performs no execution;
- the full suite reports 1144 tests OK.

Desktop path on macOS:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt
scripts/run_pyside_mock.sh
```

Select `DEMO RUNWAY` and follow steps `01` through `12`. Ollama is optional; use `scripts/run_pyside_ollama.sh` only when a local Ollama service and model are already available.

## Safety And Privacy

- Local cognitive stores, exports, backups, logs, `.env`, virtual environments, and built app artifacts are Git-ignored and excluded from the public repository.
- Context Injection is disabled in the verified submission baseline.
- Experience live capture is opt-in, process-memory-only, redacted, bounded, and expires on restart.
- Learning candidates are not automatically promoted.
- The runner has no shell, subprocess, arbitrary slash-command dispatcher, network action, or background autonomy.
- The macOS `.app` is a local wrapper, not a signed redistributable package.

## Submission Checklist

- [x] Public GitHub repository with relevant source license.
- [x] English project description and functionality explanation.
- [x] README collaboration summary for Codex/GPT-5.6.
- [x] Existing-versus-Build-Week provenance documentation.
- [x] Installation, supported-platform, and no-rebuild testing instructions.
- [x] Primary `/feedback` Session ID.
- [x] Demo under three minutes recorded with audio.
- [ ] Replace `ADD_PUBLIC_YOUTUBE_URL_HERE` with the public YouTube URL.
- [ ] Confirm the YouTube video is publicly visible and contains no unlicensed music/material.
- [ ] Submit the Devpost entry before the deadline.

## Honest Non-Claims

Proto-Mind does not claim consciousness, unrestricted autonomy, neural self-training, hidden chain-of-thought storage, automatic self-modification, or production-ready security. It is an inspectable prototype showing how continuity, evidence, supervised learning, and bounded action can coexist in a local personal system.
