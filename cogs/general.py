import discord
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def custom_help(self, ctx):
        embed = discord.Embed(
            title="✨ 할 일 관리 봇 도움말",
            description="아래의 명령어들을 사용하여 할 일을 관리하고 알림을 설정할 수 있습니다.\n\n",
            color=discord.Color.blue()
        )
        embed.add_field(name="`!add <할 일>`", value="새로운 할 일을 목록에 추가합니다.", inline=False)
        embed.add_field(name="`!show` (또는 `!list`)", value="현재 등록된 할 일과 중요도/데드라인 정보를 모두 확인합니다.", inline=False)
        embed.add_field(name="`!edit <ID> <수정할 내용>`", value="기존에 작성된 할 일의 내용을 수정합니다.", inline=False)
        embed.add_field(name="`!done <ID>`", value="할 일을 완료 처리하고 목록에서 지웁니다! 수고하셨음을 알려드립니다.", inline=False)
        embed.add_field(name="`!delete <ID>`", value="목록에서 할 일을 삭제합니다.", inline=False)
        embed.add_field(name="`!important <ID>`", value="해당 할 일을 중요 상태로 변경하여 알림 시 빨갛고 굵은 폰트로 눈에 띄게 합니다.", inline=False)
        embed.add_field(name="`!deadline <ID> <YYYY-MM-DD>`", value="마감 기한을 설정합니다. (D-Day가 표시됩니다!)", inline=False)
        embed.add_field(name="`!dnd <시간(hours)>`", value="입력한 시간 동안 30분 단위 알림 작동을 일시 중지합니다.", inline=False)
        embed.add_field(name="`!dnd_off`", value="방해금지 모드를 즉시 해제합니다.", inline=False)
        embed.set_footer(text="스마트하게 일정 관리를 해보세요!")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))
