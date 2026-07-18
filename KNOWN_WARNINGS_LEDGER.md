# Proto-Mind Known Warnings Ledger v1

Purpose: document accepted legacy warning debt without hiding, repairing, migrating, or rewriting source records.

Accepted baseline recorded: 2026-07-01.

## Accepted Rules

- `accepted_dangling_consolidation_receipt`: the historical `cq_20260626201008_e7ed` apply receipt lacks `applied_record_id`. Cross-store traceability and automatic rollback proof are incomplete; current runtime execution is unaffected.
- `accepted_legacy_action_receipt_v1`: historical read-only action `act_20260628165932_d2a9` predates receipt-v2 fields such as `run_id`, command count, metadata snapshot, and `receipt_hash`. Run-once protection remains active.
- `accepted_context_enable_readiness_guard`: proposal `act_20260628170033_9176` targets `/context injection enable` and is intentionally refused by current read-only auto-allowed execution policy. The warnings demonstrate protective gating.
- `accepted_approved_unconfirmed_queue_state`: approved-but-unconfirmed proposals remain lifecycle debt only; approval does not execute target commands.

## Acceptance Policy

- Acceptance means documented and understood, not repaired or suppressed.
- All findings remain visible through `/warnings list` and `/warnings inspect` and through their original doctors.
- Rules are deliberately narrow. A new record id or unmatched message remains unknown until separately reviewed.
- Runtime gates remain protective. No accepted warning authorizes execution, context changes, or data mutation.
- Leave this debt in place unless a separate migration/repair milestone is explicitly planned with Rule 0 checkpoint, review, rollback strategy, and tests.

## Source Files

- `proto_mind/data/action_queue.jsonl`
- `proto_mind/data/consolidation_queue.jsonl`

This file is documentation only. Runtime warning commands read it but never update it.
