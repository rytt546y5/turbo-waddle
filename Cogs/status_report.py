import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import io

# =====================
# DATA MANAGEMENT
# =====================
DATA_FILE = "status_report_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# =====================
# MODAL (編集用画面)
# =====================
class StatusEditModal(ui.Modal):
    def __init__(self, message_id: str, current_title: str, current_content: str):
        super().__init__(title="現状報告の中身を編集")
        self.message_id = message_id
        
        self.title_input = ui.TextInput(
            label="自分だけに表示されるEmbedのタイトル",
            default=current_title,
            placeholder="例：現在の取引状況について",
            max_length=100
        )
        self.content_input = ui.TextInput(
            label="自分だけに表示される本文（絵文字使用可）",
            style=discord.TextStyle.long,
            default=current_content,
            placeholder="例：現在スタッフが少ないため、対応に5分ほど頂いております。 <:emoji_name:id>",
            max_length=2000
        )
        self.add_item(self.title_input)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        if self.message_id in data:
            data[self.message_id]["hidden_title"] = self.title_input.value
            data[self.message_id]["hidden_content"] = self.content_input.value
            save_data(data)
            await interaction.response.send_message(f"✅ パネル（ID: {self.message_id}）の内容を更新しました。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ データが見つかりませんでした。", ephemeral=True)

# =====================
# VIEW (永続ボタン)
# =====================
class StatusPanelView(ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=None) # 永続化
        self.message_id = str(message_id)

    @ui.button(label="詳細な状況を確認する", style=discord.ButtonStyle.success, custom_id="status_report_btn")
    async def show_status(self, interaction: discord.Interaction, button: ui.Button):
        data = load_data()
        panel_info = data.get(self.message_id)

        if not panel_info:
            return await interaction.response.send_message("❌ この報告パネルのデータは存在しません。", ephemeral=True)

        # 自分にだけ見える（Ephemeral）Embed
        embed = discord.Embed(
            title=panel_info["hidden_title"],
            description=panel_info["hidden_content"],
            color=discord.Color.green()
        )
        embed.set_footer(text="※このメッセージはあなただけに表示されています。")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =====================
# COG (メイン機能)
# =====================
class StatusReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status_setup", description="現状報告パネルを新規設置します（管理者のみ）")
    @app_commands.describe(
        public_title="チャンネルに見えるタイトルの設定",
        public_desc="チャンネルに見える説明文の設定",
        hidden_title="ボタンを押した後に見えるタイトルの初期値",
        hidden_content="ボタンを押した後に見える内容の初期値"
    )
    @app_commands.default_permissions(administrator=True)
    async def status_setup(
        self, interaction: discord.Interaction, 
        public_title: str, 
        public_desc: str, 
        hidden_title: str, 
        hidden_content: str
    ):
        # 設置するEmbed
        embed = discord.Embed(
            title=public_title,
            description=f"{public_desc}\n\n下のボタンから詳細な現状を確認できます。",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Status System")

        await interaction.response.send_message("⌛ パネルを生成中...", ephemeral=True)
        
        # チャンネルにパネルを送信
        msg = await interaction.channel.send(embed=embed)
        
        # データを保存
        data = load_data()
        data[str(msg.id)] = {
            "hidden_title": hidden_title,
            "hidden_content": hidden_content
        }
        save_data(data)

        # 正式なView（メッセージID紐付け）に更新
        view = StatusPanelView(msg.id)
        await msg.edit(view=view)
        
        await interaction.edit_original_response(content=f"✅ 設置完了しました。\n**パネルID:** `{msg.id}`\n編集時はこのIDを使用してください。")

    @app_commands.command(name="status_edit", description="設置済みパネルの『自分だけにしか見えない内容』を編集します")
    @app_commands.describe(panel_id="編集したいパネルのメッセージID（またはパネルID）")
    @app_commands.default_permissions(administrator=True)
    async def status_edit(self, interaction: discord.Interaction, panel_id: str):
        data = load_data()
        panel_info = data.get(panel_id)

        if not panel_info:
            return await interaction.response.send_message("❌ そのIDのパネルは見つかりませんでした。", ephemeral=True)

        # 編集用Modalを出す
        await interaction.response.send_modal(
            StatusEditModal(panel_id, panel_info["hidden_title"], panel_info["hidden_content"])
        )

async def setup(bot):
    # サーバー起動時に、保存されている全パネルのViewを有効化する
    data = load_data()
    for msg_id in data.keys():
        bot.add_view(StatusPanelView(msg_id))
        
    await bot.add_cog(StatusReport(bot))
