import discord
from discord.ext import commands
from discord import app_commands
import l5_core # ルートにある l5_core.py を読み込む
import asyncio

class L5IDCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="l5id", description="LEVEL5 IDの自動作成を開始します")
    @app_commands.describe(count="作成数", password="パスワード")
    @app_commands.default_permissions(administrator=True)
    async def l5id_start(self, interaction: discord.Interaction, count: int, password: str):
        await interaction.response.send_message(f"🚀 {count}件の作成を開始します。完了までお待ちください...", ephemeral=True)
        
        def log_callback(message, level):
            print(f"L5ID [{level}]: {message}")

        try:
            # l5_core.py の中にある run_batch を実行
            await l5_core.run_batch(
                count=count,
                headless=True,
                password=password,
                logcb=log_callback,
                stop_flag=lambda: False
            )
            await interaction.followup.send(f"✅ {count}件の作成が完了しました。")
        except Exception as e:
            await interaction.followup.send(f"❌ エラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(L5IDCog(bot))
