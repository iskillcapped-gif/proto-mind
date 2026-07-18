# Proto-Mind v0

Proto-Mind v0 is a Python 3.11 local research workstation for experimenting with a cognitive architecture layered on top of an LLM-style reasoning component. The goal is not model training and not classic RAG. Memory is treated as part of internal cognition: the system decides when to retrieve memory, which memories matter, and what should persist for future reasoning.

## Architecture

The system is intentionally small and modular:

- `observer.py`: analyzes the incoming turn, classifies the query, estimates importance, and extracts topic tags.
- `memory_store.py`: provides JSON-backed storage for working and persistent memory.
- `memory_keeper.py`: retrieves relevant memory with lightweight heuristics, decides what to store, promotes important knowledge, and decays stale working memories.
- `reasoners/`: pluggable reasoning backends, including mock and local Ollama integration.
- `coordinator.py`: orchestrates the full processing pipeline.
- `models.py`: defines the core dataclasses.
- `config.py`: reads local runtime configuration from environment variables.
- `main.py`: interactive CLI entrypoint.
- `ui/app.py`: minimal local inspection UI for observing the cognition flow.

## Memory Model

Proto-Mind uses two memory layers:

- Working memory:
  - recent conversational context
  - temporary project conclusions
  - active topic tracking
- Persistent memory:
  - durable preferences
  - project decisions
  - important facts and insights that should influence future reasoning

Retrieval is heuristic rather than keyword-only. Each memory gets a score based on:

- tag overlap
- memory importance
- recency
- usage count relevance

This helps the prototype show memory as selective internal context, not a raw text dump.

## Explicit Memory Control

Memory v2.0 adds deterministic operator commands for explicit persistent memories:

```text
/memory status
/memory list
/memory list --all
/memory remember <text>
/memory inspect <id>
/memory search <query>
/memory forget <id>
/memory doctor
```

Explicit memories are stored as `type="explicit"` records in the existing JSON-backed persistent memory file. `/memory forget` is a soft-delete: it marks the explicit memory forgotten/inactive rather than physically deleting it. Search is simple case-insensitive substring matching; there are no embeddings, vector database, or LLM-based consolidation in this layer.

`/memory doctor` is read-only. It reports persistent-memory load health, explicit active/forgotten counts, duplicate and near-duplicate explicit memories, long or low-information records, invalid confidence values, unknown types, and conservative possible conflicts. It gives recommendations but never applies fixes automatically.

## Goal Stack

Goal Stack v1.0 adds deterministic local goal control:

```text
/goals status
/goals add <title>
/goals add <title> --priority high|normal|low
/goals list
/goals list --all
/goals inspect <id>
/goals focus <id>
/goals pause <id>
/goals complete <id>
/goals cancel <id>
/goals reopen <id>
```

Goals are stored in `proto_mind/data/goals.jsonl`. Only one goal can be focused at a time. Pausing, completing, or cancelling a goal clears focus. This is an operator-control layer only: no LLM planning, auto-goal generation, or task queue is enabled yet.

## Task Queue

Task Queue v1.0 adds deterministic local task control:

```text
/tasks status
/tasks add <title>
/tasks add <title> --priority high|normal|low
/tasks add <title> --goal <goal_id>
/tasks list
/tasks list --all
/tasks list --goal <goal_id>
/tasks next
/tasks inspect <id>
/tasks start <id>
/tasks block <id> <reason>
/tasks unblock <id>
/tasks done <id> [result text]
/tasks cancel <id>
/tasks reopen <id>
```

Tasks are stored in `proto_mind/data/tasks.jsonl`. `/tasks next` prefers in-progress tasks, then open tasks by high/normal/low priority and creation time. Tasks may link to goals through `goal_id`, and `/tasks list --goal <goal_id>` filters that relationship. This layer does not generate tasks automatically, call an LLM planner, execute shell commands, or take autonomous action.

## Experiment Journal

Experiment Journal v1.0 adds deterministic local experiment tracking:

```text
/experiments status
/experiments start <title>
/experiments start <title> --goal <goal_id>
/experiments start <title> --task <task_id>
/experiments list
/experiments list --all
/experiments list --goal <goal_id>
/experiments list --task <task_id>
/experiments inspect <id>
/experiments hypothesis <id> <text>
/experiments predict <id> <text>
/experiments method <id> <text>
/experiments run <id>
/experiments result <id> <text>
/experiments reflect <id> <text>
/experiments lesson <id> <text>
/experiments complete <id>
/experiments inconclusive <id>
/experiments cancel <id>
/experiments reopen <id>
```

