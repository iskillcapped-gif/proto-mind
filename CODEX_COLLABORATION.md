# How Proto-Mind Used Codex And GPT-5.6

This record explains the human/AI collaboration for the OpenAI Build Week submission. It complements the machine-readable baseline diff in `contest/provenance/`.

## Collaboration Model

The operator defined the product direction, accepted or rejected milestones, set safety boundaries, and approved each work block. Codex/GPT-5.6 inspected the local project, proposed scoped implementations, wrote code and tests, ran verification, diagnosed regressions, and maintained the architecture ledger.

The project used a strict workflow:

1. Create a timestamped checkpoint before changes.
2. Inspect the current architecture and existing tests.
3. Implement one bounded milestone.
4. Add regression coverage.
5. Run the complete test suite and compile checks.
6. Compare protected store/export SHA-256 when the milestone claimed to be read-only.
7. Report limitations and leave risky expansion for a separate approval.

## Where Codex Accelerated Development

- Converted a broad personal cognitive-system goal into incremental, testable milestones.
- Implemented bilingual continuity, memory governance, grounding, and long-turn soak tests.
- Designed typed Experience events and provenance validation instead of storing hidden free-form chain-of-thought.
- Built deterministic redaction, consent, bounds, failure-isolation, and activation-readiness benchmarks.
- Connected normal cognitive turns to an explicitly consented process-memory pilot.
- Added a compact Observe-to-Verify episode view and a judge-facing Showcase.
- Maintained hundreds of regression tests and synchronized Registry, Policy, architecture, and operator documentation.
- Diagnosed concrete failures, including redaction tokens split at truncation boundaries, and added regressions before proceeding.

## Key Human Decisions

The operator retained control over the consequential choices:

- Proto-Mind should become a local personal cognitive operating system, not a collection of commands.
- Existing functionality must be disclosed as pre-contest foundation.
- Context Injection remains disabled for the contest baseline.
- Experience capture requires exact process-session consent and is discarded on restart.
- Full prompts, hidden/system text, and secrets must not be stored in Experience previews.
- Learning candidates must not be automatically promoted into memory or skills.
- The runner remains four fixed read-only internal callbacks with no shell or free-form dispatch.
- No production self-modification or autonomous external action is allowed.

## Build Week Milestone Chain

The machine-readable baseline proves these modules were absent or changed after July 11:

- v3.1b Memory Write Governance.
- v3.1c Bilingual Grounding and Reflection.
- v3.1d Cognitive Continuity Soak.
- v3.2a-v3.2m Experience Ledger, privacy, consent, evidence, learning-review, and readiness layers.
- v3.3a Supervised In-Memory Experience Pilot.
- v3.3b Cognitive Turn Episode View.
- v3.3c-v3.4h supervised candidate review, exact-token memory lesson promotion, durable provenance/recall, outcome review, lifecycle apply, and restart-safe audit.
- v3.5a-v3.5v supervised procedural skill contracts, apply, provenance, outcome/lifecycle review, durable archive/restore, guardrails, and post-restore readiness.
- Contest Showcase v1.
- PySide Cognitive Control Room v2.1.0 with a preview-gated twelve-step contest Demo Runway.
- Build Week Provenance Pack v1.

## Required Session Evidence

The operator submitted `/feedback` from the project task where the Build Week functionality was developed and supplied the returned identifier:

```text
Primary Codex /feedback Session ID: 019d73be-1d7e-7401-8efe-f5e165736db4
Additional milestone Session IDs: optional
```

This identifier came from the actual Codex `/feedback` flow and was not inferred from local files or fabricated.

## Honest Claim

Recommended submission wording:

> Proto-Mind existed before Build Week as a local-first memory, command, and safety architecture. During Build Week, Codex and GPT-5.6 meaningfully extended it into an explainable cognitive loop with bilingual continuity hardening, typed Experience provenance, supervised in-memory capture, verification, and a contest-ready product narrative.

This wording deliberately credits the prior foundation and limits the contest claim to evidence present in the baseline/current diff.
