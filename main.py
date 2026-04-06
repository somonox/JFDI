import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

import discord
from discord.ext import commands
from config import TOKEN

intents = discord.Intents.default()
intents.message_content = True

# 기본 help 명령어 비활성화 (커스텀 help를 위해)
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'{bot.user} 온라인!')
    # Cogs 로드
    initial_extensions = ['cogs.tasks', 'cogs.general', 'cogs.timetable']
    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            print(f"Loaded extension '{extension}'")
        except Exception as e:
            print(f"Failed to load extension {extension}.", e)

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN is not set in .env file.")