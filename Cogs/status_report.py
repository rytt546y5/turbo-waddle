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
    def __init__(self, message_id: str, data: dict):
        super().__init__(title="現状報告の全編集")
        self.message_id = message_id
        
        # 公開パネルのタイトル
        self.p_title = ui.TextInput(label="公開パネルのタイトル", default=data.get("p_title", ""), max_length=100)
        # 公開パネルの説明
        self.p_desc = ui.TextInput(label="公開パネルの説明文", style=discord.TextStyle.long, default=data.get("p_desc", ""), max_length=1000)
        # 隠しメッセージのタイトル（絵文字不可）
        self.h_title = ui.TextInput(label="隠しメッセージのタイトル(絵文字不可)", default=data.get("hidden_title", ""), max_length=100)
        # 隠しメッセージの本文（絵文字OK！）
        self.h_content = ui.TextInput(label="隠しメッセージの本文(絵文字OK)", style=discord.TextStyle.long, default=data.get("hidden_content", ""), max_length=2000)
        
        for item in [self.p_title, self.p_desc, self.h_title, self.h_content]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        mid = self.message_id
        
        # データを更新
        data[mid] = {
            "p_title": self.p_title.value,
            "p_desc": self.p_desc.value,
            "hidden_title": self.h_title.value,
            "hidden_content": self.h_content.value
        }
        save_data(data)

        # 【重要】チャンネルに見えている「元のパネル」を即座に書き換える
        try:
            target_msg = await interaction.channel.fetch_message(int(mid))
            new_embed = discord.Embed(title=self.p_title.value, description=self.p_desc.value, color=discord.Color.blue())
            new_embed.set_footer(text="Status System (Updated)")
            await target_msg.edit(embed=new_embed)
            await interaction.response.send_message("✅ 公開パネルと隠し内容の両方を更新しました。", ephemeral=True)
        except:
            await interaction.response.send_message("✅ 隠し内容は更新しましたが、元のメッセージが見つかりませんでした。", ephemeral=True)

# =====================
# VIEW
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

# =====================
# COG
# =====================
class StatusReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status_setup", description="現状報告パネルを新規設置")
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
        await interaction.response.send_modal(StatusEditModal(panel_id, data[panel_id]))

async def setup(bot):
    data = load_data()
    for mid in data.keys(): bot.add_view(StatusPanelView(mid))
    await bot.add_cog(StatusReport(bot))
