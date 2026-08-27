import discord
from discord.ext import commands, tasks
from datetime import timedelta, datetime
import json
import os
import aiohttp
import io
import zlib
import base64
from config import (
    CHANNEL_ID,
    TASKS_DATA_FILE,
    TLI_BASE_URL,
    TLI_CREDENTIALS_FILE,
)
from utils.time_utils import get_kst_now, is_sleep_time, calculate_d_day
from utils.task_storage import (
    CURRENT_SCHEMA_VERSION,
    backup_legacy_file,
    load_task_document,
    save_json_atomic,
)
from utils.tlitodos import TLITODOSClient, TLITODOSError

DATA_FILE = TASKS_DATA_FILE

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tasks_dict = {}
        self.task_counter = 1
        self.user_dnd = {}  # {user_id: until_datetime}
        self._document_extras = {}
        self.tli_credentials = {}
        self._tli_clients = {}
        self.load_data()
        self.load_tli_credentials()
        self.reminder_loop.start()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            data, migrated = load_task_document(DATA_FILE)
            self.task_counter = data["counter"]
            self.tasks_dict = data["tasks"]
            self._document_extras = {
                key: value
                for key, value in data.items()
                if key not in {"schema_version", "counter", "tasks", "user_dnd"}
            }

            user_dnd_raw = data.get("user_dnd", {})
            now = get_kst_now()
            for uid, until_str in user_dnd_raw.items():
                try:
                    until_dt = datetime.fromisoformat(until_str)
                    if until_dt > now:
                        self.user_dnd[int(uid)] = until_dt
                except (TypeError, ValueError):
                    continue

            if migrated:
                backup_legacy_file(DATA_FILE)
                self.save_data()
                print("Migrated legacy tasks JSON to schema version 2.")
        except Exception as e:
            print(f"Error loading tasks data: {e}")

    def save_data(self):
        try:
            # DND 데이터를 문자열로 변환
            dnd_data = {str(uid): dt.isoformat() for uid, dt in self.user_dnd.items()}
            document = dict(self._document_extras)
            document.update({
                "schema_version": CURRENT_SCHEMA_VERSION,
                "counter": self.task_counter,
                "tasks": self.tasks_dict,
                "user_dnd": dnd_data,
            })
            save_json_atomic(DATA_FILE, document)
        except Exception as e:
            print(f"Error saving tasks data: {e}")

    def load_tli_credentials(self):
        if not os.path.exists(TLI_CREDENTIALS_FILE):
            return
        try:
            with open(TLI_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            users = raw.get("users", raw) if isinstance(raw, dict) else {}
            normalized = {}
            for user_id, record in users.items():
                if not isinstance(record, dict):
                    continue
                access_token = record.get("access_token") or record.get("token")
                if not isinstance(access_token, str):
                    continue
                normalized[str(user_id)] = {
                    "access_token": access_token,
                    "refresh_token": record.get("refresh_token"),
                    "expires_at": record.get("expires_at"),
                    "tli_user_id": record.get("tli_user_id"),
                }
            self.tli_credentials = normalized
            self._tli_clients.clear()
        except Exception as e:
            print(f"Error loading TLITODOS credentials: {e}")

    def save_tli_credentials(self):
        save_json_atomic(
            TLI_CREDENTIALS_FILE,
            {"schema_version": 2, "users": self.tli_credentials},
            file_mode=0o600,
        )

    def _tli_client_for(self, user_id):
        user_key = str(user_id)
        record = self.tli_credentials.get(user_key)
        if not record:
            return None
        cached = self._tli_clients.get(user_key)
        if cached:
            return cached

        def persist_session(session):
            record.update(session)
            record.pop("token", None)
            self.save_tli_credentials()

        client = TLITODOSClient(
            record.get("access_token") or record.get("token", ""),
            TLI_BASE_URL,
            refresh_token=record.get("refresh_token"),
            on_session_update=persist_session,
        )
        self._tli_clients[user_key] = client
        return client

    def _build_task(self, raw_task, *, require_deadline=False):
        parts = raw_task.split()
        deadline_str = None
        content = raw_task
        if len(parts) > 1:
            last_word = parts[-1]
            if last_word.lower() == 'week':
                content = " ".join(parts[:-1])
                deadline_str = (get_kst_now() + timedelta(days=7)).strftime("%Y-%m-%d")
            elif last_word.isdigit():
                content = " ".join(parts[:-1])
                deadline_str = (get_kst_now() + timedelta(days=int(last_word))).strftime("%Y-%m-%d")
        if require_deadline and deadline_str is None:
            raise ValueError("deadline is required")
        return {
            "content": content,
            "important": False,
            "hobby": False,
            "deadline": deadline_str,
        }

    def _store_task(self, task_data):
        task_id = self.task_counter
        self.tasks_dict[task_id] = task_data
        self.task_counter += 1
        self.save_data()
        return task_id

    def _linked_tli_client(self, task_data):
        link = task_data.get("tli")
        if not isinstance(link, dict) or "todo_id" not in link:
            return None, None
        owner_id = str(link.get("owner_id", ""))
        return self._tli_client_for(owner_id), link

    @staticmethod
    def _tli_error_text(error):
        if error.status == 401:
            return "TLITODOS 세션이 만료되었거나 유효하지 않습니다. `!reg_tli <accessToken> [refreshToken]`으로 다시 등록해 주세요."
        return f"TLITODOS 오류: {error}"

    def cog_unload(self):
        self.reminder_loop.cancel()

    def _format_tasks_list(self, now, filter_type="all"):
        filtered_tasks = []
        for task_id, task_data in self.tasks_dict.items():
            is_important = task_data.get("important", False)
            is_hobby = task_data.get("hobby", False)

            if filter_type == "important" and not is_important:
                continue
            if filter_type == "hobby" and not is_hobby:
                continue
            if filter_type == "remain" and (is_important or is_hobby):
                continue
            
            filtered_tasks.append((task_id, task_data))
            
        def sort_key(item):
            t_id, t_data = item
            # 취미는 무조건 맨 하단 (True는 1, False는 0)
            is_hobby_val = 1 if t_data.get("hobby", False) else 0
            # 나머지는 난이도 낮은 순서대로 오름차순 (0부터)
            diff_val = t_data.get("difficulty", 0)
            return (is_hobby_val, diff_val, t_id)
            
        filtered_tasks.sort(key=sort_key)

        tasks_str_list = []
        for task_id, task_data in filtered_tasks:
            is_important = task_data.get("important", False)
            is_hobby = task_data.get("hobby", False)
            difficulty = task_data.get("difficulty", 0)

            diff_str = f" [난이도: {'⭐'*difficulty}]" if not is_hobby and difficulty > 0 else ""
            content = f"{task_data['content']}{diff_str}"
            deadline_str = calculate_d_day(task_data["deadline"], now)

            # 도박 로직 처리
            gambling_str = ""
            is_failed = False
            if "gambling" in task_data and task_data["deadline"]:
                merchandise = task_data["gambling"]["merchandise"]
                user_str = task_data["gambling"]["user"]
                
                # 마감 기한 초과 여부 확인 (D-Day 지난 경우)
                deadline_date = datetime.strptime(task_data["deadline"], "%Y-%m-%d").date()
                if (deadline_date - now.date()).days < 0:
                    is_failed = True
                
                if is_failed:
                    gambling_str = f" 🚨 [벌칙 당첨] {user_str}님에게 {merchandise} 사주기!"
                else:
                    gambling_str = f" 🎰 (실패시 {user_str}님에게 {merchandise})"

            if is_failed:
                text_block = f"```ansi\n\u001b[2;31m\u001b[1m[{task_id}] {content}{deadline_str}{gambling_str}\u001b[0m\n```"
                tasks_str_list.append(text_block)
            elif is_important:
                text_block = f"```ansi\n\u001b[2;31m\u001b[1m[{task_id}] {content}{deadline_str}{gambling_str}\u001b[0m\n```"
                tasks_str_list.append(text_block)
            elif is_hobby:
                tasks_str_list.append(f"🎨 [{task_id}] {content}{deadline_str}{gambling_str}")
            else:
                tasks_str_list.append(f"- [{task_id}] {content}{deadline_str}{gambling_str}")

            if "detail" in task_data:
                tasks_str_list.append(f"  └ 📝 상세: {task_data['detail']}")
            if "parent" in task_data:
                tasks_str_list.append(f"  └ 🔗 상위 목표: ID {task_data['parent']}")
            if "depends_on" in task_data and task_data["depends_on"]:
                tasks_str_list.append(f"  └ 🔒 선행 목표: ID {', '.join(map(str, task_data['depends_on']))}")

        return "\n".join(tasks_str_list)

    @tasks.loop(minutes=30)
    async def reminder_loop(self):
        now = get_kst_now()

        # 취침 시간 체크
        if is_sleep_time():
            print(f"취침 시간(KST {now.hour}시)이라 알림을 건너뜁니다.")
            return

        # 기간이 지난 DND 항목 정리
        expired_uids = [uid for uid, until in self.user_dnd.items() if now >= until]
        for uid in expired_uids:
            del self.user_dnd[uid]
        if expired_uids:
            self.save_data()

        channel = self.bot.get_channel(CHANNEL_ID)
        if channel and self.tasks_dict:
            # 멘션 대상 결정
            members = [m for m in channel.members if not m.bot]
            non_dnd_members = [m for m in members if m.id not in self.user_dnd]
            
            # 모든 멤버가 DND 중이면 알림 건너뜀
            if not non_dnd_members:
                print(f"모든 멤버가 방해금지 모드라 알림을 건너뜁니다.")
                return

            mention_str = "@everyone"
            # 한명이라도 DND 중이면 (그리고 모두가 DND인 건 아니면) 개별 멘션
            if len(non_dnd_members) < len(members):
                mention_str = " ".join([m.mention for m in non_dnd_members])

            tasks_msg = self._format_tasks_list(now, "all")
            if tasks_msg:
                await channel.send(f"{mention_str} 🔔 **30분 알림! 오늘 할 일:**\n{tasks_msg}")

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(aliases=['list'])
    async def show(self, ctx, filter_type: str = "all"):
        if not self.tasks_dict:
            await ctx.send("📭 현재 등록된 할 일이 없습니다.")
            return

        now = get_kst_now()
        tasks_msg = self._format_tasks_list(now, filter_type)
        if not tasks_msg:
            await ctx.send(f"📭 조건('{filter_type}')에 맞는 할 일이 없습니다.")
            return
        await ctx.send(f"📋 **현재 할 일 목록 ({filter_type}):**\n{tasks_msg}")

    @commands.command()
    async def add(self, ctx, *, task):
        task_data = self._build_task(task)
        task_id = self._store_task(task_data)
        msg = f"✅ 추가 완료: `[{task_id}] {task_data['content']}`"
        if task_data["deadline"]:
            msg += f" (자동 데드라인: {task_data['deadline']})"
        await ctx.send(msg)

    @commands.command()
    async def reg_tli(self, ctx, access_token, refresh_token=None):
        message_deleted = True
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            message_deleted = False

        access_token = access_token.strip()
        refresh_token = refresh_token.strip() if refresh_token else None
        client = TLITODOSClient(
            access_token,
            TLI_BASE_URL,
            refresh_token=refresh_token,
        )
        try:
            profile = await client.me()
        except TLITODOSError as error:
            if error.status != 401 or refresh_token is not None:
                await ctx.send(f"⚠️ {self._tli_error_text(error)}")
                return
            # A single argument may be a refresh token. This keeps the old
            # single-access-token form working while allowing refresh-only registration.
            client = TLITODOSClient(
                "",
                TLI_BASE_URL,
                refresh_token=access_token,
            )
            try:
                await client.refresh_session()
                profile = await client.me()
            except TLITODOSError as refresh_error:
                await ctx.send(f"⚠️ {self._tli_error_text(refresh_error)}")
                return

        user_key = str(ctx.author.id)
        self.tli_credentials[user_key] = {
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "expires_at": client.expires_at,
            "tli_user_id": profile.get("userId"),
        }
        self._tli_clients.pop(user_key, None)
        self.save_tli_credentials()
        warning = "" if message_deleted else " 봇에 메시지 삭제 권한이 없어 원본 토큰 메시지는 직접 삭제해 주세요."
        await ctx.send(f"🔐 {ctx.author.mention}님의 TLITODOS 계정을 등록했습니다.{warning}")

    @commands.command()
    async def add_both(self, ctx, *, task):
        client = self._tli_client_for(ctx.author.id)
        if client is None:
            await ctx.send("⚠️ 먼저 `!reg_tli <accessToken> [refreshToken]`으로 TLITODOS 토큰을 등록해 주세요.")
            return

        try:
            task_data = self._build_task(task, require_deadline=True)
        except ValueError:
            await ctx.send(
                "⚠️ TLITODOS에는 마감일이 필요합니다. `!add_both <내용> <D-day 숫자|week>` 형식으로 입력해 주세요. 예: `!add_both 과제 제출 3`"
            )
            return
        try:
            todo_id = await client.create_todo(task_data)
        except TLITODOSError as error:
            await ctx.send(f"⚠️ {self._tli_error_text(error)}")
            return

        task_data["tli"] = {
            "todo_id": todo_id,
            "owner_id": str(ctx.author.id),
        }
        task_id = self._store_task(task_data)
        await ctx.send(
            f"✅ 양쪽에 추가 완료: JFDI `[{task_id}]`, TLITODOS `[{todo_id}]` — {task_data['content']}"
        )

    @commands.command()
    async def sync_tli(self, ctx, task_id: int):
        task_data = self.tasks_dict.get(task_id)
        if task_data is None:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")
            return
        if not task_data.get("deadline"):
            await ctx.send(
                f"⚠️ ID `{task_id}`에 마감일이 없습니다. 먼저 `!deadline {task_id} YYYY-MM-DD`로 설정해 주세요."
            )
            return

        client = self._tli_client_for(ctx.author.id)
        if client is None:
            await ctx.send("⚠️ 먼저 `!reg_tli <accessToken> [refreshToken]`으로 TLITODOS 토큰을 등록해 주세요.")
            return

        link = task_data.get("tli")
        if isinstance(link, dict) and str(link.get("owner_id")) != str(ctx.author.id):
            await ctx.send("⚠️ 이 항목은 다른 사용자의 TLITODOS 계정에 연결되어 있습니다.")
            return

        try:
            if isinstance(link, dict) and link.get("todo_id") is not None:
                todo_id = int(link["todo_id"])
                await client.update_todo(todo_id, task_data)
                action = "갱신"
            else:
                todo_id = await client.create_todo(task_data)
                task_data["tli"] = {
                    "todo_id": todo_id,
                    "owner_id": str(ctx.author.id),
                }
                action = "생성"
            self.save_data()
            await ctx.send(f"🔄 동기화 완료: JFDI `[{task_id}]` → TLITODOS `[{todo_id}]` ({action})")
        except TLITODOSError as error:
            await ctx.send(f"⚠️ {self._tli_error_text(error)}")

    @commands.command()
    async def edit(self, ctx, task_id: int, *, new_task):
        if task_id in self.tasks_dict:
            self.tasks_dict[task_id]["content"] = new_task
            await ctx.send(f"✏️ 수정 완료: `[{task_id}] {new_task}`")
            self.save_data()
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def delete(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            client, link = self._linked_tli_client(self.tasks_dict[task_id])
            if link is not None and client is None:
                await ctx.send("⚠️ 연결된 TLITODOS 항목을 삭제할 사용자 토큰이 없습니다. 해당 사용자가 `!reg_tli <accessToken> [refreshToken]`으로 다시 등록해야 합니다.")
                return
            if link is not None:
                try:
                    await client.delete_todo(int(link["todo_id"]))
                except TLITODOSError as error:
                    if error.status != 404:
                        await ctx.send(f"⚠️ {self._tli_error_text(error)} JFDI 항목은 유지했습니다.")
                        return
            del self.tasks_dict[task_id]
            self.save_data()
            suffix = " (TLITODOS에서도 삭제됨)" if link is not None else ""
            await ctx.send(f"🗑️ 삭제 완료: ID `{task_id}`{suffix}")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def done(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            # 선행 목표 체크
            depends_on_list = self.tasks_dict[task_id].get("depends_on", [])
            unfinished_deps = [str(dep) for dep in depends_on_list if dep in self.tasks_dict]
            if unfinished_deps:
                await ctx.send(f"⚠️ ID `{task_id}`을(를) 완료하려면 먼저 선행 목표를 완료해야 합니다 (남은 선행 ID: {', '.join(unfinished_deps)}).")
                return
            
            # 하위 목표 체크
            unfinished_subtasks = [str(sid) for sid, sdata in self.tasks_dict.items() if sdata.get("parent") == task_id]
            if unfinished_subtasks:
                await ctx.send(f"⚠️ ID `{task_id}`을(를) 완료하려면 먼저 연결된 하위 목표를 완료해야 합니다 (남은 하위 ID: {', '.join(unfinished_subtasks)}).")
                return

            task_content = self.tasks_dict[task_id]["content"]
            client, link = self._linked_tli_client(self.tasks_dict[task_id])
            if link is not None and client is None:
                await ctx.send("⚠️ 연결된 TLITODOS 항목을 완료할 사용자 토큰이 없습니다. 해당 사용자가 `!reg_tli <accessToken> [refreshToken]`으로 다시 등록해야 합니다.")
                return
            if link is not None:
                try:
                    await client.complete_todo(int(link["todo_id"]))
                except TLITODOSError as error:
                    await ctx.send(f"⚠️ {self._tli_error_text(error)} JFDI 항목은 유지했습니다.")
                    return
            del self.tasks_dict[task_id]
            await ctx.send(f"✔️ 완료하셨군요! 수고하셨습니다: **{task_content}**")
            self.save_data()
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def important(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            if "important" not in self.tasks_dict[task_id]:
                self.tasks_dict[task_id]["important"] = False
            self.tasks_dict[task_id]["important"] = not self.tasks_dict[task_id]["important"]
            status = "중요" if self.tasks_dict[task_id]["important"] else "일반"
            await ctx.send(f"🔥 상태 변경: ID `{task_id}`이(가) **{status}** 상태가 되었습니다.")
            self.save_data()
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def hobby(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            if "hobby" not in self.tasks_dict[task_id]:
                self.tasks_dict[task_id]["hobby"] = False
            self.tasks_dict[task_id]["hobby"] = not self.tasks_dict[task_id]["hobby"]
            status = "취미" if self.tasks_dict[task_id]["hobby"] else "일반"
            await ctx.send(f"🎨 상태 변경: ID `{task_id}`이(가) **{status}** 상태가 되었습니다.")
            self.save_data()
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def deadline(self, ctx, task_id: int, date_str: str):
        if task_id in self.tasks_dict:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                self.tasks_dict[task_id]["deadline"] = date_str
                await ctx.send(f"⏰ 데드라인 설정 완료: ID `{task_id}` -> **{date_str}**")
                self.save_data()
            except ValueError:
                await ctx.send("⚠️ 날짜 형식이 잘못되었습니다. `YYYY-MM-DD` 형식으로 입력해주세요. (예: 2026-03-10)")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def gambling(self, ctx, task_id: int, merchandise: str, deadline_input: str, user: str):
        if task_id not in self.tasks_dict:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")
            return

        if deadline_input.lower() == 'week':
            target_date = get_kst_now() + timedelta(days=7)
            deadline_str = target_date.strftime("%Y-%m-%d")
        elif deadline_input.isdigit():
            target_date = get_kst_now() + timedelta(days=int(deadline_input))
            deadline_str = target_date.strftime("%Y-%m-%d")
        else:
            try:
                datetime.strptime(deadline_input, "%Y-%m-%d")
                deadline_str = deadline_input
            except ValueError:
                await ctx.send("⚠️ 날짜 형식이 잘못되었습니다. 숫자, 'week', 혹은 `YYYY-MM-DD` 형식으로 입력해주세요.")
                return

        self.tasks_dict[task_id]["deadline"] = deadline_str
        self.tasks_dict[task_id]["gambling"] = {"merchandise": merchandise, "user": user}
        
        await ctx.send(f"🎰 도박 성립! ID `{task_id}`을(를) **{deadline_str}** 까지 완료하지 못하면 {user} 님에게 **{merchandise}**을(를) 사줘야 합니다!")
        self.save_data()

    @commands.command()
    async def detail(self, ctx, task_id: int, *, detailsText: str):
        if task_id in self.tasks_dict:
            self.tasks_dict[task_id]["detail"] = detailsText
            await ctx.send(f"📝 상세 정보 추가 완료: ID `{task_id}` -> {detailsText}")
            self.save_data()
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def difficulty(self, ctx, task_id: int, level: int):
        if task_id not in self.tasks_dict:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")
            return

        if self.tasks_dict[task_id].get("hobby", False):
            await ctx.send("⚠️ 취미 상태인 목표는 작업 난이도를 설정할 수 없습니다.")
            return

        if not 1 <= level <= 5:
            await ctx.send("⚠️ 작업 난이도는 1에서 5 사이의 숫자여야 합니다.")
            return

        self.tasks_dict[task_id]["difficulty"] = level
        await ctx.send(f"🔥 난이도 설정 완료: ID `{task_id}` -> **{'⭐'*level}**")
        self.save_data()

    @commands.command()
    async def subtask(self, ctx, parent_id: int, *, content: str):
        if parent_id not in self.tasks_dict:
            await ctx.send(f"⚠️ 상위 목표로 지정한 ID `{parent_id}`을(를) 찾을 수 없습니다.")
            return

        if content.isdigit():
            child_id = int(content)
            if child_id in self.tasks_dict:
                if child_id == parent_id:
                    await ctx.send("⚠️ 자기 자신을 하위 목표로 설정할 수 없습니다.")
                    return
                # 기존 태스크를 하위 태스크로 연결
                self.tasks_dict[child_id]["parent"] = parent_id
                await ctx.send(f"🔗 기존 목표 연결 완료: ID `{child_id}`이(가) ID `{parent_id}`의 하위 목표로 편입되었습니다.")
                self.save_data()
                return

        self.tasks_dict[self.task_counter] = {
            "content": content,
            "important": False,
            "hobby": False,
            "deadline": None,
            "parent": parent_id
        }
        await ctx.send(f"🌿 하위 목표 추가 완료: `[{self.task_counter}] {content}` (상위: {parent_id})")
        self.task_counter += 1
        self.save_data()

    @commands.command()
    async def depend(self, ctx, task_id: int, depends_on_id: int):
        if task_id not in self.tasks_dict:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")
            return
        if depends_on_id not in self.tasks_dict:
            await ctx.send(f"⚠️ 선행 목표 ID `{depends_on_id}`을(를) 찾을 수 없습니다.")
            return
        
        if "depends_on" not in self.tasks_dict[task_id]:
            self.tasks_dict[task_id]["depends_on"] = []
        
        if depends_on_id not in self.tasks_dict[task_id]["depends_on"]:
            self.tasks_dict[task_id]["depends_on"].append(depends_on_id)
            await ctx.send(f"🔗 연결 완료: ID `{task_id}`은(는) 이제 ID `{depends_on_id}`이(가) 완료되어야 진행(done)할 수 있습니다.")
            self.save_data()
        else:
            await ctx.send(f"⚠️ 이미 설정된 선행 목표입니다.")

    @commands.command()
    async def diagram(self, ctx, page: int = 1):
        if not self.tasks_dict:
            await ctx.send("📭 목표 다이어그램을 그릴 데이터가 없습니다.")
            return

        ITEMS_PER_PAGE = 10
        total_items = len(self.tasks_dict)
        total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

        if page < 1 or page > total_pages:
            await ctx.send(f"⚠️ 페이지 범위를 벗어났습니다. (1~{total_pages}페이지)")
            return

        tasks_list = list(self.tasks_dict.items())
        start_idx = (page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_tasks = dict(tasks_list[start_idx:end_idx])

        # 현재 페이지의 태스크와 연관된 부모/선행 태스크 ID 수집 (이름 표시를 위함)
        referenced_ids = set(page_tasks.keys())
        for task_id, task_data in page_tasks.items():
            if "parent" in task_data and task_data["parent"] in self.tasks_dict:
                referenced_ids.add(task_data["parent"])
            if "depends_on" in task_data:
                for dep in task_data["depends_on"]:
                    if dep in self.tasks_dict:
                        referenced_ids.add(dep)

        mermaid_lines = ["graph LR"]
        # 모든 참조된 노드 생성
        for r_id in referenced_ids:
            safe_content = self.tasks_dict[r_id]['content'].replace('"', "'")
            chunk_size = 15
            chunks = [safe_content[i:i+chunk_size] for i in range(0, len(safe_content), chunk_size)]
            wrapped_content = "<br>".join(chunks)
            mermaid_lines.append(f'    T{r_id}["<b>[{r_id}]</b><br>{wrapped_content}"]')
            
        # 엣지 연결 (현재 페이지 태스크 기준)
        for task_id, task_data in page_tasks.items():
            if "parent" in task_data and task_data["parent"] in self.tasks_dict:
                mermaid_lines.append(f'    T{task_data["parent"]} --> T{task_id}')
            if "depends_on" in task_data:
                for dep_id in task_data["depends_on"]:
                    if dep_id in self.tasks_dict:
                        mermaid_lines.append(f'    T{dep_id} -.->|선행| T{task_id}')

        mermaid_graph = "\n".join(mermaid_lines)
        
        await ctx.send(f"⏳ 다이어그램 이미지 생성 중... (페이지 {page}/{total_pages})")
        
        try:
            graph_bytes = mermaid_graph.encode('utf-8')
            compressed = zlib.compress(graph_bytes, 9)
            b64 = base64.urlsafe_b64encode(compressed).decode('utf-8')
            url = f"https://kroki.io/mermaid/png/{b64}"
            
            headers = {"User-Agent": "Mozilla/5.0"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        file = discord.File(io.BytesIO(img_data), filename="diagram.png")
                        await ctx.send("📊 **목표 연관관계 다이어그램:**", file=file)
                    else:
                        await ctx.send(f"⚠️ 렌더링 서버 오류 ㅠㅠ (상태 코드: {resp.status})\n\n참고용 코드:\n```mermaid\n{mermaid_graph}\n```")
        except Exception as e:
            await ctx.send(f"⚠️ 이미지를 생성하는 동안 오류가 발생했습니다: {e}\n\n참고용 코드:\n```mermaid\n{mermaid_graph}\n```")

    @commands.command()
    async def dnd(self, ctx, hours: float):
        now = get_kst_now()
        until = now + timedelta(hours=hours)
        self.user_dnd[ctx.author.id] = until
        self.save_data()
        await ctx.send(f"🔇 {ctx.author.mention}님 정숙! {hours}시간 동안 알림에서 제외됩니다.\n종료 예정: `{until.strftime('%Y-%m-%d %H:%M:%S')} KST`")

    @commands.command()
    async def dnd_off(self, ctx):
        if ctx.author.id in self.user_dnd:
            del self.user_dnd[ctx.author.id]
            self.save_data()
            await ctx.send(f"🔊 {ctx.author.mention}님의 방해금지 모드가 해제되었습니다.")
        else:
            await ctx.send(f"❓ {ctx.author.mention}님은 현재 방해금지 모드가 아닙니다.")

async def setup(bot):
    await bot.add_cog(Tasks(bot))
