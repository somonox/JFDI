"""Small async client and mapping helpers for the TLITODOS REST API."""

from __future__ import annotations

import json
from collections.abc import Callable
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

    return {
        "title": str(task.get("content", "")).strip(),
        "importance": "HIGH" if task.get("important", False) else "NONE",
        "hardship": difficulty,
        "dueDate": due_date,
        "visibility": "PRIVATE",
        "groupId": None,
        "isRoutine": True,
    }


class TLITODOSClient:
    def __init__(
        self,
        access_token: str,
        base_url: str,
        *,
        refresh_token: str | None = None,
        on_session_update: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at: str | None = None
        self.base_url = base_url.rstrip("/")
        self.on_session_update = on_session_update

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticate: bool = True,
        retry_after_refresh: bool = True,
    ) -> Any:
        headers = {}
        if authenticate:
            headers["Authorization"] = f"Bearer {self.access_token}"
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

                if (
                    response.status == 401
                    and authenticate
                    and retry_after_refresh
                    and self.refresh_token
                ):
                    await self.refresh_session()
                    return await self._request(
                        method,
                        path,
                        payload=payload,
                        authenticate=authenticate,
                        retry_after_refresh=False,
                    )

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

    async def refresh_session(self) -> dict[str, Any]:
        if not self.refresh_token:
            raise TLITODOSError(401, "저장된 TLITODOS 리프레시 토큰이 없습니다.")

        result = await self._request(
            "POST",
            "/api/v1/auth/refresh",
            payload={"refreshToken": self.refresh_token},
            authenticate=False,
            retry_after_refresh=False,
        )
        if not isinstance(result, dict) or not result.get("accessToken"):
            raise TLITODOSError(502, "TLITODOS 토큰 갱신 응답이 올바르지 않습니다.")

        self.access_token = result["accessToken"]
        self.refresh_token = result.get("refreshToken") or self.refresh_token
        self.expires_at = result.get("expiresAt")
        session = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }
        if self.on_session_update:
            self.on_session_update(session)
        return session

    async def me(self) -> dict[str, Any]:
        result = await self._request("GET", "/api/v1/users/me")
        return result if isinstance(result, dict) else {}

    async def _category_id(self) -> int:
        categories = await self._request("GET", "/api/v1/categories")
        if isinstance(categories, list):
            # TLITODOS seeds "취미" first, so taking categories[0] makes
            # ordinary JFDI tasks land in the wrong column. Match the names
            # recognized as the main todo category by the frontend instead.
            preferred_names = {"해야할일", "할일", "과제"}
            for category in categories:
                normalized_name = "".join(str(category.get("name", "")).split())
                if normalized_name in preferred_names:
                    return int(category["categoryId"])
            for category in categories:
                if category.get("name") == "JFDI":
                    return int(category["categoryId"])
            for category in categories:
                normalized_name = "".join(str(category.get("name", "")).split())
                if normalized_name != "취미":
                    return int(category["categoryId"])
            if categories:
                return int(categories[0]["categoryId"])

        created = await self._request(
            "POST",
            "/api/v1/categories",
            payload={"name": "할일", "color": "#33FF57"},
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
        payload["categoryId"] = await self._category_id()
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
