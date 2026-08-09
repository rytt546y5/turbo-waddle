import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import io

DATA_FILE = "status_report_data.json"

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
# MODAL (編集画面)
# =====================
class StatusEditModal(ui.Modal):
    def __init__(self, message_id: str, data: dict, bot):
        super().__init__(title="現状報告の全編集")
        self.message_id = message_id
        self.bot = bot
        
        self.p_title = ui.TextInput(label="公開パネルのタイトル", default=data.get("p_title", ""), max_length=100)
        self.p_desc = ui.TextInput(label="公開パネルの説明文", style=discord.TextStyle.long, default=data.get("p_desc", ""), max_length=1000)
        self.h_title = ui.TextInput(label="隠しメッセージのタイトル", default=data.get("hidden_title", ""), max_length=100)
        self.h_content = ui.TextInput(label="隠しメッセージの本文", style=discord.TextStyle.long, default=data.get("hidden_content", ""), max_length=2000)
        
        for item in [self.p_title, self.p_desc, self.h_title, self.h_content]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        all_data = load_data()
        mid = self.message_id
        gid = str(interaction.guild.id)
        
        # 1. データを更新
        all_data[mid] = {
            "p_title": self.p_title.value,
            "p_desc": self.p_desc.value,
            "hidden_title": self.h_title.value,
            "hidden_content": self.h_content.value
        }
        save_data(all_data)

        # 2. 公開パネルを編集
        try:
            target_msg = await interaction.channel.fetch_message(int(mid))
            new_embed = discord.Embed(title=self.p_title.value, description=self.p_desc.value, color=discord.Color.blue())
            new_embed.set_footer(text="Status System")
            await target_msg.edit(embed=new_embed)
        except: pass

        # 3. 【新機能】通知チャンネルへ自動送信
        notify_channel_id = all_data.get(f"notify_{gid}")
        if notify_channel_id:
            notify_channel = interaction.guild.get_channel(int(notify_channel_id))
            if notify_channel:
                # メンションを機能させるために content に入れる
                notice_embed = discord.Embed(
                    title="@everyone", # 枠内のタイトル
                    description=f"-お知らせ-\n進行状況が更新されました。",
                    color=0x67ACC
                )
                # content側に@everyoneを入れることで、実際に通知が飛びます
                await notify_channel.send(content="@everyone", embed=notice_embed)

        await interaction.response.send_message("✅ 更新完了し、通知を送信しました。", ephemeral=True)

# =====================
# VIEW / COG
# =====================
class StatusPanelView(ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.message_id = str(message_id)

    @ui.button(label="詳細な状況を確認する", style=discord.ButtonStyle.success, custom_id="status_report_btn")
    async def show_status(self, interaction: discord.Interaction, button: ui.Button):
        data = load_data()
        panel = data.get(self.message_id)
        if not panel: return await interaction.response.send_message("❌ データなし", ephemeral=True)
        embed = discord.Embed(title=panel["hidden_title"], description=panel["hidden_content"], color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

class StatusReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status_notify_set", description="更新通知を飛ばすチャンネルを設定します")
    @app_commands.default_permissions(administrator=True)
    async def status_notify_set(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_data()
        data[f"notify_{interaction.guild.id}"] = channel.id
        save_data(data)
        await interaction.response.send_message(f"✅ 通知先を {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="status_setup", description="パネルを新規設置")
    @app_commands.default_permissions(administrator=True)
    async def status_setup(self, interaction: discord.Interaction, title: str, description: str):
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        await interaction.response.send_message("⌛ 作成中...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed)
        data = load_data()
        data[str(msg.id)] = {"p_title": title, "p_desc": description, "hidden_title": "未設定", "hidden_content": "未設定"}
        save_data(data)
        await msg.edit(view=StatusPanelView(msg.id))
        await interaction.edit_original_response(content=f"✅ 設置完了。ID: `{msg.id}`")

    @app_commands.command(name="status_edit", description="パネル内容を丸ごと編集")
    @app_commands.default_permissions(administrator=True)
    async def status_edit(self, interaction: discord.Interaction, panel_id: str):
        data = load_data()
        if panel_id not in data: return await interaction.response.send_message("❌ ID不明", ephemeral=True)
        await interaction.response.send_modal(StatusEditModal(panel_id, data[panel_id], self.bot))

async def setup(bot):
    data = load_data()
    for mid in list(data.keys()):
        if mid.isdigit(): bot.add_view(StatusPanelView(mid))
    await bot.add_cog(StatusReport(bot))
