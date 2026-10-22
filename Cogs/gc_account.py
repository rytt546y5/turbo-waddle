import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

STATE_FILE = Path("gc_account_state.json")
GIF_DIR = Path("gc_account_gifs")
REASONS = ["魔獣戦", "魔神王or最高神戦", "イベント", "ストーリー", "ミッション", "現在周回中"]
DURATIONS = ["すぐやめる", "1時間前後", "未定"]
REPORTS = {
    "login": "グラクロにログインしました",
    "interrupt": "グラクロのプレイを中断しました",
    "end": "グラクロのプレイを終了しました。",
}


def blank_state():
    return {
        "panel_channel_id": None, "panel_message_id": None, "report_channel_id": None,
        "active_user_id": None, "active_username": None, "status": "free",
        "reasons": [], "duration": None,
        "gifs": {"login": None, "interrupt": None, "end": None},
    }


class GCAccountCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.state = blank_state()
        try:
            if STATE_FILE.exists():
                saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.state.update(saved)
                self.state.setdefault("gifs", blank_state()["gifs"])
                for k in ("login", "interrupt", "end"):
                    self.state["gifs"].setdefault(k, None)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[gc_account] 状態ファイル読込エラー: {e}")

    def save(self):
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)

    async def cog_load(self):
        self.bot.add_view(AccountPanel(self))

    def panel_embed(self):
        status = self.state["status"]
        if status == "active":
            desc = f"🔴 **使用中：{self.state.get('active_username') or '不明'}さん**"
        elif status == "interrupted":
            desc = f"🟠 **中断中：{self.state.get('active_username') or '不明'}さん（使用権保持中）**"
        else:
            desc = "🟢 **現在空いています**"
        embed = discord.Embed(title="グラクロ共有アカウント管理",
            description=desc + "\n\nボタンで利用状況を操作してください。中断中は本人が再開または終了するまで他の人は開始できません。",
            color=discord.Color.blurple())
        if status != "free":
            embed.add_field(name="プレイ目的", value="、".join(self.state.get("reasons") or []) or "未選択", inline=False)
            embed.add_field(name="予定時間", value=self.state.get("duration") or "未設定", inline=False)
        embed.set_footer(text="利用状況はBot再起動後も保存されます")
        return embed

    async def refresh_panel(self):
        cid, mid = self.state.get("panel_channel_id"), self.state.get("panel_message_id")
        if not cid or not mid:
            return
        try:
            channel = self.bot.get_channel(int(cid)) or await self.bot.fetch_channel(int(cid))
            msg = await channel.fetch_message(int(mid))
            await msg.edit(embed=self.panel_embed(), view=AccountPanel(self))
        except (discord.HTTPException, AttributeError, TypeError):
            pass

    async def report(self, kind, username, reasons=None, duration=None):
        cid = self.state.get("report_channel_id")
        if not cid:
            return "報告先が未設定です。管理者が /gc-panel を実行してください。"
        try:
            channel = self.bot.get_channel(int(cid)) or await self.bot.fetch_channel(int(cid))
        except discord.HTTPException as e:
            return f"報告先チャンネルを取得できません: {e}"
        embed = discord.Embed(title=f"{username}さんが{REPORTS[kind]}",
            color={"login": discord.Color.green(), "interrupt": discord.Color.orange(), "end": discord.Color.red()}[kind],
            timestamp=datetime.now(timezone.utc))
        if kind == "login":
            embed.add_field(name="プレイ目的", value="、".join(reasons or []) or "未選択", inline=False)
            embed.add_field(name="予定時間", value=duration or "未設定", inline=False)
        files = []
        filename = self.state.get("gifs", {}).get(kind)
        if filename:
            path = GIF_DIR / Path(filename).name
            if path.is_file():
                files.append(discord.File(path, filename=path.name))
                embed.set_image(url=f"attachment://{path.name}")
        try:
            await channel.send(content="@everyone", embed=embed, files=files,
                allowed_mentions=discord.AllowedMentions(everyone=True))
            return None
        except discord.HTTPException as e:
            for f in files:
                f.close()
            return f"報告送信失敗（権限などを確認してください）: {e}"

    async def start(self, interaction, reasons, duration):
        async with self.lock:
            if self.state["status"] != "free":
                await interaction.response.send_message(
                    f"現在は{self.state.get('active_username') or '別の利用者'}さんが利用中または中断中です。",
                    ephemeral=True)
                return
            self.state.update(active_user_id=interaction.user.id,
                active_username=interaction.user.display_name, status="active",
                reasons=reasons, duration=duration)
            self.save()
        err = await self.report("login", interaction.user.display_name, reasons, duration)
        await self.refresh_panel()
        msg = "利用開始を記録しました。"
        if err:
            msg += "\n" + err
        await interaction.response.send_message(msg, ephemeral=True)

    async def operate(self, interaction, action):
        if action == "start":
            if self.state["status"] != "free":
                await interaction.response.send_message(
                    f"現在は{self.state.get('active_username') or '別の利用者'}さんが利用中または中断中です。",
                    ephemeral=True)
                return
            await interaction.response.send_message("利用開始の設定を選んでください。",
                view=StartView(self), ephemeral=True)
            return

        async with self.lock:
            status = self.state["status"]
            if status == "free":
                await interaction.response.send_message("現在、利用中の人はいません。", ephemeral=True)
                return
            if self.state.get("active_user_id") != interaction.user.id:
                await interaction.response.send_message("この操作は現在の利用者本人だけが実行できます。", ephemeral=True)
                return
            if action == "interrupt":
                if status != "active":
                    await interaction.response.send_message("すでに中断中です。", ephemeral=True)
                    return
                self.state["status"] = "interrupted"
                report_kind = "interrupt"
            elif action == "resume":
                if status != "interrupted":
                    await interaction.response.send_message("中断中ではありません。", ephemeral=True)
                    return
                self.state["status"] = "active"
                report_kind = "login"
            elif action == "end":
                self.state.update(status="free", active_user_id=None, active_username=None, reasons=[], duration=None)
                report_kind = "end"
            else:
                await interaction.response.send_message("不明な操作です。", ephemeral=True)
                return
            username = self.state.get("active_username") or interaction.user.display_name
            reasons = list(self.state.get("reasons") or [])
            duration = self.state.get("duration")
            self.save()
        err = await self.report(report_kind, username, reasons, duration)
        await self.refresh_panel()
        text = {"interrupt": "プレイを中断しました。使用権は保持されています。",
                "resume": "プレイを再開しました。", "end": "プレイを終了し、共有アカウントを空き状態にしました。"}[action]
        if err:
            text += "\n" + err
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="gc-panel", description="グラクロ操作パネルを設置し、報告先を設定")
    @app_commands.describe(report_channel="報告を送信するチャンネル")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gc_panel(self, interaction: discord.Interaction, report_channel: discord.TextChannel):
        old_cid, old_mid = self.state.get("panel_channel_id"), self.state.get("panel_message_id")
        self.state["report_channel_id"] = report_channel.id
        message = None
        if old_cid == interaction.channel_id and old_mid:
            try:
                message = await interaction.channel.fetch_message(int(old_mid))
                await message.edit(embed=self.panel_embed(), view=AccountPanel(self))
            except discord.HTTPException:
                message = None
        if message is None:
            message = await interaction.channel.send(embed=self.panel_embed(), view=AccountPanel(self))
        self.state.update(panel_channel_id=interaction.channel_id, panel_message_id=message.id)
        self.save()
        await interaction.response.send_message(f"パネルを設置しました。報告先：{report_channel.mention}", ephemeral=True)

    @app_commands.command(name="gc-gif", description="報告に添付するGIFを設定（添付なしで解除）")
    @app_commands.describe(event="GIFを使う報告の種類", gif="GIFファイル（省略すると解除）")
    @app_commands.choices(event=[
        app_commands.Choice(name="ログイン・再開", value="login"),
        app_commands.Choice(name="中断", value="interrupt"),
        app_commands.Choice(name="終了", value="end")])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gc_gif(self, interaction: discord.Interaction, event: app_commands.Choice[str],
                     gif: discord.Attachment | None = None):
        key = event.value
        if gif is None:
            old = self.state["gifs"].get(key)
            self.state["gifs"][key] = None
            self.save()
            if old:
                (GIF_DIR / Path(old).name).unlink(missing_ok=True)
            await interaction.response.send_message("GIF設定を解除しました。", ephemeral=True)
            return
        if not gif.filename.lower().endswith(".gif"):
            await interaction.response.send_message("拡張子が .gif のファイルを指定してください。", ephemeral=True)
            return
        if gif.size > 8 * 1024 * 1024:
            await interaction.response.send_message("GIFは8MB以下にしてください。", ephemeral=True)
            return
        GIF_DIR.mkdir(parents=True, exist_ok=True)
        dest = GIF_DIR / f"{key}.gif"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(gif.url) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")
                    data = await response.read()
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("ファイルが大きすぎます")
            dest.write_bytes(data)
        except Exception as e:
            await interaction.response.send_message(f"GIF保存に失敗しました: {e}", ephemeral=True)
            return
        self.state["gifs"][key] = dest.name
        self.save()
        await interaction.response.send_message("GIFを保存しました。再起動後も利用できます。", ephemeral=True)

    @gc_panel.error
    @gc_gif.error
    async def command_error(self, interaction, error):
        msg = "このコマンドはサーバー管理権限が必要です。" if isinstance(error, app_commands.MissingPermissions) else f"エラー: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


