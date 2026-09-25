# Bundled runtimes

Proto-Mind's portable edition includes unmodified Python source plus compiled
open-source runtimes. Runtime versions, source URLs and archive SHA-256 hashes
are recorded in `distribution-manifest.json` next to this directory.

- SwiftTerm 1.20.0, MIT-licensed terminal emulator compiled into the native app.
  Its license is included as `SwiftTerm-LICENSE.txt`; SwiftPM dependency versions
  are pinned in the source repository's `native/Package.resolved`.
- CPython 3.12.14, assembled by Astral's python-build-standalone (20260901).
  Python and its native dependency licenses are preserved here as `Python-LICENSE*`.
  Python's own `LICENSE.txt` and pip's vendor licenses also remain in the runtime.
- OpenAI Codex 0.153.4, official Apple Silicon package. Apache 2.0 license and
  upstream NOTICE are included as `Codex-LICENSE.txt` and `Codex-NOTICE.txt`.
  The package includes its code-mode host, ripgrep and zsh runtime resources.
  The upstream zsh license, ripgrep 15.2.0 notices and PCRE2 10.45 license are
  included separately. zsh is OpenAI's patched build of commit
  `77045ef899e53b9598bebc5a41db93a548a40ca6`; Proto-Mind adds no further patch.

## Document libraries (0.72.0)

Claude integration (0.73.0) includes the official Claude Agent SDK 0.2.159 and
unmodified Claude Code 2.1.281. Their wheel metadata and license files remain
under `../core/claude_packages/`; `claude-requirements.txt` records all dependency
versions and accepted hashes. The Claude Code executable retains Anthropic's
signature. Claude Code is subject to Anthropic's terms:
https://code.claude.com/docs/en/legal-and-compliance . It is not an open-source
component or an included account/subscription. Each user signs in independently.

The portable app also includes python-docx 1.2.0, openpyxl 3.1.5,
python-pptx 1.0.2, ReportLab 4.4.3, Pillow 11.3.0, lxml 6.0.1,
XlsxWriter 3.2.5, typing_extensions 4.15.0, et_xmlfile 2.0.0,
charset-normalizer 3.4.3 and defusedxml 0.7.1. Their original license files
and package metadata remain in `../core/document_packages/*dist-info/`
(and package folders where supplied upstream). Exact versions and allowed
wheel SHA-256 values are copied here as `document-requirements.txt`.
The environment is assembled from those wheels, not copied from the user's
Python installation. Native binary wheels are signed with the bundle.

Proto-Mind is an independent application. It does not include an OpenAI account,
subscription, API credit or the proprietary Computer Use service. Third-party
accounts and optional services are connected by each user separately.
