import unittest
from datetime import timedelta
from types import SimpleNamespace

from cogs.tasks import Tasks
from utils.time_utils import get_kst_now
from utils.tlitodos import TLITODOSError


class FakeContext:
    def __init__(self, user_id=42):
        self.author = SimpleNamespace(id=user_id, mention=f"<@{user_id}>")
        self.sent = []
        self.message = SimpleNamespace(delete=self._delete_message)
        self.message_deleted = False

    async def _delete_message(self):
        self.message_deleted = True

    async def send(self, message=None, **kwargs):
        self.sent.append(message if message is not None else kwargs)


class FakeTLIClient:
    def __init__(self, todo_id=900, error=None):
        self.todo_id = todo_id
        self.error = error
        self.created = []
        self.updated = []
        self.deleted = []
        self.completed = []

    async def create_todo(self, task):
        if self.error:
            raise self.error
        self.created.append(dict(task))
        return self.todo_id

    async def update_todo(self, todo_id, task):
        if self.error:
            raise self.error
        self.updated.append((todo_id, dict(task)))

    async def delete_todo(self, todo_id):
        if self.error:
            raise self.error
        self.deleted.append(todo_id)

    async def complete_todo(self, todo_id):
        if self.error:
            raise self.error
        self.completed.append(todo_id)


def task_cog(tasks=None):
    cog = Tasks.__new__(Tasks)
    cog.tasks_dict = tasks or {}
    cog.task_counter = max(cog.tasks_dict, default=0) + 1
    cog.user_dnd = {}
    cog._document_extras = {}
    cog.tli_credentials = {}
    cog._tli_clients = {}
    cog.save_data = lambda: None
    return cog


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_access_token_record_still_builds_client(self):
        cog = task_cog()
        cog.tli_credentials["42"] = {"token": "legacy-access-token"}

        client = cog._tli_client_for(42)

        self.assertEqual(client.access_token, "legacy-access-token")
        self.assertIsNone(client.refresh_token)

    async def test_add_remains_local_only(self):
        cog = task_cog()
        ctx = FakeContext()
        cog._tli_client_for = lambda _: self.fail("!add must not access TLITODOS")

        await Tasks.add.callback(cog, ctx, task="로컬만")

        self.assertEqual(cog.tasks_dict[1]["content"], "로컬만")
        self.assertNotIn("tli", cog.tasks_dict[1])

    async def test_add_both_links_item_to_invoking_user(self):
        cog = task_cog()
        ctx = FakeContext(user_id=77)
        client = FakeTLIClient(todo_id=123)
        cog._tli_client_for = lambda user_id: client if user_id == 77 else None

        await Tasks.add_both.callback(cog, ctx, task="양쪽 등록 2")

        task = cog.tasks_dict[1]
        self.assertEqual(task["content"], "양쪽 등록")
        self.assertEqual(task["tli"], {"todo_id": 123, "owner_id": "77"})
        expected_deadline = (get_kst_now() + timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertEqual(task["deadline"], expected_deadline)

    async def test_add_both_requires_dday_without_calling_tli(self):
        cog = task_cog()
        ctx = FakeContext(user_id=77)
        client = FakeTLIClient()
        cog._tli_client_for = lambda _: client

        await Tasks.add_both.callback(cog, ctx, task="마감일 없는 항목")

        self.assertEqual(cog.tasks_dict, {})
        self.assertEqual(client.created, [])
        self.assertIn("D-day", ctx.sent[-1])

    async def test_sync_requires_existing_deadline(self):
        cog = task_cog({5: {"content": "기존 무기한 항목", "deadline": None}})
        ctx = FakeContext(user_id=77)
        cog._tli_client_for = lambda _: self.fail(
            "deadline validation must happen before TLITODOS access"
        )

        await Tasks.sync_tli.callback(cog, ctx, task_id=5)

        self.assertIn("!deadline 5", ctx.sent[-1])

    async def test_delete_removes_remote_before_local(self):
        task = {
            "content": "연결됨",
            "tli": {"todo_id": 321, "owner_id": "42"},
        }
        cog = task_cog({5: task})
        ctx = FakeContext()
        client = FakeTLIClient()
        cog._linked_tli_client = lambda _: (client, task["tli"])

        await Tasks.delete.callback(cog, ctx, task_id=5)

        self.assertEqual(client.deleted, [321])
        self.assertNotIn(5, cog.tasks_dict)

    async def test_delete_keeps_local_item_when_remote_delete_fails(self):
        task = {
            "content": "연결됨",
            "tli": {"todo_id": 321, "owner_id": "42"},
        }
        cog = task_cog({5: task})
        ctx = FakeContext()
        client = FakeTLIClient(error=TLITODOSError(500, "remote failed"))
        cog._linked_tli_client = lambda _: (client, task["tli"])

        await Tasks.delete.callback(cog, ctx, task_id=5)

        self.assertIn(5, cog.tasks_dict)
        self.assertIn("JFDI 항목은 유지", ctx.sent[-1])


if __name__ == "__main__":
    unittest.main()
