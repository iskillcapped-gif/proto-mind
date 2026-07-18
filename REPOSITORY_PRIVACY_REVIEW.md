# Proto-Mind Repository Privacy Review

Review date: 2026-07-18

This review covers the source, tests, scripts, documentation, setup metadata, and assets intended for the first public repository snapshot. It is a local deterministic review, not a third-party security audit.

## Publication Boundary

The repository intentionally excludes local cognitive and runtime state through `.gitignore`:

- `proto_mind/data/`
- `proto_mind/exports/`
- `backups/`
- `logs/`
- `dist/`
- `.env`
- `.venv/` and caches

The tracked `.env.example` contains only local mock/Ollama defaults and no credentials.

## Findings Resolved

- The generated current-state provenance manifest now records the working tree as `.` instead of embedding the operator's absolute home path.
- The macOS launcher builder and generated `.app` launcher resolve the checkout from their own locations instead of embedding a user-specific path.
- Public setup examples use `/path/to/proto_mind`.
- Personal names in test fixtures were replaced with neutral operator values.

## Intentional Test Fixtures

Provider-shaped tokens, credential labels, and private-key markers remain only in `proto_mind/experience_privacy.py`, `proto_mind/experience_capture_soak.py`, and their regression tests. They are synthetic values used to verify redaction and are not live credentials.

The Codex `/feedback` Session ID is intentionally public submission evidence and is documented in the Build Week provenance files. It is not an API credential or an authentication token.

## Review Checks

- Enumerated the exact Git candidate set with `git ls-files --others --exclude-standard` before the initial commit.
- Confirmed ignored runtime stores with `git check-ignore -v`.
- Scanned candidate files for common private-key, OpenAI, GitHub, AWS, Google API, credential-label, email, personal-name, and absolute-home-path patterns.
- Reviewed all matches and classified the credential-shaped values as synthetic privacy fixtures.
- Checked candidate file sizes and types; no unexpected large or binary submission file was found.
- Compared SHA-256 inventories of `proto_mind/data` and `proto_mind/exports` before and after the source-only privacy patch.

## Known Pre-Publication Decisions

- Apache License 2.0 was selected for permissive reuse with an explicit patent grant; the canonical license text is tracked in `LICENSE`.
- The local macOS `.app` wrapper is not signed or redistributable; it is a convenience launcher for an existing checkout.
- Privacy review reduces accidental disclosure risk but cannot prove the absence of every possible sensitive value.

## Safe Recheck

Before every public push, recheck the staged snapshot rather than the whole working directory:

```bash
git diff --cached --check
git diff --cached --stat
git grep -n '/Users/' --cached
git status --short
```

Do not add ignored runtime stores with `git add -f`.
