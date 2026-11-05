import os
import json
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from storage import Store
from web_dashboard import start_web_dashboard

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
MAIN_OWNER_ID = int(os.getenv("MAIN_OWNER_ID", "0"))
PREFIX = os.getenv("PREFIX", "$")
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")
WEB_SECRET = os.getenv("WEB_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler()
    ],
)
log = logging.getLogger("tag-manager")
store = Store()

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


def is_main_owner(user_id: int) -> bool:
    return user_id == MAIN_OWNER_ID


def is_owner(user_id: int) -> bool:
    return is_main_owner(user_id) or store.is_owner(user_id)


def owner_check():
    async def predicate(ctx):
        if not is_owner(ctx.author.id):
            raise commands.CheckFailure("هذا الأمر مخصص لأونرات البوت.")
        return True
    return commands.check(predicate)


def main_owner_check():
    async def predicate(ctx):
        if not is_main_owner(ctx.author.id):
            raise commands.CheckFailure("هذا الأمر مخصص لمالك البوت الأساسي.")
        return True
    return commands.check(predicate)


def make_embed(title: str, description: str = "", color: discord.Color = discord.Color.blurple()):
    e = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    e.set_footer(text="TAG MANAGER")
    return e


class TagModal(discord.ui.Modal, title="تعديل تاق السيرفر"):
    tag = discord.ui.TextInput(
        label="نص التاق",
        placeholder="مثال: S7",
        min_length=1,
        max_length=4,
        required=True,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        store.set_guild(self.guild_id, tag=str(self.tag.value).strip())
        await interaction.response.send_message(
            embed=make_embed("تم حفظ التاق", f"التاق الحالي: `{discord.utils.escape_markdown(str(self.tag.value).strip())}`", discord.Color.green()),
            ephemeral=True,
        )


class GuildConfigSelect(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild

        roles = [r for r in guild.roles if not r.is_default and not r.managed and r < guild.me.top_role]
        self.add_item(RolePicker(roles))
        self.add_item(LogChannelPicker([c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_owner(interaction.user.id):
            await interaction.response.send_message("ليس لديك صلاحية استخدام هذه اللوحة.", ephemeral=True)
            return False
        return True


class RolePicker(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=r.name[:100], value=str(r.id)) for r in roles[:25]]
        if not options:
            options = [discord.SelectOption(label="لا توجد رتب متاحة", value="none")]
        super().__init__(placeholder="اختر الرتبة المرتبطة بالتاق", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("لا توجد رتبة متاحة للاختيار.", ephemeral=True)
        role_id = int(self.values[0])
        store.set_guild(interaction.guild_id, role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(embed=make_embed("تم تحديث الرتبة", f"الرتبة المحددة: {role.mention}", discord.Color.green()), ephemeral=True)


class LogChannelPicker(discord.ui.Select):
    def __init__(self, channels):
        options = [discord.SelectOption(label=f"#{c.name}"[:100], value=str(c.id)) for c in channels[:25]]
        if not options:
            options = [discord.SelectOption(label="لا توجد قنوات متاحة", value="none")]
        super().__init__(placeholder="اختر روم اللوق", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("لا توجد قناة متاحة للاختيار.", ephemeral=True)
        channel_id = int(self.values[0])
        store.set_guild(interaction.guild_id, log_channel_id=channel_id)
        channel = interaction.guild.get_channel(channel_id)
        await interaction.response.send_message(embed=make_embed("تم تحديث روم اللوق", f"القناة المحددة: {channel.mention}", discord.Color.green()), ephemeral=True)


class MainPanelView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_owner(interaction.user.id):
            await interaction.response.send_message("ليس لديك صلاحية استخدام هذه اللوحة.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="تعديل التاق", style=discord.ButtonStyle.primary)
    async def edit_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TagModal(self.guild.id))

    @discord.ui.button(label="إعداد الرتبة واللوق", style=discord.ButtonStyle.secondary)
    async def role_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=make_embed("إعداد الرتبة وروم اللوق", "استخدم القائمتين لتحديد الرتبة والقناة."),
            view=GuildConfigSelect(self.guild),
            ephemeral=True,
        )

    @discord.ui.button(label="عرض الإعدادات", style=discord.ButtonStyle.success)
    async def show_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = store.get_guild(self.guild.id)
        role = self.guild.get_role(data.get("role_id")) if data.get("role_id") else None
        channel = self.guild.get_channel(data.get("log_channel_id")) if data.get("log_channel_id") else None
        embed = make_embed("إعدادات السيرفر")
        embed.add_field(name="التاق", value=f"`{data.get('tag') or 'غير محدد'}`", inline=True)
        embed.add_field(name="الرتبة", value=role.mention if role else "غير محددة", inline=True)
        embed.add_field(name="روم اللوق", value=channel.mention if channel else "غير محدد", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    log.info("Connected as %s (%s)", bot.user, bot.user.id)
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}help"))
    if not getattr(bot, "web_started", False):
        await start_web_dashboard(bot, store, MAIN_OWNER_ID, WEB_HOST, WEB_PORT, WEB_PASSWORD, WEB_SECRET)
        bot.web_started = True
    if not periodic_tag_scan.is_running():
        periodic_tag_scan.start()


@bot.command(name="help")
async def help_command(ctx):
    embed = make_embed(
        "TAG MANAGER | قائمة الأوامر",
        "بوت إدارة ومراقبة Server Tag.\nاختر لوحة التحكم داخل ديسكورد أو استخدم الأوامر النصية.",
    )
    embed.add_field(name="أوامر عامة", value=f"`{PREFIX}help` عرض المساعدة\n`{PREFIX}panel` فتح لوحة ديسكورد", inline=False)
    embed.add_field(name="إعدادات السيرفر", value=f"`{PREFIX}settag TAG` تحديد التاق\n`{PREFIX}setrole @Role` تحديد الرتبة\n`{PREFIX}setlog #channel` تحديد روم اللوق\n`{PREFIX}config` عرض الإعدادات", inline=False)
    embed.add_field(name="إدارة الأونرات", value=f"`{PREFIX}owners` عرض الأونرات\n`{PREFIX}owner add @user` إضافة أونر\n`{PREFIX}owner remove @user` إزالة أونر", inline=False)
    embed.add_field(name="المزامنة", value=f"`{PREFIX}sync` مزامنة أفضل جهد للأعضاء المتاحين", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="panel", aliases=["dashboard"])
@owner_check()
async def panel_command(ctx):
    embed = make_embed("لوحة تحكم TAG MANAGER", "هذه لوحة تحكم تفاعلية داخل Discord.\nاختر الإجراء من الأزرار بالأسفل.")
    await ctx.send(embed=embed, view=MainPanelView(ctx.guild))


@bot.command(name="settag")
@owner_check()
async def set_tag(ctx, *, tag: str):
    tag = tag.strip()
    if not 1 <= len(tag) <= 4:
        return await ctx.reply("يجب أن يكون التاق من حرف إلى 4 أحرف.")
    store.set_guild(ctx.guild.id, tag=tag)
    await ctx.reply(embed=make_embed("تم حفظ التاق", f"التاق المحدد: `{discord.utils.escape_markdown(tag)}`", discord.Color.green()))


@bot.command(name="setrole")
@owner_check()
async def set_role(ctx, role: discord.Role):
    # discord.py Role.is_default is a method; calling it avoids treating
    # the bound method itself as truthy for every role.
    if role.is_default() or role.managed:
        return await ctx.reply("اختر رتبة عادية يمكن للبوت إدارتها.")
    if ctx.guild.me.top_role <= role:
        return await ctx.reply("ارفع رتبة البوت فوق الرتبة المحددة.")
    store.set_guild(ctx.guild.id, role_id=role.id)
    await ctx.reply(embed=make_embed("تم تحديد الرتبة", role.mention, discord.Color.green()))


@bot.command(name="setlog")
@owner_check()
async def set_log(ctx, channel: discord.TextChannel):
    store.set_guild(ctx.guild.id, log_channel_id=channel.id)
    await ctx.reply(embed=make_embed("تم تحديد روم اللوق", channel.mention, discord.Color.green()))


@bot.command(name="config")
@owner_check()
async def config_command(ctx):
    data = store.get_guild(ctx.guild.id)
    role = ctx.guild.get_role(data.get("role_id")) if data.get("role_id") else None
    channel = ctx.guild.get_channel(data.get("log_channel_id")) if data.get("log_channel_id") else None
    embed = make_embed("إعدادات السيرفر")
    embed.add_field(name="التاق", value=f"`{data.get('tag') or 'غير محدد'}`", inline=True)
    embed.add_field(name="الرتبة", value=role.mention if role else "غير محددة", inline=True)
    embed.add_field(name="اللوق", value=channel.mention if channel else "غير محدد", inline=True)
    await ctx.reply(embed=embed)


@bot.command(name="owners")
@main_owner_check()
async def owners_command(ctx):
    ids = [MAIN_OWNER_ID] + store.list_owners()
    lines = [f"<@{uid}> (`{uid}`)" for uid in ids if uid]
    await ctx.reply(embed=make_embed("قائمة أونرات البوت", "\n".join(lines) or "لا يوجد أونرات."))


@bot.group(name="owner", invoke_without_command=True)
@main_owner_check()
async def owner_group(ctx):
    await ctx.reply(f"الاستخدام: `{PREFIX}owner add @user` أو `{PREFIX}owner remove @user`")


@owner_group.command(name="add")
@main_owner_check()
async def owner_add(ctx, user: discord.User):
    if user.id == MAIN_OWNER_ID:
        return await ctx.reply("هذا هو مالك البوت الأساسي بالفعل.")
    if store.is_owner(user.id):
        return await ctx.reply("هذا المستخدم موجود بالفعل في قائمة الأونرات.")
    store.add_owner(user.id)
    await ctx.reply(embed=make_embed("تمت إضافة أونر", f"{user.mention} (`{user.id}`)", discord.Color.green()))


@owner_group.command(name="remove")
@main_owner_check()
async def owner_remove(ctx, user: discord.User):
    if user.id == MAIN_OWNER_ID:
        return await ctx.reply("لا يمكن إزالة مالك البوت الأساسي.")
    if not store.is_owner(user.id):
        return await ctx.reply("هذا المستخدم ليس ضمن قائمة الأونرات.")
    store.remove_owner(user.id)
    await ctx.reply(embed=make_embed("تمت إزالة أونر", f"{user.mention} (`{user.id}`)", discord.Color.orange()))


async def apply_role(guild: discord.Guild, member: discord.Member, added: bool):
    data = store.get_guild(guild.id)
    role = guild.get_role(data.get("role_id")) if data.get("role_id") else None
    if not role:
        return "role_not_configured"
    try:
        if added and role not in member.roles:
            await member.add_roles(role, reason="Server tag detected")
        elif not added and role in member.roles:
            await member.remove_roles(role, reason="Server tag removed")
        return "success"
    except discord.Forbidden:
        log.warning("Cannot manage role %s in guild %s", role.id, guild.id)
        return "missing_permissions"
    except discord.HTTPException:
        log.exception("Role update failed")
        return "api_error"


async def send_log(guild: discord.Guild, member: discord.Member, added: bool, tag: str, result: str):
    data = store.get_guild(guild.id)
    channel = guild.get_channel(data.get("log_channel_id")) if data.get("log_channel_id") else None
    event = "تمت إضافة التاق" if added else "تمت إزالة التاق"
    embed = make_embed(event, color=discord.Color.green() if added else discord.Color.orange())
    embed.add_field(name="العضو", value=f"{member.mention}\n`{member}`", inline=True)
    embed.add_field(name="التاق", value=f"`{discord.utils.escape_markdown(tag or 'غير معروف')}`", inline=True)
    embed.add_field(name="نتيجة الرتبة", value=result, inline=True)
    embed.add_field(name="معرف العضو", value=f"`{member.id}`", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    store.add_log({
        "guild_id": guild.id,
        "member_id": member.id,
        "username": str(member),
        "event": "TAG_ADDED" if added else "TAG_REMOVED",
        "tag": tag,
        "result": result,
        "timestamp": discord.utils.utcnow().isoformat(),
    })
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            log.warning("Missing send permission in log channel %s", channel.id)


async def scan_guild_tags(guild: discord.Guild):
    """
    Full best-effort scan using Discord's official List Guild Members endpoint.
    The endpoint returns each member's User object; when `primary_guild` is
    present, it can be compared with the configured Server Tag.

    Missing `primary_guild` is treated as unknown, never as tag removal.
    """
    settings = store.get_guild(guild.id)
    configured_tag = settings.get("tag")
    role_id = settings.get("role_id")
    if not configured_tag or not role_id:
        return {"checked": 0, "changed": 0, "unknown": 0, "pages": 0, "skipped": "not_configured"}

    role = guild.get_role(int(role_id))
    if role is None:
        return {"checked": 0, "changed": 0, "unknown": 0, "pages": 0, "skipped": "role_missing"}

    checked = changed = unknown = pages = 0
    after = "0"
    route = discord.http.Route("GET", "/guilds/{guild_id}/members", guild_id=guild.id)

    while True:
        try:
            batch = await bot.http.request(route, params={"limit": 1000, "after": after})
        except discord.HTTPException as exc:
            log.warning("Member scan failed for guild %s: %s", guild.id, exc)
            break

        if not isinstance(batch, list) or not batch:
            break

        pages += 1
        for member_data in batch:
            user_data = member_data.get("user") or {}
            user_id = user_data.get("id")
            if not user_id:
                unknown += 1
                continue

            # The field is optional in the API response. Missing means unknown,
            # not proof that the member removed their tag.
            if "primary_guild" not in user_data:
                unknown += 1
                continue

            primary = user_data.get("primary_guild")
            if primary is None:
                matches = False
                observed_tag = configured_tag
            elif isinstance(primary, dict):
                observed_tag = primary.get("tag") or configured_tag
                matches = (
                    primary.get("identity_enabled") is True
                    and str(primary.get("identity_guild_id")) == str(guild.id)
                    and primary.get("tag") == configured_tag
                )
            else:
                unknown += 1
                continue

            checked += 1
            member_id = int(user_id)
            member = guild.get_member(member_id)
            if member is None:
                try:
                    member = await guild.fetch_member(member_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    unknown += 1
                    continue

            has_role = role in member.roles
            store.set_member_tag(guild.id, member_id, matches)

            # Enforce the configured role based on the currently observed tag.
            if matches != has_role:
                result = await apply_role(guild, member, matches)
                if result == "success":
                    changed += 1
                    await send_log(guild, member, matches, observed_tag or configured_tag, result)

        after = str(batch[-1].get("user", {}).get("id", ""))
        if not after or len(batch) < 1000:
            break

    return {"checked": checked, "changed": changed, "unknown": unknown, "pages": pages}


@tasks.loop(seconds=30)
async def periodic_tag_scan():
    for guild in list(bot.guilds):
        settings = store.get_guild(guild.id)
        if settings.get("tag") and settings.get("role_id"):
            result = await scan_guild_tags(guild)
            log.info(
                "Tag scan guild=%s checked=%s changed=%s unknown=%s pages=%s",
                guild.id, result["checked"], result["changed"],
                result["unknown"], result["pages"]
            )


@periodic_tag_scan.before_loop
async def before_periodic_tag_scan():
    await bot.wait_until_ready()


@bot.event
async def on_socket_response(payload):
    """
    Best-effort listener for Gateway member updates.

    Important:
    - The public Discord bot API does not guarantee that Server Tag / primary_guild
      changes are sent to bots as GUILD_MEMBER_UPDATE events.
    - If the `primary_guild` key is absent, this update does not contain enough
      information to decide whether the member has/removed the tag.
    - If the key is explicitly present with null, it means there is no primary guild
      in this payload, so a previously tracked tag can be removed.
    """
    if not isinstance(payload, dict) or payload.get("t") != "GUILD_MEMBER_UPDATE":
        return

    data = payload.get("d") or {}
    guild_id = data.get("guild_id")
    user_data = data.get("user") or {}

    # Do not interpret an omitted field as tag removal: Discord can send partial data.
    if not guild_id or not user_data.get("id") or "primary_guild" not in user_data:
        return

    try:
        guild_id = int(guild_id)
        member_id = int(user_data["id"])
    except (TypeError, ValueError):
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    try:
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return

    settings = store.get_guild(guild.id)
    configured_tag = settings.get("tag")
    primary = user_data.get("primary_guild")

    if primary is None:
        matches = False
        observed_tag = configured_tag or "غير معروف"
    elif isinstance(primary, dict):
        identity_guild_id = primary.get("identity_guild_id")
        observed_tag = primary.get("tag") or configured_tag or "غير معروف"
        matches = (
            primary.get("identity_enabled") is True
            and str(identity_guild_id) == str(guild.id)
            and (not configured_tag or primary.get("tag") == configured_tag)
        )
    else:
        # Unexpected payload shape; do not change roles based on uncertain data.
        return

    old_state = store.has_member_tag(guild.id, member.id)
    if matches == old_state:
        return

    store.set_member_tag(guild.id, member.id, matches)
    result = await apply_role(guild, member, matches)
    await send_log(guild, member, matches, observed_tag, result)


@bot.command(name="sync")
@owner_check()
async def sync_command(ctx):
    await ctx.reply("بدأ فحص أعضاء السيرفر الآن. قد يستغرق وقتاً حسب عدد الأعضاء.")
    result = await scan_guild_tags(ctx.guild)
    if result.get("skipped") == "not_configured":
        return await ctx.send("حدد التاق والرتبة أولاً باستخدام settag و setrole.")
    if result.get("skipped") == "role_missing":
        return await ctx.send("الرتبة المحددة غير موجودة. أعد تحديدها باستخدام setrole.")
    embed = make_embed("نتيجة فحص التاقات")
    embed.add_field(name="الأعضاء الذين أمكن فحصهم", value=str(result["checked"]), inline=True)
    embed.add_field(name="تغييرات الرتب", value=str(result["changed"]), inline=True)
    embed.add_field(name="بيانات غير متاحة", value=str(result["unknown"]), inline=True)
    embed.add_field(name="صفحات الأعضاء", value=str(result["pages"]), inline=True)
    embed.set_footer(text="يتكرر الفحص تلقائياً كل 30 ثانية؛ الحقول غير المتاحة لا تؤدي إلى سحب الرتبة.")
    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return await ctx.reply("ليس لديك صلاحية استخدام هذا الأمر.")
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.reply(f"هناك مدخل ناقص. استخدم `{PREFIX}help`.")
    if isinstance(error, commands.BadArgument):
        return await ctx.reply("المدخل غير صحيح. تحقق من المنشن أو الرتبة أو القناة.")
    log.exception("Command error", exc_info=error)
    await ctx.reply("حدث خطأ غير متوقع. راجع ملف bot.log.")


async def main():
    if not TOKEN:
        raise RuntimeError("ضع DISCORD_TOKEN داخل ملف .env")
    if not MAIN_OWNER_ID:
        raise RuntimeError("ضع MAIN_OWNER_ID داخل ملف .env")
    if not WEB_PASSWORD or not WEB_SECRET:
        raise RuntimeError("ضع WEB_PASSWORD و WEB_SECRET داخل ملف .env")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
