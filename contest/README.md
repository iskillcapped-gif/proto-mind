# Proto-Mind Build Week Evidence

Start with [`BUILD_WEEK_PROVENANCE.md`](../BUILD_WEEK_PROVENANCE.md) for the human-readable prior-work versus Build Week disclosure.

See [`REPOSITORY_PRIVACY_REVIEW.md`](../REPOSITORY_PRIVACY_REVIEW.md) for the public repository boundary, resolved portability/privacy findings, and known pre-publication decisions.

Machine-readable evidence is generated under `contest/provenance/`:

- `baseline_manifest.json` hashes submission-relevant files read directly from the July 11 archive.
- `current_manifest.json` hashes the corresponding current working-tree scope.
- `contest_delta.json` classifies added, changed, removed, and unchanged files and reports metric deltas.

Regenerate and validate:

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.contest_provenance
python3 -m json.tool contest/provenance/baseline_manifest.json >/dev/null
python3 -m json.tool contest/provenance/current_manifest.json >/dev/null
python3 -m json.tool contest/provenance/contest_delta.json >/dev/null
```

Generated evidence intentionally excludes runtime data, exports, logs, backups, caches, and secrets. Do not commit those private paths.
