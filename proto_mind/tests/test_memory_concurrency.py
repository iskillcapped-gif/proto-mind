"""Real processes and threads exercise whole core-memory mutations."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from proto_mind.memory_commands import remember_explicit_memory, forget_explicit_memory
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.native_bridge import NativeMemoryStore
from proto_mind.observer import Observer


def _store(directory, cls=MemoryStore):
    root = Path(directory)
    return cls(root / "working.json", root / "persistent.json")


def _record(identity):
    return MemoryRecord(identity, "explicit", 1.0, "operator", id=identity)


def _append_worker(directory, start, number):
    if not start.wait(10):
        raise RuntimeError("Start signal missing")
    store = _store(directory)
    for index in range(12):
        record = _record(f"writer-{number}-{index}")
        store.add_working_record(record)
        store.add_persistent_record(record)


def _paused_mutation(directory, action, ready, release):
    store = _store(directory)
    save = store.save_persistent_memory

    def pause(records):
        ready.set()
        if not release.wait(10):
            raise RuntimeError("Release signal missing")
        save(records)

    with patch.object(store, "save_persistent_memory", side_effect=pause):
        if action == "remember":
            remember_explicit_memory(store, "A remembered preference")
        elif action == "forget":
            forget_explicit_memory(store, "original")
        elif action == "usage":
            MemoryKeeper(store).record_retrieval_usage([_record("original")])
        elif action == "cleanup":
            MemoryHygiene(store).apply_cleanup()
        elif action == "decision":
            keeper = MemoryKeeper(store)
            text = "We decided to use SQLite."
            summary = keeper.evaluate_interaction(text, "", Observer().analyze(text), [])
            keeper.apply_memory_updates(summary)
        else:
            with store.transaction():
                records = store.load_persistent_memory()
                records[0].importance = 0.8
                store.save_persistent_memory(records)


def _competing_writer(directory, attempted, done):
    store = _store(directory, NativeMemoryStore)
    attempted.set()
    store.add_persistent_record(_record("concurrent"))
    done.set()


def _fork_during_transaction(directory):
    store = _store(directory)
    child = -1
    try:
        with store.transaction():
            child = os.fork()
        if child == 0:
            store.add_persistent_record(_record("forked"))
    except BaseException:
        if child == 0:
            os._exit(1)
        raise
    if child == 0:
        os._exit(0)
    _, status = os.waitpid(child, 0)
    if os.waitstatus_to_exitcode(status) != 0:
        raise RuntimeError("Forked writer could not release inherited context and acquire fresh locks")


class MemoryConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.context = multiprocessing.get_context("spawn")

    def join_processes(self, processes):
        for process in processes:
            process.join(15)
            if process.is_alive():
                process.terminate()
                process.join(5)
            self.assertEqual(process.exitcode, 0)

    def test_concurrent_initialization_and_appends_preserve_every_record_in_both_layers(self):
        start = self.context.Event()
        processes = [self.context.Process(target=_append_worker, args=(self.root, start, n)) for n in range(4)]
        for process in processes:
            process.start()
        start.set()
        self.join_processes(processes)
        store = _store(self.root)
        expected = {f"writer-{n}-{i}" for n in range(4) for i in range(12)}
        for records in (store.load_working_memory(), store.load_persistent_memory()):
            self.assertEqual(len(records), len(expected))
            self.assertEqual({record.id for record in records}, expected)

    def test_logical_mutations_exclude_another_process_until_their_stale_snapshot_is_saved(self):
        for action in ("remember", "forget", "usage", "cleanup", "decision", "replacement"):
            with self.subTest(action=action):
                root = self.root / action
                store = _store(root)
                original = _record("original")
                duplicate = deepcopy(original); duplicate.id = "duplicate"
                store.save_persistent_memory([original, duplicate] if action == "cleanup" else [original])
                ready, release, attempted, done = (self.context.Event() for _ in range(4))
                first = self.context.Process(target=_paused_mutation, args=(root, action, ready, release))
                second = self.context.Process(target=_competing_writer, args=(root, attempted, done))
                first.start()
                try:
                    self.assertTrue(ready.wait(10), "First writer reached its save")
                    second.start()
                    self.assertTrue(attempted.wait(10))
                    self.assertFalse(done.wait(0.2), "Competing writer must wait for the complete mutation")
                finally:
                    release.set()
                    self.join_processes([p for p in (first, second) if p.pid is not None])
                records = store.load_persistent_memory()
                self.assertIn("concurrent", {record.id for record in records})
                if action == "forget":
                    self.assertFalse(next(r for r in records if r.id == "original").active)
                if action == "usage":
                    self.assertEqual(next(r for r in records if r.id == "original").usage_count, 1)
                if action == "cleanup":
                    self.assertEqual(len(records), 2)

    def test_threads_with_separate_store_instances_preserve_every_usage_increment(self):
        store = _store(self.root)
        selected = _record("used")
        store.add_working_record(selected)
        store.add_persistent_record(selected)

        def touch(_):
            keeper = MemoryKeeper(_store(self.root))
            for _ in range(10):
                keeper.record_retrieval_usage([selected])

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(touch, range(4)))
        self.assertEqual(store.load_working_memory()[0].usage_count, 40)
        self.assertEqual(store.load_persistent_memory()[0].usage_count, 40)

    def test_nested_transaction_across_store_instances_is_reentrant(self):
        store, other = _store(self.root), _store(self.root)
        with store.transaction(), other.transaction():
            other.add_working_record(_record("working"))
            store.add_persistent_record(_record("persistent"))
        self.assertEqual(other.load_persistent_memory()[0].id, "persistent")

    def test_forked_child_can_leave_inherited_context_and_acquire_its_own_lock(self):
        process = self.context.Process(target=_fork_during_transaction, args=(self.root,))
        process.start()
        self.join_processes([process])
        self.assertEqual(_store(self.root).load_persistent_memory()[0].id, "forked")

    def test_deleted_or_superseded_retrieval_is_not_resurrected_by_promotion(self):
        for state in ("deleted", "superseded"):
            with self.subTest(state=state):
                store = _store(self.root / state)
                selected = _record("stale"); selected.type = "insight"; selected.usage_count = 3
                store.add_working_record(selected)
                if state == "deleted":
                    store.delete_working_record(selected.id)
                else:
                    changed = deepcopy(selected); changed.active = False
                    store.upsert_working_record(changed)
                keeper = MemoryKeeper(store)
                text = "What do you remember?"
                summary = keeper.evaluate_interaction(text, "", Observer().analyze(text), [selected])
                self.assertTrue(summary.should_promote_existing)
                keeper.apply_memory_updates(summary, [selected])
                self.assertEqual(store.load_persistent_memory(), [])
                self.assertEqual(summary.promoted_record_ids, [])

    def test_native_read_does_not_create_store_or_lock_files(self):
        root = self.root / "missing"
        store = _store(root, NativeMemoryStore)
        self.assertEqual(store.load_working_memory() + store.load_persistent_memory(), [])
        self.assertFalse(root.exists())
        store.add_persistent_record(_record("first"))
        self.assertEqual(_store(root, NativeMemoryStore).load_persistent_memory()[0].id, "first")
        self.assertFalse(store.working_path.exists())

    def test_failed_replace_cleans_temporary_file_preserves_bytes_and_releases_locks(self):
        store = _store(self.root)
        store.add_persistent_record(_record("original"))
        before = store.persistent_path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("Disk fixture")):
            with self.assertRaises(OSError):
                store.add_persistent_record(_record("failed"))
        self.assertEqual(store.persistent_path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".*.tmp")), [])
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_store(self.root).add_persistent_record, _record("retry")).result(timeout=5)
        self.assertEqual({r.id for r in store.load_persistent_memory()}, {"original", "retry"})

    def test_temporary_collision_neither_overwrites_nor_removes_existing_file(self):
        store = _store(self.root)
        identity = UUID("00000000-0000-0000-0000-000000000001")
        collision = self.root / f".persistent.json.{identity.hex}.tmp"
        collision.write_text("preserve")
        before = store.persistent_path.read_bytes()
        with patch("proto_mind.memory_store.uuid4", return_value=identity), self.assertRaises(FileExistsError):
            store.add_persistent_record(_record("failed"))
        self.assertEqual(collision.read_text(), "preserve")
        self.assertEqual(store.persistent_path.read_bytes(), before)

    def test_invalid_payload_preserves_valid_json_and_cleans_temporary_file(self):
        store = _store(self.root)
        record = _record("invalid"); record.importance = float("nan")
        with self.assertRaises(ValueError):
            store.add_persistent_record(record)
        self.assertEqual(json.loads(store.persistent_path.read_bytes()), [])
        self.assertEqual(list(self.root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
