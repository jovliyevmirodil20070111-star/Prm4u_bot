"""
╔══════════════════════════════════════════════════════╗
║         PRm4u GAME BOT  v2.2  — @mirodil_info        ║
║  O'rnatish:  pip install aiogram aiohttp psycopg2-binary ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio, random, aiohttp, os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

TOKEN            = "8720740940:AAGE1imTXRGhtOZ-fYH_nzh1tJstwgCeE38"
SUPPORT_LINK     = "https://t.me/mirodil_info"
ADMIN_IDS        = [5656375477]
PR_PER_DOLLAR    = 20_000
CHANNEL_USERNAME = "@Prm4ufree"   # ← O'z kanal username ingizni yozing
CHANNEL_LINK     = "https://t.me/prm4ufree"  # ← Kanal linki
CHANNEL_PR_GIFT  = 10_000
COMMISSION_PCT = 5
WIN_GIF_ID     = "CgACAgQAAxkBAAFJuWlqB4DEKxfR8xGgIi11Hpbyi9FviAACvwIAAhn8VVGXEPylDK8y3DsE"
LOSS_GIF_ID    = "CgACAgQAAxkBAAFJuWdqB4DBtfQlp_oKd8LheQFKFCEsCAACpQIAAqnITFF-EHFNd1WImjsE"
STAKES         = [500, 1_000, 2_000, 3_000, 5_000, 10_000]
THROW_TIMEOUT  = 180

DATABASE_URL = os.environ.get("DATABASE_URL", "")
bot_obj = Bot(token=TOKEN)
dp      = Dispatcher()
user_states = {}
game_timers = {}
waiting_timers = {}
# ════════════════════════════════════════════════════════
#  🗄️  DATABASE (PostgreSQL)
# ════════════════════════════════════════════════════════
def dbc():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = dbc(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id     BIGINT PRIMARY KEY,
        username    TEXT    DEFAULT '',
        full_name   TEXT    DEFAULT '',
        pr          INTEGER DEFAULT 1000,
        last_bonus  TEXT    DEFAULT '',
        lang        TEXT    DEFAULT 'uz',
        wins        INTEGER DEFAULT 0,
        losses      INTEGER DEFAULT 0,
        usd_balance REAL    DEFAULT 0,
        channel_claimed INTEGER DEFAULT 0
    )""")
    # Eski DB larga ustunlarni qo'shish (migration)
    try:
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS usd_balance REAL DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS channel_claimed INTEGER DEFAULT 0")
    except: pass
    c.execute("""CREATE TABLE IF NOT EXISTS games (
        id         SERIAL PRIMARY KEY,
        creator_id BIGINT,
        joiner_id  BIGINT  DEFAULT 0,
        stake      INTEGER,
        status     TEXT    DEFAULT 'waiting',
        p1_dice    INTEGER DEFAULT 0,
        p2_dice    INTEGER DEFAULT 0,
        winner_id  BIGINT  DEFAULT 0,
        created_at TEXT,
        started_at TEXT    DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transfers (
        id         SERIAL PRIMARY KEY,
        from_id    BIGINT,
        to_id      BIGINT,
        amount     INTEGER,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    c.execute("INSERT INTO settings VALUES ('usd_uzs','12700') ON CONFLICT DO NOTHING")
    c.execute("INSERT INTO settings VALUES ('rate_fetch','') ON CONFLICT DO NOTHING")
    conn.commit(); conn.close()

def register(uid, username, full_name):
    conn = dbc(); c = conn.cursor()
    c.execute("INSERT INTO users (user_id,username,full_name) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
              (uid, username or "", full_name or ""))
    conn.commit(); conn.close()

def get_user(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
    r = c.fetchone(); conn.close(); return r

def get_pr(uid):        u = get_user(uid); return u[3] if u else 0
def get_lang(uid):      u = get_user(uid); return u[5] if u else 'uz'
def get_wl(uid):        u = get_user(uid); return (u[6], u[7]) if u else (0, 0)
def get_usd_bal(uid):   u = get_user(uid); return round(u[8], 4) if u and u[8] else 0.0
def is_channel_claimed(uid): u = get_user(uid); return bool(u[9]) if u else False

def set_channel_claimed(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET channel_claimed=1 WHERE user_id=%s", (uid,))
    conn.commit(); conn.close()

def set_lang(uid, lang):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, uid))
    conn.commit(); conn.close()

def change_pr(uid, delta):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET pr=GREATEST(0,pr+%s) WHERE user_id=%s", (delta, uid))
    conn.commit(); conn.close()

def change_usd(uid, delta):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET usd_balance=GREATEST(0,usd_balance+%s) WHERE user_id=%s", (delta, uid))
    conn.commit(); conn.close()

def add_win(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET wins=wins+1 WHERE user_id=%s", (uid,))
    conn.commit(); conn.close()

def add_loss(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET losses=losses+1 WHERE user_id=%s", (uid,))
    conn.commit(); conn.close()

def get_setting(k):
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=%s", (k,))
    r = c.fetchone(); conn.close(); return r[0] if r else None

def set_setting(k, v):
    conn = dbc(); c = conn.cursor()
    c.execute("INSERT INTO settings VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=%s", (k, str(v), str(v)))
    conn.commit(); conn.close()

def do_transfer(from_id, to_id, amount):
    """Faqat PR transfer — $ transferi yo'q"""
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT pr FROM users WHERE user_id=%s", (from_id,))
    fp = c.fetchone()
    c.execute("SELECT user_id FROM users WHERE user_id=%s", (to_id,))
    tu = c.fetchone()
    if not fp or fp[0] < amount or not tu:
        conn.close(); return False, "no_funds" if fp and fp[0] < amount else "no_user"
    c.execute("UPDATE users SET pr=pr-%s WHERE user_id=%s", (amount, from_id))
    c.execute("UPDATE users SET pr=pr+%s WHERE user_id=%s", (amount, to_id))
    c.execute("INSERT INTO transfers (from_id,to_id,amount,created_at) VALUES (%s,%s,%s,%s)",
              (from_id, to_id, amount, datetime.now().isoformat()))
    conn.commit(); conn.close(); return True, "ok"

def claim_bonus(uid):
    u = get_user(uid)
    if not u: return False, (0, 0)
    last = u[4]; now = datetime.now()
    if last:
        try:
            diff = now - datetime.fromisoformat(last)
            if diff.total_seconds() < 86400:
                rem = timedelta(seconds=86400) - diff
                h, s = divmod(int(rem.total_seconds()), 3600)
                return False, (h, s // 60)
        except: pass
    amount = random.randint(1, 100)
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE users SET pr=pr+%s,last_bonus=%s WHERE user_id=%s",
              (amount, now.isoformat(), uid))
    conn.commit(); conn.close(); return True, amount

async def get_usd_uzs():
    last = get_setting("rate_fetch")
    now  = datetime.now()
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < 86400:
                return int(get_setting("usd_uzs") or 12700)
        except: pass
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.exchangerate-api.com/v4/latest/USD",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                d = await r.json()
                uzs = int(d["rates"]["UZS"])
                set_setting("usd_uzs", uzs)
                set_setting("rate_fetch", now.isoformat())
                return uzs
    except:
        return int(get_setting("usd_uzs") or 12700)

def create_game(uid, stake):
    conn = dbc(); c = conn.cursor()
    c.execute("INSERT INTO games (creator_id,stake,created_at) VALUES (%s,%s,%s) RETURNING id",
              (uid, stake, datetime.now().isoformat()))
    gid = c.fetchone()[0]; conn.commit(); conn.close(); return gid

def get_waiting_games(exclude_uid=None):
    conn = dbc(); c = conn.cursor()
    if exclude_uid:
        c.execute("SELECT id,creator_id,stake FROM games WHERE status='waiting' AND creator_id!=%s ORDER BY created_at LIMIT 20", (exclude_uid,))
    else:
        c.execute("SELECT id,creator_id,stake FROM games WHERE status='waiting' ORDER BY created_at LIMIT 20")
    r = c.fetchall(); conn.close(); return r

def get_game(gid):
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT * FROM games WHERE id=%s", (gid,))
    r = c.fetchone(); conn.close(); return r

def start_game(gid, joiner_id):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET joiner_id=%s,status='p1_turn',started_at=%s WHERE id=%s",
              (joiner_id, datetime.now().isoformat(), gid))
    conn.commit(); conn.close()

