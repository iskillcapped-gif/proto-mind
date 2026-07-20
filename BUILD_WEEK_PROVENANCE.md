# OpenAI Build Week Provenance

This document distinguishes the pre-existing Proto-Mind foundation from work added during the OpenAI Build Week submission period. It is intentionally conservative: the project is not presented as having been created entirely during the event.

Official period:

- Submission period starts: July 13, 2026 at 9:00 AM Pacific Time.
- Submission deadline: July 21, 2026 at 5:00 PM Pacific Time.
- Rules: <https://openai.devpost.com/rules>

The rules permit an existing project when it is meaningfully extended with Codex and/or GPT-5.6 after the submission period starts. Only the new work is eligible for evaluation, and prior/new work must be clearly distinguished with timestamped Codex logs, dated commits, or equivalent evidence.

## Pre-Contest Baseline

The accepted baseline is the latest available checkpoint that is unambiguously earlier than the submission period:

```text
Archive: backups/proto_mind_backup_2026-07-11_05-02-19.tar.gz
Local timestamp: 2026-07-11T05:02:19+03:00
SHA-256: 50a39b36aca72e1ae74ad8afe80004bfac1fe1eb3c66a2f168519246a680d4df
```

The baseline already contained a substantial local-first architecture. Notable prior work included:

- CLI, tkinter, PySide, local macOS launcher, Python 3.11 environment selection, and operator logs.
- Explicit memory, reflection, goals, tasks, experiments, skills, world model, identity, context, and operating-loop stores and commands.
- Natural Router, Command Registry, Action Policy, diagnostics, snapshots, exports, warning inspection, and operator rituals.
- A four-command read-only runner with exact confirmation and bounded in-memory evidence through v3.0i.
- Bilingual Cognitive Baseline v3.1a.
- 343 registered command prefixes across 39 categories.
- 664 unit-test methods in `proto_mind/tests/test_flow.py`.

These capabilities are disclosed as pre-existing foundation, not claimed as Build Week work.

## Build Week Extensions

The current source tree is compared directly with the July 11 archive by SHA-256. The principal additions after that baseline are:

### Cognitive Continuity Hardening

- Memory Write Governance v3.1b: pure retrieval by default, explicit telemetry, compact user-input-only automatic memory, and quality preview.
- Bilingual Grounding and Reflection v3.1c: shared Russian/English response signals and source-aware grounding.
- Cognitive Continuity Soak v3.1d: a deterministic 25-turn temporary-store scenario with byte-stable read-only turns.

### Experience And Learning Evidence

- Experience Ledger Foundation and temporary hash-chain persistence policy.
- Typed cognitive and action events with explicit provenance.
- Explainability, episode projection, learning candidate review, and explicit-ID duplicate review.
- Consent-state, privacy-redaction, bounded-growth, and activation-readiness benchmarks.
- No automatic lesson apply or persistent live capture was enabled.

### Supervised Product Surface

