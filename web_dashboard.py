import hmac
import hashlib
import secrets
from aiohttp import web
import discord


def page(title, body):
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | TAG MANAGER</title>
<style>
:root{{--bg:#313338;--panel:#2b2d31;--panel2:#1e1f22;--text:#f2f3f5;--muted:#b5bac1;--accent:#5865f2;--line:#3f4147;--green:#23a559;--red:#da373c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Arial,Tahoma,sans-serif}}
a{{color:inherit;text-decoration:none}}button,input,select{{font:inherit}}.layout{{display:flex;min-height:100vh}}
.side{{width:245px;background:var(--panel2);padding:22px 14px;flex-shrink:0}}.brand{{font-weight:800;letter-spacing:1px;padding:8px 12px 25px}}
.nav a{{display:block;padding:12px;border-radius:7px;color:var(--muted);margin:4px 0}}.nav a:hover,.nav a.active{{background:#404249;color:white}}
.main{{flex:1;padding:28px;max-width:1400px;margin:auto;width:100%}}.top{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:25px}}
h1{{font-size:25px;margin:0 0 8px}}h2{{font-size:17px;margin:0 0 16px}}p,.muted{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:20px 0}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:16px}}
.metric{{font-size:28px;font-weight:800;margin-top:10px}}.btn{{background:var(--accent);color:white;border:0;border-radius:6px;padding:10px 16px;cursor:pointer;font-weight:700}}
.btn.secondary{{background:#4e5058}}.btn.danger{{background:var(--red)}}input,select{{background:var(--panel2);border:1px solid var(--line);color:white;border-radius:6px;padding:11px;width:100%;margin:7px 0 14px}}
label{{display:block;color:var(--muted);font-size:13px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:right;padding:12px;border-bottom:1px solid var(--line);font-size:13px}}th{{color:var(--muted)}}.status{{color:#23a559;font-weight:bold}}.row{{display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
.notice{{padding:12px;border-radius:7px;background:#3b3d44;color:var(--muted);margin:12px 0}}.login{{max-width:420px;margin:12vh auto;padding:28px;background:var(--panel);border-radius:12px}}
@media(max-width:760px){{.layout{{display:block}}.side{{width:100%;padding:12px}}.nav{{display:flex;overflow:auto;gap:5px}}.nav a{{white-space:nowrap}}.main{{padding:16px}}}}
</style></head><body>{body}</body></html>"""


def signed(value, secret):
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_app(bot, store, main_owner_id, password, secret):
    routes = web.RouteTableDef()
    sessions = set()

    def is_authenticated(request):
        token = request.cookies.get("tm_session", "")
        return bool(token and token in sessions)

    def require_auth(handler):
        async def wrapped(request):
            if not is_authenticated(request):
                raise web.HTTPFound("/login")
            return await handler(request)
        return wrapped

    def is_main(request):
        try:
            return int(request.cookies.get("tm_uid", "0")) == int(main_owner_id)
        except ValueError:
            return False

    @routes.get("/")
    async def home(request):
        if not is_authenticated(request):
            raise web.HTTPFound("/login")
        raise web.HTTPFound("/dashboard")

    @routes.get("/login")
    async def login_page(request):
        body = """<div class="login"><h1>TAG MANAGER</h1><p>تسجيل دخول لوحة التحكم</p>
<form method="post" action="/login"><label>Discord User ID لمالك البوت</label><input name="uid" required>
<label>كلمة مرور لوحة التحكم</label><input name="password" type="password" required>
<button class="btn" type="submit">تسجيل الدخول</button></form></div>"""
        return web.Response(text=page("Login", body), content_type="text/html")

    @routes.post("/login")
    async def login(request):
        form = await request.post()
        try:
            uid = int(form.get("uid", "0"))
        except ValueError:
            uid = 0
        supplied = str(form.get("password", ""))
        if uid != int(main_owner_id) or not hmac.compare_digest(supplied, password):
            return web.Response(text=page("Login", '<div class="login"><h1>تعذر تسجيل الدخول</h1><p>بيانات الدخول غير صحيحة.</p><a href="/login">العودة</a></div>'), content_type="text/html", status=401)
        token = secrets.token_urlsafe(32)
        sessions.add(token)
        response = web.HTTPFound("/dashboard")
        response.set_cookie("tm_session", token, httponly=True, samesite="Strict", secure=False, max_age=43200)
        response.set_cookie("tm_uid", str(uid), httponly=True, samesite="Strict", secure=False, max_age=43200)
        raise response

    @routes.get("/logout")
    async def logout(request):
        token = request.cookies.get("tm_session", "")
        sessions.discard(token)
        response = web.HTTPFound("/login")
        response.del_cookie("tm_session")
        response.del_cookie("tm_uid")
        raise response

    def shell(active, content):
        nav = [
            ("/dashboard", "Dashboard"),
            ("/settings", "إعدادات التاق"),
            ("/logs", "سجل الأحداث"),
            ("/owners", "أونرات البوت"),
        ]
        links = "".join(f'<a class="{"active" if path == active else ""}" href="{path}">{label}</a>' for path, label in nav)
        body = f"""<div class="layout"><aside class="side"><div class="brand">TAG MANAGER</div><nav class="nav">{links}<a href="/logout">تسجيل الخروج</a></nav></aside>
<main class="main"><div class="top"><div><h1>{active.replace("/", "").title() or "Dashboard"}</h1><div class="muted">لوحة إدارة بوت Discord</div></div><span class="status">BOT STATUS: {"ONLINE" if bot.is_ready() else "OFFLINE"}</span></div>{content}</main></div>"""
        return web.Response(text=page("Dashboard", body), content_type="text/html")

    @routes.get("/dashboard")
    @require_auth
    async def dashboard(request):
        stats = store.stats()
        guild_count = len(bot.guilds)
        members = sum(g.member_count or 0 for g in bot.guilds)
        content = f"""<div class="grid">
<div class="card"><div class="muted">السيرفرات المتصلة</div><div class="metric">{guild_count}</div></div>
<div class="card"><div class="muted">إجمالي الأعضاء التقريبي</div><div class="metric">{members}</div></div>
<div class="card"><div class="muted">إضافات التاق المسجلة</div><div class="metric">{stats["added"]}</div></div>
<div class="card"><div class="muted">إزالات التاق المسجلة</div><div class="metric">{stats["removed"]}</div></div></div>
<div class="card"><h2>حالة النظام</h2><p>البوت: <b>{"متصل" if bot.is_ready() else "غير متصل"}</b></p><p>التخزين: ملفات JSON محلية داخل مجلد data.</p><p>عدد الأحداث المحفوظة: {stats["events"]}</p></div>
<div class="card"><h2>السيرفرات</h2><table><tr><th>السيرفر</th><th>Server ID</th><th>الأعضاء</th></tr>{''.join(f"<tr><td>{discord.utils.escape_markdown(g.name)}</td><td>{g.id}</td><td>{g.member_count or 0}</td></tr>" for g in bot.guilds)}</table></div>"""
        return shell("/dashboard", content)

    @routes.get("/settings")
    @require_auth
    async def settings_page(request):
        guilds = bot.guilds
        selected = request.query.get("guild", str(guilds[0].id) if guilds else "")
        guild = bot.get_guild(int(selected)) if selected.isdigit() else None
        if guild is None and guilds:
            guild = guilds[0]
        if guild is None:
            content = '<div class="card">البوت غير موجود في أي سيرفر.</div>'
            return shell("/settings", content)
        data = store.get_guild(guild.id)
        role_options = "".join(f'<option value="{r.id}" {"selected" if r.id == data.get("role_id") else ""}>{discord.utils.escape_markdown(r.name)}</option>' for r in guild.roles if not r.is_default and not r.managed)
        channel_options = "".join(f'<option value="{c.id}" {"selected" if c.id == data.get("log_channel_id") else ""}>#{discord.utils.escape_markdown(c.name)}</option>' for c in guild.text_channels)
        guild_options = "".join(f'<option value="{g.id}" {"selected" if g.id == guild.id else ""}>{discord.utils.escape_markdown(g.name)}</option>' for g in guilds)
        content = f"""<div class="card"><h2>إعدادات السيرفر</h2><form method="get" action="/settings"><label>السيرفر</label><select name="guild" onchange="this.form.submit()">{guild_options}</select></form>
<form method="post" action="/settings"><input type="hidden" name="guild_id" value="{guild.id}">
<label>التاق المطلوب</label><input name="tag" maxlength="4" value="{data.get("tag") or ""}" placeholder="مثال: S7">
<label>الرتبة المرتبطة</label><select name="role_id"><option value="">غير محددة</option>{role_options}</select>
<label>روم اللوق</label><select name="log_channel_id"><option value="">غير محدد</option>{channel_options}</select>
<button class="btn" type="submit">حفظ الإعدادات</button></form></div>
<div class="notice">تنبيه: حفظ الإعدادات لا يثبت أن Discord يرسل تحديثات Server Tag إلى البوت. يجب اختبار Gateway على السيرفر.</div>"""
        return shell("/settings", content)

    @routes.post("/settings")
    @require_auth
    async def save_settings(request):
        form = await request.post()
        try:
            guild_id = int(form.get("guild_id", "0"))
            tag = str(form.get("tag", "")).strip()
            role_id = int(form.get("role_id")) if form.get("role_id") else None
            channel_id = int(form.get("log_channel_id")) if form.get("log_channel_id") else None
            if tag and not 1 <= len(tag) <= 4:
                raise ValueError()
            guild = bot.get_guild(guild_id)
            if guild is None:
                raise ValueError()
            if role_id:
                role = guild.get_role(role_id)
                if role is None or role.is_default or role.managed:
                    raise ValueError()
            if channel_id and not isinstance(guild.get_channel(channel_id), discord.TextChannel):
                raise ValueError()
            store.set_guild(guild_id, tag=tag or None, role_id=role_id, log_channel_id=channel_id)
        except (ValueError, TypeError):
            return web.Response(text=page("Error", '<div class="login"><h1>تعذر حفظ الإعدادات</h1><p>تحقق من القيم المحددة.</p><a href="/settings">عودة</a></div>'), content_type="text/html", status=400)
        raise web.HTTPFound(f"/settings?guild={guild_id}")

    @routes.get("/logs")
    @require_auth
    async def logs_page(request):
        rows = []
        for item in store.recent_logs(200):
            rows.append(
                "<tr>"
                f"<td>{item.get('timestamp','')}</td>"
                f"<td>{discord.utils.escape_markdown(item.get('username',''))}</td>"
                f"<td>{item.get('member_id','')}</td>"
                f"<td>{item.get('event','')}</td>"
                f"<td>{discord.utils.escape_markdown(item.get('tag',''))}</td>"
                f"<td>{discord.utils.escape_markdown(item.get('result',''))}</td>"
                "</tr>"
            )
        content = f'<div class="card"><h2>آخر 200 حدث</h2><div style="overflow:auto"><table><tr><th>الوقت</th><th>العضو</th><th>ID</th><th>الحدث</th><th>التاق</th><th>النتيجة</th></tr>{"".join(rows) or "<tr><td colspan=6>لا توجد أحداث محفوظة.</td></tr>"}</table></div></div>'
        return shell("/logs", content)

    @routes.get("/owners")
    @require_auth
    async def owners_page(request):
        owners = store.list_owners()
        rows = "".join(f"<tr><td>{uid}</td><td><form method='post' action='/owners/remove'><input type='hidden' name='uid' value='{uid}'><button class='btn danger' type='submit'>إزالة</button></form></td></tr>" for uid in owners)
        add_form = ""
        if is_main(request):
            add_form = """<form method="post" action="/owners/add"><label>Discord User ID</label><input name="uid" required><button class="btn">إضافة أونر</button></form>"""
        content = f'<div class="card"><h2>أونرات البوت</h2><p>مالك البوت الأساسي لا يمكن إزالته من هذه القائمة.</p><table><tr><th>User ID</th><th>الإجراء</th></tr>{rows or "<tr><td colspan=2>لا يوجد أونرات إضافيون.</td></tr>"}</table>{add_form}</div>'
        return shell("/owners", content)

    @routes.post("/owners/add")
    @require_auth
    async def owner_add(request):
        if not is_main(request):
            raise web.HTTPForbidden()
        form = await request.post()
        try:
            uid = int(form.get("uid", "0"))
            if uid <= 0 or uid == int(main_owner_id):
                raise ValueError()
            store.add_owner(uid)
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid Discord user ID")
        raise web.HTTPFound("/owners")

    @routes.post("/owners/remove")
    @require_auth
    async def owner_remove(request):
        if not is_main(request):
            raise web.HTTPForbidden()
        form = await request.post()
        try:
            uid = int(form.get("uid", "0"))
            if uid == int(main_owner_id):
                raise ValueError()
            store.remove_owner(uid)
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid Discord user ID")
        raise web.HTTPFound("/owners")

    app = web.Application()
    app.add_routes(routes)
    return app


async def start_web_dashboard(bot, store, main_owner_id, host, port, password, secret):
    app = create_app(bot, store, main_owner_id, password, secret)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"Web dashboard listening on http://{host}:{port}")
    bot.web_runner = runner
