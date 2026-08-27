import json
import stat
import tempfile
import unittest
from pathlib import Path

from utils.task_storage import (
    backup_legacy_file,
    load_task_document,
    migrate_task_document,
    save_json_atomic,
)


class TaskStorageTests(unittest.TestCase):
    def test_legacy_document_preserves_ids_unknown_fields_and_dnd(self):
        legacy = {
            "counter": 2,
            "tasks": {"1": {"content": "기존 할 일", "custom": {"keep": True}}},
            "user_dnd": {"42": "2099-01-01T00:00:00+09:00"},
            "future_top_level": [1, 2, 3],
        }

        migrated, changed = migrate_task_document(legacy)

        self.assertTrue(changed)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["counter"], 2)
        self.assertEqual(migrated["tasks"][1]["custom"], {"keep": True})
        self.assertEqual(migrated["future_top_level"], [1, 2, 3])
        self.assertIn("42", migrated["user_dnd"])

    def test_counter_is_repaired_without_reassigning_task_ids(self):
        migrated, _ = migrate_task_document(
            {"counter": 1, "tasks": {"8": {"content": "eight"}}, "user_dnd": {}}
        )
        self.assertEqual(migrated["counter"], 9)
        self.assertEqual(list(migrated["tasks"]), [8])

    def test_backup_and_atomic_save_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks_data.json"
            path.write_text('{"counter": 1, "tasks": {}}', encoding="utf-8")
            backup = backup_legacy_file(path)
            self.assertIsNotNone(backup)
            save_json_atomic(
                path,
                {"schema_version": 2, "counter": 1, "tasks": {}, "user_dnd": {}},
            )
            loaded, changed = load_task_document(path)
            self.assertFalse(changed)
            self.assertEqual(loaded["schema_version"], 2)
            self.assertEqual(
                json.loads(backup.read_text(encoding="utf-8"))["counter"], 1
            )

    def test_secret_file_mode_is_applied_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            save_json_atomic(path, {"refresh_token": "secret"}, file_mode=0o600)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
