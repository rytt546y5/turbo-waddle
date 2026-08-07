import discord
from discord.ext import commands
from discord import app_commands

class SimpleEmbed(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="embed_send", description="シンプルなEmbed（em式）メッセージを送信します")
    @app_commands.describe(
        title="Embedのタイトルを入力してください",
        description="Embedの本文を入力してください（\\n で改行できます）",
        channel="送信先のチャンネルを選択してください（未指定なら現在のチャンネル）",
        color="カラーコードを16進数で入力（例: ff0000 ➔ 赤）"
    )
    @app_commands.default_permissions(administrator=True) # 管理者のみ
    async def embed_send(
        self, 
        interaction: discord.Interaction, 
        title: str, 
        description: str, 
        channel: discord.TextChannel = None,
        color: str = "3498db" # デフォルトは綺麗な青色
    ):
        # カラーコードの変換処理
        try:
            embed_color = int(color.lstrip('#'), 16)
        except ValueError:
            embed_color = discord.Color.blue().value

        # Embedの作成
        # descriptionの中の「\n」という文字を実際の改行に変換します
        embed = discord.Embed(
            title=title,
            description=description.replace("\\n", "\n"),
            color=embed_color
        )

        # 送信先チャンネルの決定（指定がなければ現在のチャンネル）
        target_channel = channel or interaction.channel

        try:
            await target_channel.send(embed=embed)
            await interaction.response.send_message(f"✅ {target_channel.mention} にメッセージを送信しました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ チャンネルにメッセージを送る権限がありません。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SimpleEmbed(bot))
