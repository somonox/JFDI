import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz


# 설정
TOKEN = os.environ.get('DISCORD_TOKEN')
CHANNEL_ID = 1479135627046817989  # 알림을 보낼 채널 ID
SLEEP_START = 0   # 새벽 0시
SLEEP_END = 7     # 아침 7시

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

todo_list = ["할 일 1", "할 일 2"] # 임시 할 일 목록

def is_sleep_time():
    """현재 한국 시간이 취침 시간인지 확인"""
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    return SLEEP_START <= now.hour < SLEEP_END

@tasks.loop(minutes=30)
async def reminder_loop():
    # 취침 시간 체크
    if is_sleep_time():
        print(f"취침 시간(KST {datetime.now(pytz.timezone('Asia/Seoul')).hour}시)이라 알림을 건너뜁니다.")
        return

    channel = bot.get_channel(CHANNEL_ID)
    if channel and todo_list:
        tasks_str = "\n".join([f"- {t}" for t in todo_list])
        await channel.send(f"@everyone 🔔 **30분 알림! 오늘 할 일:**\n{tasks_str}")

@bot.event
async def on_ready():
    print(f'{bot.user} 온라인!')
    reminder_loop.start()

@bot.command()
async def add(ctx, *, task):
    todo_list.append(task)
    await ctx.send(f"추가 완료: {task}")

bot.run(TOKEN)