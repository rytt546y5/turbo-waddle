import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os

# =====================
# DATA MANAGEMENT
# =====================
DATA_FILE = "work_status_config.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# =====================
# VIEW (操作ボタン)
# =====================
class WorkControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 永続化

    async def send_report(self, interaction: discord.Interaction, status_text: str):
        data = load_data()
        gid = str(interaction.guild.id)
        # 保存されている報告先チャンネルIDを取得
        channel_id = data.get(gid)

        if not channel_id:
            return await interaction.response.send_message("❌ 報告先のチャンネルが設定されていません。パネルを再設置してください。", ephemeral=True)

        target_channel = interaction.guild.get_channel(int(channel_id))
        if not target_channel:
            return await interaction.response.send_message("❌ 報告先のチャンネルが見つかりません。", ephemeral=True)

        # 報告用Embed (赤色固定)
        embed = discord.Embed(
            title="進行状況のお知らせ",
            description=f"{interaction.user.mention} が動画編集を{status_text}。",
            color=discord.Color.red()
        )
        
        try:
            # 指定されたチャンネルに送信
            await target_channel.send(embed=embed)
            # 応答を返す
            await interaction.response.send_message(f"✅ {status_text}報告を送信しました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 報告先チャンネルへの送信権限がありません。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ エラーが発生しました: {e}", ephemeral=True)

    @ui.button(label="動画編集を開始", style=discord.ButtonStyle.danger, custom_id="work_start_v2")
    async def start_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_report(interaction, "はじめました")

    @ui.button(label="動画編集を終了", style=discord.ButtonStyle.secondary, custom_id="work_end_v2")
    async def end_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_report(interaction, "終了しました")

# =====================
# COG (メイン機能)
# =====================
class WorkStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="work_panel", description="編集報告パネルを設置します（送信先を指定可能）")
    @app_commands.describe(target_channel="報告メッセージを送信したいチャンネルを選択")
    @app_commands.default_permissions(administrator=True)
    async def work_panel(self, interaction: discord.Interaction, target_channel: discord.TextChannel):
        # 報告先チャンネルを保存
        data = load_data()
        data[str(interaction.guild.id)] = target_channel.id
        save_data(data)

        # ここを .gray() から .grey() に修正しました
        embed = discord.Embed(
            title="🎬 動画編集 報告パネル",
            description=f"作業を開始・終了する際に、下のボタンを押してください。\n報告は {target_channel.mention} に送信されます。",
            color=discord.Color.grey()
        )
        embed.set_footer(text="Work Status System")
        
        # パネルを設置
        await interaction.channel.send(embed=embed, view=WorkControlView())
        await interaction.response.send_message(f"✅ パネルを設置しました。報告先: {target_channel.mention}", ephemeral=True)

async def setup(bot):
    # 再起動時にボタンを有効化
    bot.add_view(WorkControlView())
    await bot.add_cog(WorkStatus(bot))
