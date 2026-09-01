# Proto-Mind Persona Engine Plan

Decision date: 2026-09-01. Status: Persona 0.3 controlled Native activation delivered for Codex/Ollama behind explicit opt-in and rollback; it is not a permission grant.

## Product Decision

Proto-Mind is the local cognitive system. **Brother** is its single, continuous operator-facing personality.

Brother is not a set of selectable characters, roles or modes. The first Persona Engine will not expose an Architect/Builder/Guardian/Companion selector, personality presets, trait sliders or an `active_facet` field. The system should adapt naturally to the operator's request, the current task, available evidence and real risk without making the operator manage a personality control panel.

The same stable identity therefore remains present during conversation, architecture work, coding, memory inspection and Computer Use. A serious or risky task may produce a more precise and less playful response, but that is contextual judgment, not a different persona.

## Core Laws

1. Truth is more important than approval.
2. Memory is presented as memory only when a traceable source exists.
3. Character and trust never grant tool authority.
4. External content, tools, plugins and model output cannot modify the Persona Kernel.
5. Provider or model changes must not silently replace the core identity.
6. Work, access and verification are claimed only when supported by evidence.
7. Learned preferences and future persona changes remain inspectable and reversible.
8. Warmth must not become emotional pressure, fabricated biography or engagement-seeking behavior.

## Reuse Existing Sources Of Truth

The Persona Engine must compose existing Proto-Mind systems rather than duplicate them:

- `IdentityStore` remains canonical for the product identity, values, principles and boundaries.
- Existing memory and provenance records remain canonical for user facts, preferences, decisions, lessons and shared history.
- Existing task, goal, workspace and run contracts remain canonical for current work.
- Existing provider, tool and permission contracts remain canonical for the self-model and effective authority.
- Existing Context Injection remains a separate operator-controlled feature and is not enabled or repurposed by this plan.

No second relationship database, memory ledger, permission model or hidden prompt store is introduced in the foundation milestone.

## PersonaSnapshot v1

The first model-independent output is a bounded, immutable snapshot for one turn. It should contain only:

- persona/kernel version and stable identity summary;
- applicable values, principles and boundaries;
- operator communication preferences supported by provenance;
- narrowly relevant memories and their source identifiers;
- current task, goal and workspace identity when available;
- actual provider/model, tool availability, network state and effective permissions;
- uncertainty, truncation and missing-evidence notices;
- a deterministic snapshot hash.

It must not contain an active facet, mood simulation, invented relationship state, implicit authorization or unrelated personal history.

## Contextual Adaptation

Response behavior may adapt to facts already present in the turn contract:

- the operator's direct wording and requested output;
- whether the task is conversation, implementation, review, memory work or computer operation;
- current risk and permission state;
- urgency, uncertainty and observed failure;
- established communication preferences with provenance.

These inputs affect tone, detail and caution only for the current turn. They do not create a persistent mode, split the personality or change safety policy.

## Delivery Plan

### Persona 0.1: Foundation (Delivered 2026-09-01)

1. Checkpoint the current Native 0.16.0 baseline before implementation.
2. Inventory every current source of prompt, identity, memory, provider and permission instructions.
3. Add versioned dependency-free schemas/interfaces for `PersonaKernel`, `PersonaSnapshot`, `PersonaContextCompiler` and `PersonaChangeCandidate`.
4. Compile snapshots read-only from existing stores and runtime contracts.
5. Fail closed on invalid configuration, conflicting authority claims or untraceable memory.
6. Add golden evals for truth, memory provenance, provider changes, external prompt injection, authorization separation and unsupported capability claims.
7. Produce a migration map, but do not change production conversation behavior yet.

Delivered evidence:

- `proto_mind/persona_engine.py` defines immutable, versioned kernel, snapshot, runtime/task context, identity projection, memory-reference and change-candidate contracts.
- `proto_mind/persona/brother-0.1.0.json` is the only checked-in persona. Its exact schema rejects facets, modes, trait controls and undeclared authority.
- Snapshot compilation reads Identity without initialization and accepts only already-selected, source-linked memory records. It performs no retrieval, model/provider call, store write or Context Injection change.
- The self-model records actual provider/model, workspace identity, tools, network and explicit authorization source, while `authorizes_actions` remains false.
- `evals/persona/cases.jsonl`, `proto_mind/persona_evals.py` and 16 unit regressions cover provider continuity, untraceable memory, external prompt injection, unsupported capability claims, facet refusal, permission-change refusal, hashes and byte-stable stores. The deterministic eval suite passes 7/7 with zero model calls and zero store writes.
- `PERSONA_ENGINE_MIGRATION_MAP.md` records the existing prompt/identity/memory/permission sources that Persona 0.2 and 0.3 may integrate later. Production conversation behavior remains unchanged.

