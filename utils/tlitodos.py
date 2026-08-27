"""Small async client and mapping helpers for the TLITODOS REST API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass
class TLITODOSError(Exception):
    status: int
    message: str

    def __str__(self) -> str:
        return self.message


def task_to_tli_payload(task: dict[str, Any]) -> dict[str, Any]:
    """Translate a JFDI task without mutating or dropping legacy fields."""
    difficulty = task.get("difficulty", 1)
    try:
        difficulty = max(1, min(5, int(difficulty)))
    except (TypeError, ValueError):
        difficulty = 1

    due_date = task.get("deadline")
    if due_date:
        due_date = f"{due_date}T23:59:00"

    return {
        "title": str(task.get("content", "")).strip(),
        "importance": "HIGH" if task.get("important", False) else "NONE",
        "hardship": difficulty,
        "dueDate": due_date,
        "visibility": "PRIVATE",
        "groupId": None,
        "isRoutine": False,
    }


class TLITODOSClient:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url.rstrip("/")

    async def _request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    json=payload,
                ) as response,
            ):
                response_text = await response.text()
                try:
                    body = json.loads(response_text) if response_text else None
                except json.JSONDecodeError:
                    body = response_text

                if response.status >= 400:
                    message = (
                        _error_message(body)
                        or f"TLITODOS 요청 실패 ({response.status})"
                    )
                    raise TLITODOSError(response.status, message)
                return body
        except TLITODOSError:
            raise
        except (aiohttp.ClientError, TimeoutError) as error:
            raise TLITODOSError(
                0, f"TLITODOS 서버에 연결할 수 없습니다: {error}"
            ) from error

    async def me(self) -> dict[str, Any]:
        result = await self._request("GET", "/api/v1/users/me")
        return result if isinstance(result, dict) else {}

    async def _category_id(self) -> int:
        categories = await self._request("GET", "/api/v1/categories")
        if isinstance(categories, list):
            for category in categories:
                if category.get("name") == "JFDI":
                    return int(category["categoryId"])
            if categories:
                return int(categories[0]["categoryId"])

        created = await self._request(
            "POST",
            "/api/v1/categories",
            payload={"name": "JFDI", "color": "#145DFF"},
        )
        return int(created["categoryId"])

    async def create_todo(self, task: dict[str, Any]) -> int:
        payload = task_to_tli_payload(task)
        payload["categoryId"] = await self._category_id()
        result = await self._request("POST", "/api/v1/todos", payload=payload)
        return int(result["todoId"])

    async def update_todo(self, todo_id: int, task: dict[str, Any]) -> None:
        payload = task_to_tli_payload(task)
        payload.pop("isRoutine", None)
        # categoryId is intentionally left unchanged when synchronizing an existing item.
        await self._request("PATCH", f"/api/v1/todos/{todo_id}", payload=payload)

    async def delete_todo(self, todo_id: int) -> None:
        await self._request("DELETE", f"/api/v1/todos/{todo_id}")

    async def complete_todo(self, todo_id: int) -> None:
        await self._request("PATCH", f"/api/v1/todos/{todo_id}/complete")


def _error_message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return body if isinstance(body, str) and body else None
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("message")
    if isinstance(detail, str):
        return detail
    return body.get("message")