def set_p1_dice(gid, val):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET p1_dice=%s,status='p2_turn' WHERE id=%s", (val, gid))
    conn.commit(); conn.close()

def set_p2_dice(gid, val):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET p2_dice=%s,status='resolving' WHERE id=%s", (val, gid))
    conn.commit(); conn.close()

def finish_game_db(gid, winner_id):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET winner_id=%s,status='finished' WHERE id=%s", (winner_id, gid))
    conn.commit(); conn.close()

def cancel_game_db(gid):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET status='cancelled' WHERE id=%s", (gid,))
    conn.commit(); conn.close()
def reset_game_for_rematch(gid):
    conn = dbc(); c = conn.cursor()
    c.execute("UPDATE games SET p1_dice=0, p2_dice=0, status='p1_turn' WHERE id=%s", (gid,))
    conn.commit(); conn.close()
def cancel_waiting(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("DELETE FROM games WHERE creator_id=%s AND status='waiting'", (uid,))
    conn.commit(); conn.close()

def has_waiting(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT id FROM games WHERE creator_id=%s AND status='waiting'", (uid,))
    r = c.fetchone(); conn.close(); return r[0] if r else None

def user_active_game(uid):
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT * FROM games WHERE (creator_id=%s OR joiner_id=%s) AND status IN ('p1_turn','p2_turn')", (uid, uid))
    r = c.fetchone(); conn.close(); return r

def get_stats():
    conn = dbc(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM games WHERE status='finished'"); games = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM games WHERE status='waiting'"); wait = c.fetchone()[0]
    c.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM transfers"); xfers = c.fetchone()
    conn.close(); return users, games, wait, xfers

# ════════════════════════════════════════════════════════
#  💬  MATNLAR
# ════════════════════════════════════════════════════════
T = {
"uz": {
"welcome":("🎲 <b>PRm4u O'yin Botiga Xush Kelibsiz!</b>\n\n🎟 Sizga <b>1 000 PR</b> boshlang'ich balans berildi!\n\n👇 Menyudan foydalaning:"),
"balance":("👇 <b>Sizning balans</b>\n\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n\nKurs: 1$ = {pr_per_usd:,} PR"),
"profile":("👤 <b>Profil</b>\n\n🆔 ID: <code>{uid}</code>\n📛 Ism: {name}\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n🏆 G'alabalar: {wins}\n💀 Mag'lubiyatlar: {losses}"),
"transfer_ask_id":"💸 <b>PR Transfer</b>\n\nPR yubormoqchi bo'lgan foydalanuvchining <b>Telegram ID</b> sini kiriting:\n\n💡 ID ni bilish: @userinfobot",
"transfer_ask_amt":"👤 Foydalanuvchi: <b>{name}</b>\n🆔 ID: <code>{uid}</code>\n\nQancha PR yubormoqchisiz?\n(Sizda: <b>{pr:,} PR</b>)",
"transfer_confirm":"✅ Tasdiqlash:\n\n➡️ Kimga: <a href='tg://user?id={to_id}'>{to_id}</a>\n💸 Miqdor: <b>{amount:,} PR</b>\n💰 Komissiya: 0%\n\nDavom etasizmi?",
"transfer_ok":("👍 <b>Transfer muvaffaqiyatli!</b>\n\nFoydalanuvchi <code>{to_id}</code> ga <b>{amount:,} PR</b>\n\n➖ Komissiya 0%, balansingizdan {amount:,} PR yechildi"),
"transfer_recv":"🎁 Sizga <code>{from_id}</code> dan <b>{amount:,} PR</b> transfer qilindi!",
"transfer_no_user":"❌ Bu ID li foydalanuvchi topilmadi!",
"transfer_no_funds":"❌ Yetarli PR yo'q! Sizda: <b>{pr:,} PR</b>",
"transfer_cancel":"❌ Transfer bekor qilindi.",
"transfer_self":"❌ O'zingizga transfer qila olmaysiz!",
# Obmen
"obmen_choose":"💱 <b>Ayirboshlash</b>\n\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n\nKurs: <b>1$ = {pr_per_usd:,} PR</b>\n\nQaysi yo'nalishni tanlaysiz?",
"obmen_pr_to_usd_ask":"💱 <b>PR → $</b>\n\nQancha PR ayirboshlaysiz?\nSizda: <b>{pr:,} PR</b>\n\nKurs: {pr_per_usd:,} PR = 1$\n\nMiqdor kiriting:",
"obmen_usd_to_pr_ask":"💱 <b>$ → PR</b>\n\nQancha $ ayirboshlaysiz?\nSizda: <b>{usd:.4f} $</b>\n\nKurs: 1$ = {pr_per_usd:,} PR\n\nMiqdor kiriting (masalan: 0.5):",
"obmen_pr_to_usd_confirm":"✅ Tasdiqlash:\n\n💸 Berasiz: <b>{pr:,} PR</b>\n💵 Olasiz: <b>{usd:.4f} $</b>\n\nDavom etasizmi?",
"obmen_usd_to_pr_confirm":"✅ Tasdiqlash:\n\n💵 Berasiz: <b>{usd:.4f} $</b>\n💸 Olasiz: <b>{pr:,} PR</b>\n\nDavom etasizmi?",
"obmen_ok_pr_to_usd":"✅ <b>Ayirboshlash muvaffaqiyatli!</b>\n\n➖ <b>{pr:,} PR</b> yechildi\n➕ <b>{usd:.4f} $</b> qo'shildi\n\n🎟 PR: <b>{bal_pr:,} PR</b>\n💵 USD: <b>{bal_usd:.4f} $</b>",
"obmen_ok_usd_to_pr":"✅ <b>Ayirboshlash muvaffaqiyatli!</b>\n\n➖ <b>{usd:.4f} $</b> yechildi\n➕ <b>{pr:,} PR</b> qo'shildi\n\n🎟 PR: <b>{bal_pr:,} PR</b>\n💵 USD: <b>{bal_usd:.4f} $</b>",
"obmen_no_pr":"❌ Yetarli PR yo'q! Sizda: <b>{pr:,} PR</b>",
"obmen_no_usd":"❌ Yetarli $ yo'q! Sizda: <b>{usd:.4f} $</b>",
"obmen_invalid":"❌ Noto'g'ri miqdor! Qaytadan kiriting.",
"obmen_cancel":"❌ Ayirboshlash bekor qilindi.",
"obmen_min_pr":"❌ Minimal miqdor: <b>{min_pr:,} PR</b>",
# Game
"game_menu":"🎲 <b>O'yin xonasi</b>\n\n💰 Balansingiz: <b>{pr:,} PR</b>",
"rooms_list":"🎮 <b>Ochiq xonalar ({count} ta):</b>\n\nXona tanlang yoki yangi yarating:",
"rooms_empty":"😔 Hozir ochiq xona yo'q.\nBirinchi bo'lib xona oching!",
"room_detail":("🎮 <b>Xona #{gid}</b>\n\n👤 O'yinchi: <code>#{creator_id}</code>\n🎟 Stavka: <b>{stake:,} PR</b>\n\nQo'shilasizmi?"),
"already_wait":"⏳ Siz allaqachon xona kutmoqdasiz!",
"not_enough":"😞 <b>Yetarli PR yo'q!</b>\nStavka: <b>{stake:,} PR</b>\nSizda: <b>{pr:,} PR</b>\n\nPR sotib olish: {support}",
"room_created":"⏳ <b>Xona yaratildi!</b>\n\n🆔 Xona ID: <code>#{gid}</code>\n🎟 Stavka: <b>{stake:,} PR</b>\n\nRaqib kutilmoqda... 👀",
"game_started":("🎲 <b>O'yin boshlandi!</b>\n\n🆔 Xona: #{gid}\n🎟 Stavka: {stake:,} PR\n\n🔴 <code>#{p1}</code> vs 🔵 <code>#{p2}</code>\n\n⏱ {turn_name} tosh tashlaydi!"),
"your_turn":"🎲 Sizning navbatingiz! Tosh tashlang:",
"wait_turn":"⏳ Raqib tashlashini kuting...",
"your_turn_now":"🎲 Endi sizning navbatingiz! Tosh tashlang:",
"timeout_cancel":"⏰ <b>Vaqt tugadi!</b>\n\nO'yin bekor qilindi, PR lar qaytarildi.",
"win_text":("😊 <b>Siz yutdingiz!</b>\n\n😍 Yutganingiz: <b>+{win:,} PR</b>\n💸 Komissiya (5%): <b>-{commission:,} PR</b>\n\n🆔 O'yin ID: #{gid}\n🎟 Stavka: {stake:,} PR\n✅ G'olib: <code>#{winner}</code> — 🎲 {w_dice}\n🔴 Mag'lub: <code>#{loser}</code> — 🎲 {l_dice}\n\n🎟 Balans: <b>{bal:,} PR</b>"),
"loss_text":("😢 <b>Siz yutqazdingiz!</b>\n\n🆔 O'yin ID: #{gid}\n🎟 Stavka: {stake:,} PR\n✅ G'olib: <code>#{winner}</code> — 🎲 {w_dice}\n🔴 Mag'lub: <code>#{loser}</code> — 🎲 {l_dice}\n\n🎟 Balans: <b>{bal:,} PR</b>"),
"draw_text":("🤝 <b>Durrang! PR lar qaytarildi.</b>\n\n🆔 O'yin ID: #{gid}\n🎟 Stavka: {stake:,} PR\n🎲 Ikkalangizda: {val}\n\n🎟 Balans: <b>{bal:,} PR</b>"),
"bonus_spin":"🎰 Kunlik bonus aylantirilmoqda...",
"bonus_win":"🎉 <b>Kunlik bonus!</b>\n\nSlotda: <b>{amount} PR</b>\n🎟 Balans: <b>{bal:,} PR</b>",
"bonus_wait":"⏳ Bonus olindi!\n🕐 <b>{h} soat {m} daqiqa</b> dan keyin qayta oling.",
"support_msg":"💬 <b>Murojaat uchun:</b>\n\n{link}\n\nPR sotib olish va savollar uchun.",
"buy_pr":"🛍 <b>PR sotib olish</b>\n\nNarxlar:\n🎟 10 000 PR = 0.5$\n🎟 50 000 PR = 2.5$\n🎟 100 000 PR = 5$\n\nTo'lov uchun adminga murojaat qiling:",
"cancel_ok":"❌ Bekor qilindi.",
"lang_choose":"🌐 Tilni tanlang:",
"lang_set":"✅ Til: <b>O'zbekcha</b>",
"admin_ok_pr":"✅ {uid} ga {amount:,} PR berildi. PR balansi: {bal:,} PR",
"admin_ok_usd":"✅ {uid} ga {amount:.4f} $ berildi. USD balansi: {bal:.4f} $",
"admin_rate":"✅ Kurs: 1$ = {uzs:,} so'm | {pr_per_usd:,} PR",
"admin_only":"❌ Faqat admin!",
"channel_check":"🎁 <b>10,000 PR tekinga olish</b>\n\nAvval kanalga obuna bo'ling:\n{link}\n\nObuna bo'lgach, tugmani bosing 👇",
"channel_not_subscribed":"❌ Siz hali kanalga obuna bo'lmagansiz!\n\nObuna bo'ling: {link}\n\nKeyin qayta urining.",
"channel_already_claimed":"✅ Siz allaqachon bonus PR oldiniz!\n\n🎟 Balans: <b>{pr:,} PR</b>",
"channel_bonus_ok":"🎉 <b>Tabriklaymiz!</b>\n\nKanalga obuna bo'lganingiz uchun <b>+{amount:,} PR</b> berildi!\n\n🎟 Balans: <b>{pr:,} PR</b>",
"btn_channel_bonus":"🎁 10,000 PR tekinga olish",
"btn_check_sub":"✅ Obuna bo'ldim, PR olish",
"btn_game":"🎲 O'yin xonasi","btn_balance":"🎟 Balans","btn_bonus":"🎁 Kunlik bonus",
"btn_support":"💬 Murojaat","btn_buy":"🛍 PR sotib olish","btn_lang":"🌐 Til",
"btn_transfer":"💸 PR Transfer","btn_obmen":"💱 Ayirboshlash","btn_confirm":"✅ Tasdiqlash","btn_cancel":"❌ Bekor",
"btn_throw":"🎲 Tosh tashlash","btn_join":"✅ Qo'shilish","btn_profile":"👤 Profil ko'rish",
"btn_rooms":"🎮 Xonalar ro'yxati","btn_create":"➕ Yangi xona","btn_back":"🔙 Orqaga",
"btn_pr_to_usd":"🎟➡️💵 PR → $","btn_usd_to_pr":"💵➡️🎟 $ → PR",
},
"ru": {
"welcome":("🎲 <b>Добро пожаловать в PRm4u!</b>\n\n🎟 Вам начислено <b>1 000 PR</b>!\n\n👇 Используйте меню:"),
"balance":("👇 <b>Ваш баланс</b>\n\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n\nКурс: 1$ = {pr_per_usd:,} PR"),
"profile":("👤 <b>Профиль</b>\n\n🆔 ID: <code>{uid}</code>\n📛 Имя: {name}\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n🏆 Победы: {wins}\n💀 Поражения: {losses}"),
"transfer_ask_id":"💸 <b>Перевод PR</b>\n\nВведите <b>Telegram ID</b> получателя:\n\n💡 ID узнать: @userinfobot",
"transfer_ask_amt":"👤 Пользователь: <b>{name}</b>\n🆔 ID: <code>{uid}</code>\n\nСколько PR перевести?\n(У вас: <b>{pr:,} PR</b>)",
"transfer_confirm":"✅ Подтверждение:\n\n➡️ Кому: <a href='tg://user?id={to_id}'>{to_id}</a>\n💸 Сумма: <b>{amount:,} PR</b>\n💰 Комиссия: 0%\n\nПодтвердить?",
"transfer_ok":("👍 <b>Перевод выполнен!</b>\n\nПользователю <code>{to_id}</code> — <b>{amount:,} PR</b>\n\n➖ Комиссия 0%, с баланса списано {amount:,} PR"),
"transfer_recv":"🎁 Вам переведено <b>{amount:,} PR</b> от <code>{from_id}</code>!",
"transfer_no_user":"❌ Пользователь не найден!",
"transfer_no_funds":"❌ Недостаточно PR! У вас: <b>{pr:,} PR</b>",
"transfer_cancel":"❌ Перевод отменён.",
"transfer_self":"❌ Нельзя переводить самому себе!",
# Обмен
"obmen_choose":"💱 <b>Обмен</b>\n\n🎟 PR: <b>{pr:,} PR</b>\n💵 USD: <b>{usd:.4f} $</b>\n\nКурс: <b>1$ = {pr_per_usd:,} PR</b>\n\nВыберите направление:",
"obmen_pr_to_usd_ask":"💱 <b>PR → $</b>\n\nСколько PR обменять?\nУ вас: <b>{pr:,} PR</b>\n\nКурс: {pr_per_usd:,} PR = 1$\n\nВведите сумму:",
"obmen_usd_to_pr_ask":"💱 <b>$ → PR</b>\n\nСколько $ обменять?\nУ вас: <b>{usd:.4f} $</b>\n\nКурс: 1$ = {pr_per_usd:,} PR\n\nВведите сумму (напр: 0.5):",
"obmen_pr_to_usd_confirm":"✅ Подтверждение:\n\n💸 Отдаёте: <b>{pr:,} PR</b>\n💵 Получаете: <b>{usd:.4f} $</b>\n\nПодтвердить?",
"obmen_usd_to_pr_confirm":"✅ Подтверждение:\n\n💵 Отдаёте: <b>{usd:.4f} $</b>\n💸 Получаете: <b>{pr:,} PR</b>\n\nПодтвердить?",
"obmen_ok_pr_to_usd":"✅ <b>Обмен выполнен!</b>\n\n➖ <b>{pr:,} PR</b> списано\n➕ <b>{usd:.4f} $</b> зачислено\n\n🎟 PR: <b>{bal_pr:,} PR</b>\n💵 USD: <b>{bal_usd:.4f} $</b>",
"obmen_ok_usd_to_pr":"✅ <b>Обмен выполнен!</b>\n\n➖ <b>{usd:.4f} $</b> списано\n➕ <b>{pr:,} PR</b> зачислено\n\n🎟 PR: <b>{bal_pr:,} PR</b>\n💵 USD: <b>{bal_usd:.4f} $</b>",
"obmen_no_pr":"❌ Недостаточно PR! У вас: <b>{pr:,} PR</b>",
"obmen_no_usd":"❌ Недостаточно $! У вас: <b>{usd:.4f} $</b>",
"obmen_invalid":"❌ Неверная сумма! Попробуйте снова.",
"obmen_cancel":"❌ Обмен отменён.",
"obmen_min_pr":"❌ Минимальная сумма: <b>{min_pr:,} PR</b>",
# Game
"game_menu":"🎲 <b>Игровой зал</b>\n\n💰 Баланс: <b>{pr:,} PR</b>",
"rooms_list":"🎮 <b>Открытые комнаты ({count} шт.):</b>\n\nВыберите или создайте новую:",
"rooms_empty":"😔 Нет открытых комнат.\nСоздайте первую!",
"room_detail":("🎮 <b>Комната #{gid}</b>\n\n👤 Игрок: <code>#{creator_id}</code>\n🎟 Ставка: <b>{stake:,} PR</b>\n\nВойти в игру?"),
"already_wait":"⏳ Вы уже ожидаете в комнате!",
"not_enough":"😞 <b>Недостаточно PR!</b>\nСтавка: <b>{stake:,} PR</b>\nУ вас: <b>{pr:,} PR</b>\n\nКупить PR: {support}",
"room_created":"⏳ <b>Комната создана!</b>\n\n🆔 ID: <code>#{gid}</code>\n🎟 Ставка: <b>{stake:,} PR</b>\n\nОжидание соперника... 👀",
"game_started":("🎲 <b>Игра началась!</b>\n\n🆔 Комната: #{gid}\n🎟 Ставка: {stake:,} PR\n\n🔴 <code>#{p1}</code> vs 🔵 <code>#{p2}</code>\n\n⏱ {turn_name} бросает кость!"),
"your_turn":"🎲 Ваш ход! Бросьте кость:",
"wait_turn":"⏳ Ждите хода соперника...",
"your_turn_now":"🎲 Теперь ваш ход! Бросьте кость:",
"timeout_cancel":"⏰ <b>Время вышло!</b>\n\nИгра отменена, ставки возвращены.",
"win_text":("😊 <b>Вы победили!</b>\n\n😍 Выигрыш: <b>+{win:,} PR</b>\n💸 Комиссия (5%): <b>-{commission:,} PR</b>\n\n🆔 ID игры: #{gid}\n🎟 Ставка: {stake:,} PR\n✅ Победил: <code>#{winner}</code> — 🎲 {w_dice}\n🔴 Проиграл: <code>#{loser}</code> — 🎲 {l_dice}\n\n🎟 Баланс: <b>{bal:,} PR</b>"),
"loss_text":("😢 <b>Вы проиграли!</b>\n\n🆔 ID игры: #{gid}\n🎟 Ставка: {stake:,} PR\n✅ Победил: <code>#{winner}</code> — 🎲 {w_dice}\n🔴 Проиграл: <code>#{loser}</code> — 🎲 {l_dice}\n\n🎟 Баланс: <b>{bal:,} PR</b>"),
"draw_text":("🤝 <b>Ничья! Ставки возвращены.</b>\n\n🆔 ID игры: #{gid}\n🎟 Ставка: {stake:,} PR\n🎲 У обоих: {val}\n\n🎟 Баланс: <b>{bal:,} PR</b>"),
"bonus_spin":"🎰 Прокручиваем бонус...",
"bonus_win":"🎉 <b>Ежедневный бонус!</b>\n\nВыпало: <b>{amount} PR</b>\n🎟 Баланс: <b>{bal:,} PR</b>",
"bonus_wait":"⏳ Бонус уже получен!\n🕐 Через <b>{h} ч. {m} мин.</b>",
"support_msg":"💬 <b>Поддержка:</b>\n\n{link}\n\nДля покупки PR и вопросов.",
"buy_pr":"🛍 <b>Купить PR</b>\n\nЦены:\n🎟 10 000 PR = 0.5$\n🎟 50 000 PR = 2.5$\n🎟 100 000 PR = 5$\n\nОбратитесь к администратору:",
"cancel_ok":"❌ Отменено.",
"lang_choose":"🌐 Выберите язык:",
"lang_set":"✅ Язык: <b>Русский</b>",
"admin_ok_pr":"✅ {uid} получил {amount:,} PR. PR баланс: {bal:,} PR",
"admin_ok_usd":"✅ {uid} получил {amount:.4f} $. USD баланс: {bal:.4f} $",
"admin_rate":"✅ Курс: 1$ = {uzs:,} сум | {pr_per_usd:,} PR",
"admin_only":"❌ Только для админов!",
"channel_check":"🎁 <b>Получить 10,000 PR бесплатно</b>\n\nСначала подпишитесь на канал:\n{link}\n\nПосле подписки нажмите кнопку 👇",
"channel_not_subscribed":"❌ Вы ещё не подписаны на канал!\n\nПодпишитесь: {link}\n\nЗатем попробуйте снова.",
"channel_already_claimed":"✅ Вы уже получили бонусные PR!\n\n🎟 Баланс: <b>{pr:,} PR</b>",
"channel_bonus_ok":"🎉 <b>Поздравляем!</b>\n\nЗа подписку на канал вам начислено <b>+{amount:,} PR</b>!\n\n🎟 Баланс: <b>{pr:,} PR</b>",
"btn_channel_bonus":"🎁 10,000 PR бесплатно",
"btn_check_sub":"✅ Подписался, получить PR",
"btn_game":"🎲 Игровой зал","btn_balance":"🎟 Баланс","btn_bonus":"🎁 Бонус",
"btn_support":"💬 Поддержка","btn_buy":"🛍 Купить PR","btn_lang":"🌐 Язык",
"btn_transfer":"💸 PR Перевод","btn_obmen":"💱 Обмен","btn_confirm":"✅ Подтвердить","btn_cancel":"❌ Отмена",
"btn_throw":"🎲 Бросить кость","btn_join":"✅ Войти","btn_profile":"👤 Профиль",
"btn_rooms":"🎮 Список комнат","btn_create":"➕ Новая комната","btn_back":"🔙 Назад",
"btn_pr_to_usd":"🎟➡️💵 PR → $","btn_usd_to_pr":"💵➡️🎟 $ → PR",
}
}

def tx(lang, key, **kw):
    tmpl = T.get(lang, T["uz"]).get(key, key)
    return tmpl.format(**kw) if kw else tmpl

# ════════════════════════════════════════════════════════
#  ⌨️  KLAVIATURALAR
# ════════════════════════════════════════════════════════
def main_kb(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=tx(lang,"btn_game")), KeyboardButton(text=tx(lang,"btn_balance"))],
        [KeyboardButton(text=tx(lang,"btn_bonus")), KeyboardButton(text=tx(lang,"btn_channel_bonus"))],
        [KeyboardButton(text=tx(lang,"btn_buy")), KeyboardButton(text=tx(lang,"btn_lang"))],
        [KeyboardButton(text=tx(lang,"btn_support"))],
    ], resize_keyboard=True)

