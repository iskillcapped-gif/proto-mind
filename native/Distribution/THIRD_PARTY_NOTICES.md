# Bundled runtimes

Proto-Mind's portable edition includes unmodified Python source plus compiled
open-source runtimes. Runtime versions, source URLs and archive SHA-256 hashes
are recorded in `distribution-manifest.json` next to this directory.

- CPython 3.12.14, assembled by Astral's python-build-standalone (20260901).
  Python and its native dependency licenses are preserved here as `Python-LICENSE*`.
  Python's own `LICENSE.txt` and pip's vendor licenses also remain in the runtime.
- OpenAI Codex 0.153.4, official Apple Silicon package. Apache 2.0 license and
  upstream NOTICE are included as `Codex-LICENSE.txt` and `Codex-NOTICE.txt`.
  The package includes its code-mode host, ripgrep and zsh runtime resources.
  The upstream zsh license, ripgrep 15.2.0 notices and PCRE2 10.45 license are
  included separately. zsh is OpenAI's patched build of commit
  `77045ef899e53b9598bebc5a41db93a548a40ca6`; Proto-Mind adds no further patch.

Proto-Mind is an independent application. It does not include an OpenAI account,
subscription, API credit or the proprietary Computer Use service. Third-party
accounts and optional services are connected by each user separately.
