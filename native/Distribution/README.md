# Portable macOS release

This is the **Apple Silicon, macOS 14+ beta** packaging path. It uses the same
Swift/Python source as the developer application; future features can ship in
both editions. The existing `scripts/build_native_app.sh` command, bundle ID,
developer data paths and running developer app remain independent.

## Build

On an Apple Silicon development Mac with Command Line Tools and Python 3.11+:

```sh
bash scripts/build_portable_app.sh --output dist/portable-0.62.0
```

Choose a new output directory each time; the builder refuses to overwrite a
previous release. It downloads only the pinned runtime/notice artifacts in
`runtime-lock.json`, verifies their SHA-256 hashes, and caches them under
`dist/runtime-cache/`. No `pip install`, npm environment or operator profile
is copied into the product. Inspect `distribution-manifest.json` inside the
bundle for runtime provenance and source hashes.

The source allowlist includes root Python modules, `reasoners/`, Persona's
immutable JSON kernel, the starter skill pack and the GitHub wrapper script.
It excludes private `data/`, histories, accounts, logs, exports, tests and the
operator's untracked documents even if they exist in the checkout. Python's
dependency notices come from the matching full standalone archive.

Every build signs the nested executable code, verifies the completed bundle,
then starts its own Python bridge with a disposable empty profile. A missing
module or failed bootstrap stops packaging. Output contains `Proto-Mind.app`,
the DMG, installation notes, and a DMG SHA-256 file. Nothing is uploaded.

## Storage and first launch

The portable config contains only `distribution: portable`; runtime paths are
resolved relative to the running bundle. Per-user state lives in two siblings:
`~/Library/Application Support/ProtoMind/core` and `.../native`. Keeping these
separate preserves the private-backup inventory and restore barriers.

For isolated checks, launch the executable with `--profile-root /absolute/qa`.
This redirects both stores and scopes UI preferences/keychain lookup to that
profile. It does not copy a login. The welcome screen starts no microphone or
model request and grants no cloud/Mac permission. Its dismissal is UI-only
UserDefaults state; actual consent remains in the existing PreferenceStore.

First and newly created portable conversations default to Codex with the
account catalog's default model. The developer edition retains its previous
default. Existing saved dialogs keep their provider/model. Updates replace
only the bundle; there is no automatic updater or developer-profile migration.

## Verification

```sh
bash scripts/test_native.sh --portable-only
python3 -m unittest proto_mind.tests.test_native_portable
bash scripts/run_tests.sh
bash scripts/test_native.sh
python3 scripts/verify_portable_app.py 'dist/portable-0.62.0/Proto-Mind.app' --account-probe
```

Also move a packaged app to a path containing spaces and exercise first launch,
signed-out status, setup dismissal, an unsent draft, restart and Settings.
Use disposable state and synthetic messages. Verify the app signature still
passes afterward; the read-only bundle must not gain private stores or caches.
A local isolated profile is useful evidence but does not replace a test on a
second physical Mac or the oldest supported macOS.

## Public distribution gate

The default `--sign-identity -` creates an **ad-hoc beta**, not an Apple-verified
download. No Developer ID certificate is currently available on the operator's
Mac. A public release needs Apple Developer Program membership, a Developer ID
Application certificate, hardened runtime signing, notarization and stapling.

The builder accepts `--sign-identity 'Developer ID Application: …'` and signs
inside out with the runtime option and timestamp. This path requires its own
validation with the real certificate, including Codex's code-mode host and
Python extension loading. It has not been exercised with a Developer ID.
Do not label an output notarized merely because local codesign verification
passed. Submit the finished DMG using `notarytool` and a local keychain profile,
staple Apple's accepted ticket, then test the quarantined download on a clean
Mac before publishing. Never put signing credentials in this repository.

References: [Apple Developer ID](https://developer.apple.com/developer-id/),
[notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow),
[Python standalone distributions](https://github.com/astral-sh/python-build-standalone),
[Codex release](https://github.com/openai/codex/releases/tag/rust-v0.153.4).
