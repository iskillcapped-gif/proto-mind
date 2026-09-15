"""Exercise installed code with disposable state; never use the maker's account.

--account-probe also starts/cancels an empty-profile browser login without opening
the browser, entering credentials, or starting a model turn.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from package_native_app import macho_files, run, smoke_runtime


PROBE = '''from pathlib import Path
import sys, urllib.parse
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.native_private_backup import PrivateBackup
root = Path(sys.argv[1]).resolve()
core, state = root / "core", root / "native"
data = core / "proto_mind/data"
backend = NativeBackend(core, state)
assert backend.bootstrap()["memory_count"] == 0
store = MemoryStore(data / "working_memory.json", data / "persistent_memory.json", initialize=False)
with store.transaction():
    store.save_persistent_memory([MemoryRecord(content="Portable synthetic note", type="fact", importance=0.5, source="fixture")])
    assert len(store.load_persistent_memory()) == 1
backend.close()
backend = NativeBackend(core, state)
assert backend.bootstrap()["memory_count"] == 1
backend.close()
backup = PrivateBackup(core, state)
result = backup.export(root / "verified-backup")
assert backup.verify(root / "verified-backup")["same_scope"] and result["files"] >= 1
print("PASS: fresh core, transactional memory save, restart and verified backup")
if sys.argv[2] == "account":
    client = CodexSubscription(state)
    try:
        assert client.account()["connected"] is False
        login = client.login()
        assert urllib.parse.urlsplit(login["url"]).hostname in {"auth.openai.com", "chatgpt.com", "openai.com"}
        client.connect().request("account/login/cancel", {"loginId": login["login_id"]})
        assert client.account()["connected"] is False
    finally:
        client.close()
    print("PASS: bundled Codex signed-out status, OAuth start/cancel; no model turn or credential")
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--account-probe", action="store_true")
    args = parser.parse_args()
    app = args.app.resolve()
    resources = app / "Contents/Resources"
    binaries = macho_files(app)
    for path in binaries:
        libraries = run("/usr/bin/otool", "-L", path, capture_output=True, text=True).stdout.splitlines()[1:]
        for line in libraries:
            library = line.strip().split(" (")[0]
            if library.startswith("/") and not library.startswith(("/usr/lib/", "/System/Library/")):
                raise ValueError(f"Unbundled dependency: {path.name}: {library}")
    print(f"PASS: {len(binaries)} Mach-O files have no absolute non-system library dependency", flush=True)
    smoke_runtime(app)
    with tempfile.TemporaryDirectory(prefix="pm-portable-verification-") as temporary:
        env = {key: value for key, value in os.environ.items() if key in {"HOME", "TMPDIR", "LANG", "USER", "SHELL"}}
        env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", PYTHONPATH=str(resources / "core"),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                   PROTO_MIND_CODEX_EXECUTABLE=str(resources / "runtime/codex/bin/codex"))
        run(resources / "runtime/python/bin/python3", "-c", PROBE, temporary,
            "account" if args.account_probe else "offline", env=env, cwd=resources / "core", timeout=90)
    if (resources / "core/proto_mind/data").exists() or list((resources / "core").rglob("__pycache__")):
        raise ValueError("Runtime wrote private data or caches into installed code")
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", app)
    print("PASS: bundle signature remains valid; no core stores or caches inside installed code")


if __name__ == "__main__":
    main()