def balance_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=tx(lang,"btn_transfer"), callback_data="transfer_start"),
            InlineKeyboardButton(text=tx(lang,"btn_obmen"), callback_data="obmen_start"),
        ],
        [
            InlineKeyboardButton(text=tx(lang,"btn_buy"), callback_data="buy_pr"),
        ],
    ])

def obmen_direction_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=tx(lang,"btn_pr_to_usd"), callback_data="obmen_pr_usd"),
            InlineKeyboardButton(text=tx(lang,"btn_usd_to_pr"), callback_data="obmen_usd_pr"),
        ],
        [InlineKeyboardButton(text=tx(lang,"btn_cancel"), callback_data="obmen_cancel")],
    ])

def obmen_confirm_kb(lang, direction, amount_pr, amount_usd):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=tx(lang,"btn_confirm"),
            callback_data=f"obmen_confirm_{direction}_{amount_pr}_{amount_usd}"
        ),
        InlineKeyboardButton(text=tx(lang,"btn_cancel"), callback_data="obmen_cancel"),
    ]])

def game_main_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_rooms"), callback_data="rooms_list"),
        InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room"),
    ]])

def stakes_kb(lang):
    rows = []; row = []
    for s in STAKES:
        row.append(InlineKeyboardButton(text=f"{s:,} PR", callback_data=f"newroom_{s}"))
        if len(row) == 3: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ O'z miqdorimni kiritaman", callback_data="custom_stake")])
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_back"), callback_data="game_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rooms_kb(lang, rooms):
    rows = []
    for gid, cid, stake in rooms:
        rows.append([InlineKeyboardButton(text=f"🎮 {stake:,} PR | #{cid}", callback_data=f"room_{gid}")])
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room")])
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_back"), callback_data="game_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def room_detail_kb(lang, gid, creator_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tx(lang,"btn_join"), callback_data=f"join_{gid}"),
         InlineKeyboardButton(text=tx(lang,"btn_profile"), url=f"tg://user?id={creator_id}")],
        [InlineKeyboardButton(text=tx(lang,"btn_back"), callback_data="rooms_list")],
    ])

