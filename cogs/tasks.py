import discord
from discord.ext import commands, tasks
from datetime import timedelta, datetime
import json
import os
from config import CHANNEL_ID
from utils.time_utils import get_kst_now, is_sleep_time, calculate_d_day

DATA_FILE = "tasks_data.json"

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tasks_dict = {}
        self.task_counter = 1
        self.dnd_until = None
        self.load_data()
        self.reminder_loop.start()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.task_counter = data.get("counter", 1)
                    stored_tasks = data.get("tasks", {})
                    self.tasks_dict = {int(k): v for k, v in stored_tasks.items()}
            except Exception as e:
                print(f"Error loading tasks data: {e}")

    def save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"counter": self.task_counter, "tasks": self.tasks_dict}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving tasks data: {e}")

    def cog_unload(self):
        self.reminder_loop.cancel()

    def _format_tasks_list(self, now, filter_type="all"):
        tasks_str_list = []
        for task_id, task_data in self.tasks_dict.items():
            is_important = task_data.get("important", False)
            is_hobby = task_data.get("hobby", False)

            if filter_type == "important" and not is_important:
                continue
            if filter_type == "hobby" and not is_hobby:
                continue
            if filter_type == "remain" and (is_important or is_hobby):
                continue

            content = task_data["content"]
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

        # 방해금지 모드 체크
        if self.dnd_until and now < self.dnd_until:
            print(f"방해금지 모드 켜짐 (종료 시간: {self.dnd_until.strftime('%Y-%m-%d %H:%M:%S')})")
            return
        elif self.dnd_until and now >= self.dnd_until:
            self.dnd_until = None # 기간 종료시 초기화

        channel = self.bot.get_channel(CHANNEL_ID)
        if channel and self.tasks_dict:
            tasks_msg = self._format_tasks_list(now, "all")
            if tasks_msg:
                await channel.send(f"@everyone 🔔 **30분 알림! 오늘 할 일:**\n{tasks_msg}")

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
        parts = task.split()
        deadline_str = None
        if len(parts) > 1:
            last_word = parts[-1]
            if last_word.lower() == 'week':
                task = " ".join(parts[:-1])
                now = get_kst_now()
                target_date = now + timedelta(days=7)
                deadline_str = target_date.strftime("%Y-%m-%d")
            elif last_word.isdigit():
                days = int(last_word)
                task = " ".join(parts[:-1])
                now = get_kst_now()
                target_date = now + timedelta(days=days)
                deadline_str = target_date.strftime("%Y-%m-%d")

        self.tasks_dict[self.task_counter] = {"content": task, "important": False, "hobby": False, "deadline": deadline_str}
        
        msg = f"✅ 추가 완료: `[{self.task_counter}] {task}`"
        if deadline_str:
            msg += f" (자동 데드라인: {deadline_str})"
            
        await ctx.send(msg)
        self.task_counter += 1
        self.save_data()

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
            del self.tasks_dict[task_id]
            await ctx.send(f"🗑️ 삭제 완료: ID `{task_id}`")
            self.save_data()
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
    async def subtask(self, ctx, parent_id: int, *, content: str):
        if parent_id not in self.tasks_dict:
            await ctx.send(f"⚠️ 상위 목표로 지정한 ID `{parent_id}`을(를) 찾을 수 없습니다.")
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
    async def diagram(self, ctx):
        if not self.tasks_dict:
            await ctx.send("📭 목표 다이어그램을 그릴 데이터가 없습니다.")
            return

        mermaid_lines = ["graph TD"]
        for task_id, task_data in self.tasks_dict.items():
            safe_content = task_data['content'].replace('"', "'")
            # Create Node
            mermaid_lines.append(f'    T{task_id}["[{task_id}] {safe_content}"]')
            
            # Parent-Child
            if "parent" in task_data and task_data["parent"] in self.tasks_dict:
                mermaid_lines.append(f'    T{task_data["parent"]} --> T{task_id}')
            
            # Dependencies
            if "depends_on" in task_data:
                for dep_id in task_data["depends_on"]:
                    if dep_id in self.tasks_dict:
                        mermaid_lines.append(f'    T{dep_id} -.->|선행| T{task_id}')

        mermaid_graph = "\n".join(mermaid_lines)
        # Check length if there's massive amount of tasks, though embed limits won't matter for basic messages
        if len(mermaid_graph) > 1900:
            mermaid_graph = mermaid_graph[:1900] + "\n    ... (Too large to display fully)"
        await ctx.send(f"📊 **목표 연관관계 다이어그램:**\n```mermaid\n{mermaid_graph}\n```")

    @commands.command()
    async def dnd(self, ctx, hours: float):
        now = get_kst_now()
        self.dnd_until = now + timedelta(hours=hours)
        await ctx.send(f"🔇 방해금지 모드가 설정되었습니다. ({hours}시간 동안 알림이 오지 않습니다.)\n종료 예정: `{self.dnd_until.strftime('%Y-%m-%d %H:%M:%S')} KST`")

    @commands.command()
    async def dnd_off(self, ctx):
        self.dnd_until = None
        await ctx.send("🔊 방해금지 모드가 해제되었습니다. 알림이 다시 시작됩니다.")

async def setup(bot):
    await bot.add_cog(Tasks(bot))