class StartView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        self.reasons = []
        self.duration = None
        self.add_item(ReasonSelect(self))
        self.add_item(DurationSelect(self))

    @discord.ui.button(label="利用開始を確定", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction, button):
        if not self.duration:
            await interaction.response.send_message("予定時間を1つ選択してください。", ephemeral=True)
            return
        await self.cog.start(interaction, self.reasons, self.duration)
        self.stop()


class ReasonSelect(discord.ui.Select):
    def __init__(self, parent):
        self.parent = parent
        super().__init__(placeholder="プレイ目的（複数選択可）", min_values=0, max_values=len(REASONS),
            options=[discord.SelectOption(label=x, value=x) for x in REASONS], row=0)
    async def callback(self, interaction):
        self.parent.reasons = list(self.values)
        await interaction.response.defer()


class DurationSelect(discord.ui.Select):
    def __init__(self, parent):
        self.parent = parent
        super().__init__(placeholder="予定時間（1つ選択）", min_values=1, max_values=1,
            options=[discord.SelectOption(label=x, value=x) for x in DURATIONS], row=1)
    async def callback(self, interaction):
        self.parent.duration = self.values[0]
        await interaction.response.defer()


class AccountPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="利用開始", style=discord.ButtonStyle.success, custom_id="gc_account:start")
    async def start_btn(self, interaction, button):
        await self.cog.operate(interaction, "start")

    @discord.ui.button(label="中断", style=discord.ButtonStyle.secondary, custom_id="gc_account:interrupt")
    async def interrupt_btn(self, interaction, button):
        await self.cog.operate(interaction, "interrupt")

    @discord.ui.button(label="再開", style=discord.ButtonStyle.primary, custom_id="gc_account:resume")
    async def resume_btn(self, interaction, button):
        await self.cog.operate(interaction, "resume")

    @discord.ui.button(label="終了", style=discord.ButtonStyle.danger, custom_id="gc_account:end")
    async def end_btn(self, interaction, button):
        await self.cog.operate(interaction, "end")


async def setup(bot):
    await bot.add_cog(GCAccountCog(bot))
