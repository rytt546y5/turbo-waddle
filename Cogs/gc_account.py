import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ==========================================
# 基本設定
# ==========================================

STATE_FILE = Path("gc_account_state.json")
GIF_DIR = Path("gc_account_gifs")

REASONS = [
    "魔獣戦",
    "魔神王or最高神戦",
    "イベント",
    "ストーリー",
    "ミッション",
    "現在周回中",
    "その他",
]

DURATIONS = [
    "すぐやめる",
    "1時間前後",
    "未定",
]

REPORTS = {
    "login": "グラクロにログインしました",
    "interrupt": "グラクロのプレイを中断しました",
    "end": "グラクロのプレイを終了しました。",
}


# ==========================================
# 初期状態
# ==========================================

def blank_state():
    return {
        "panel_channel_id": None,
        "panel_message_id": None,
        "report_channel_id": None,
        "active_user_id": None,
        "active_username": None,
        "status": "free",
        "reasons": [],
        "duration": None,
        "other_detail": None,
        "gifs": {
            "login": None,
            "interrupt": None,
            "end": None,
        },
    }


# ==========================================
# メインCog
# ==========================================

class GCAccountCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.state = blank_state()

        try:
            if STATE_FILE.exists():
                saved = json.loads(
                    STATE_FILE.read_text(encoding="utf-8")
                )

                self.state.update(saved)

                # 古い保存データとの互換性
                self.state.setdefault("other_detail", None)
                self.state.setdefault(
                    "gifs",
                    blank_state()["gifs"]
                )

                for key in ("login", "interrupt", "end"):
                    self.state["gifs"].setdefault(key, None)

        except (OSError, json.JSONDecodeError) as e:
            print(f"[gc_account] 状態ファイル読込エラー: {e}")

    # --------------------------------------
    # 状態保存
    # --------------------------------------

    def save(self):
        tmp = STATE_FILE.with_suffix(".tmp")

        tmp.write_text(
            json.dumps(
                self.state,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(STATE_FILE)

    async def cog_load(self):
        self.bot.add_view(AccountPanel(self))

    # --------------------------------------
    # 操作パネルのEmbed
    # --------------------------------------

    def panel_embed(self):

        status = self.state["status"]

        if status == "active":
            desc = (
                f"🔴 **使用中："
                f"{self.state.get('active_username') or '不明'}さん**"
            )

        elif status == "interrupted":
            desc = (
                f"🟠 **中断中："
                f"{self.state.get('active_username') or '不明'}さん"
                f"（使用権保持中）**"
            )

        else:
            desc = "🟢 **現在空いています**"

        embed = discord.Embed(
            title="グラクロ共有アカウント管理",
            description=(
                desc
                + "\n\n"
                "ボタンで利用状況を操作してください。\n"
                "中断中は本人が再開または終了するまで"
                "他の人は開始できません。"
            ),
            color=discord.Color.blurple(),
        )

        if status != "free":

            reason_text = (
                "、".join(self.state.get("reasons") or [])
                or "未選択"
            )

            other_detail = self.state.get("other_detail")

            if other_detail:
                reason_text += f"（その他：{other_detail}）"

            embed.add_field(
                name="プレイ目的",
                value=reason_text,
                inline=False,
            )

            embed.add_field(
                name="予定時間",
                value=self.state.get("duration") or "未設定",
                inline=False,
            )

        embed.set_footer(
            text="利用状況はBot再起動後も保存されます"
        )

        return embed

    # --------------------------------------
    # 操作パネルの更新
    # --------------------------------------

    async def refresh_panel(self):

        cid = self.state.get("panel_channel_id")
        mid = self.state.get("panel_message_id")

        if not cid or not mid:
            return

        try:
            channel = (
                self.bot.get_channel(int(cid))
                or await self.bot.fetch_channel(int(cid))
            )

            message = await channel.fetch_message(int(mid))

            await message.edit(
                embed=self.panel_embed(),
                view=AccountPanel(self),
            )

        except (
            discord.HTTPException,
            AttributeError,
            TypeError,
        ) as e:
            print(f"[gc_account] パネル更新エラー: {e}")

    # --------------------------------------
    # 報告メッセージ送信
    # --------------------------------------

    async def report(
        self,
        kind,
        username,
        reasons=None,
        duration=None,
        other_detail=None,
        end_note=None,
    ):

        cid = self.state.get("report_channel_id")

        if not cid:
            return (
                "報告先が未設定です。"
                "管理者が /gc-panel を実行してください。"
            )

        try:
            channel = (
                self.bot.get_channel(int(cid))
                or await self.bot.fetch_channel(int(cid))
            )

        except discord.HTTPException as e:
            return f"報告先チャンネルを取得できません: {e}"

        embed = discord.Embed(
            title=f"{username}さんが{REPORTS[kind]}",
            color={
                "login": discord.Color.green(),
                "interrupt": discord.Color.orange(),
                "end": discord.Color.red(),
            }[kind],
            timestamp=datetime.now(timezone.utc),
        )

        # 利用開始・再開時の情報
        if kind == "login":

            reason_text = (
                "、".join(reasons or [])
                or "未選択"
            )

            if other_detail:
                reason_text += f"（その他：{other_detail}）"

            embed.add_field(
                name="プレイ目的",
                value=reason_text,
                inline=False,
            )

            embed.add_field(
                name="予定時間",
                value=duration or "未設定",
                inline=False,
            )

        # 利用終了時の記録
        if kind == "end":

            if reasons:
                reason_text = "、".join(reasons)

                if other_detail:
                    reason_text += f"（その他：{other_detail}）"

                embed.add_field(
                    name="利用目的",
                    value=reason_text,
                    inline=False,
                )

            if end_note:
                embed.add_field(
                    name="今回行ったこと",
                    value=end_note[:1000],
                    inline=False,
                )

        # GIF添付
        files = []

        filename = self.state.get("gifs", {}).get(kind)

        if filename:
            path = GIF_DIR / Path(filename).name

            if path.is_file():
                files.append(
                    discord.File(
                        path,
                        filename=path.name,
                    )
                )

                embed.set_image(
                    url=f"attachment://{path.name}"
                )

        try:
            await channel.send(
                content="@everyone",
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions(
                    everyone=True
                ),
            )

            return None

        except discord.HTTPException as e:

            for file in files:
                file.close()

            return (
                "報告送信失敗（権限などを確認してください）: "
                f"{e}"
            )

    # --------------------------------------
    # 利用開始
    # --------------------------------------

    async def start(
        self,
        interaction,
        reasons,
        duration,
        other_detail=None,
    ):

        async with self.lock:

            if self.state["status"] != "free":

                await interaction.response.send_message(
                    f"現在は"
                    f"{self.state.get('active_username') or '別の利用者'}"
                    "さんが利用中または中断中です。",
                    ephemeral=True,
                )

                return

            self.state.update(
                active_user_id=interaction.user.id,
                active_username=interaction.user.display_name,
                status="active",
                reasons=list(reasons),
                duration=duration,
                other_detail=other_detail,
            )

            self.save()

        err = await self.report(
            "login",
            interaction.user.display_name,
            reasons,
            duration,
            other_detail=other_detail,
        )

        await self.refresh_panel()

        message = "利用開始を記録しました。"

        if err:
            message += "\n" + err

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    # --------------------------------------
    # 利用終了の確定
    # --------------------------------------

    async def complete_end(
        self,
        interaction,
        end_note=None,
    ):

        async with self.lock:

            if self.state["status"] == "free":

                await interaction.response.send_message(
                    "現在、利用中の人はいません。",
                    ephemeral=True,
                )

                return

            if (
                self.state.get("active_user_id")
                != interaction.user.id
            ):

                await interaction.response.send_message(
                    "この操作は現在の利用者本人だけが実行できます。",
                    ephemeral=True,
                )

                return

            username = (
                self.state.get("active_username")
                or interaction.user.display_name
            )

            reasons = list(
                self.state.get("reasons") or []
            )

            duration = self.state.get("duration")
            other_detail = self.state.get("other_detail")

            self.state.update(
                status="free",
                active_user_id=None,
                active_username=None,
                reasons=[],
                duration=None,
                other_detail=None,
            )

            self.save()

        err = await self.report(
            "end",
            username,
            reasons,
            duration,
            other_detail=other_detail,
            end_note=end_note,
        )

        await self.refresh_panel()

        message = (
            "プレイを終了し、共有アカウントを空き状態にしました。"
        )

        if err:
            message += "\n" + err

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    # --------------------------------------
    # 中断・再開・終了の操作
    # --------------------------------------

    async def operate(self, interaction, action):

        # 終了時は記録入力フォームを表示
        if action == "end":

            if self.state["status"] == "free":

                await interaction.response.send_message(
                    "現在、利用中の人はいません。",
                    ephemeral=True,
                )

                return

            if (
                self.state.get("active_user_id")
                != interaction.user.id
            ):

                await interaction.response.send_message(
                    "この操作は現在の利用者本人だけが実行できます。",
                    ephemeral=True,
                )

                return

            await interaction.response.send_modal(
                EndNoteModal(self)
            )

            return

        # 利用開始
        if action == "start":

            if self.state["status"] != "free":

                await interaction.response.send_message(
                    f"現在は"
                    f"{self.state.get('active_username') or '別の利用者'}"
                    "さんが利用中または中断中です。",
                    ephemeral=True,
                )

                return

            await interaction.response.send_message(
                "利用開始の設定を選んでください。",
                view=StartView(self),
                ephemeral=True,
            )

            return

        async with self.lock:

            status = self.state["status"]

            if status == "free":

                await interaction.response.send_message(
                    "現在、利用中の人はいません。",
                    ephemeral=True,
                )

                return

            if (
                self.state.get("active_user_id")
                != interaction.user.id
            ):

                await interaction.response.send_message(
                    "この操作は現在の利用者本人だけが実行できます。",
                    ephemeral=True,
                )

                return

            if action == "interrupt":

                if status != "active":

                    await interaction.response.send_message(
                        "すでに中断中です。",
                        ephemeral=True,
                    )

                    return

                self.state["status"] = "interrupted"
                report_kind = "interrupt"

            elif action == "resume":

                if status != "interrupted":

                    await interaction.response.send_message(
                        "中断中ではありません。",
                        ephemeral=True,
                    )

                    return

                self.state["status"] = "active"
                report_kind = "login"

            else:

                await interaction.response.send_message(
                    "不明な操作です。",
                    ephemeral=True,
                )

                return

            username = (
                self.state.get("active_username")
                or interaction.user.display_name
            )

            reasons = list(
                self.state.get("reasons") or []
            )

            duration = self.state.get("duration")
            other_detail = self.state.get("other_detail")

            self.save()

        err = await self.report(
            report_kind,
            username,
            reasons,
            duration,
            other_detail=other_detail,
        )

        await self.refresh_panel()

        if action == "interrupt":
            message = (
                "プレイを中断しました。"
                "使用権は保持されています。"
            )

        else:
            message = "プレイを再開しました。"

        if err:
            message += "\n" + err

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    # --------------------------------------
    # パネル設置・報告先設定
    # --------------------------------------

    @app_commands.command(
        name="gc-panel",
        description="グラクロ操作パネルを設置し、報告先を設定",
    )
    @app_commands.describe(
        report_channel="報告を送信するチャンネル"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def gc_panel(
        self,
        interaction: discord.Interaction,
        report_channel: discord.TextChannel,
    ):

        old_cid = self.state.get("panel_channel_id")
        old_mid = self.state.get("panel_message_id")

        self.state["report_channel_id"] = report_channel.id

        message = None

        if (
            old_cid == interaction.channel_id
            and old_mid
        ):

            try:
                message = await interaction.channel.fetch_message(
                    int(old_mid)
                )

                await message.edit(
                    embed=self.panel_embed(),
                    view=AccountPanel(self),
                )

            except discord.HTTPException:
                message = None

        if message is None:

            message = await interaction.channel.send(
                embed=self.panel_embed(),
                view=AccountPanel(self),
            )

        self.state.update(
            panel_channel_id=interaction.channel_id,
            panel_message_id=message.id,
        )

        self.save()

        await interaction.response.send_message(
            f"パネルを設置しました。"
            f"報告先：{report_channel.mention}",
            ephemeral=True,
        )

    # --------------------------------------
    # GIF設定
    # --------------------------------------

    @app_commands.command(
        name="gc-gif",
        description="報告に添付するGIFを設定（添付なしで解除）",
    )
    @app_commands.describe(
        event="GIFを使う報告の種類",
        gif="GIFファイル（省略すると解除）",
    )
    @app_commands.choices(
        event=[
            app_commands.Choice(
                name="ログイン・再開",
                value="login",
            ),
            app_commands.Choice(
                name="中断",
                value="interrupt",
            ),
            app_commands.Choice(
                name="終了",
                value="end",
            ),
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def gc_gif(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
        gif: discord.Attachment | None = None,
    ):

        key = event.value

        # GIF設定解除
        if gif is None:

            old = self.state["gifs"].get(key)
            self.state["gifs"][key] = None

            self.save()

            if old:
                (
                    GIF_DIR / Path(old).name
                ).unlink(missing_ok=True)

            await interaction.response.send_message(
                "GIF設定を解除しました。",
                ephemeral=True,
            )

            return

        # GIF形式チェック
        if not gif.filename.lower().endswith(".gif"):

            await interaction.response.send_message(
                "拡張子が .gif のファイルを指定してください。",
                ephemeral=True,
            )

            return

        if gif.size > 8 * 1024 * 1024:

            await interaction.response.send_message(
                "GIFは8MB以下にしてください。",
                ephemeral=True,
            )

            return

        GIF_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        dest = GIF_DIR / f"{key}.gif"

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(gif.url) as response:

                    if response.status != 200:
                        raise RuntimeError(
                            f"HTTP {response.status}"
                        )

                    data = await response.read()

            if len(data) > 8 * 1024 * 1024:
                raise ValueError(
                    "ファイルが大きすぎます"
                )

            dest.write_bytes(data)

        except Exception as e:

            await interaction.response.send_message(
                f"GIF保存に失敗しました: {e}",
                ephemeral=True,
            )

            return

        self.state["gifs"][key] = dest.name
        self.save()

        await interaction.response.send_message(
            "GIFを保存しました。再起動後も利用できます。",
            ephemeral=True,
        )

    # --------------------------------------
    # コマンドエラー処理
    # --------------------------------------

    @gc_panel.error
    @gc_gif.error
    async def command_error(
        self,
        interaction,
        error,
    ):

        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):

            message = (
                "このコマンドはサーバー管理権限が必要です。"
            )

        else:
            message = f"エラー: {error}"

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True,
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


# ==========================================
# 利用開始時の設定画面
# ==========================================

class StartView(discord.ui.View):

    def __init__(self, cog):

        super().__init__(timeout=300)

        self.cog = cog
        self.reasons = []
        self.duration = None

        self.add_item(ReasonSelect(self))
        self.add_item(DurationSelect(self))

    @discord.ui.button(
        label="利用開始を確定",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def confirm(
        self,
        interaction,
        button,
    ):

        if not self.duration:

            await interaction.response.send_message(
                "予定時間を1つ選択してください。",
                ephemeral=True,
            )

            return

        # その他を選んでいる場合は詳細入力へ
        if "その他" in self.reasons:

            await interaction.response.send_modal(
                OtherPurposeModal(self)
            )

            return

        await self.cog.start(
            interaction,
            self.reasons,
            self.duration,
        )

        self.stop()


# ==========================================
# その他の目的を入力するフォーム
# ==========================================

class OtherPurposeModal(
    discord.ui.Modal,
    title="その他のプレイ目的",
):

    detail = discord.ui.TextInput(
        label="具体的な内容",
        placeholder=(
            "例：キャラクターの装備変更、"
            "必殺技レベルの確認、ボックス整理、"
            "チーム編成の変更"
        ),
        min_length=1,
        max_length=200,
        required=True,
    )

    def __init__(self, start_view):

        super().__init__()

        self.start_view = start_view

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        detail = str(self.detail.value).strip()

        if not detail:

            await interaction.response.send_message(
                "その他の内容を入力してください。",
                ephemeral=True,
            )

            return

        await self.start_view.cog.start(
            interaction,
            self.start_view.reasons,
            self.start_view.duration,
            other_detail=detail,
        )

        self.start_view.stop()


# ==========================================
# 利用終了時の記録フォーム
# ==========================================

class EndNoteModal(
    discord.ui.Modal,
    title="利用終了の記録",
):

    note = discord.ui.TextInput(
        label="今回行ったこと（任意）",
        placeholder=(
            "例：装備変更、必殺技レベル確認、"
            "ボックス整理など。空欄でもOK"
        ),
        max_length=500,
        required=False,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, cog):

        super().__init__()

        self.cog = cog

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        note = str(self.note.value).strip() or None

        await self.cog.complete_end(
            interaction,
            end_note=note,
        )


# ==========================================
# プレイ目的の選択欄
# ==========================================

class ReasonSelect(discord.ui.Select):

    def __init__(self, start_view):

        self.start_view = start_view

        super().__init__(
            placeholder="プレイ目的（複数選択可）",
            min_values=0,
            max_values=len(REASONS),
            options=[
                discord.SelectOption(
                    label=reason,
                    value=reason,
                )
                for reason in REASONS
            ],
            row=0,
        )

    async def callback(self, interaction):

        self.start_view.reasons = list(self.values)

        await interaction.response.defer()


# ==========================================
# 予定時間の選択欄
# ==========================================

class DurationSelect(discord.ui.Select):

    def __init__(self, start_view):

        self.start_view = start_view

        super().__init__(
            placeholder="予定時間（1つ選択）",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=duration,
                    value=duration,
                )
                for duration in DURATIONS
            ],
            row=1,
        )

    async def callback(self, interaction):

        self.start_view.duration = self.values[0]

        await interaction.response.defer()


# ==========================================
# メイン操作パネル
# ==========================================

class AccountPanel(discord.ui.View):

    def __init__(self, cog):

        super().__init__(timeout=None)

        self.cog = cog

    @discord.ui.button(
        label="利用開始",
        style=discord.ButtonStyle.success,
        custom_id="gc_account:start",
    )
    async def start_btn(
        self,
        interaction,
        button,
    ):

        await self.cog.operate(
            interaction,
            "start",
        )

    @discord.ui.button(
        label="中断",
        style=discord.ButtonStyle.secondary,
        custom_id="gc_account:interrupt",
    )
    async def interrupt_btn(
        self,
        interaction,
        button,
    ):

        await self.cog.operate(
            interaction,
            "interrupt",
        )

    @discord.ui.button(
        label="再開",
        style=discord.ButtonStyle.primary,
        custom_id="gc_account:resume",
    )
    async def resume_btn(
        self,
        interaction,
        button,
    ):

        await self.cog.operate(
            interaction,
            "resume",
        )

    @discord.ui.button(
        label="終了",
        style=discord.ButtonStyle.danger,
        custom_id="gc_account:end",
    )
    async def end_btn(
        self,
        interaction,
        button,
    ):

        await self.cog.operate(
            interaction,
            "end",
        )


# ==========================================
# Cog読み込み
# ==========================================

async def setup(bot):
    await bot.add_cog(
        GCAccountCog(bot)
    )