Experiments are stored in `proto_mind/data/experiments.jsonl`. The journal captures a simple hypothesis/prediction → method/result → reflection/lesson loop, optionally linked to a goal or task. Completing an experiment does not auto-complete linked tasks; it only prints a suggested `/tasks done ...` command. There is no LLM experiment generation, autonomous execution, or shell action in this layer.

## Skill Library

Skill Library v1.0 adds deterministic procedural memory:

```text
/skills status
/skills add <name>
/skills add <name> --category <category>
/skills add <name> --summary <summary>
/skills list
/skills list --all
/skills list --category <category>
/skills inspect <id>
/skills update <id> --summary <text>
/skills body <id> <text>
/skills append <id> <text>
/skills tag <id> <tag>
/skills untag <id> <tag>
/skills search <query>
/skills search <query> --all
/skills use <id>
/skills archive <id>
/skills restore <id>
```

Skills are stored in `proto_mind/data/skills.jsonl`. They represent repeatable procedures, checklists, workflows, and operator patterns. Search is deterministic case-insensitive substring matching. `/skills use <id>` retrieves the stored body and increments usage metadata, but it never executes commands or actions.

## World Model Lite

World Model Lite v1.0 adds deterministic prediction-vs-reality tracking:

```text
/world status
/world predict <situation> -> <prediction>
/world predict <situation> -> <prediction> --confidence 0.0-1.0
/world predict <situation> -> <prediction> --goal <goal_id>
/world predict <situation> -> <prediction> --task <task_id>
/world predict <situation> -> <prediction> --experiment <experiment_id>
/world list
/world list --all
/world list --status open|observed|scored|archived
/world inspect <id>
/world expect <id> <expected_signal>
/world observe <id> <actual_outcome>
/world score <id> <0-5>
/world lesson <id> <lesson text>
/world archive <id>
/world reopen <id>
/world stats
```

Records are stored in `proto_mind/data/world_model.jsonl`. Scores are explicit operator judgments from `0` to `5`; `/world score` requires an observed outcome first. This is not a neural world model: there is no automatic prediction generation, LLM scoring, shell execution, or autonomous action.

## Reasoner Backends

Proto-Mind now supports pluggable local backends:

- `mock`
  - zero-dependency fallback
  - useful for architecture development and tests
- `ollama`
  - local HTTP integration against an Ollama server
  - default local model target: `qwen3:8b`
  - graceful fallback to mock-style reasoning if Ollama is unavailable

Configuration is controlled with environment variables:

```bash
PROTO_MIND_REASONER=mock|ollama
PROTO_MIND_OLLAMA_MODEL=qwen3:8b
PROTO_MIND_OLLAMA_URL=http://localhost:11434
```

Defaults:

- `PROTO_MIND_REASONER=mock`
- `PROTO_MIND_OLLAMA_MODEL=qwen3:8b`
- `PROTO_MIND_OLLAMA_URL=http://localhost:11434`

## Processing Flow

For each interaction:

1. `Observer` analyzes the input.
2. `MemoryKeeper` retrieves relevant memory when needed.
3. The selected reasoner backend produces a response shaped by that memory.
4. `MemoryKeeper` evaluates whether the interaction should be stored.
5. Important memories may be promoted from working memory to persistent memory.
6. The coordinator returns the full turn trace, including observer state, retrieved memory, and memory save decision.

## Ollama Setup

Proto-Mind is designed to run locally on a Mac with Ollama. Current official references:

