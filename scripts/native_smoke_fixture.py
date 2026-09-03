"""Copy code (never personal stores) into a disposable native-UI test project."""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import random
import shutil
import struct
import sys
import tempfile
from uuid import uuid4
import zlib


def text_pdf(pages: list[str]) -> bytes:
    """Tiny ASCII PDF fixtures with real xref offsets; never a user's document."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               (f"<< /Type /Pages /Count {len(pages)} /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages))) + "] >>").encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for index, text in enumerate(pages):
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 14 Tf 40 740 Td ({escaped}) Tj ET".encode("ascii") if text else b""
        objects += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + index * 2} 0 R >>".encode(),
                    f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"]
    data, offsets = b"%PDF-1.4\n", [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return data + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def pdf_fixture(project: Path, state: Path) -> None:
    """Empty local chat and three public synthetic PDF pages for Finder drop QA."""
    (project / "sample.pdf").write_bytes(text_pdf(["PAGE ONE: local PDF preview only.", "PAGE TWO: selected text, no automatic send.", "PAGE THREE: do not include unless selected."]))
    (project / "blank.pdf").write_bytes(text_pdf([""]))
    (project / "broken.pdf").write_bytes(b"%PDF-invalid synthetic fixture\n")
    chat_id = str(uuid4())
    chat = {"id": chat_id, "title": "PDF drop test", "createdAt": 800_000_000, "updatedAt": 800_000_000,
            "messages": [], "provider": "mock", "model": "", "draft": "Summarize the selected PDF pages.", "workspacePath": str(project)}
    state.mkdir(mode=0o700)
    history = state / "conversations.json"
    history.write_text(json.dumps({"version": 5, "selectedID": chat_id, "conversations": [chat]}), encoding="utf-8")
    history.chmod(0o600)
    print(f"PDF fixture: {state} (synthetic pages; Mock; cloud disabled)")


def attachment_fixture(project: Path, state: Path) -> None:
    """A large synthetic image and restored draft; no user pictures or accounts."""
    width, height = 1448, 850
    pixels = random.Random(42).randbytes(width * height * 3)
    rows = b"".join(b"\0" + pixels[row * width * 3:(row + 1) * width * 3] for row in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
             + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    file = project / "synthetic-image.png"
    file.write_bytes(image)
    (project / "drop-note.txt").write_text("Synthetic drag-and-drop test. No personal data.\n", encoding="utf-8")
    (project / "unsupported.pdf").write_bytes(b"%PDF-synthetic unsupported fixture\n")
    metadata = {"schema": "proto_mind.native_image.v1", "path": str(file), "name": file.name,
                "sha256": hashlib.sha256(image).hexdigest(), "mime_type": "image/png", "size_bytes": len(image),
                "width": width, "height": height}
    def message(role, text, **extra):
        return {"id": str(uuid4()), "role": role, "text": text, "raw": "", "evidence": None,
                "notices": [], "createdAt": 800_000_000, "isError": False, **extra}
    chat_id = str(uuid4())
    messages = []
    for index in range(5):
        messages += [message("user", f"Synthetic question {index + 1}"),
                     message("assistant", "This is a local layout fixture. No model was called.\n" * 3)]
    messages += [message("user", "Check this synthetic image", imageContext=[metadata], isError=True),
                 message("report", "Historical fixture: Codex stopped before initialization.", isError=True)]
    chat = {"id": chat_id, "title": "Attachment recovery test", "createdAt": 800_000_000, "updatedAt": 800_000_000,
            "messages": messages, "provider": "mock", "model": "", "draft": "Check this synthetic image",
            "workspacePath": str(project), "pendingImages": [metadata]}
    state.mkdir(mode=0o700)
    history = state / "conversations.json"
    history.write_text(json.dumps({"version": 4, "selectedID": chat_id, "conversations": [chat]}), encoding="utf-8")
    history.chmod(0o600)
    print(f"Attachment fixture: {state} ({len(image)}-byte synthetic PNG; cloud disabled)")


def notice_fixture(project: Path, state: Path) -> None:
    """Synthetic interrupted/completed records; no model calls or personal history."""
    sys.path.insert(0, str(project))
    from proto_mind.native_desk import capture_artifacts
    from proto_mind.native_work_sessions import WorkSessionStore, workspace_identity
    from proto_mind.native_workspace import WorkspaceReader

    state.mkdir(mode=0o700)
    store = WorkSessionStore(state, project)
    reader = WorkspaceReader(str(project))
    chat_id = str(uuid4())
    messages, runs = [], []
    cases = [
        ("Interrupted synthetic image request", None),
        ("Completed reply without criteria", []),
        ("Completed reply with criteria", ["Read the synthetic answer", "Check this is only a fixture"]),
    ]
    for text, criteria in cases:
        run_id = str(uuid4())
        with store.begin(run_id=run_id, conversation_id=chat_id, text=text, provider="mock", model="", effort="",
                         mode="chat", workspace=workspace_identity(project), sources=[], criteria=criteria) as run:
            run.dispatch()
            if criteria is not None:
                run.complete("Synthetic completed reply. No model or tool was called.",
                             artifacts=capture_artifacts(run.record, reader))
        runs.append(run_id)
        for role, value in [("user", text), ("report" if criteria is None else "assistant",
                "Synthetic interruption; no automatic retry." if criteria is None else "Local fixture answer.")]:
            messages.append({"id": str(uuid4()), "role": role, "text": value, "raw": "", "evidence": None,
                             "notices": [], "createdAt": 800_000_000, "isError": criteria is None})
    chat = {"id": chat_id, "title": "Notice and review test", "createdAt": 800_000_000, "updatedAt": 800_000_000,
            "messages": messages, "provider": "mock", "model": "", "draft": "", "workspacePath": str(project)}
    history = state / "conversations.json"
    history.write_text(json.dumps({"version": 4, "selectedID": chat_id, "conversations": [chat]}), encoding="utf-8")
    history.chmod(0o600)
    print(f"Notice fixture: {state} (3 synthetic records; cloud disabled); runs={','.join(runs)}")


def memory_suggestion_fixture(project: Path, state: Path) -> None:
    """Synthetic completed-source metadata for UI review; no provider or tools are called."""
    sys.path.insert(0, str(project))
    from proto_mind.native_memory_suggestions import suggestions
    from proto_mind.native_work_sessions import WorkSessionStore, workspace_identity

    state.mkdir(mode=0o700)
    chat_id, user_id = str(uuid4()), str(uuid4())
    text = "Мы решили использовать кобальтовую палитру.\nЯ предпочитаю короткий итог после проверки тестов."
    with WorkSessionStore(state, project).begin(run_id=str(uuid4()), conversation_id=chat_id, text=text,
            provider="codex", model="synthetic-ui-source-no-model-call", effort="low", mode="chat",
            workspace=workspace_identity(project), sources=[]) as run:
        run.dispatch()
        completed = run.complete("Synthetic UI source only; no actual model call or task execution.")
    report = suggestions(project, state, completed, text)
    def message(identifier, role, text, **extra):
        return {"id": identifier, "role": role, "text": text, "raw": "", "evidence": None,
                "notices": [], "createdAt": 800_000_000, "isError": False, **extra}
    messages = [message(user_id, "user", text), message(str(uuid4()), "assistant",
        "Синтетический UI-пример. Под ответом появились две цитаты для памяти проекта. Ни одна пока не сохранена; модель не вызывалась.",
        memorySuggestions=report, memorySuggestionSourceID=user_id)]
    chat = {"id": chat_id, "title": "Memory suggestion review · fixture", "createdAt": 800_000_000, "updatedAt": 800_000_000,
            "messages": messages, "provider": "mock", "model": "", "draft": "", "workspacePath": str(project)}
    history = state / "conversations.json"
    history.write_text(json.dumps({"version": 5, "selectedID": chat_id, "conversations": [chat]}, ensure_ascii=False), encoding="utf-8")
    history.chmod(0o600)
    print(f"Memory suggestion fixture: {state} (synthetic source; no provider call, cloud disabled)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--attachment-state", type=Path)
    group.add_argument("--notice-state", type=Path)
    group.add_argument("--pdf-state", type=Path)
    group.add_argument("--memory-suggestion-state", type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    if temporary not in destination.parents or destination.exists():
        raise SystemExit("Fixture must be a new directory inside the system temporary directory.")
    selected_state = args.attachment_state or args.notice_state or args.pdf_state or args.memory_suggestion_state
    state = selected_state.resolve() if selected_state else None
    if state is not None and (temporary not in state.parents or state.exists() or state == destination or destination in state.parents):
        raise SystemExit("State must be a separate new directory inside the system temporary directory.")
    source = Path(__file__).resolve().parent.parent
    shutil.copytree(
        source / "proto_mind", destination / "proto_mind",
        ignore=shutil.ignore_patterns("data", "exports", "__pycache__", "tests"),
    )
    print(f"Native smoke fixture: {destination} (code only; no personal stores copied)")
    if state is not None:
        (memory_suggestion_fixture if args.memory_suggestion_state else pdf_fixture if args.pdf_state else notice_fixture if args.notice_state else attachment_fixture)(destination, state)


if __name__ == "__main__":
    main()
