import unittest

from aiohttp import web

from utils.tlitodos import TLITODOSClient, TLITODOSError, task_to_tli_payload


class PayloadTests(unittest.TestCase):
    def test_task_mapping(self):
        payload = task_to_tli_payload(
            {
                "content": "과제 제출",
                "important": True,
                "difficulty": 9,
                "deadline": "2026-08-27",
                "legacy": "preserved elsewhere",
            }
        )
        self.assertEqual(payload["title"], "과제 제출")
        self.assertEqual(payload["importance"], "HIGH")
        self.assertEqual(payload["hardship"], 5)
        self.assertEqual(payload["dueDate"], "2026-08-27T23:59:00")
        self.assertEqual(payload["visibility"], "PRIVATE")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        app = web.Application()
        app.router.add_get("/api/v1/users/me", self.me)
        app.router.add_get("/api/v1/categories", self.categories)
        app.router.add_post("/api/v1/todos", self.create_todo)
        app.router.add_delete("/api/v1/todos/{todo_id}", self.delete_todo)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.client = TLITODOSClient("per-user-token", f"http://127.0.0.1:{port}")

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def me(self, request):
        self.requests.append(request)
        if request.headers.get("Authorization") != "Bearer per-user-token":
            return web.json_response({"detail": {"message": "bad token"}}, status=401)
        return web.json_response({"userId": 7, "name": "tester"})

    async def categories(self, request):
        self.requests.append(request)
        return web.json_response([{"categoryId": 3, "name": "JFDI"}])

    async def create_todo(self, request):
        self.requests.append(request)
        body = await request.json()
        self.assertEqual(body["categoryId"], 3)
        self.assertEqual(body["title"], "동기화 테스트")
        return web.json_response({"todoId": 99}, status=201)

    async def delete_todo(self, request):
        self.requests.append(request)
        return web.json_response({"detail": {"message": "already gone"}}, status=404)

    async def test_create_uses_registered_bearer_token_and_category(self):
        profile = await self.client.me()
        todo_id = await self.client.create_todo({"content": "동기화 테스트"})
        self.assertEqual(profile["userId"], 7)
        self.assertEqual(todo_id, 99)
        self.assertTrue(
            all(
                r.headers.get("Authorization") == "Bearer per-user-token"
                for r in self.requests
            )
        )

    async def test_error_contains_status_and_server_message(self):
        with self.assertRaises(TLITODOSError) as caught:
            await self.client.delete_todo(99)
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(str(caught.exception), "already gone")


if __name__ == "__main__":
    unittest.main()