- Ollama macOS install guide: [docs.ollama.com/macos](https://docs.ollama.com/macos)
- Ollama Qwen3 library page: [ollama.com/library/qwen3](https://ollama.com/library/qwen3)

At the time of writing, the Ollama macOS docs say macOS Sonoma (v14) or newer is supported, and the Qwen3 library page lists `qwen3:8b` as a local model option.

Install and start Ollama, then pull the model:

```bash
ollama run qwen3:8b
```

If you want Proto-Mind to use Ollama:

```bash
export PROTO_MIND_REASONER=ollama
export PROTO_MIND_OLLAMA_MODEL=qwen3:8b
export PROTO_MIND_OLLAMA_URL=http://localhost:11434
```

If Ollama is down or the model is missing, Proto-Mind will return a transparent fallback message and continue in mock mode for that turn.

## Desktop Launchers

The PySide desktop shell can be launched directly:

```bash
python3 -m proto_mind.pyside_app
```

For local Mac double-click use, build the lightweight `.app` wrapper:

```bash
scripts/build_macos_app_launcher.sh
open dist/Proto-Mind.app
```

This launcher is local-only: it resolves the existing checkout relative to `dist/Proto-Mind.app` and depends on a local Python/PySide6 install plus Ollama at `http://localhost:11434`. It is not a signed or redistributable packaged app.

To add a local Desktop shortcut:

```bash
scripts/install_macos_app_shortcut.sh
```

The generated launcher includes a simple `ProtoMind.icns` icon when macOS `iconutil` is available. If Finder shows an old icon, reopen Finder or rebuild the launcher.

## Demo Scenarios

### 1. Continuity scenario

```text
You: We decided the coordinator should orchestrate observer, memory keeper, and reasoner.
You: As we discussed earlier, what is the coordinator responsible for?
```

Expected behavior:
- the second turn triggers memory retrieval
- the prior decision is reused
- the answer mentions continuity and integrated context

### 2. Preference scenario

```text
You: I prefer concise architectural explanations for future Proto-Mind discussions.
You: What style should you use when explaining the MVP later?
```

Expected behavior:
- the preference is stored
- the later response can use it as stable context

### 3. Project decision scenario

```text
You: Let's use JSON files for memory storage in v0.
You: What persistent architectural decisions do we already have?
```

Expected behavior:
- the storage choice becomes a decision memory
- it is promoted into persistent memory
- it becomes available in later reasoning

## Running The CLI

From the repository root:

```bash
python3 -m proto_mind.main
```

Then interact in the shell:

```text
You: We decided persistent memory should store stable project conclusions.
You: As we discussed earlier, what belongs in persistent memory?
```

The CLI now prints:

- final response
- observer output
- retrieved memory
- memory save decision with explicit store/promote semantics and rationale strings

## Running The Research UI

Install the lightweight local UI dependencies:

```bash
python3 -m pip install -r requirements-ui.txt
```

Launch the UI:

```bash
python3 -m uvicorn proto_mind.ui.app:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

The UI is intentionally plain and inspection-first. It shows:

- User Input
- Observer Output
- Retrieved Memory
- Final Response
- Memory Save Decision with rationale, stored record information, and promotion results
- Current Working Memory
- Current Persistent Memory

Recent refinement:

- preference declarations are less memory-greedy and usually avoid retrieval unless the turn clearly asks for continuity
- follow-up turns can promote an already reused memory explicitly, instead of implying promotion on a new unstored memory
- memory decision output now separates `should_store`, `should_promote_new`, and `should_promote_existing`
- memory inventory questions such as `What do you currently remember?` and `What decisions are we using now?` are handled as a dedicated retrieval mode
- newer explicit decisions can supersede older conflicting decisions, and inactive decisions are deprioritized in future retrieval

## Memory Inventory And Overrides

Proto-Mind now distinguishes between:

- continuity follow-ups
- memory inventory / introspection questions
- new declarations such as preferences or decisions

Examples of memory inventory questions:

- `What do you currently remember?`
- `What preferences and decisions do you currently remember separately?`
- `What durable architectural decisions do we currently have?`
- `What storage system are we using now?`

These turns trigger memory retrieval and are answered from stored memory rather than generic architectural improvisation.

Proto-Mind also supports lightweight override handling for explicit decision changes. If a newer decision clearly replaces an older one, the older decision can be marked inactive or superseded, and retrieval will prefer the newer active decision.

## Example Local Usage Flow

1. Start Ollama and ensure `qwen3:8b` is available locally.
2. Export `PROTO_MIND_REASONER=ollama`.
3. Launch the UI or CLI.
4. Enter an architectural decision such as `We decided JSON-backed memory is enough for v0.`
5. Enter a follow-up such as `As we discussed earlier, what memory storage are we using?`
6. Inspect how the observer classified the turn, which memories were selected, and whether the turn was saved or promoted.

## Reflection Journal

Reflection Journal v1.0 adds deterministic operator reflection over the local session log:

```bash
/reflection status
/reflection now
/reflection now --last 10
/reflection list
/reflection inspect <id>
```

Entries are appended to `proto_mind/data/reflection_journal.jsonl`. The journal summarizes recent session-log activity, warning-like signals, memory-command activity, and follow-up recommendations. It does not call an LLM, does not change reasoning, and does not write conclusions into persistent memory.

## Testing

Run:

```bash
python3 -m unittest proto_mind.tests.test_flow
```

The tests cover:

- observer classification
- memory retrieval scoring
- store and promotion logic
- end-to-end continuity flow
- backend selection
- Ollama fallback behavior without requiring a live Ollama instance

## Design Notes

This MVP intentionally avoids:

- model training
- vector databases
- heavy ML dependencies
- production chatbot complexity

The focus is architectural clarity and a clean baseline for later research iterations.

## Future Extensions

- Add a self-reflection layer that critiques reasoning and updates memory priorities.
- Add more internal roles beyond `MemoryKeeper`, such as planner or evaluator modules.
- Replace heuristic retrieval with lightweight semantic matching or embeddings while preserving the same architecture.
- Add more local backends such as DeepSeek-R1 distill 8B without changing the coordinator contract.
