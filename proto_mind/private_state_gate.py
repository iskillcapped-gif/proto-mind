"""Keep ordinary writers out of an explicitly interrupted private-state restore."""
from contextvars import ContextVar
from pathlib import Path
import os
import stat

RESTORE_MARKER = ".private-restore.json"
GENERATION_FILE = ".private-state-generation.json"
RESTORE_WRITER = ContextVar("private_restore_writer", default=False)


def require_available(directory: Path) -> None:
    if not RESTORE_WRITER.get() and (directory / RESTORE_MARKER).is_symlink():
        raise ValueError("Маркер восстановления повреждён. Исходные данные не изменены.")
    if not RESTORE_WRITER.get() and (directory / RESTORE_MARKER).exists():
        raise ValueError("Восстановление данных не завершено. Откройте «Полная копия» и выберите продолжение или возврат прежних данных.")


def generation(directory: Path) -> bytes | None:
    try: descriptor = os.open(directory / GENERATION_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError: return None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise ValueError("Некорректная версия локальных данных.")
        raw = stream.read(1025)
        if len(raw) > 1024: raise ValueError("Некорректная версия локальных данных.")
        return raw
