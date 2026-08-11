import discord
from discord.ext import commands
from discord import app_commands, ui

# =====================
# VIEW (操作ボタン)
# =====================
class WorkControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 永続化

    @ui.button(label="動画編集を開始", style=discord.ButtonStyle.danger, custom_id="work_start_btn")
    async def start_work(self, interaction: discord.Interaction, button: ui.Button):
        # 開始のEmbed
        embed = discord.Embed(
            title="進行状況のお知らせ",
            description=f"{interaction.user.mention} が動画編集を始めました。",
            color=discord.Color.red()
        )
        # チャンネルに送信（全員に見える形式）
        await interaction.channel.send(embed=embed)
        # ボタンを押した本人には完了通知（自分だけに表示）
        await interaction.response.send_message("✅ 開始報告を送信しました。", ephemeral=True)

    @ui.button(label="動画編集を終了", style=discord.ButtonStyle.secondary, custom_id="work_end_btn")
    async def end_work(self, interaction: discord.Interaction, button: ui.Button):
        # 終了のEmbed
        embed = discord.Embed(
            title="進行状況のお知らせ",
            description=f"{interaction.user.mention} が動画編集を終了しました。",
            color=discord.Color.red()
        )
        # チャンネルに送信
        await interaction.channel.send(embed=embed)
        # ボタンを押した本人には完了通知
        await interaction.response.send_message("✅ 終了報告を送信しました。", ephemeral=True)

# =====================
# COG (コマンド本体)
# =====================
class WorkStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="work_panel", description="編集開始/終了の報告パネルを設置します")
    @app_commands.default_permissions(administrator=True)
    async def work_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎬 動画編集 報告パネル",
            description="作業を開始・終了する際に、下のボタンを押してください。",
            color=discord.Color.gray()
        )
        embed.set_footer(text="Work Status System")
        
        # パネルを設置
        await interaction.channel.send(embed=embed, view=WorkControlView())
        await interaction.response.send_message("✅ 報告用パネルを設置しました。", ephemeral=True)

async def setup(bot):
    # 再起動後もボタンが動くように登録
    bot.add_view(WorkControlView())
    await bot.add_cog(WorkStatus(bot))
