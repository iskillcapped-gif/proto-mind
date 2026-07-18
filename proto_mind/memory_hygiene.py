from __future__ import annotations

import re
from collections import defaultdict

from proto_mind.memory_store import MemoryStore
from proto_mind.models import (
    MemoryHygieneApplyResult,
    MemoryHygieneCleanupCandidate,
    MemoryHygieneDuplicateGroup,
    MemoryHygieneOrphanReference,
    MemoryHygienePreview,
    MemoryHygieneReferenceRepairApplyResult,
    MemoryHygieneReferenceRepairPreview,
    MemoryHygieneReferenceRepair,
    MemoryHygieneRecordRef,
    MemoryRecord,
)
from proto_mind.topic_utils import extract_topic_tags, topic_weight


class MemoryHygiene:
    REPAIR_DOMAIN_TOPICS = {"storage", "json", "sqlite", "backend", "persistence"}

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def preview_cleanup(self) -> MemoryHygienePreview:
        working = self.store.load_working_memory()
        persistent = self.store.load_persistent_memory()
        grouped: dict[str, list[tuple[str, MemoryRecord]]] = defaultdict(list)

        for record in working:
            grouped[self.normalize_content(record.content)].append(("working", record))
        for record in persistent:
            grouped[self.normalize_content(record.content)].append(("persistent", record))

        duplicate_groups: list[MemoryHygieneDuplicateGroup] = []
        replacement_record_ids: dict[str, str] = {}
        for normalized, records in grouped.items():
            if not normalized or len(records) < 2:
                continue

            keep_layer, keep_record = self._choose_keep_record(records)
            refs = [self._record_ref(layer, record) for layer, record in records]
            cleanup_candidates = [
                MemoryHygieneCleanupCandidate(
                    id=record.id,
                    layer=layer,
                    reason=self._cleanup_reason(layer, record, keep_layer, keep_record),
                )
                for layer, record in records
                if self._safe_to_remove(layer, record, keep_layer, keep_record)
            ]
            for candidate in cleanup_candidates:
                replacement_record_ids[candidate.id] = keep_record.id
            duplicate_groups.append(
                MemoryHygieneDuplicateGroup(
                    normalized_content=normalized,
                    records=refs,
                    keep_record_id=keep_record.id,
                    keep_layer=keep_layer,
                    cleanup_candidates=cleanup_candidates,
                    recommendation_reason=self._keep_reason(keep_layer, keep_record),
                )
            )

        cleanup_count = sum(len(group.cleanup_candidates) for group in duplicate_groups)
        notes = [
            "Cleanup is limited to exact normalized-content duplicates.",
            "Unique superseded or historical decisions are preserved.",
        ]
        return MemoryHygienePreview(
            duplicate_groups=duplicate_groups,
            cleanup_candidate_count=cleanup_count,
            safe_to_apply=True,
            replacement_record_ids=replacement_record_ids,
            notes=notes,
        )

    def apply_cleanup(self) -> MemoryHygieneApplyResult:
        preview = self.preview_cleanup()
        remove_working = {
            candidate.id
            for group in preview.duplicate_groups
            for candidate in group.cleanup_candidates
            if candidate.layer == "working"
        }
        remove_persistent = {
            candidate.id
            for group in preview.duplicate_groups
            for candidate in group.cleanup_candidates
            if candidate.layer == "persistent"
        }

        if remove_working:
            working = [record for record in self.store.load_working_memory() if record.id not in remove_working]
            self.store.save_working_memory(working)
        if remove_persistent:
            persistent = [record for record in self.store.load_persistent_memory() if record.id not in remove_persistent]
            self.store.save_persistent_memory(persistent)

        repaired_refs = self._repair_superseded_by_references(preview.replacement_record_ids)

        return MemoryHygieneApplyResult(
            preview=preview,
            removed_working_ids=sorted(remove_working),
            removed_persistent_ids=sorted(remove_persistent),
            repaired_superseded_by_refs=repaired_refs,
        )

    def preview_reference_repair(self) -> MemoryHygieneReferenceRepairPreview:
        layered = self._load_layered_records()
        existing_ids = {record.id for _, record in layered}
        active_decisions = [
            (layer, record)
            for layer, record in layered
            if record.type == "decision" and record.active
        ]
        orphaned_references: list[MemoryHygieneOrphanReference] = []

        for layer, record in layered:
            if not record.superseded_by or record.superseded_by in existing_ids:
                continue
            orphaned_references.append(
                self._orphan_reference_preview(
                    layer=layer,
                    record=record,
                    active_decisions=active_decisions,
                )
            )

        return MemoryHygieneReferenceRepairPreview(
            orphaned_references=orphaned_references,
            repairable_count=sum(1 for reference in orphaned_references if reference.auto_repairable),
            notes=[
                "Reference repair only updates orphaned superseded_by ids.",
                "Auto-repair requires one unambiguous active decision with overlapping specific domain topics.",
                "Content, superseded_at, and superseded_reason are preserved.",
            ],
        )

    def apply_reference_repair(self) -> MemoryHygieneReferenceRepairApplyResult:
        preview = self.preview_reference_repair()
        replacement_record_ids = {
            reference.missing_superseded_by: reference.candidate_record_id
            for reference in preview.orphaned_references
            if reference.auto_repairable and reference.candidate_record_id
        }
        repaired_refs = self._repair_superseded_by_references(replacement_record_ids)
        return MemoryHygieneReferenceRepairApplyResult(
            preview=preview,
            repaired_superseded_by_refs=repaired_refs,
        )

    def _repair_superseded_by_references(
        self,
        replacement_record_ids: dict[str, str],
    ) -> list[MemoryHygieneReferenceRepair]:
        if not replacement_record_ids:
            return []

        working = self.store.load_working_memory()
        persistent = self.store.load_persistent_memory()
        existing_ids = {record.id for record in working + persistent}
        safe_replacements = {
            removed_id: kept_id
            for removed_id, kept_id in replacement_record_ids.items()
            if kept_id in existing_ids
        }
        if not safe_replacements:
            return []

        repaired: list[MemoryHygieneReferenceRepair] = []
        working_changed = self._repair_layer_references("working", working, safe_replacements, repaired)
        persistent_changed = self._repair_layer_references("persistent", persistent, safe_replacements, repaired)
        if working_changed:
            self.store.save_working_memory(working)
        if persistent_changed:
            self.store.save_persistent_memory(persistent)
        return repaired

    def _orphan_reference_preview(
        self,
        *,
        layer: str,
        record: MemoryRecord,
        active_decisions: list[tuple[str, MemoryRecord]],
    ) -> MemoryHygieneOrphanReference:
        if record.type != "decision" or record.active:
            return MemoryHygieneOrphanReference(
                record_id=record.id,
                layer=layer,
                content_preview=self._preview(record.content),
                memory_type=record.type,
                missing_superseded_by=record.superseded_by or "",
                candidate_record_id=None,
                candidate_layer=None,
                candidate_content_preview=None,
                shared_topics=[],
                auto_repairable=False,
                confidence="none",
                reason="Not auto-repairable because only superseded decision records are eligible.",
            )

        record_topics = self._repair_topics(record)
        candidates: list[tuple[str, MemoryRecord, list[str]]] = []
        for candidate_layer, candidate in active_decisions:
            if candidate.id == record.id:
                continue
            candidate_topics = self._repair_topics(candidate)
            shared_topics = sorted(record_topics & candidate_topics)
            domain_overlap = sorted((record_topics & candidate_topics) & self.REPAIR_DOMAIN_TOPICS)
            specific_overlap = [topic for topic in shared_topics if topic_weight(topic) >= 0.6]
            if domain_overlap and specific_overlap:
                candidates.append((candidate_layer, candidate, shared_topics))

        if len(candidates) == 1:
            candidate_layer, candidate, shared_topics = candidates[0]
            return MemoryHygieneOrphanReference(
                record_id=record.id,
                layer=layer,
                content_preview=self._preview(record.content),
                memory_type=record.type,
                missing_superseded_by=record.superseded_by or "",
                candidate_record_id=candidate.id,
                candidate_layer=candidate_layer,
                candidate_content_preview=self._preview(candidate.content),
                shared_topics=shared_topics,
                auto_repairable=True,
                confidence="high",
                reason="Auto-repairable because exactly one active decision shares specific storage-domain topics.",
            )

        reason = (
            "No active decision shares specific storage-domain topics."
            if not candidates
            else "Not auto-repairable because multiple active decisions are plausible repair targets."
        )
        return MemoryHygieneOrphanReference(
            record_id=record.id,
            layer=layer,
            content_preview=self._preview(record.content),
            memory_type=record.type,
            missing_superseded_by=record.superseded_by or "",
            candidate_record_id=None,
            candidate_layer=None,
            candidate_content_preview=None,
            shared_topics=[],
            auto_repairable=False,
            confidence="none",
            reason=reason,
        )

    @staticmethod
    def _repair_layer_references(
        layer: str,
        records: list[MemoryRecord],
        replacement_record_ids: dict[str, str],
        repaired: list[MemoryHygieneReferenceRepair],
    ) -> bool:
        changed = False
        for record in records:
            if not record.superseded_by:
                continue
            replacement_id = replacement_record_ids.get(record.superseded_by)
            if not replacement_id:
                continue
            old_id = record.superseded_by
            record.superseded_by = replacement_id
            repaired.append(
                MemoryHygieneReferenceRepair(
                    record_id=record.id,
                    layer=layer,
                    old_superseded_by=old_id,
                    new_superseded_by=replacement_id,
                )
            )
            changed = True
        return changed

    def _load_layered_records(self) -> list[tuple[str, MemoryRecord]]:
        return [
            *[("working", record) for record in self.store.load_working_memory()],
            *[("persistent", record) for record in self.store.load_persistent_memory()],
        ]

    @staticmethod
    def _repair_topics(record: MemoryRecord) -> set[str]:
        topics: set[str] = set(record.tags)
        topics.update(extract_topic_tags(record.content))
        return {topic for topic in topics if topic_weight(topic) >= 0.6}

    @staticmethod
    def normalize_content(content: str) -> str:
        normalized = re.sub(r"\s+", " ", content.strip().lower())
        return normalized.rstrip(" .!?;:")

    def _choose_keep_record(self, records: list[tuple[str, MemoryRecord]]) -> tuple[str, MemoryRecord]:
        return max(records, key=lambda item: self._keep_score(item[0], item[1]))

    @staticmethod
    def _keep_score(layer: str, record: MemoryRecord) -> tuple[int, int, float, int, int, str]:
        return (
            1 if layer == "persistent" else 0,
            1 if record.active else 0,
            record.importance,
            record.usage_count,
            1 if record.source == "promoted" else 0,
            record.timestamp,
        )

    @staticmethod
    def _safe_to_remove(
        layer: str,
        record: MemoryRecord,
        keep_layer: str,
        keep_record: MemoryRecord,
    ) -> bool:
        if record.id == keep_record.id:
            return False
        if record.type != keep_record.type:
            return False
        if record.active != keep_record.active:
            return False
        if record.superseded_by != keep_record.superseded_by:
            return False
        if layer == "persistent" and keep_layer != "persistent":
            return False
        return True

    @staticmethod
    def _record_ref(layer: str, record: MemoryRecord) -> MemoryHygieneRecordRef:
        return MemoryHygieneRecordRef(
            id=record.id,
            layer=layer,
            content_preview=MemoryHygiene._preview(record.content),
            memory_type=record.type,
            source=record.source,
            importance=record.importance,
            usage_count=record.usage_count,
            active=record.active,
            superseded_by=record.superseded_by,
            timestamp=record.timestamp,
        )

    @staticmethod
    def _preview(content: str, limit: int = 96) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."

    @staticmethod
    def _keep_reason(layer: str, record: MemoryRecord) -> str:
        layer_reason = "persistent memory is preferred over working memory" if layer == "persistent" else "working memory record is the safest equivalent to keep"
        state_reason = "active state is preserved" if record.active else "superseded historical state is preserved"
        return f"Keep {record.id} because {layer_reason}; {state_reason}."

    @staticmethod
    def _cleanup_reason(
        layer: str,
        record: MemoryRecord,
        keep_layer: str,
        keep_record: MemoryRecord,
    ) -> str:
        if layer == "working" and keep_layer == "persistent":
            return "Working duplicate is already represented by an equivalent persistent record."
        if layer == "working":
            return "Duplicate working record has identical normalized content and equivalent state."
        if layer == "persistent":
            return "Duplicate persistent record has identical normalized content and equivalent active/superseded state."
        return f"Duplicate of kept record {keep_record.id}."
