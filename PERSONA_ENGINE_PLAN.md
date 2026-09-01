# Proto-Mind Persona Engine Plan

Decision date: 2026-09-01. Status: Persona 0.1 foundation delivered; not yet connected to production prompts and not a permission grant.

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

### Persona 0.2: Visible Preview

Show a bounded Native inspector for the snapshot that would be used: identity version, relevant sources, actual model/tools/permissions, omitted-context notices and evidence limits. This remains read-only and must not expose private chain-of-thought.

### Persona 0.3: Controlled Activation

Route the same validated snapshot through provider adapters, with parity tests across supported models and a visible rollback to the previous prompt path. Activation must not enable Context Injection, add permissions, create a second model call or silently write memory.

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