def throw_kb(lang, gid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_throw"), callback_data=f"throw_{gid}")
    ]])

def transfer_confirm_kb(lang, to_id, amount):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_confirm"), callback_data=f"tr_yes_{to_id}_{amount}"),
        InlineKeyboardButton(text=tx(lang,"btn_cancel"), callback_data="tr_no"),
    ]])

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
    ]])

def support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Admin — @mirodil_info", url=SUPPORT_LINK)
    ]])

def channel_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga o'tish", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text=tx(lang,"btn_check_sub"), callback_data="channel_claim")],
    ])

# ════════════════════════════════════════════════════════
#  🎮  O'YIN LOGIKASI
# ════════════════════════════════════════════════════════
async def send_gif_and_text(chat_id, is_win, text):
    gif = WIN_GIF_ID if is_win else LOSS_GIF_ID
    sent = False
    try:
        await bot_obj.send_animation(chat_id, animation=gif, caption=text, parse_mode="HTML")
        sent = True
    except: pass
    if not sent:
        try:
            await bot_obj.send_document(chat_id, document=gif, caption=text, parse_mode="HTML")
            sent = True
        except: pass
    if not sent:
        await bot_obj.send_message(chat_id, text, parse_mode="HTML")

async def timeout_task(gid, stake, p1_id, p2_id):
    await asyncio.sleep(THROW_TIMEOUT)
    game = get_game(gid)
    if not game or game[4] not in ('p1_turn', 'p2_turn'): return
    cancel_game_db(gid)
    change_pr(p1_id, stake); change_pr(p2_id, stake)
    for uid in [p1_id, p2_id]:
        lang = get_lang(uid)
        try: await bot_obj.send_message(uid, tx(lang, "timeout_cancel"), parse_mode="HTML")
        except: pass

