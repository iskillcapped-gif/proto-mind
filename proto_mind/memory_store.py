from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from proto_mind.models import MemoryRecord


class MemoryStore:
    def __init__(
        self,
        working_path: str | Path,
        persistent_path: str | Path,
    ) -> None:
        self.working_path = Path(working_path)
        self.persistent_path = Path(persistent_path)
        self._ensure_files()

    def _ensure_files(self) -> None:
        for path in (self.working_path, self.persistent_path):
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("[]", encoding="utf-8")

    def load_working_memory(self) -> list[MemoryRecord]:
        return self._load_records(self.working_path)

    def load_persistent_memory(self) -> list[MemoryRecord]:
        return self._load_records(self.persistent_path)

    def save_working_memory(self, records: list[MemoryRecord]) -> None:
        self._save_records(self.working_path, records)

    def save_persistent_memory(self, records: list[MemoryRecord]) -> None:
        self._save_records(self.persistent_path, records)

    def add_working_record(self, record: MemoryRecord) -> None:
        records = self.load_working_memory()
        records.append(record)
        self.save_working_memory(records)

    def add_persistent_record(self, record: MemoryRecord) -> None:
        records = self.load_persistent_memory()
        records.append(record)
        self.save_persistent_memory(records)

    def upsert_working_record(self, record: MemoryRecord) -> None:
        records = self.load_working_memory()
        self._upsert(records, record)
        self.save_working_memory(records)

    def upsert_persistent_record(self, record: MemoryRecord) -> None:
        records = self.load_persistent_memory()
        self._upsert(records, record)
        self.save_persistent_memory(records)

    def delete_working_record(self, record_id: str) -> None:
        records = [record for record in self.load_working_memory() if record.id != record_id]
        self.save_working_memory(records)

    def delete_persistent_record(self, record_id: str) -> None:
        records = [record for record in self.load_persistent_memory() if record.id != record_id]
        self.save_persistent_memory(records)

    def _load_records(self, path: Path) -> list[MemoryRecord]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [MemoryRecord.from_dict(item) for item in raw]

    def _save_records(self, path: Path, records: list[MemoryRecord]) -> None:
        payload = [record.to_dict() for record in records]
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _upsert(records: list[MemoryRecord], candidate: MemoryRecord) -> None:
        for index, record in enumerate(records):
            if record.id == candidate.id:
                records[index] = candidate
                return
        records.append(candidate)
