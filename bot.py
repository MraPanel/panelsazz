# -*- coding: utf-8 -*-
"""
ربات فروش پنل (ادمین) پاسارگاد
- خرید پنل با محصولات تعریف‌شده توسط مدیر
- پرداخت به ازای مصرف (کسر خودکار از کیف پول)
- قیمت‌ها به دلار، دریافت لحظه‌ای نرخ دلار از اینترنت
- همه دکمه‌ها شیشه‌ای (Inline)
- متن‌ها و دکمه‌ها از پنل مدیریت قابل ویرایش هستند
"""
import asyncio
import json
import logging
import math
import os
import secrets
import string
import time
from datetime import datetime

import aiosqlite
import httpx
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pgbot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
DB_PATH = os.getenv("DB_PATH", "bot.db")
GB = 1024 ** 3
BILLING_INTERVAL = 300  # ثانیه

# ----------------------------------------------------------------------------
# متن‌ها و دکمه‌های پیش‌فرض (از پنل مدیریت قابل تغییر)
# ----------------------------------------------------------------------------
DEFAULT_TEXTS = {
    "welcome": ("👋 به ربات فروش پنل خوش آمدید.\nاز دکمه‌های زیر استفاده کنید.",
                "پیام خوش‌آمدگویی", ""),
    "choose_product": ("🛒 یکی از محصولات زیر را انتخاب کنید:", "پیام لیست محصولات", ""),
    "no_products": ("فعلاً محصولی برای فروش موجود نیست.", "پیام نبود محصول", ""),
    "insufficient": ("❌ موجودی کیف پول کافی نیست.\nمبلغ مورد نیاز: {need} تومان\nموجودی شما: {balance} تومان\nکمبود: {lack} تومان",
                     "پیام موجودی ناکافی", "{need} {balance} {lack}"),
    "purchased": ("✅ پنل شما ساخته شد.\n\n🌐 آدرس: {url}\n👤 نام کاربری: <code>{username}</code>\n🔑 رمز: <code>{password}</code>\n⏳ انقضا: {expire}",
                  "پیام پس از خرید", "{url} {username} {password} {expire}"),
    "no_services": ("شما هنوز سرویسی ندارید.", "پیام نبود سرویس", ""),
    "account": ("👤 <b>حساب کاربری</b>\n\n🆔 آیدی: <code>{id}</code>\n💰 موجودی: {balance} تومان\n📥 مجموع شارژها: {deposit} تومان\n🧾 مجموع پرداخت‌ها: {spent} تومان\n📦 تعداد پنل‌ها: {count}\n💵 نرخ دلار: {rate} تومان",
                "پیام حساب کاربری", "{id} {balance} {deposit} {spent} {count} {rate}"),
    "topup_ask": ("💳 مبلغ شارژ را به تومان ارسال کنید (فقط عدد):", "پیام درخواست مبلغ شارژ", ""),
    "topup_card": ("مبلغ <b>{amount}</b> تومان را به کارت زیر واریز کنید و سپس عکس رسید را ارسال کنید:\n\n💳 <code>{card}</code>\n👤 {holder}",
                   "پیام اطلاعات کارت", "{amount} {card} {holder}"),
    "topup_wait": ("✅ رسید ثبت شد. پس از تأیید مدیر، کیف پول شارژ می‌شود.", "پیام ثبت رسید", ""),
    "topup_ok": ("✅ پرداخت شما تأیید شد و {amount} تومان به کیف پول اضافه شد.", "پیام تأیید شارژ", "{amount}"),
    "topup_no": ("❌ پرداخت شما تأیید نشد. در صورت اشتباه با پشتیبانی تماس بگیرید.", "پیام رد شارژ", ""),
    "support": ("📞 برای پشتیبانی پیام دهید: {support}", "پیام پشتیبانی", "{support}"),
    "suspended": ("⚠️ موجودی کیف پول شما تمام شد و پنل <code>{username}</code> غیرفعال شد.\nپس از شارژ، به‌صورت خودکار فعال می‌شود.",
                  "پیام غیرفعال‌سازی مصرفی", "{username}"),
    "expired": ("⚠️ پنل <code>{username}</code> منقضی/تمام‌شده است. از بخش سرویس‌ها تمدید کنید.",
                "پیام انقضای پنل", "{username}"),
}
DEFAULT_BUTTONS = {
    "buy": ("🛒 خرید پنل", "خرید پنل"),
    "services": ("📦 سرویس‌ها", "سرویس‌ها"),
    "account": ("👤 حساب کاربری", "حساب کاربری"),
    "topup": ("💳 شارژ کیف پول", "شارژ کیف پول"),
    "support": ("📞 پشتیبانی", "پشتیبانی"),
    "back": ("⬅️ بازگشت", "بازگشت"),
    "pay": ("✅ پرداخت از کیف پول", "پرداخت"),
    "passwd": ("🔑 تغییر رمز", "تغییر رمز"),
    "renew": ("🔄 تمدید", "تمدید"),
    "random": ("🎲 رمز تصادفی", "رمز تصادفی"),
    "activate": ("⚡ فعال‌سازی", "فعال‌سازی"),
    "admin": ("⚙️ مدیریت", "ورود به مدیریت"),
}

# فیلدهای تنظیماتی که مدیر می‌تواند تغییر دهد: key -> (برچسب, پیش‌فرض)
SETTING_FIELDS = {
    "panel_url": ("آدرس پنل پاسارگاد (مثلاً https://panel.example.com)", ""),
    "panel_user": ("نام کاربری ادمین اصلی پنل", ""),
    "panel_pass": ("رمز ادمین اصلی پنل", ""),
    "panel_apikey": ("API Key پنل (اختیاری؛ اگر پر باشد به‌جای نام‌کاربری/رمز استفاده می‌شود)", ""),
    "admin_extra": ("JSON اضافه برای ساخت ادمین (اختیاری، مثلاً {\"role\": \"...\"})", ""),
    "card_number": ("شماره کارت", ""),
    "card_holder": ("نام صاحب کارت", ""),
    "support": ("آیدی پشتیبانی (مثلاً @support)", "@support"),
    "min_usage_usd": ("حداقل موجودی (دلار) برای شروع پنل پرداخت به ازای مصرف", "1"),
    "rate_url": ("آدرس API نرخ دلار", "https://call4.tgju.org/ajax.json"),
    "rate_path": ("مسیر نرخ در JSON (با نقطه جدا شود)", "current.price_dollar_rl.p"),
    "rate_div": ("عدد تقسیم برای تبدیل به تومان (ریال=10، تومان=1)", "10"),
}

