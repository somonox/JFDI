import discord
from discord.ext import commands, tasks
from datetime import timedelta, datetime
from config import CHANNEL_ID
from utils.time_utils import get_kst_now, is_sleep_time, calculate_d_day

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tasks_dict = {}
        self.task_counter = 1
        self.dnd_until = None
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    def _format_tasks_list(self, now):
        tasks_str_list = []
        for task_id, task_data in self.tasks_dict.items():
            content = task_data["content"]
            deadline_str = calculate_d_day(task_data["deadline"], now)

            if task_data["important"]:
                text_block = f"```ansi\n\u001b[2;31m\u001b[1m[{task_id}] {content}{deadline_str}\u001b[0m\n```"
                tasks_str_list.append(text_block)
            else:
                tasks_str_list.append(f"- [{task_id}] {content}{deadline_str}")

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
            tasks_msg = self._format_tasks_list(now)
            await channel.send(f"@everyone 🔔 **30분 알림! 오늘 할 일:**\n{tasks_msg}")

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(aliases=['list'])
    async def show(self, ctx):
        if not self.tasks_dict:
            await ctx.send("📭 현재 등록된 할 일이 없습니다.")
            return

        now = get_kst_now()
        tasks_msg = self._format_tasks_list(now)
        await ctx.send(f"📋 **현재 할 일 목록:**\n{tasks_msg}")

    @commands.command()
    async def add(self, ctx, *, task):
        self.tasks_dict[self.task_counter] = {"content": task, "important": False, "deadline": None}
        await ctx.send(f"✅ 추가 완료: `[{self.task_counter}] {task}`")
        self.task_counter += 1

    @commands.command()
    async def edit(self, ctx, task_id: int, *, new_task):
        if task_id in self.tasks_dict:
            self.tasks_dict[task_id]["content"] = new_task
            await ctx.send(f"✏️ 수정 완료: `[{task_id}] {new_task}`")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def delete(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            del self.tasks_dict[task_id]
            await ctx.send(f"🗑️ 삭제 완료: ID `{task_id}`")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def done(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            task_content = self.tasks_dict[task_id]["content"]
            del self.tasks_dict[task_id]
            await ctx.send(f"✔️ 완료하셨군요! 수고하셨습니다: **{task_content}**")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def important(self, ctx, task_id: int):
        if task_id in self.tasks_dict:
            self.tasks_dict[task_id]["important"] = not self.tasks_dict[task_id]["important"]
            status = "중요" if self.tasks_dict[task_id]["important"] else "일반"
            await ctx.send(f"🔥 상태 변경: ID `{task_id}`이(가) **{status}** 상태가 되었습니다.")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

    @commands.command()
    async def deadline(self, ctx, task_id: int, date_str: str):
        if task_id in self.tasks_dict:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                self.tasks_dict[task_id]["deadline"] = date_str
                await ctx.send(f"⏰ 데드라인 설정 완료: ID `{task_id}` -> **{date_str}**")
            except ValueError:
                await ctx.send("⚠️ 날짜 형식이 잘못되었습니다. `YYYY-MM-DD` 형식으로 입력해주세요. (예: 2026-03-10)")
        else:
            await ctx.send(f"⚠️ ID `{task_id}` 할 일을 찾을 수 없습니다.")

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
