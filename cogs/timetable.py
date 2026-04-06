import discord
from discord.ext import commands
import json
import os

DATA_FILE = "timetable_data.json"

class Timetable(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timetable_dict = {}
        self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.timetable_dict = json.load(f)
            except Exception as e:
                print(f"Error loading timetable data: {e}")

    def save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.timetable_dict, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving timetable data: {e}")

    @commands.group(invoke_without_command=True)
    async def tt(self, ctx):
        await ctx.send("사용법: `!tt add <요일> <시간> <내용>`, `!tt list [@유저]`, `!tt remove <요일> <시간>`")

    @tt.command()
    async def add(self, ctx, day: str, time: str, *, subject: str):
        user_id = str(ctx.author.id)
        if user_id not in self.timetable_dict:
            self.timetable_dict[user_id] = {}
        if day not in self.timetable_dict[user_id]:
            self.timetable_dict[user_id][day] = {}
        
        self.timetable_dict[user_id][day][time] = subject
        self.save_data()
        await ctx.send(f"📅 시간표 추가 완료: `{day}` 요일 `{time}`에 **{subject}** 저장됨!")

    @tt.command()
    async def list(self, ctx, member: discord.Member = None):
        target_user = member or ctx.author
        user_id = str(target_user.id)
        
        if user_id not in self.timetable_dict or not self.timetable_dict[user_id]:
            await ctx.send(f"📭 {target_user.display_name}님의 시간표에 등록된 일정이 없습니다.")
            return
            
        embed = discord.Embed(
            title=f"📅 {target_user.display_name}님의 시간표 (루틴)",
            color=discord.Color.green()
        )
        
        days_order = ["월", "화", "수", "목", "금", "토", "일", "매일"]
        for d in days_order:
            if d in self.timetable_dict[user_id] and self.timetable_dict[user_id][d]:
                schedule_strs = []
                sorted_times = sorted(self.timetable_dict[user_id][d].items())
                for t, subj in sorted_times:
                    schedule_strs.append(f"⏰ `{t}` : **{subj}**")
                embed.add_field(name=f"{d}요일" if len(d) == 1 else d, value="\n".join(schedule_strs), inline=False)
                
        for cd, tasks in self.timetable_dict[user_id].items():
            if cd not in days_order and tasks:
                schedule_strs = []
                sorted_times = sorted(tasks.items())
                for t, subj in sorted_times:
                    schedule_strs.append(f"⏰ `{t}` : **{subj}**")
                embed.add_field(name=f"{cd}", value="\n".join(schedule_strs), inline=False)
                
        await ctx.send(embed=embed)

    @tt.command()
    async def remove(self, ctx, day: str, time: str):
        user_id = str(ctx.author.id)
        if user_id in self.timetable_dict and day in self.timetable_dict[user_id] and time in self.timetable_dict[user_id][day]:
            del self.timetable_dict[user_id][day][time]
            if not self.timetable_dict[user_id][day]:
                del self.timetable_dict[user_id][day]
            self.save_data()
            await ctx.send(f"🗑️ 시간표 삭제 완료: `{day}` 의 `{time}` 일정이 삭제되었습니다.")
        else:
            await ctx.send("⚠️ 해당 일정(요일/시간)을 찾을 수 없습니다.")

async def setup(bot):
    await bot.add_cog(Timetable(bot))