async def waiting_room_timeout(gid, uid):
    await asyncio.sleep(40)
    game = get_game(gid)
    if not game or game[4] != 'waiting': return
    cancel_game_db(gid)
    waiting_timers.pop(gid, None)
    lang = get_lang(uid)
    try:
        await bot_obj.send_message(uid,
            "⏰ <b>Xona yopildi!</b>\n\n40 sekund ichida hech kim kirmadi.",
            parse_mode="HTML")
    except: pass

async def resolve_game(gid):
    game = get_game(gid)
    if not game: return
    gid_, p1, p2, stake = game[0], game[1], game[2], game[3]
    p1_val, p2_val = game[5], game[6]
    lang1, lang2 = get_lang(p1), get_lang(p2)
    commission = int(stake * COMMISSION_PCT / 100)
    if p1_val == p2_val:
        change_pr(p1, stake); change_pr(p2, stake)
        finish_game_db(gid, 0)
        for uid, lang in [(p1, lang1), (p2, lang2)]:
            bal = get_pr(uid)
            await send_gif_and_text(uid, False, tx(lang,"draw_text", gid=gid, stake=stake, val=p1_val, bal=bal))
    else:
        winner_id = p1 if p1_val > p2_val else p2
        loser_id  = p2 if p1_val > p2_val else p1
        w_dice = p1_val if p1_val > p2_val else p2_val
        l_dice = p2_val if p1_val > p2_val else p1_val
        winnings = (stake * 2) - commission
        change_pr(winner_id, winnings)
        if ADMIN_IDS: change_pr(ADMIN_IDS[0], commission)
        add_win(winner_id); add_loss(loser_id)
        finish_game_db(gid, winner_id)
        winner_bal = get_pr(winner_id); loser_bal = get_pr(loser_id)
        wlang = get_lang(winner_id); llang = get_lang(loser_id)
        await send_gif_and_text(winner_id, True,
            tx(wlang,"win_text", gid=gid, stake=stake, win=winnings-stake,
               commission=commission, winner=winner_id, loser=loser_id, w_dice=w_dice, l_dice=l_dice, bal=winner_bal))
        await send_gif_and_text(loser_id, False,
            tx(llang,"loss_text", gid=gid, stake=stake,
               winner=winner_id, loser=loser_id, w_dice=w_dice, l_dice=l_dice, bal=loser_bal))