- Supervised In-Memory Experience Pilot v3.3a with exact process-session consent.
- Cognitive Turn Episode View v3.3b connecting Observe, Interpret, Recall, Respond, Memory decision, Reflect, Verify, and exact event IDs.
- Operator-Reviewed Learning Bridge Preview v3.3c deriving bounded candidates only from exact redacted cognitive evidence, with no apply or persistence.
- Learning Candidate Confirmation Design v3.3d with exact candidate tokens, bounded process-memory decisions, and non-executable promotion dry-runs.
- Learning Promotion Eligibility Review v3.3e with accepted-decision gating and target-specific exact duplicate checks over operator-selected detached IDs only.
- Learning Promotion Proposal Receipt v3.3f with fixed target schemas, selected-scope digest binding, exact proposal tokens, and bounded restart-expiring receipts without apply.
- Learning Promotion Apply Readiness Review v3.3g with current-evidence/hash revalidation and explicit receipt/rollback safeguards; the readiness surface itself invokes no writer.
- Supervised Memory Lesson Promotion Pilot v3.4a with a fresh exact-token gate, current-store hash binding, one atomic verified memory write, run-once process receipt, and no skill/batch/automatic apply.
- Durable Learning Provenance v3.4b with an embedded hashed candidate-to-proposal envelope, restart-safe `/memory why <id>`, Memory Doctor tamper detection, and no new writer or apply scope.
- Verified Lesson Recall v3.4c with provenance-gated bilingual restart recall, inspectable fail-closed filtering, grounding evidence, and byte-stable temporary-store verification.
- Learning Outcome Review v3.4d with exact post-apply Experience lineage, advisory keep/reject/supersede candidates, verified replacement requirements, and no automatic mutation.
- Supervised Lesson Lifecycle Decision v3.4e with exact current-outcome tokens, bounded restart-expiring operator receipts, run-once protection, and no lesson lifecycle mutation or apply.
- Learning Lifecycle Apply Readiness v3.4f with current provenance/evidence/store-hash revalidation and explicit transition/rollback contracts.
- Supervised Lesson Lifecycle Apply Pilot v3.4g with one second exact-token transition per process, byte-stable keep, one-record reject/supersede, immutable provenance checks, and exact-byte rollback on verification failure.
- Lifecycle Transition Audit v3.4h with restart-safe read-only state reconstruction, provenance/timestamp/replacement/cycle diagnostics, and no repair or invented historical receipt.
- Procedural Skill Contract v3.5a with source-bound read-only operator templates, explicit procedure/permission/verification fields, exact active duplicate checks, and no synthesis, writer, promotion, or execution.
- Procedural Skill Authoring Receipt v3.5b with exact visible operator fields, source-and-payload token binding, 16 bounded restart-expiring process receipts, current-state drift diagnostics, and no Skill Library writer or execution.
- Procedural Skill Apply Readiness v3.5c with current receipt/source/global duplicate/store-hash revalidation, deterministic target identity, fixed atomic receipt and rollback requirements, and no token generation, writer invocation, or execution from readiness.
- Supervised Procedural Skill Apply Pilot v3.5d with a second exact token, one atomic verified non-executable Skill Library append per process, exact-byte rollback, compact source provenance, and no procedure execution or automatic apply.
- Durable Skill Provenance Inspection v3.5e with embedded restart-safe source/contract/payload/confirmation hashes plus read-only `/skills why` and provenance Doctor diagnostics; no second writer or skill execution.
- Procedural Skill Outcome Review v3.5f with exact provenance-bound manual-use lineage, advisory success/failure/mixed candidates, explicit telemetry exclusion, and no event capture, skill mutation, or execution.
- Supervised Manual Skill Outcome Capture v3.5g with exact session consent, a second provenance/evidence-bound token, one bounded four-event process-memory batch, restart-expiring receipts, and no procedure execution or persistent-store mutation.
- Supervised Procedural Skill Outcome Decision v3.5h with exact review/capture-bound keep-revise-archive tokens, one terminal process receipt per skill, later-evidence drift diagnostics, and no apply readiness or Skill Library mutation.
- Procedural Skill Lifecycle Apply Readiness v3.5i with current decision/evidence/capture/provenance/skill-byte revalidation and decision-specific keep/archive/revise safeguards, but no apply token or lifecycle writer.
- Supervised Procedural Skill Lifecycle Apply Pilot v3.5j with one separately confirmed keep no-op or atomic archive, exact-byte rollback, immutable provenance, unchanged-memory proof, process receipts, and no revision or procedure execution.
- Durable Procedural Skill Lifecycle Audit v3.5k with restart-safe read-only state reconstruction, explicit archived ambiguity, provenance/drift checks, and no invented transition history or writer expansion.
- Durable Skill Lifecycle Metadata Design Lock v3.5l with a pure hashed archive-envelope contract, bounded evidence fingerprints, deterministic tamper checks, no writer, and no Registry expansion.
- Durable Skill Lifecycle Writer Readiness v3.5m with current archive evidence/byte revalidation, fixed future envelope blueprint, exact mutation/receipt/rollback plan, and no token or writer.
- Durable Skill Lifecycle Metadata Apply Pilot v3.5n with a separate exact token, one atomic three-field archive transition, fixed receipt verification, exact-byte rollback, and restart-safe embedded evidence.
- Durable Skill Lifecycle Restore Design Review v3.5o with embedded prior-archive evidence, current-state/duplicate revalidation, exact future mutation and receipt boundaries, and no token or writer.
- Direct Lifecycle Status Guardrail v3.5p with byte-stable refusal for lifecycle-managed/corrupt generic archive/restore and preserved legacy/operator compatibility.
- Lifecycle-Managed Skill Payload Guardrail v3.5q with byte-stable refusal for summary/body/tag/use mutations on lifecycle-managed/corrupt records and preserved pre-lifecycle/operator compatibility.
- Durable Restore Authorization Readiness v3.5r with exact current hash/evidence binding, immutable-field and future receipt/rollback scope, and no token generator, authorization engine, state, writer, or mutation.
- Contest Showcase v1 with a deterministic three-minute narrative and safety doctor.
- Build Week Provenance Pack v1.

## Objective Delta

The generated evidence under `contest/provenance/` is the source of truth for these values.

| Metric | July 11 baseline | Current Build Week state | Delta |
|---|---:|---:|---:|
| Submission-relevant files | 69 | 142 | +73 |
| Python files | 66 | 115 | +49 |
| Unit-test methods | 664 | 1116 | +452 |
| Registry commands | 343 | 387 | +44 |
| Registry categories | 39 | 41 | +2 |

The file delta is not inferred from modification time. Every baseline and current submission-relevant file is hashed, then classified as added, changed, removed, or unchanged. The current manifest reports 73 added, 15 changed, 0 removed, and 54 unchanged files.

## Reproduce The Evidence

From the project root:

```bash
scripts/which_python.sh
/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.contest_provenance
python3 -m json.tool contest/provenance/baseline_manifest.json >/dev/null
python3 -m json.tool contest/provenance/current_manifest.json >/dev/null
python3 -m json.tool contest/provenance/contest_delta.json >/dev/null
```

Generated files:

- `contest/provenance/baseline_manifest.json`
- `contest/provenance/current_manifest.json`
- `contest/provenance/contest_delta.json`

The scope includes source, tests, scripts, documentation, setup metadata, and safe assets. It excludes cognitive data, exports, backups, logs, caches, virtual environments, app build output, Git metadata, and the generated provenance files themselves.

## Codex / GPT-5.6 Evidence

Submission evidence should include:

- Primary `/feedback` Codex Session ID: `019d73be-1d7e-7401-8efe-f5e165736db4`.
- Any additional Codex Session IDs used for major Build Week milestones.
- This timestamped checkpoint chain and its SHA-256 manifests.
- Git commits created from this point onward. Git history must not be backdated or presented as proof for earlier work.
- The demo narration and README explanation of where Codex accelerated implementation and where the operator made product/safety decisions.

## Evidence Limitations

- The July 11 archive and SHA-256 manifests are local equivalent evidence, not a third-party timestamp authority.
- The directory was not a Git repository during the first part of Build Week, so no historical Git commits will be fabricated.
- The primary Codex Session ID above was supplied by the operator from the actual `/feedback` result for the main Build Week project task; additional milestone IDs remain optional.
- Runtime stores are intentionally excluded to protect local user data; this does not weaken source-code comparison.