# ----------------------------------------------------------------------------
# پایگاه داده
# ----------------------------------------------------------------------------
db: aiosqlite.Connection = None
_settings_cache: dict = {}


async def db_init():
    global db
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0,
        total_deposit INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0, joined INTEGER);
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT,
        days INTEGER DEFAULT 0, gb REAL DEFAULT 0, price_usd REAL, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS services(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER,
        panel_username TEXT, kind TEXT, expire_ts INTEGER DEFAULT 0,
        last_usage INTEGER DEFAULT 0, base_usage INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active', created INTEGER);
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        status TEXT DEFAULT 'pending', file_id TEXT, created INTEGER);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    await db.commit()
    for row in await db_all("SELECT key,value FROM settings"):
        _settings_cache[row["key"]] = row["value"]


async def db_exec(sql, args=()):
    cur = await db.execute(sql, args)
    await db.commit()
    return cur


async def db_one(sql, args=()):
    cur = await db.execute(sql, args)
    return await cur.fetchone()


async def db_all(sql, args=()):
    cur = await db.execute(sql, args)
    return await cur.fetchall()


def gs(key, default=None):
    if key in _settings_cache:
        return _settings_cache[key]
    if default is not None:
        return default
    if key in SETTING_FIELDS:
        return SETTING_FIELDS[key][1]
    return ""


