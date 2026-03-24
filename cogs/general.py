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
        embed.add_field(name="`!add <할 일> [키워드/숫자]`", value="할 일을 추가합니다. 마지막에 `week` 혹은 숫자(일수)를 적으면 기한이 자동 계산됩니다.", inline=False)
        embed.add_field(name="`!show [필터]` (또는 `!list`)", value="현재 할 일을 확인합니다. 필터: `all`, `important`, `hobby`, `remain`", inline=False)
        embed.add_field(name="`!edit <ID> <내용>`", value="기존에 작성된 할 일의 내용을 수정합니다.", inline=False)
        embed.add_field(name="`!done <ID>`", value="할 일을 완료 처리하고 목록에서 지웁니다!", inline=False)
        embed.add_field(name="`!delete <ID>`", value="목록에서 할 일을 삭제합니다.", inline=False)
        embed.add_field(name="`!important <ID>`", value="해당 할 일을 중요 상태로 변경합니다.", inline=False)
        embed.add_field(name="`!hobby <ID>`", value="해당 할 일을 취미 상태로 토글합니다.", inline=False)
        embed.add_field(name="`!gambling <ID> <물건> <기한> <@유저>`", value="기한 내에 실패 시 유저에게 물건을 사주는 벌칙을 추가합니다.", inline=False)
        embed.add_field(name="`!detail <ID> <내용>`", value="할 일에 대한 세부 설명을 덧붙입니다.", inline=False)
        embed.add_field(name="`!subtask <부모ID> <내용>`", value="특정 목표의 하위 목표를 생성합니다. (본체도 개별 할 일로 사용 가능)", inline=False)
        embed.add_field(name="`!depend <ID> <선행ID>`", value="특정 목표를 완료하기 위해 먼저 완료해야 할 선행 목표를 설정합니다.", inline=False)
        embed.add_field(name="`!diagram`", value="설정된 하위/선행 목표들을 다이어그램(순서도)으로 시각화하여 보여줍니다.", inline=False)
        embed.add_field(name="`!deadline <ID> <YYYY-MM-DD>`", value="마감 기한을 직접 설정합니다.", inline=False)
        embed.add_field(name="`!dnd <시간(hours)>`", value="입력한 시간 동안 알림 작동을 중지합니다.", inline=False)
        embed.add_field(name="`!dnd_off`", value="방해금지 모드를 즉시 해제합니다.", inline=False)
        embed.set_footer(text="스마트하게 일정 관리를 해보세요!")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))
