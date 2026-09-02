"""Versioned application-authored guidance, never a learned core-store record."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat

from proto_mind.experience_learning_skill_authoring import _validate_authored_contract, ProceduralSkillAuthoringError
from proto_mind.native_private_records import digest, encoded

PACK_PATH = Path(__file__).with_name("starter_skills.json")
PACK_ID = "proto_mind.starter_skills"
PACK_VERSION = "1.0.0"
IDS = frozenset({"builtin.project_orientation", "builtin.verified_change", "builtin.failure_diagnosis", "builtin.work_handoff"})
MAX_BYTES = 40_000
REFERENCE_FIELDS = {"origin", "skill_id", "skill_name", "version", "pack_id", "pack_hash", "contract_hash"}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate starter skill field.")
        result[key] = value
    return result


def validate_pack(body: dict) -> None:
    if (not isinstance(body, dict) or set(body) != {"schema", "id", "version", "origin", "learned_from_user", "executable", "skills"}
            or body["schema"] != "proto_mind.starter_skill_pack.v1" or body["id"] != PACK_ID
            or body["version"] != PACK_VERSION or body["origin"] != "bundled"
            or body["learned_from_user"] is not False or body["executable"] is not False
            or not isinstance(body["skills"], list) or len(body["skills"]) != len(IDS)):
        raise ValueError("Invalid bundled starter skill pack.")
    identifiers = []
    for row in body["skills"]:
        if not isinstance(row, dict) or set(row) != {"id", "contract"} or not isinstance(row.get("id"), str) or row["id"] not in IDS:
            raise ValueError("Unknown or executable starter skill entry.")
        identifiers.append(row["id"])
        try:
            _validate_authored_contract(row["contract"])
        except ProceduralSkillAuthoringError as exc:
            raise ValueError("Invalid starter skill contract.") from exc
        for value in row["contract"].values():
            for item in value if isinstance(value, list) else [value]:
                if len(item) > 800 or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in item):
                    raise ValueError("Starter skill text exceeds its plain-text limit.")
    if set(identifiers) != IDS:
        raise ValueError("Duplicate or missing starter skill ID.")


class StarterSkills:
    def __init__(self) -> None:
        self.raw = self._read()
        self.body = json.loads(self.raw, object_pairs_hook=_unique)
        validate_pack(self.body)
        self.sha256 = digest(self.body)

    @staticmethod
    def _read() -> bytes:
        descriptor = os.open(PACK_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise ValueError("Starter skill pack must be a bounded regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Starter skill pack grew beyond its limit.")
            return raw
        finally:
            os.close(descriptor)

    def revalidate(self) -> None:
        if self._read() != self.raw:
            raise ValueError("Starter skill pack changed before dispatch. No automatic retry.")

    def metadata(self) -> dict:
        return {"id": PACK_ID, "version": PACK_VERSION, "sha256": self.sha256}

    def rows(self) -> dict:
        return {row["id"]: {"contract": deepcopy(row["contract"]), "reference": {
            "origin": "bundled", "skill_id": row["id"], "skill_name": row["contract"]["name"],
            "version": PACK_VERSION, "pack_id": PACK_ID, "pack_hash": self.sha256, "contract_hash": digest(row["contract"]),
        }} for row in self.body["skills"]}

    def snapshot(self) -> dict:
        self.revalidate()
        return {"schema": "proto_mind.native_starter_skills.v1", "read_only": True, "no_execution": True,
                "pack": deepcopy(self.body), "sha256": self.sha256, "hash_material": encoded(self.body).decode()}
