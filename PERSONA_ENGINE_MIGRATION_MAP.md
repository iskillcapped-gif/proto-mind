# Persona Engine Prompt Migration Map

Date: 2026-09-01. Status: Persona 0.2 provider-readiness contracts delivered; no production prompt migration is active.

## Current Sources

| Current source | Current path | Current behavior | Persona 0.1 treatment |
| --- | --- | --- | --- |
| Observer state | `observer.py` -> `Coordinator.handle` | Deterministically classifies the user turn and whether memory is needed. | Remains unchanged. A future adapter may map its factual query/task classification into `PersonaTaskContext`; it cannot select another personality. |
| Retrieved memory | `MemoryKeeper.retrieve` -> reasoner | Supplies already-selected `MemoryRecord` objects. Retrieval is pure by default. | The compiler accepts only this selected list, never scans the full store, and preserves record/provenance identity. Memory content is quoted data, not instruction authority. |
| Existing reasoner prompt | `OllamaReasoner._build_system_prompt` | Defines Proto-Mind identity, memory-use rules, observer context and correction hints. Native Codex currently reuses it as `baseInstructions`. | Remains the production source in Persona 0.1. Later activation may replace only the identity/memory projection after parity tests; observer and correction semantics need an explicit compatibility map. |
| Native Chat developer instruction | `CodexSubscription._chat_answer` | Permanently keeps the provider thread chat-only and refuses tool claims. | Remains a provider safety boundary. Persona text cannot weaken or replace it. |
| Native Full Mac developer instruction | `native_agent.AGENT_INSTRUCTIONS` via `CodexSubscription.agent_answer` | Describes broad operator-granted foreground authority, limits, evidence and stop behavior. | Remains an execution boundary. `PersonaRuntimeContext` may report its facts but never grants or reconstructs the permission. |
| Native agent contract | `native_agent_contract.py` | Freezes model, workspace, tools, limits and verification semantics before a Full Mac turn. | Canonical source for future self-model projection. Unsupported or contradictory claims fail closed. |
| Identity / Values | `identity.py`, private `identity.json` | Stores product profile, values, principles and boundaries; not currently injected into reasoning. | `read_persona_source` exposes active fields without initialization or rewrite. The compiler projects them separately from the checked-in Brother kernel. |
| Context Injection | `context_pack.py` through `main.py` | Separate explicit operator toggle for normal CLI prompts; currently disabled locally. | Remains separate. Persona compilation neither enables, disables nor reuses this mechanism. |
| Attachments and criteria | `native_bridge.py` context helpers | Adds explicit selected text/image/PDF metadata and operator criteria to the current user turn. | Remains user/task material, not Persona Kernel content. External instructions cannot mutate identity or permissions. |
| Durable Codex bootstrap | `native_codex.py::_bootstrap_prompt` | Quotes bounded local conversation once when starting a provider thread. | Remains quoted history. It cannot become personality configuration or authorization. |
| Provider defaults | Codex/Ollama model behavior | Can affect style and wording when explicit local identity is sparse. | Persona 0.3 must demonstrate invariant parity before activation. Provider style is never the canonical identity. |

## Foundation Data Flow

```text
checked-in Brother kernel (read-only)
              +
IdentityStore.read_persona_source() (read-only)
              +
already-selected MemoryRecord objects (read-only)
              +
caller-supplied task and factual runtime authority
              |
              v
PersonaContextCompiler
              |
              v
hashed PersonaSnapshot v1
```

The output is inspectable preview data. `authorizes_actions=false`, `context_injection_changed=false`, and no model/provider method consumes it in Persona 0.1.

## Later Activation Boundary

Persona 0.3 may feed a validated snapshot into both Codex and Ollama only after:

1. golden invariants pass for every supported provider path;
2. the old and new prompt projections are compared on continuity and grounding fixtures;
3. provider safety instructions remain separate and stronger than persona context;
4. a visible local preview and rollback path exist;
5. no unrelated memory, absolute local path, private chain-of-thought or authority token enters the snapshot;
6. Context Injection remains an independent operator setting.

Activation is a separate milestone. This map does not authorize a production prompt change.

## Verified Adapter Readiness

Native 0.18.0 now checks the planned boundary without crossing it:

- Codex placement is `baseInstructions` on every `thread/start` or `thread/resume`; the existing chat-only or Full Mac `developerInstructions` remain separate and cannot be replaced by Persona context.
- Ollama placement is the first system message rebuilt for every request; loopback-only transport remains a separate runtime control.
- Mock is parity/control evidence only and has no production prompt placement.
- The future prompt context is bounded, canonical and hash-linked to one validated `PersonaSnapshot`; selected memory remains quoted data with visible provenance, never instruction authority.
- Provider parity compares kernel, Identity, selected memory and task invariants while preserving truthful provider/model/access differences in separate runtime hashes.
- Context Injection must be independently disabled for readiness. No setting is changed automatically.

These are validated plans, not active adapters. `SubscriptionReasoner`, `NativeOllamaReasoner` and `MockReasoner` still behave exactly as before until Persona 0.3 is implemented and explicitly enabled.