async def ss(key, value):
    _settings_cache[key] = value
    await db_exec("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


async def sdel(key):
    _settings_cache.pop(key, None)
    await db_exec("DELETE FROM settings WHERE key=?", (key,))


# ----------------------------------------------------------------------------
# متن‌ها / دکمه‌ها
# ----------------------------------------------------------------------------
def T(key, **kw):
    text = gs("text_" + key, DEFAULT_TEXTS[key][0])
    try:
        return text.format(**kw)
    except Exception:
        return text


def B(key):
    return gs("btn_" + key, DEFAULT_BUTTONS[key][0])


def num(n):
    return f"{int(n):,}"


def fa2en(s: str) -> str:
    return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace(",", "").replace("،", "").strip()


def kb(rows):
    """rows: [[(text, data_or_url), ...], ...]  همه دکمه‌ها شیشه‌ای"""
    out = []
    for row in rows:
        r = []
        for text, d in row:
            if d.startswith("http"):
                r.append(InlineKeyboardButton(text=text, url=d))
            else:
                r.append(InlineKeyboardButton(text=text, callback_data=d))
        out.append(r)
    return InlineKeyboardMarkup(inline_keyboard=out)


def is_admin(uid):
    return uid in ADMIN_IDS


def rand_pass(n=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def fmt_ts(ts):
    return "نامحدود" if not ts else datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------------
# نرخ دلار (لحظه‌ای از اینترنت)
# ----------------------------------------------------------------------------
_rate_cache = {"ts": 0, "val": 0}


async def fetch_rate_raw():
    url = gs("rate_url")
    path = gs("rate_path").split(".")
    div = float(gs("rate_div") or 10)
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = await c.get(url)
        r.raise_for_status()
        data = r.json()
    for p in path:
        data = data[int(p)] if isinstance(data, list) else data[p]
    val = float(str(data).replace(",", "").strip())
    return int(val / div)


async def get_rate() -> int:
    """نرخ نهایی (تومان) شامل درصد سود/حاشیه"""
    margin = float(gs("rate_margin", "0") or 0)
    if gs("rate_mode", "auto") == "manual":
        base = int(float(gs("manual_rate", "0") or 0))
    else:
        if time.time() - _rate_cache["ts"] > 60:  # کش ۶۰ ثانیه
            try:
                _rate_cache["val"] = await fetch_rate_raw()
                _rate_cache["ts"] = time.time()
                await ss("last_rate", str(_rate_cache["val"]))
            except Exception as e:
                log.warning("rate fetch failed: %s", e)
                _rate_cache["ts"] = time.time() - 50  # ۱۰ ثانیه بعد دوباره تلاش
                if not _rate_cache["val"]:
                    _rate_cache["val"] = int(float(gs("last_rate", "0") or gs("manual_rate", "0") or 0))
        base = _rate_cache["val"]
    return int(base * (1 + margin / 100))


def to_toman(usd, rate):
    return int(math.ceil(usd * rate))


# ----------------------------------------------------------------------------
# ارتباط با API پاسارگاد
# ----------------------------------------------------------------------------
class Panel:
    def __init__(self):
        self.token = None
        self.token_ts = 0

    def base(self):
        return gs("panel_url").rstrip("/")

    async def _headers(self, force=False):
        key = gs("panel_apikey")
        if key:
            return {"X-Api-Key": key}
        if force or not self.token or time.time() - self.token_ts > 1200:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(self.base() + "/api/admin/token",
                                 data={"username": gs("panel_user"), "password": gs("panel_pass")})
                r.raise_for_status()
                self.token = r.json()["access_token"]
                self.token_ts = time.time()
        return {"Authorization": f"Bearer {self.token}"}

    async def req(self, method, path, **kw):
        for attempt in (0, 1):
            h = await self._headers(force=attempt == 1)
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.request(method, self.base() + path, headers=h, **kw)
            if r.status_code == 401 and attempt == 0 and not gs("panel_apikey"):
                continue
            r.raise_for_status()
            return r.json() if r.content else {}

    # --- عملیات ادمین‌ها (اگر ساختار API در نسخه شما فرق دارد فقط همین بخش را اصلاح کنید) ---
    async def create_admin(self, username, password):
        body = {"username": username, "password": password, "is_sudo": False}
        try:
            body.update(json.loads(gs("admin_extra") or "{}"))
        except Exception:
            pass
        return await self.req("POST", "/api/admin", json=body)

    async def modify_admin(self, username, **fields):
        body = {"is_sudo": False}
        body.update(fields)
        return await self.req("PUT", f"/api/admin/{username}", json=body)

    async def set_disabled(self, username, disabled: bool):
        return await self.modify_admin(username, is_disabled=disabled)

    async def set_password(self, username, password):
        return await self.modify_admin(username, password=password)

    async def get_usage(self, username):
        """مصرف کل (بایت) این ادمین؛ در صورت خطا None"""
        try:
            data = await self.req("GET", "/api/admins", params={"username": username})
            items = data if isinstance(data, list) else data.get("admins", data.get("items", []))
            for a in items:
                if a.get("username") == username:
                    return int(a.get("used_traffic") or 0)
        except Exception as e:
            log.warning("get_usage list failed: %s", e)
        try:
            data = await self.req("GET", f"/api/admin/usage/{username}")
            return int(data if isinstance(data, (int, float)) else data.get("used_traffic", 0))
        except Exception as e:
            log.warning("get_usage failed for %s: %s", username, e)
            return None


panel = Panel()

# ----------------------------------------------------------------------------
# Bot / Router / FSM
# ----------------------------------------------------------------------------
r = Router()


class Topup(StatesGroup):
    amount = State()
    receipt = State()


class Passwd(StatesGroup):
    value = State()


class SetVal(StatesGroup):
    value = State()


class TextEdit(StatesGroup):
    value = State()


class ProdAdd(StatesGroup):
    name = State()
    days = State()
    gb = State()
    price = State()


class UserFind(StatesGroup):
    uid = State()
    amount = State()


class Broadcast(StatesGroup):
    text = State()


class Guard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = event.from_user
        if u:
            await db_exec("INSERT OR IGNORE INTO users(id,username,joined) VALUES(?,?,?)", (u.id, u.username or "", int(time.time())))
            row = await db_one("SELECT banned FROM users WHERE id=?", (u.id,))
            if row and row["banned"] and not is_admin(u.id):
                return
        return await handler(event, data)


async def show(ev, text, markup=None):
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.edit_text(text, reply_markup=markup)
        except Exception:
            await ev.message.answer(text, reply_markup=markup)
        await ev.answer()
    else:
        await ev.answer(text, reply_markup=markup)


def main_menu(uid):
    rows = [
        [(B("buy"), "buy"), (B("services"), "svcs")],
        [(B("account"), "acc"), (B("topup"), "top")],
        [(B("support"), "sup")],
    ]
    if is_admin(uid):
        rows.append([(B("admin"), "adm")])
    return kb(rows)


# ------------------------------- شروع / منو --------------------------------
@r.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(T("welcome"), reply_markup=main_menu(m.from_user.id))


@r.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, T("welcome"), main_menu(c.from_user.id))


@r.callback_query(F.data == "sup")
async def cb_support(c: CallbackQuery):
    await show(c, T("support", support=gs("support")), kb([[(B("back"), "menu")]]))


# ------------------------------- حساب کاربری -------------------------------
@r.callback_query(F.data == "acc")
async def cb_account(c: CallbackQuery):
    u = await db_one("SELECT * FROM users WHERE id=?", (c.from_user.id,))
    cnt = (await db_one("SELECT COUNT(*) n FROM services WHERE user_id=?", (c.from_user.id,)))["n"]
    rate = await get_rate()
    await show(c, T("account", id=u["id"], balance=num(u["balance"]), deposit=num(u["total_deposit"]),
                    spent=num(u["total_spent"]), count=cnt, rate=num(rate)),
               kb([[(B("topup"), "top")], [(B("back"), "menu")]]))


# ------------------------------- خرید ---------------------------------------
def prod_line(p, rate):
    if p["kind"] == "usage":
        return f"{p['name']} — هر گیگ {p['price_usd']:g}$ (≈ {num(to_toman(p['price_usd'], rate))} تومان)"
    days = f"{p['days']} روزه" if p["days"] else "نامحدود در زمان"
    gb = f"{p['gb']:g} گیگ" if p["gb"] else "حجم نامحدود"
    return f"{p['name']} — {days}، {gb} — {p['price_usd']:g}$ (≈ {num(to_toman(p['price_usd'], rate))} تومان)"


@r.callback_query(F.data == "buy")
async def cb_buy(c: CallbackQuery):
    prods = await db_all("SELECT * FROM products WHERE active=1 ORDER BY id")
    if not prods:
        return await show(c, T("no_products"), kb([[(B("back"), "menu")]]))
    rate = await get_rate()
    rows = [[(prod_line(p, rate), f"p:{p['id']}")] for p in prods]
    rows.append([(B("back"), "menu")])
    await show(c, T("choose_product"), kb(rows))


@r.callback_query(F.data.startswith("p:"))
async def cb_product(c: CallbackQuery):
    p = await db_one("SELECT * FROM products WHERE id=?", (int(c.data[2:]),))
    if not p:
        return await c.answer("محصول یافت نشد", show_alert=True)
    rate = await get_rate()
    txt = "🛍 <b>" + prod_line(p, rate) + "</b>"
    if p["kind"] == "usage":
        txt += f"\n\nپرداخت به ازای مصرف: مصرف شما به‌صورت خودکار از کیف پول کسر می‌شود.\nحداقل موجودی برای شروع: {gs('min_usage_usd')}$"
    await show(c, txt, kb([[(B("pay"), f"pay:{p['id']}")], [(B("back"), "buy")]]))


@r.callback_query(F.data.startswith("pay:"))
async def cb_pay(c: CallbackQuery):
    p = await db_one("SELECT * FROM products WHERE id=? AND active=1", (int(c.data[4:]),))
    if not p:
        return await c.answer("محصول یافت نشد", show_alert=True)
    uid = c.from_user.id
    rate = await get_rate()
    if rate <= 0:
        return await c.answer("نرخ دلار تنظیم نشده است. با پشتیبانی تماس بگیرید.", show_alert=True)
    if p["kind"] == "usage":
        cost, need = 0, to_toman(float(gs("min_usage_usd") or 1), rate)
    else:
        cost = need = to_toman(p["price_usd"], rate)
    u = await db_one("SELECT balance FROM users WHERE id=?", (uid,))
    if u["balance"] < need:
        return await show(c, T("insufficient", need=num(need), balance=num(u["balance"]), lack=num(need - u["balance"])),
                          kb([[(B("topup"), "top")], [(B("back"), "buy")]]))
    if cost:
        cur = await db_exec("UPDATE users SET balance=balance-?, total_spent=total_spent+? WHERE id=? AND balance>=?", (cost, cost, uid, cost))
        if cur.rowcount == 0:
            return await c.answer("موجودی کافی نیست", show_alert=True)
    username = f"u{uid}_{secrets.token_hex(2)}"
    password = rand_pass()
    try:
        await panel.create_admin(username, password)
    except Exception as e:
        log.error("create_admin failed: %s", e)
        if cost:
            await db_exec("UPDATE users SET balance=balance+?, total_spent=total_spent-? WHERE id=?", (cost, cost, uid))
        return await show(c, "❌ ساخت پنل با خطا مواجه شد. مبلغ بازگردانده شد. بعداً دوباره تلاش کنید.", kb([[(B("back"), "menu")]]))
    expire = int(time.time() + p["days"] * 86400) if (p["kind"] == "fixed" and p["days"]) else 0
    await db_exec("INSERT INTO services(user_id,product_id,panel_username,kind,expire_ts,created) VALUES(?,?,?,?,?,?)",
                  (uid, p["id"], username, p["kind"], expire, int(time.time())))
    await show(c, T("purchased", url=gs("panel_url"), username=username, password=password, expire=fmt_ts(expire)),
               kb([[(B("services"), "svcs")], [(B("back"), "menu")]]))


# ------------------------------- سرویس‌ها -----------------------------------
STATUS_FA = {"active": "🟢 فعال", "suspended": "🟠 معلق (کمبود موجودی)", "expired": "🔴 منقضی", "limited": "🔴 حجم تمام شده"}


@r.callback_query(F.data == "svcs")
async def cb_services(c: CallbackQuery):
    rows_db = await db_all("SELECT * FROM services WHERE user_id=? ORDER BY id DESC", (c.from_user.id,))
    if not rows_db:
        return await show(c, T("no_services"), kb([[(B("back"), "menu")]]))
    rows = [[(f"{STATUS_FA.get(s['status'], s['status'])[:2]} {s['panel_username']}", f"s:{s['id']}")] for s in rows_db]
    rows.append([(B("back"), "menu")])
    await show(c, "📦 سرویس‌های شما:", kb(rows))


async def service_view(c, sid):
    s = await db_one("SELECT s.*, p.name pname, p.gb pgb, p.days pdays, p.price_usd pprice FROM services s "
                     "LEFT JOIN products p ON p.id=s.product_id WHERE s.id=? AND s.user_id=?", (sid, c.from_user.id))
    if not s:
        return await c.answer("سرویس یافت نشد", show_alert=True)
    used = max(0, (s["last_usage"] or 0) - (s["base_usage"] or 0))
    txt = (f"📦 <b>{s['pname'] or 'سرویس'}</b>\n\n👤 نام کاربری: <code>{s['panel_username']}</code>\n"
           f"🌐 آدرس: {gs('panel_url')}\n📊 وضعیت: {STATUS_FA.get(s['status'], s['status'])}\n"
           f"📈 مصرف: {used / GB:.2f} گیگ")
    if s["kind"] == "fixed":
        txt += f"\n⏳ انقضا: {fmt_ts(s['expire_ts'])}"
        if s["pgb"]:
            txt += f"\n📦 سقف حجم: {s['pgb']:g} گیگ"
    rows = [[(B("passwd"), f"pw:{sid}")]]
    if s["kind"] == "fixed":
        rows[0].append((B("renew"), f"rn:{sid}"))
    elif s["status"] == "suspended":
        rows[0].append((B("activate"), f"act:{sid}"))
    rows.append([(B("back"), "svcs")])
    await show(c, txt, kb(rows))


@r.callback_query(F.data.startswith("s:"))
async def cb_service(c: CallbackQuery):
    await service_view(c, int(c.data[2:]))


# --- تغییر رمز
@r.callback_query(F.data.startswith("pw:"))
async def cb_pw(c: CallbackQuery, state: FSMContext):
    sid = int(c.data[3:])
    await state.set_state(Passwd.value)
    await state.update_data(sid=sid)
    await show(c, "🔑 رمز جدید را ارسال کنید (حداقل ۸ کاراکتر) یا رمز تصادفی بگیرید:",
               kb([[(B("random"), f"pwr:{sid}")], [(B("back"), f"s:{sid}")]]))


async def apply_password(ev, uid, sid, pw):
    s = await db_one("SELECT * FROM services WHERE id=? AND user_id=?", (sid, uid))
    if not s:
        return
    try:
        await panel.set_password(s["panel_username"], pw)
    except Exception as e:
        log.error("set_password failed: %s", e)
        return await show(ev, "❌ تغییر رمز انجام نشد. بعداً تلاش کنید.", kb([[(B("back"), f"s:{sid}")]]))
    await show(ev, f"✅ رمز جدید پنل <code>{s['panel_username']}</code>:\n<code>{pw}</code>", kb([[(B("back"), f"s:{sid}")]]))


@r.callback_query(F.data.startswith("pwr:"))
async def cb_pwr(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await apply_password(c, c.from_user.id, int(c.data[4:]), rand_pass())


@r.message(Passwd.value)
async def msg_pw(m: Message, state: FSMContext):
    pw = (m.text or "").strip()
    if len(pw) < 8:
        return await m.answer("رمز باید حداقل ۸ کاراکتر باشد.")
    sid = (await state.get_data())["sid"]
    await state.clear()
    try:
        await m.delete()
    except Exception:
        pass
    await apply_password(m, m.from_user.id, sid, pw)


# --- تمدید
@r.callback_query(F.data.startswith("rn:"))
async def cb_renew(c: CallbackQuery):
    sid = int(c.data[3:])
    s = await db_one("SELECT s.*, p.name pname, p.price_usd pprice, p.days pdays FROM services s JOIN products p ON p.id=s.product_id WHERE s.id=? AND s.user_id=?", (sid, c.from_user.id))
    if not s:
        return await c.answer("سرویس یا محصول یافت نشد", show_alert=True)
    rate = await get_rate()
    cost = to_toman(s["pprice"], rate)
    await show(c, f"🔄 تمدید <b>{s['pname']}</b> برای {s['pdays'] or 'نامحدود'} روز\nهزینه: {num(cost)} تومان ({s['pprice']:g}$)",
               kb([[(B("pay"), f"rnc:{sid}")], [(B("back"), f"s:{sid}")]]))


@r.callback_query(F.data.startswith("rnc:"))
async def cb_renew_confirm(c: CallbackQuery):
    sid, uid = int(c.data[4:]), c.from_user.id
    s = await db_one("SELECT s.*, p.price_usd pprice, p.days pdays FROM services s JOIN products p ON p.id=s.product_id WHERE s.id=? AND s.user_id=?", (sid, uid))
    if not s:
        return await c.answer("یافت نشد", show_alert=True)
    cost = to_toman(s["pprice"], await get_rate())
    u = await db_one("SELECT balance FROM users WHERE id=?", (uid,))
    if u["balance"] < cost:
        return await show(c, T("insufficient", need=num(cost), balance=num(u["balance"]), lack=num(cost - u["balance"])),
                          kb([[(B("topup"), "top")], [(B("back"), f"s:{sid}")]]))
    used = await panel.get_usage(s["panel_username"])
    try:
        await panel.set_disabled(s["panel_username"], False)
    except Exception as e:
        log.error("renew enable failed: %s", e)
        return await show(c, "❌ تمدید انجام نشد. مبلغی کسر نشد.", kb([[(B("back"), f"s:{sid}")]]))
    await db_exec("UPDATE users SET balance=balance-?, total_spent=total_spent+? WHERE id=?", (cost, cost, uid))
    now = int(time.time())
    new_exp = 0 if not s["pdays"] else int(max(now, s["expire_ts"] or 0) + s["pdays"] * 86400)
    base = used if used is not None else s["last_usage"]
    await db_exec("UPDATE services SET expire_ts=?, status='active', base_usage=?, last_usage=? WHERE id=?", (new_exp, base, base, sid))
    await service_view(c, sid)


@r.callback_query(F.data.startswith("act:"))
async def cb_activate(c: CallbackQuery):
    sid = int(c.data[4:])
    s = await db_one("SELECT * FROM services WHERE id=? AND user_id=?", (sid, c.from_user.id))
    u = await db_one("SELECT balance FROM users WHERE id=?", (c.from_user.id,))
    if not s or u["balance"] <= 0:
        return await c.answer("ابتدا کیف پول را شارژ کنید.", show_alert=True)
    try:
        await panel.set_disabled(s["panel_username"], False)
        await db_exec("UPDATE services SET status='active' WHERE id=?", (sid,))
    except Exception:
        return await c.answer("خطا در فعال‌سازی", show_alert=True)
    await service_view(c, sid)


# ------------------------------- شارژ کیف پول -------------------------------
@r.callback_query(F.data == "top")
async def cb_topup(c: CallbackQuery, state: FSMContext):
    await state.set_state(Topup.amount)
    await show(c, T("topup_ask"), kb([[(B("back"), "menu")]]))


@r.message(Topup.amount)
async def msg_topup_amount(m: Message, state: FSMContext):
    try:
        amount = int(fa2en(m.text or ""))
        assert amount >= 1000
    except Exception:
        return await m.answer("مبلغ نامعتبر است. فقط عدد (حداقل ۱٬۰۰۰ تومان) ارسال کنید.")
    await state.update_data(amount=amount)
    await state.set_state(Topup.receipt)
    await m.answer(T("topup_card", amount=num(amount), card=gs("card_number"), holder=gs("card_holder")),
                   reply_markup=kb([[(B("back"), "menu")]]))


@r.message(Topup.receipt, F.photo)
async def msg_topup_receipt(m: Message, state: FSMContext, bot: Bot):
    amount = (await state.get_data())["amount"]
    await state.clear()
    fid = m.photo[-1].file_id
    cur = await db_exec("INSERT INTO payments(user_id,amount,file_id,created) VALUES(?,?,?,?)", (m.from_user.id, amount, fid, int(time.time())))
    pid = cur.lastrowid
    await m.answer(T("topup_wait"), reply_markup=kb([[(B("back"), "menu")]]))
    cap = f"💳 درخواست شارژ #{pid}\nکاربر: <code>{m.from_user.id}</code> @{m.from_user.username or '-'}\nمبلغ: {num(amount)} تومان"
    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(aid, fid, caption=cap, reply_markup=kb([[("✅ تأیید", f"rcp:ok:{pid}"), ("❌ رد", f"rcp:no:{pid}")]]))
        except Exception:
            pass


@r.message(Topup.receipt)
async def msg_topup_receipt_bad(m: Message):
    await m.answer("لطفاً عکس رسید پرداخت را ارسال کنید.")


async def reactivate_suspended(bot, uid):
    u = await db_one("SELECT balance FROM users WHERE id=?", (uid,))
    if not u or u["balance"] <= 0:
        return
    for s in await db_all("SELECT * FROM services WHERE user_id=? AND status='suspended'", (uid,)):
        try:
            await panel.set_disabled(s["panel_username"], False)
            await db_exec("UPDATE services SET status='active' WHERE id=?", (s["id"],))
            await bot.send_message(uid, f"✅ پنل <code>{s['panel_username']}</code> دوباره فعال شد.")
        except Exception as e:
            log.warning("reactivate failed: %s", e)


@r.callback_query(F.data.startswith("rcp:"))
async def cb_receipt(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        return await c.answer()
    _, act, pid = c.data.split(":")
    p = await db_one("SELECT * FROM payments WHERE id=?", (int(pid),))
    if not p or p["status"] != "pending":
        return await c.answer("قبلاً بررسی شده", show_alert=True)
    if act == "ok":
        await db_exec("UPDATE payments SET status='approved' WHERE id=?", (p["id"],))
        await db_exec("UPDATE users SET balance=balance+?, total_deposit=total_deposit+? WHERE id=?", (p["amount"], p["amount"], p["user_id"]))
        await bot.send_message(p["user_id"], T("topup_ok", amount=num(p["amount"])))
        await reactivate_suspended(bot, p["user_id"])
        mark = "✅ تأیید شد"
    else:
        await db_exec("UPDATE payments SET status='rejected' WHERE id=?", (p["id"],))
        await bot.send_message(p["user_id"], T("topup_no"))
        mark = "❌ رد شد"
    try:
        await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{mark}", reply_markup=None)
    except Exception:
        pass
    await c.answer(mark)


# ============================= پنل مدیریت ===================================
def admin_only(f):
    async def wrap(ev, *a, **kw):
        if not is_admin(ev.from_user.id):
            if isinstance(ev, CallbackQuery):
                await ev.answer()
            return
        return await f(ev, *a, **kw)
    wrap.__name__ = f.__name__
    return wrap


ADMIN_ROWS = [
    [("🛍 محصولات", "a:prod"), ("💲 قیمت و دلار", "a:rate")],
    [("📝 ویرایش متن‌ها", "a:txt"), ("🔘 ویرایش دکمه‌ها", "a:btn")],
    [("⚙️ تنظیمات", "a:set"), ("👥 کاربران", "a:usr")],
    [("📊 آمار", "a:stats"), ("📢 پیام همگانی", "a:bc")],
    [("⬅️ منوی کاربر", "menu")],
]


@r.message(Command("admin"))
@admin_only
async def cmd_admin(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("⚙️ پنل مدیریت", reply_markup=kb(ADMIN_ROWS))


@r.callback_query(F.data == "adm")
@admin_only
async def cb_admin(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, "⚙️ پنل مدیریت", kb(ADMIN_ROWS))


BACK_ADM = [("⬅️ بازگشت", "adm")]


# --- محصولات
@r.callback_query(F.data == "a:prod")
@admin_only
async def a_prod(c: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = []
    for p in await db_all("SELECT * FROM products ORDER BY id"):
        on = "🟢" if p["active"] else "⚪"
        rows.append([(f"{on} {p['name']} ({p['price_usd']:g}$)", f"a:pt:{p['id']}"), ("🗑", f"a:pd:{p['id']}")])
    rows.append([("➕ محصول جدید", "a:padd")])
    rows.append(BACK_ADM)
    await show(c, "🛍 محصولات (روی نام بزنید تا فعال/غیرفعال شود):", kb(rows))


@r.callback_query(F.data.startswith("a:pt:"))
@admin_only
async def a_ptoggle(c: CallbackQuery, state: FSMContext):
    await db_exec("UPDATE products SET active=1-active WHERE id=?", (int(c.data[5:]),))
    await a_prod(c, state)


@r.callback_query(F.data.startswith("a:pd:"))
@admin_only
async def a_pdel(c: CallbackQuery, state: FSMContext):
    await db_exec("DELETE FROM products WHERE id=?", (int(c.data[5:]),))
    await a_prod(c, state)


@r.callback_query(F.data == "a:padd")
@admin_only
async def a_padd(c: CallbackQuery, state: FSMContext):
    await state.set_state(ProdAdd.name)
    await show(c, "نام محصول را ارسال کنید (مثلاً: محصول ۱ پنل یک‌ماهه):", kb([BACK_ADM]))


@r.message(ProdAdd.name)
@admin_only
async def a_padd_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await m.answer("نوع محصول:", reply_markup=kb([[("📦 ثابت (زمان/حجم مشخص)", "a:pk:fixed")], [("⚡ پرداخت به ازای مصرف", "a:pk:usage")]]))


@r.callback_query(F.data.startswith("a:pk:"))
@admin_only
async def a_padd_kind(c: CallbackQuery, state: FSMContext):
    kind = c.data[5:]
    await state.update_data(kind=kind)
    if kind == "fixed":
        await state.set_state(ProdAdd.days)
        await show(c, "تعداد روز را ارسال کنید (۰ = نامحدود در زمان):")
    else:
        await state.update_data(days=0, gb=0)
        await state.set_state(ProdAdd.price)
        await show(c, "قیمت <b>هر گیگ</b> را به دلار ارسال کنید (مثلاً 0.5):")


@r.message(ProdAdd.days)
@admin_only
async def a_padd_days(m: Message, state: FSMContext):
    try:
        d = int(fa2en(m.text))
    except Exception:
        return await m.answer("عدد معتبر ارسال کنید.")
    await state.update_data(days=d)
    await state.set_state(ProdAdd.gb)
    await m.answer("سقف حجم به گیگ را ارسال کنید (۰ = نامحدود):")


@r.message(ProdAdd.gb)
@admin_only
async def a_padd_gb(m: Message, state: FSMContext):
    try:
        g = float(fa2en(m.text))
    except Exception:
        return await m.answer("عدد معتبر ارسال کنید.")
    await state.update_data(gb=g)
    await state.set_state(ProdAdd.price)
    await m.answer("قیمت محصول را به دلار ارسال کنید:")


@r.message(ProdAdd.price)
@admin_only
async def a_padd_price(m: Message, state: FSMContext):
    try:
        price = float(fa2en(m.text))
    except Exception:
        return await m.answer("عدد معتبر ارسال کنید.")
    d = await state.get_data()
    await state.clear()
    await db_exec("INSERT INTO products(name,kind,days,gb,price_usd) VALUES(?,?,?,?,?)", (d["name"], d["kind"], d["days"], d["gb"], price))
    await m.answer("✅ محصول ثبت شد.", reply_markup=kb([[("🛍 محصولات", "a:prod")], BACK_ADM]))


# --- قیمت و دلار
async def rate_view(c):
    mode = gs("rate_mode", "auto")
    final = await get_rate()
    txt = (f"💲 <b>مدیریت قیمت</b>\n\nحالت نرخ: {'🌐 خودکار از اینترنت' if mode == 'auto' else '✍️ دستی'}\n"
           f"نرخ دلار مورد استفاده: <b>{num(final)}</b> تومان\nدرصد سود روی نرخ: {gs('rate_margin', '0')}%\n"
           f"نرخ دستی: {gs('manual_rate', '0')}\nآخرین نرخ دریافتی: {gs('last_rate', '-')}")
    await show(c, txt, kb([
        [("🔀 تغییر حالت خودکار/دستی", "a:rmode")],
        [("✍️ نرخ دستی", "a:sv:manual_rate"), ("➕ درصد سود", "a:sv:rate_margin")],
        [("🔗 منبع نرخ", "a:sv:rate_url")],
        BACK_ADM]))


@r.callback_query(F.data == "a:rate")
@admin_only
async def a_rate(c: CallbackQuery):
    await rate_view(c)


@r.callback_query(F.data == "a:rmode")
@admin_only
async def a_rmode(c: CallbackQuery):
    await ss("rate_mode", "manual" if gs("rate_mode", "auto") == "auto" else "auto")
    await rate_view(c)


# --- تنظیمات عمومی (آدرس پنل، کارت، ...)
EXTRA_FIELDS = {"manual_rate": "نرخ دستی دلار (تومان)", "rate_margin": "درصد سود روی نرخ دلار (مثلاً 5)"}


@r.callback_query(F.data == "a:set")
@admin_only
async def a_set(c: CallbackQuery):
    rows = [[(label.split(" (")[0], f"a:sv:{k}")] for k, (label, _) in SETTING_FIELDS.items()]
    rows.append(BACK_ADM)
    await show(c, "⚙️ کدام مورد را تغییر می‌دهید؟", kb(rows))


@r.callback_query(F.data.startswith("a:sv:"))
@admin_only
async def a_sv(c: CallbackQuery, state: FSMContext):
    key = c.data[5:]
    label = SETTING_FIELDS[key][0] if key in SETTING_FIELDS else EXTRA_FIELDS[key]
    cur = gs(key) if "pass" not in key and "apikey" not in key else "***"
    await state.set_state(SetVal.value)
    await state.update_data(key=key)
    await show(c, f"✏️ {label}\n\nمقدار فعلی: <code>{cur or '-'}</code>\n\nمقدار جدید را ارسال کنید (برای پاک‌کردن: -)", kb([BACK_ADM]))


@r.message(SetVal.value)
@admin_only
async def a_sv_value(m: Message, state: FSMContext):
    key = (await state.get_data())["key"]
    await state.clear()
    val = (m.text or "").strip()
    if val == "-":
        await sdel(key)
    else:
        await ss(key, val)
    if key.startswith("panel_"):
        panel.token = None
        try:
            await m.delete()
        except Exception:
            pass
    if key.startswith("rate_") or key == "manual_rate":
        _rate_cache["ts"] = 0
    await m.answer("✅ ذخیره شد.", reply_markup=kb([BACK_ADM]))


# --- ویرایش متن‌ها و دکمه‌ها
@r.callback_query(F.data == "a:txt")
@admin_only
async def a_txt(c: CallbackQuery):
    rows = [[(v[1], f"a:t:{k}")] for k, v in DEFAULT_TEXTS.items()]
    rows.append(BACK_ADM)
    await show(c, "📝 کدام متن را ویرایش می‌کنید؟", kb(rows))


@r.callback_query(F.data.startswith("a:t:"))
@admin_only
async def a_t(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    d = DEFAULT_TEXTS[key]
    await state.set_state(TextEdit.value)
    await state.update_data(kind="text", key=key)
    ph = f"\n\nمتغیرها: <code>{d[2]}</code>" if d[2] else ""
    await show(c, f"متن فعلی «{d[1]}»:\n\n<code>{gs('text_' + key, d[0])}</code>{ph}\n\nمتن جدید را ارسال کنید (HTML مجاز است). برای بازنشانی به پیش‌فرض: -",
               kb([[("⬅️ بازگشت", "a:txt")]]))


@r.callback_query(F.data == "a:btn")
@admin_only
async def a_btn(c: CallbackQuery):
    rows = [[(f"{gs('btn_' + k, v[0])}", f"a:b:{k}")] for k, v in DEFAULT_BUTTONS.items()]
    rows.append(BACK_ADM)
    await show(c, "🔘 روی دکمه مورد نظر بزنید تا متنش عوض شود:", kb(rows))


@r.callback_query(F.data.startswith("a:b:"))
@admin_only
async def a_b(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    await state.set_state(TextEdit.value)
    await state.update_data(kind="btn", key=key)
    await show(c, f"متن جدید دکمه «{DEFAULT_BUTTONS[key][1]}» را ارسال کنید (برای بازنشانی: -)", kb([[("⬅️ بازگشت", "a:btn")]]))


@r.message(TextEdit.value)
@admin_only
async def a_text_value(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    k = ("text_" if d["kind"] == "text" else "btn_") + d["key"]
    if m.text.strip() == "-":
        await sdel(k)
    else:
        await ss(k, m.html_text if d["kind"] == "text" else m.text.strip())
    await m.answer("✅ ذخیره شد.", reply_markup=kb([BACK_ADM]))


# --- کاربران
@r.callback_query(F.data == "a:usr")
@admin_only
async def a_usr(c: CallbackQuery, state: FSMContext):
    await state.set_state(UserFind.uid)
    await show(c, "آیدی عددی کاربر را ارسال کنید:", kb([BACK_ADM]))


async def user_card(uid):
    u = await db_one("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        return None, None
    n = (await db_one("SELECT COUNT(*) n FROM services WHERE user_id=?", (uid,)))["n"]
    txt = (f"👤 <code>{u['id']}</code> @{u['username'] or '-'}\n💰 موجودی: {num(u['balance'])}\n📥 شارژ: {num(u['total_deposit'])}\n"
           f"🧾 پرداختی: {num(u['total_spent'])}\n📦 پنل‌ها: {n}\n🚫 مسدود: {'بله' if u['banned'] else 'خیر'}")
    mk = kb([[("➕ افزایش موجودی", f"a:ub:{uid}:+"), ("➖ کاهش موجودی", f"a:ub:{uid}:-")],
             [("🚫 مسدود/آزاد", f"a:ban:{uid}")], BACK_ADM])
    return txt, mk


@r.message(UserFind.uid)
@admin_only
async def a_usr_find(m: Message, state: FSMContext):
    try:
        uid = int(fa2en(m.text))
    except Exception:
        return await m.answer("آیدی عددی ارسال کنید.")
    txt, mk = await user_card(uid)
    if not txt:
        return await m.answer("کاربر یافت نشد.")
    await state.clear()
    await m.answer(txt, reply_markup=mk)


@r.callback_query(F.data.startswith("a:ban:"))
@admin_only
async def a_ban(c: CallbackQuery):
    uid = int(c.data[6:])
    await db_exec("UPDATE users SET banned=1-banned WHERE id=?", (uid,))
    txt, mk = await user_card(uid)
    await show(c, txt, mk)


@r.callback_query(F.data.startswith("a:ub:"))
@admin_only
async def a_ub(c: CallbackQuery, state: FSMContext):
    _, _, uid, sign = c.data.split(":")
    await state.set_state(UserFind.amount)
    await state.update_data(uid=int(uid), sign=sign)
    await show(c, "مبلغ (تومان) را ارسال کنید:", kb([BACK_ADM]))


@r.message(UserFind.amount)
@admin_only
async def a_ub_amount(m: Message, state: FSMContext, bot: Bot):
    try:
        amt = int(fa2en(m.text))
    except Exception:
        return await m.answer("عدد معتبر ارسال کنید.")
    d = await state.get_data()
    await state.clear()
    delta = amt if d["sign"] == "+" else -amt
    await db_exec("UPDATE users SET balance=balance+? WHERE id=?", (delta, d["uid"]))
    if delta > 0:
        await reactivate_suspended(bot, d["uid"])
    txt, mk = await user_card(d["uid"])
    await m.answer(txt, reply_markup=mk)


# --- آمار / پیام همگانی
@r.callback_query(F.data == "a:stats")
@admin_only
async def a_stats(c: CallbackQuery):
    users = (await db_one("SELECT COUNT(*) n FROM users"))["n"]
    svc = (await db_one("SELECT COUNT(*) n FROM services"))["n"]
    dep = (await db_one("SELECT COALESCE(SUM(total_deposit),0) s FROM users"))["s"]
    spent = (await db_one("SELECT COALESCE(SUM(total_spent),0) s FROM users"))["s"]
    pend = (await db_one("SELECT COUNT(*) n FROM payments WHERE status='pending'"))["n"]
    await show(c, f"📊 <b>آمار</b>\n\n👥 کاربران: {users}\n📦 پنل‌های ساخته‌شده: {svc}\n📥 مجموع شارژها: {num(dep)} تومان\n"
                  f"🧾 مجموع فروش/مصرف: {num(spent)} تومان\n⏳ رسیدهای در انتظار: {pend}", kb([BACK_ADM]))


@r.callback_query(F.data == "a:bc")
@admin_only
async def a_bc(c: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.text)
    await show(c, "متن پیام همگانی را ارسال کنید:", kb([BACK_ADM]))


@r.message(Broadcast.text)
@admin_only
async def a_bc_send(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    ok = 0
    for u in await db_all("SELECT id FROM users WHERE banned=0"):
        try:
            await bot.send_message(u["id"], m.html_text)
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"✅ برای {ok} کاربر ارسال شد.", reply_markup=kb([BACK_ADM]))


# ============================ کار پس‌زمینه (صورتحساب) ========================
async def notify(bot, uid, text):
    try:
        await bot.send_message(uid, text)
    except Exception:
        pass


async def billing_loop(bot: Bot):
    await asyncio.sleep(15)
    while True:
        try:
            if gs("panel_url"):
                rate = await get_rate()
                rows = await db_all("SELECT s.*, p.price_usd pprice, p.gb pgb FROM services s "
                                    "LEFT JOIN products p ON p.id=s.product_id WHERE s.status='active'")
                for s in rows:
                    used = await panel.get_usage(s["panel_username"])
                    if used is None:
                        continue
                    if s["kind"] == "usage":
                        delta = used - (s["last_usage"] or 0)
                        if delta > 0 and rate > 0:
                            cost = int(math.ceil(delta / GB * s["pprice"] * rate))
                            await db_exec("UPDATE users SET balance=balance-?, total_spent=total_spent+? WHERE id=?", (cost, cost, s["user_id"]))
                        await db_exec("UPDATE services SET last_usage=? WHERE id=?", (used, s["id"]))
                        u = await db_one("SELECT balance FROM users WHERE id=?", (s["user_id"],))
                        if u["balance"] <= 0:
                            try:
                                await panel.set_disabled(s["panel_username"], True)
                                await db_exec("UPDATE services SET status='suspended' WHERE id=?", (s["id"],))
                                await notify(bot, s["user_id"], T("suspended", username=s["panel_username"]))
                            except Exception as e:
                                log.warning("suspend failed: %s", e)
                    else:
                        await db_exec("UPDATE services SET last_usage=? WHERE id=?", (used, s["id"]))
                        reason = None
                        if s["expire_ts"] and time.time() > s["expire_ts"]:
                            reason = "expired"
                        elif s["pgb"] and (used - (s["base_usage"] or 0)) >= s["pgb"] * GB:
                            reason = "limited"
                        if reason:
                            try:
                                await panel.set_disabled(s["panel_username"], True)
                                await db_exec("UPDATE services SET status=? WHERE id=?", (reason, s["id"]))
                                await notify(bot, s["user_id"], T("expired", username=s["panel_username"]))
                            except Exception as e:
                                log.warning("disable failed: %s", e)
        except Exception as e:
            log.exception("billing loop error: %s", e)
        await asyncio.sleep(BILLING_INTERVAL)


# ----------------------------------------------------------------------------
async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN تنظیم نشده است (فایل .env)")
    await db_init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(Guard())
    dp.callback_query.middleware(Guard())
    dp.include_router(r)
    asyncio.create_task(billing_loop(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
