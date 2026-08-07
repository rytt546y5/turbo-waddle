import discord
from discord.ext import commands
import os
from dotenv import load_dotenv # 追加
import asyncio

# === .envファイルから秘密情報を読み込む ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Loading Cogs...")
        if not os.path.exists("./Cogs"):
            os.makedirs("./Cogs")
            
        for file in os.listdir("./Cogs"):
            if file.endswith(".py"):
                await self.load_extension(f"Cogs.{file[:-3]}")
                print(f"Loaded: {file}")
        
        await self.tree.sync()
        print("SYNC DONE")

bot = MyBot()

@bot.event
async def on_ready():
    # 永続View（ボタン）を再起動後に復活させる設定
    # もし status_report.py などで add_view している場合はここでも自動で認識されます
    print(f"✅ 起動成功: {bot.user.name}")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ エラー: .env ファイルに DISCORD_TOKEN が設定されていません。")