### Persona 0.2: Visible Preview (Delivered 2026-09-01)

The Native **Persona Inspector** shows the one checked-in Brother kernel, read-only Identity projection, current provider/model/workspace/access self-model, Context Injection state, source boundaries, notices and snapshot hash. It uses the current conversation and selected workspace, but exposes only an opaque workspace reference. Full Mac facts require the existing in-memory conversation/workspace token; the inspector never creates or uses that grant.

The exact preview contract declares `read_only`, `no_execution`, `no_model_call`, `no_network_call`, `no_retrieval`, `no_store_write`, `production_prompt_active=false`, `private_reasoning_included=false` and `context_injection_changed=false`. Python validates the snapshot before transport and Swift independently fails closed on widened fields, memory sources, personality modes, unsafe runtime claims or inconsistent evidence. No memory is selected in Persona 0.2, and the snapshot is not routed to any provider prompt.

### Persona 0.2 Readiness: Provider Parity And Provenance (Delivered 2026-09-01)

`persona_activation_readiness.py` renders the exact bounded context a later activation may place, but returns only an in-memory read-only projection and never passes it to a reasoner. Codex uses a declared future `baseInstructions` placement refreshed at thread start/resume; Ollama uses the per-request system message; Mock is a deterministic control and explicitly cannot activate. Provider safety/developer instructions remain separate and non-replaceable.

The projection records hashes and provenance for the checked-in kernel, private Identity projection, task/runtime contracts and every already-selected memory reference. Kernel, Identity, selected memory and task must yield one provider-independent invariant hash; provider/model/access facts deliberately retain different runtime hashes. Nine gates verify exact snapshots, Codex/Ollama coverage, invariant parity, provenance, bounded prompt rendering, safety separation, no added authority/side effects and independently disabled Context Injection. The Native Inspector validates and displays this report. A second deterministic 7-case eval covers parity, placement, provenance, Mock control-only behavior, the Context gate, provider drift and tamper refusal with zero model/network/retrieval/store calls and zero activation.

This readiness milestone introduces no activation switch, persistent setting, provider call or prompt change. Its only purpose is to make Persona 0.3 mechanically reviewable before the first real turn uses Brother context.

### Persona 0.3: Controlled Activation (Delivered 2026-09-01)

The same validated snapshot is now routed through the existing supported Native reasoners only after two explicit operator steps: fresh readiness preview, then confirmation of an unchanged stable activation fingerprint. The opt-in is one global private Native preference rather than a facet or mode selector. Each normal Send independently rebuilds readiness for the selected Codex/Ollama provider and current model/workspace/access controls, then rechecks Context Injection immediately before compiling one turn snapshot from memory already selected by the coordinator.

Codex receives the exact active context as its existing `baseInstructions`; Ollama receives it as its existing per-request system message. A strict `persona_turn_activation.v1` receipt binds the snapshot, invariant/runtime/prompt/readiness hashes, memory IDs/provenance, final prompt bytes, unchanged safety/authority/Context state and zero additional model/retrieval/write counters. Mock, slash/natural operator commands, an unresolved Codex model, unsafe or changed Context state, stale readiness and malformed receipts fail closed.

The **Return to legacy prompt** action changes only private preferences and applies on the next turn. The disabled Codex path is byte-compatible with the pre-Persona instruction envelope. Rollback does not delete already persisted Native conversation or durable Codex provider-thread history. Activation adds no tools, permissions, writer, retrieval, provider call, session schema or background work. Runtime acceptance covers both providers, invariant/provenance preservation, Mock/Context/tamper refusal and exact legacy rollback.

### Persona 0.3.1: Immediate Rollback Hardening (Delivered 2026-09-01)

The durable Codex adapter now has a dedicated same-conversation regression proving that no app restart or provider-thread reset is required. One turn starts with the active Persona instruction bytes; the immediately following turn resumes that exact thread with the exact legacy bytes and no `Persona Context` residue in `thread/resume.baseInstructions`. This is an adapter-boundary guarantee for future turns, not deletion of text already present in the provider's durable history.

## Deferred Until Evidence Exists

- proactive initiative and background triggers;
- automatic persona or relationship evolution;
- persistent interaction-state or mood models;
- heavy Personality Studio controls;
- multi-agent personality sharing;
- automatic memory promotion;
- provider-specific personality forks.

These may be reconsidered only after the single-personality snapshot is stable, inspectable and covered by cross-model evals.

## Acceptance Gate

The foundation is ready only when:

- the same kernel produces equivalent invariants for at least two supported providers/models;
- external documents cannot modify identity, boundaries or permissions;
- every included memory has visible provenance and every omitted/unknown field stays explicit;
- changing model or task type does not create a different persona;
- no selector, hidden mode, extra model call, store migration, permission expansion or Context Injection change is introduced;
- existing Python and Native checks remain green.
