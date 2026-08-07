import discord
from discord.ext import commands
from discord import app_commands

class AdminGuard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.interaction_check = self.global_admin_check

    async def global_admin_check(self, interaction: discord.Interaction) -> bool:
        # スラッシュコマンドのみ制限をかける
        if interaction.type == discord.InteractionType.application_command:
            if interaction.user.guild_permissions.administrator:
                return True
            await interaction.response.send_message("❌ **権限エラー**: この操作はサーバー管理者のみ可能です。", ephemeral=True)
            return False
        return True

async def setup(bot):
    await bot.add_cog(AdminGuard(bot))
