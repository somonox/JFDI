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
        self.assertEqual(payload["dueDate"], "2026-08-27")
        self.assertEqual(payload["visibility"], "PRIVATE")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        app = web.Application()
        app.router.add_get("/api/v1/users/me", self.me)
        app.router.add_post("/api/v1/auth/refresh", self.refresh)
        app.router.add_get("/api/v1/categories", self.categories)
        app.router.add_post("/api/v1/todos", self.create_todo)
        app.router.add_patch("/api/v1/todos/{todo_id}", self.update_todo)
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
        if request.headers.get("Authorization") not in {
            "Bearer per-user-token",
            "Bearer refreshed-access-token",
        }:
            return web.json_response({"detail": {"message": "bad token"}}, status=401)
        return web.json_response({"userId": 7, "name": "tester"})

    async def refresh(self, request):
        self.requests.append(request)
        body = await request.json()
        if body.get("refreshToken") != "old-refresh-token":
            return web.json_response(
                {"detail": {"message": "bad refresh token"}}, status=401
            )
        return web.json_response(
            {
                "accessToken": "refreshed-access-token",
                "refreshToken": "rotated-refresh-token",
                "expiresAt": "2026-08-28T00:00:00Z",
            }
        )

    async def categories(self, request):
        self.requests.append(request)
        return web.json_response(
            [
                {"categoryId": 3, "name": "취미"},
                {"categoryId": 4, "name": "해야할 일"},
            ]
        )

    async def create_todo(self, request):
        self.requests.append(request)
        body = await request.json()
        self.assertEqual(body["categoryId"], 4)
        self.assertEqual(body["title"], "동기화 테스트")
        return web.json_response({"todoId": 99}, status=201)

    async def delete_todo(self, request):
        self.requests.append(request)
        return web.json_response({"detail": {"message": "already gone"}}, status=404)

    async def update_todo(self, request):
        self.requests.append(request)
        body = await request.json()
        self.assertEqual(body["categoryId"], 4)
        self.assertEqual(body["dueDate"], "2026-08-27")
        return web.json_response({"todoId": int(request.match_info["todo_id"]), **body})

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

    async def test_update_repairs_category_and_uses_date_only(self):
        await self.client.update_todo(
            475,
            {
                "content": "테스트",
                "deadline": "2026-08-27",
                "difficulty": 1,
            },
        )

        update_requests = [
            request
            for request in self.requests
            if request.method == "PATCH" and request.path.endswith("/todos/475")
        ]
        self.assertEqual(len(update_requests), 1)

    async def test_401_refreshes_rotates_persists_and_retries(self):
        updates = []
        client = TLITODOSClient(
            "expired-access-token",
            self.client.base_url,
            refresh_token="old-refresh-token",
            on_session_update=updates.append,
        )

        profile = await client.me()

        self.assertEqual(profile["userId"], 7)
        self.assertEqual(client.access_token, "refreshed-access-token")
        self.assertEqual(client.refresh_token, "rotated-refresh-token")
        self.assertEqual(
            updates,
            [
                {
                    "access_token": "refreshed-access-token",
                    "refresh_token": "rotated-refresh-token",
                    "expires_at": "2026-08-28T00:00:00Z",
                }
            ],
        )
        refresh_requests = [
            request
            for request in self.requests
            if request.path.endswith("/auth/refresh")
        ]
        self.assertEqual(len(refresh_requests), 1)
        self.assertIsNone(refresh_requests[0].headers.get("Authorization"))


if __name__ == "__main__":
    unittest.main()