# ════════════════════════════════════════════════════════
#  📲  HANDLERLAR
# ════════════════════════════════════════════════════════
@dp.message(Command("start"))
async def h_start(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    await msg.answer(tx(lang,"welcome"), parse_mode="HTML", reply_markup=main_kb(lang))

@dp.message(F.text.in_(["🎟 Balans","🎟 Баланс"]))
async def h_balance(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    pr  = get_pr(uid)
    usd = get_usd_bal(uid)
    await msg.answer(
        tx(lang,"balance", pr=pr, usd=usd, pr_per_usd=PR_PER_DOLLAR),
        parse_mode="HTML", reply_markup=balance_kb(lang)
    )

# ─── Transfer ───────────────────────────────────────────
@dp.callback_query(F.data == "transfer_start")
async def cb_transfer_start(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    user_states[uid] = {'step': 'transfer_id'}
    await cb.message.answer(tx(lang,"transfer_ask_id"), parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data == "tr_no")
async def cb_tr_no(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    user_states.pop(uid, None)
    await cb.message.edit_text(tx(lang,"transfer_cancel"))
    await cb.answer()

@dp.callback_query(F.data.startswith("tr_yes_"))
async def cb_tr_yes(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    parts = cb.data.split("_"); to_id = int(parts[2]); amount = int(parts[3])
    ok, reason = do_transfer(uid, to_id, amount)
    if ok:
        await cb.message.edit_text(tx(lang,"transfer_ok", to_id=to_id, amount=amount), parse_mode="HTML")
        to_lang = get_lang(to_id)
        try: await bot_obj.send_message(to_id, tx(to_lang,"transfer_recv", from_id=uid, amount=amount), parse_mode="HTML")
        except: pass
    else:
        pr = get_pr(uid)
        await cb.message.edit_text(tx(lang,"transfer_no_funds", pr=pr), parse_mode="HTML")
    user_states.pop(uid, None); await cb.answer()

# ─── Obmen (Ayirboshlash) ───────────────────────────────
@dp.callback_query(F.data == "obmen_start")
async def cb_obmen_start(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    pr  = get_pr(uid); usd = get_usd_bal(uid)
    await cb.message.answer(
        tx(lang,"obmen_choose", pr=pr, usd=usd, pr_per_usd=PR_PER_DOLLAR),
        parse_mode="HTML", reply_markup=obmen_direction_kb(lang)
    )
    await cb.answer()

@dp.callback_query(F.data == "obmen_pr_usd")
async def cb_obmen_pr_usd(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    pr = get_pr(uid)
    user_states[uid] = {'step': 'obmen_pr_to_usd'}
    await cb.message.edit_text(
        tx(lang,"obmen_pr_to_usd_ask", pr=pr, pr_per_usd=PR_PER_DOLLAR),
        parse_mode="HTML"
    )
    await cb.answer()

@dp.callback_query(F.data == "obmen_usd_pr")
async def cb_obmen_usd_pr(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    usd = get_usd_bal(uid)
    user_states[uid] = {'step': 'obmen_usd_to_pr'}
    await cb.message.edit_text(
        tx(lang,"obmen_usd_to_pr_ask", usd=usd, pr_per_usd=PR_PER_DOLLAR),
        parse_mode="HTML"
    )
    await cb.answer()

@dp.callback_query(F.data == "obmen_cancel")
async def cb_obmen_cancel(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    user_states.pop(uid, None)
    await cb.message.edit_text(tx(lang,"obmen_cancel"))
    await cb.answer()

@dp.callback_query(F.data.startswith("obmen_confirm_"))
async def cb_obmen_confirm(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    # obmen_confirm_{direction}_{amount_pr}_{amount_usd_x10000}
    parts = cb.data.split("_")
    direction = parts[2]
    amount_pr  = int(parts[3])
    amount_usd = int(parts[4]) / 10000.0

    if direction == "prtousd":
        pr = get_pr(uid)
        if pr < amount_pr:
            await cb.answer(tx(lang,"obmen_no_pr", pr=pr), show_alert=True); return
        change_pr(uid, -amount_pr)
        change_usd(uid, amount_usd)
        bal_pr  = get_pr(uid); bal_usd = get_usd_bal(uid)
        await cb.message.edit_text(
            tx(lang,"obmen_ok_pr_to_usd", pr=amount_pr, usd=amount_usd, bal_pr=bal_pr, bal_usd=bal_usd),
            parse_mode="HTML"
        )
    else:  # usdtopr
        usd = get_usd_bal(uid)
        if usd < amount_usd - 0.00001:
            await cb.answer(tx(lang,"obmen_no_usd", usd=usd), show_alert=True); return
        change_usd(uid, -amount_usd)
        change_pr(uid, amount_pr)
        bal_pr  = get_pr(uid); bal_usd = get_usd_bal(uid)
        await cb.message.edit_text(
            tx(lang,"obmen_ok_usd_to_pr", usd=amount_usd, pr=amount_pr, bal_pr=bal_pr, bal_usd=bal_usd),
            parse_mode="HTML"
        )
    user_states.pop(uid, None)
    await cb.answer()

# ─── Buy PR ─────────────────────────────────────────────
@dp.callback_query(F.data == "buy_pr")
async def cb_buy_pr(cb: types.CallbackQuery):
    lang = get_lang(cb.from_user.id)
    await cb.message.answer(tx(lang,"buy_pr"), parse_mode="HTML", reply_markup=support_kb())
    await cb.answer()

# ─── Game ────────────────────────────────────────────────
@dp.message(F.text.in_(["🎲 O'yin xonasi","🎲 Игровой зал"]))
async def h_game(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid); pr = get_pr(uid)
    await msg.answer(tx(lang,"game_menu", pr=pr), parse_mode="HTML", reply_markup=game_main_kb(lang))

@dp.callback_query(F.data == "game_back")
async def cb_game_back(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid); pr = get_pr(uid)
    await cb.message.edit_text(tx(lang,"game_menu", pr=pr), parse_mode="HTML", reply_markup=game_main_kb(lang))
    await cb.answer()

@dp.callback_query(F.data == "rooms_list")
async def cb_rooms(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    rooms = get_waiting_games(exclude_uid=uid)
    if not rooms:
        await cb.message.edit_text(tx(lang,"rooms_empty"), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room")],
                [InlineKeyboardButton(text=tx(lang,"btn_back"), callback_data="game_back")],
            ]))
    else:
        await cb.message.edit_text(tx(lang,"rooms_list", count=len(rooms)), parse_mode="HTML",
                                    reply_markup=rooms_kb(lang, rooms))
    await cb.answer()

@dp.callback_query(F.data.startswith("room_"))
async def cb_room_detail(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    gid = int(cb.data.split("_")[1]); game = get_game(gid)
    if not game or game[4] != 'waiting':
        await cb.answer("❌ Xona topilmadi yoki to'lgan!", show_alert=True); return
    await cb.message.edit_text(tx(lang,"room_detail", gid=gid, creator_id=game[1], stake=game[3]),
                                parse_mode="HTML", reply_markup=room_detail_kb(lang, gid, game[1]))
    await cb.answer()

@dp.callback_query(F.data.startswith("profile_"))
async def cb_profile(cb: types.CallbackQuery):
    lang = get_lang(cb.from_user.id); view_id = int(cb.data.split("_")[1])
    u = get_user(view_id)
    if not u: await cb.answer("❌ Foydalanuvchi topilmadi!", show_alert=True); return
    name = u[2] or u[1] or f"#{view_id}"
    usd  = get_usd_bal(view_id)
    await cb.answer(
        tx(lang,"profile", uid=view_id, name=name, pr=u[3], usd=usd, wins=u[6], losses=u[7]),
        show_alert=True
    )

@dp.callback_query(F.data == "create_room")
async def cb_create_room(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    if has_waiting(uid): await cb.answer(tx(lang,"already_wait"), show_alert=True); return
    await cb.message.edit_text(tx(lang,"game_menu", pr=get_pr(uid)), parse_mode="HTML", reply_markup=stakes_kb(lang))
    await cb.answer()

@dp.callback_query(F.data.startswith("newroom_"))
async def cb_newroom(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    stake = int(cb.data.split("_")[1]); pr = get_pr(uid)
    if pr < stake:
        await cb.answer(tx(lang,"not_enough", stake=stake, pr=pr, support=SUPPORT_LINK), show_alert=True); return
    gid = create_game(uid, stake)
    task = asyncio.create_task(waiting_room_timeout(gid, uid))
    waiting_timers[gid] = task
    await cb.message.edit_text(tx(lang,"room_created", gid=gid, stake=stake), parse_mode="HTML")
    await cb.answer()
@dp.callback_query(F.data == "custom_stake")
async def cb_custom_stake(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    if has_waiting(uid):
        await cb.answer("⏳ Siz allaqachon xona kutmoqdasiz!", show_alert=True); return
    user_states[uid] = {'step': 'custom_stake'}
    await cb.message.edit_text(
        "✏️ <b>O'z stavkangizni kiriting</b>\n\n💡 100 dan 10,000 gacha son kiriting:",
        parse_mode="HTML"
    )
    await cb.answer()
@dp.callback_query(F.data.startswith("join_"))
async def cb_join(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    gid = int(cb.data.split("_")[1]); game = get_game(gid)
    if not game or game[4] != 'waiting':
        await cb.answer("❌ Xona mavjud emas!", show_alert=True); return
    p1, stake = game[1], game[3]
    if uid == p1: await cb.answer("❌ O'z xonangizga qo'shila olmaysiz!", show_alert=True); return
    pr = get_pr(uid)
    if pr < stake:
        await cb.answer(tx(lang,"not_enough", stake=stake, pr=pr, support=SUPPORT_LINK), show_alert=True); return
    p1_pr = get_pr(p1)
    if p1_pr < stake:
        cancel_waiting(p1)
        await cb.answer("❌ Xona yaratuvchida PR yetarli emas!", show_alert=True); return
    if gid in waiting_timers:
        waiting_timers[gid].cancel()
        del waiting_timers[gid]
    change_pr(uid, -stake); change_pr(p1, -stake)
    start_game(gid, uid)
    p1_lang = get_lang(p1); p2_lang = lang
    started_p1 = tx(p1_lang,"game_started", gid=gid, stake=stake, p1=p1, p2=uid, turn_name=f"#{p1}")
    started_p2 = tx(p2_lang,"game_started", gid=gid, stake=stake, p1=p1, p2=uid, turn_name=f"#{p1}")
    try: await bot_obj.send_message(p1, started_p1, parse_mode="HTML", reply_markup=throw_kb(p1_lang, gid))
    except: pass
    await cb.message.answer(started_p2 + "\n\n" + tx(p2_lang,"wait_turn"), parse_mode="HTML")
    task = asyncio.create_task(timeout_task(gid, stake, p1, uid))
    game_timers[gid] = task
    await cb.answer()

@dp.callback_query(F.data.startswith("throw_"))
async def cb_throw(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    gid = int(cb.data.split("_")[1]); game = get_game(gid)
    if not game: await cb.answer("❌ O'yin topilmadi!", show_alert=True); return
    status, p1, p2, stake = game[4], game[1], game[2], game[3]
    if status == 'p1_turn' and uid != p1: await cb.answer("⏳ Hozir raqib navbati!", show_alert=True); return
    if status == 'p2_turn' and uid != p2: await cb.answer("⏳ Raqib navbati!", show_alert=True); return
    if status not in ('p1_turn', 'p2_turn'): await cb.answer("❌ Noto'g'ri holat!", show_alert=True); return
    try: await cb.message.edit_reply_markup()
    except: pass
    dice_msg = await bot_obj.send_dice(cb.message.chat.id, emoji="🎲")
    val = dice_msg.dice.value
    await asyncio.sleep(4)
    if status == 'p1_turn':
        set_p1_dice(gid, val)
        p2_lang = get_lang(p2)
        await bot_obj.send_message(p1, f"✅ Siz tosh taShladingiz: <b>{val}</b>\n\n⏳ Raqib tashlashini kuting...", parse_mode="HTML")
        try: await bot_obj.send_message(p2, tx(p2_lang,"your_turn_now"), parse_mode="HTML", reply_markup=throw_kb(p2_lang, gid))
        except: pass
        if gid in game_timers: game_timers[gid].cancel()
        game_timers[gid] = asyncio.create_task(timeout_task(gid, stake, p1, p2))
    else:
        set_p2_dice(gid, val)
        await bot_obj.send_message(p2, f"✅ Siz tosh taShladingiz: <b>{val}</b>\n\n⏳ Natija hisoblanmoqda...", parse_mode="HTML")
        if gid in game_timers: game_timers[gid].cancel(); del game_timers[gid]
        await resolve_game(gid)
    await cb.answer()

# ─── Bonus ──────────────────────────────────────────────
@dp.message(F.text.in_(["🎁 Kunlik bonus","🎁 Бонус"]))
async def h_bonus(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    ok, result = claim_bonus(uid)
    if not ok:
        h, m = result
        await msg.answer(tx(lang,"bonus_wait", h=h, m=m), parse_mode="HTML"); return
    wait = await msg.answer(tx(lang,"bonus_spin"))
    await bot_obj.send_dice(msg.chat.id, emoji="🎰")
    await asyncio.sleep(3); await wait.delete()
    await msg.answer(tx(lang,"bonus_win", amount=result, bal=get_pr(uid)), parse_mode="HTML")

@dp.message(F.text.in_(["🛍 PR sotib olish","🛍 Купить PR"]))
async def h_buy(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"buy_pr"), parse_mode="HTML", reply_markup=support_kb())

@dp.message(F.text.in_(["💬 Murojaat","💬 Поддержка"]))
async def h_support(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"support_msg", link=SUPPORT_LINK), parse_mode="HTML", reply_markup=support_kb())

@dp.message(F.text.in_(["🌐 Til","🌐 Язык"]))
async def h_lang(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"lang_choose"), reply_markup=lang_kb())

@dp.callback_query(F.data.startswith("lang_"))
async def cb_lang(cb: types.CallbackQuery):
    lang = cb.data.split("_")[1]; set_lang(cb.from_user.id, lang)
    await cb.message.delete()
    await cb.message.answer(tx(lang,"lang_set"), parse_mode="HTML", reply_markup=main_kb(lang))
    await cb.answer()

BUTTON_TEXTS = [
    "🎁 10,000 PR tekinga olish", "🎁 10,000 PR бесплатно",
    "🎟 Balans", "🎟 Баланс",
    "🎁 Kunlik bonus", "🎁 Бонус",
    "🛍 PR sotib olish", "🛍 Купить PR",
    "💬 Murojaat", "💬 Поддержка",
    "🌐 Til", "🌐 Язык",
    "🎲 O'yin xonasi", "🎲 Игровой зал",
]
# ─── Text input handler (transfer + obmen) ──────────────
@dp.message(F.text & ~F.text.startswith("/") & ~F.text.in_(BUTTON_TEXTS))
async def h_text(msg: types.Message):
    uid   = msg.from_user.id
    lang  = get_lang(uid)
    state = user_states.get(uid)
    if not state: return
    text  = msg.text.strip()

    # ── Transfer flow ──
    if state['step'] == 'transfer_id':
        if not text.isdigit(): await msg.answer("❌ Faqat raqam kiriting!"); return
        to_id = int(text)
        if to_id == uid: await msg.answer(tx(lang,"transfer_self")); user_states.pop(uid,None); return
        to_u = get_user(to_id)
        if not to_u: await msg.answer(tx(lang,"transfer_no_user"), parse_mode="HTML"); return
        user_states[uid] = {'step': 'transfer_amount', 'to_id': to_id}
        name = to_u[2] or to_u[1] or f"#{to_id}"
        await msg.answer(tx(lang,"transfer_ask_amt", name=name, uid=to_id, pr=get_pr(uid)), parse_mode="HTML")

    elif state['step'] == 'transfer_amount':
        if not text.isdigit(): await msg.answer("❌ Faqat raqam kiriting!"); return
        amount = int(text); to_id = state['to_id']; pr = get_pr(uid)
        if amount <= 0: await msg.answer("❌ 0 dan katta raqam kiriting!"); return
        if amount > pr: await msg.answer(tx(lang,"transfer_no_funds", pr=pr), parse_mode="HTML"); return
        user_states.pop(uid, None)
        await msg.answer(tx(lang,"transfer_confirm", to_id=to_id, amount=amount),
                         parse_mode="HTML", reply_markup=transfer_confirm_kb(lang, to_id, amount))

    # ── Obmen flow: PR → $ ──
    elif state['step'] == 'obmen_pr_to_usd':
        if not text.isdigit():
            await msg.answer(tx(lang,"obmen_invalid")); return
        amount_pr = int(text)
        if amount_pr < PR_PER_DOLLAR:
            await msg.answer(tx(lang,"obmen_min_pr", min_pr=PR_PER_DOLLAR), parse_mode="HTML"); return
        pr = get_pr(uid)
        if amount_pr > pr:
            await msg.answer(tx(lang,"obmen_no_pr", pr=pr), parse_mode="HTML"); return
        amount_usd = amount_pr / PR_PER_DOLLAR
        # amount_usd ni int ga o'tkazish uchun * 10000 saqlaymiz
        usd_key = int(round(amount_usd * 10000))
        user_states.pop(uid, None)
        await msg.answer(
            tx(lang,"obmen_pr_to_usd_confirm", pr=amount_pr, usd=amount_usd),
            parse_mode="HTML",
            reply_markup=obmen_confirm_kb(lang, "prtousd", amount_pr, usd_key)
        )

    # ── Obmen flow: $ → PR ──
    elif state['step'] == 'obmen_usd_to_pr':
        try:
            text_clean = text.replace(",", ".")
            amount_usd = float(text_clean)
            if amount_usd <= 0: raise ValueError()
        except:
            await msg.answer(tx(lang,"obmen_invalid")); return
        usd = get_usd_bal(uid)
        if amount_usd > usd + 0.00001:
            await msg.answer(tx(lang,"obmen_no_usd", usd=usd), parse_mode="HTML"); return
        amount_pr = int(amount_usd * PR_PER_DOLLAR)
        if amount_pr <= 0:
            await msg.answer(tx(lang,"obmen_min_pr", min_pr=1), parse_mode="HTML"); return
        usd_key = int(round(amount_usd * 10000))
        user_states.pop(uid, None)
        await msg.answer(
            tx(lang,"obmen_usd_to_pr_confirm", usd=amount_usd, pr=amount_pr),
            parse_mode="HTML",
            reply_markup=obmen_confirm_kb(lang, "usdtopr", amount_pr, usd_key)
        )
    elif state['step'] == 'custom_stake':
        if not text.isdigit():
            await msg.answer("❌ Faqat raqam kiriting!"); return
        amount = int(text)
        if amount < 100 or amount > 10000:
            await msg.answer("❌ 100 dan 10,000 gacha son kiriting!"); return
        pr = get_pr(uid)
        if pr < amount:
            await msg.answer(f"❌ Yetarli PR yo'q! Sizda: {pr:,} PR"); return
        user_states.pop(uid, None)
        gid = create_game(uid, amount)
        task = asyncio.create_task(waiting_room_timeout(gid, uid))
        waiting_timers[gid] = task
        await msg.answer(
            f"⏳ <b>Xona yaratildi!</b>\n\n🆔 Xona ID: <code>#{gid}</code>\n🎟 Stavka: <b>{amount:,} PR</b>\n\nRaqib kutilmoqda... 👀",
            parse_mode="HTML"
        )
@dp.message(F.text.in_(["🎁 10,000 PR tekinga olish","🎁 10,000 PR бесплатно"]))
async def h_channel_bonus(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    if is_channel_claimed(uid):
        await msg.answer(tx(lang,"channel_already_claimed", pr=get_pr(uid)), parse_mode="HTML"); return
    await msg.answer(
        tx(lang,"channel_check", link=CHANNEL_LINK),
        parse_mode="HTML",
        reply_markup=channel_kb(lang)
    )

@dp.callback_query(F.data == "channel_claim")
async def cb_channel_claim(cb: types.CallbackQuery):
    uid = cb.from_user.id; lang = get_lang(uid)
    if is_channel_claimed(uid):
        await cb.answer(tx(lang,"channel_already_claimed", pr=get_pr(uid)), show_alert=True); return
    try:
        member = await bot_obj.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=uid)
        is_member = member.status not in ("left", "kicked", "banned")
    except:
        is_member = False
    if not is_member:
        await cb.answer(tx(lang,"channel_not_subscribed", link=CHANNEL_LINK), show_alert=True); return
    set_channel_claimed(uid)
    change_pr(uid, CHANNEL_PR_GIFT)
    pr = get_pr(uid)
    await cb.message.edit_text(
        tx(lang,"channel_bonus_ok", amount=CHANNEL_PR_GIFT, pr=pr),
        parse_mode="HTML"
    )
    await cb.answer()

# ════════════════════════════════════════════════════════
#  👑  ADMIN BUYRUQLARI
# ════════════════════════════════════════════════════════
def is_admin(uid): return uid in ADMIN_IDS

@dp.message(Command("give_pr"))
@dp.message(Command("give"))
async def cmd_give_pr(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    p = msg.text.split()
    if len(p) != 3 or not p[1].isdigit() or not p[2].isdigit():
        await msg.answer("❌ Format: /give_pr <miqdor> <user_id>"); return
    uid, amount = int(p[2]), int(p[1])
    change_pr(uid, amount)
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"admin_ok_pr", uid=uid, amount=amount, bal=get_pr(uid)), parse_mode="HTML")

@dp.message(Command("give_usd"))
async def cmd_give_usd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    p = msg.text.split()
    if len(p) != 3:
        await msg.answer("❌ Format: /give_usd <miqdor> <user_id>\nMasalan: /give_usd 1.5 123456"); return
    try:
        uid = int(p[2])
        amount = float(p[1])
        if amount <= 0: raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri format! Masalan: /give_usd 123456 1.5"); return
    u = get_user(uid)
    if not u:
        await msg.answer("❌ Foydalanuvchi topilmadi!"); return
    change_usd(uid, amount)
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"admin_ok_usd", uid=uid, amount=amount, bal=get_usd_bal(uid)), parse_mode="HTML")

@dp.message(Command("rate"))
async def cmd_rate(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    p = msg.text.split()
    if len(p) != 2 or not p[1].isdigit():
        await msg.answer("❌ Format: /rate <kurs_so'm>\nMasalan: /rate 13000"); return
    uzs = int(p[1])
    set_setting("usd_uzs", uzs)
    set_setting("rate_fetch", datetime.now().isoformat())
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"admin_rate", uzs=uzs, pr_per_usd=PR_PER_DOLLAR), parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    users, games, wait, xfers = get_stats()
    await msg.answer(
        f"📊 <b>Statistika:</b>\n\n👤 Foydalanuvchilar: <b>{users:,}</b>\n"
        f"🎲 Tugagan o'yinlar: <b>{games:,}</b>\n⏳ Kutayotgan: <b>{wait}</b>\n"
        f"💸 Transferlar: <b>{xfers[0]:,}</b> ta / <b>{xfers[1]:,}</b> PR",
        parse_mode="HTML")
@dp.message(Command("take_pr"))
async def cmd_take_pr(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Faqat admin!"); return
    p = msg.text.split()
    if len(p) != 3 or not p[1].isdigit() or not p[2].isdigit():
        await msg.answer("❌ Format: /take_pr <miqdor> <user_id>"); return
    amount, uid = int(p[1]), int(p[2])
    u = get_user(uid)
    if not u:
        await msg.answer("❌ Foydalanuvchi topilmadi!"); return
    if u[3] < amount:
        await msg.answer(f"❌ Foydalanuvchida faqat {u[3]:,} PR bor!"); return
    change_pr(uid, -amount)
    await msg.answer(f"✅ {uid} dan {amount:,} PR ayirildi. PR balansi: {get_pr(uid):,} PR")

@dp.message(Command("take_usd"))
async def cmd_take_usd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Faqat admin!"); return
    p = msg.text.split()
    if len(p) != 3:
        await msg.answer("❌ Format: /take_usd <miqdor> <user_id>"); return
    try:
        amount, uid = float(p[1]), int(p[2])
        if amount <= 0: raise ValueError()
    except:
        await msg.answer("❌ Noto'g'ri format!"); return
    u = get_user(uid)
    if not u:
        await msg.answer("❌ Foydalanuvchi topilmadi!"); return
    if get_usd_bal(uid) < amount:
        await msg.answer(f"❌ Foydalanuvchida faqat {get_usd_bal(uid):.4f} $ bor!"); return
    change_usd(uid, -amount)
    await msg.answer(f"✅ {uid} dan {amount:.4f} $ ayirildi. USD balansi: {get_usd_bal(uid):.4f} $")
# ════════════════════════════════════════════════════════
async def main():
    init_db()
    print("✅ PRm4u Bot v2.2 + PostgreSQL ishga tushdi!")
    await dp.start_polling(bot_obj)

if __name__ == "__main__":
    asyncio.run(main())
