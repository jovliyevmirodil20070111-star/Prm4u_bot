"""
╔══════════════════════════════════════════════════════╗
║         PRm4u GAME BOT  v2.0  — @mirodil_info        ║
║  O'rnatish:  pip install aiogram aiohttp             ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio, sqlite3, random, aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# ════════════════════════════════════════════════════════
#  ⚙️  SOZLAMALAR
# ════════════════════════════════════════════════════════
TOKEN          = "8720740940:AAGE1imTXRGhtOZ-fYH_nzh1tJstwgCeE38"
SUPPORT_LINK   = "https://t.me/mirodil_info"
ADMIN_IDS      = [5656375477]
PR_PER_DOLLAR  = 20_000          # 10 000 PR = 0.5$
COMMISSION_PCT = 5               # 5% komissiya
WIN_GIF_ID     = "CgACAgQAAxkBAAFJuWlqB4DEKxfR8xGgIi11Hpbyi9FviAACvwIAAhn8VVGXEPylDK8y3DsE"
LOSS_GIF_ID    = "CgACAgQAAxkBAAFJuWdqB4DBtfQlp_oKd8LheQFKFCEsCAACpQIAAqnITFF-EHFNd1WImjsE"
STAKES         = [500, 1_000, 2_000, 3_000, 5_000, 10_000]
THROW_TIMEOUT  = 180             # 3 daqiqa — tosh tashlash vaqti

DB = "prm4u.db"
bot_obj = Bot(token=TOKEN)
dp      = Dispatcher()

# Ko'p bosqichli amallar uchun xotira
user_states   = {}   # {uid: {'step': ..., ...}}
game_timers   = {}   # {gid: asyncio.Task}

# ════════════════════════════════════════════════════════
#  🗄️  DATABASE
# ════════════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id   INTEGER PRIMARY KEY,
        username  TEXT    DEFAULT '',
        full_name TEXT    DEFAULT '',
        pr        INTEGER DEFAULT 1000,
        last_bonus TEXT   DEFAULT '',
        lang      TEXT    DEFAULT 'uz',
        wins      INTEGER DEFAULT 0,
        losses    INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS games (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        joiner_id  INTEGER DEFAULT 0,
        stake      INTEGER,
        status     TEXT    DEFAULT 'waiting',
        p1_dice    INTEGER DEFAULT 0,
        p2_dice    INTEGER DEFAULT 0,
        winner_id  INTEGER DEFAULT 0,
        created_at TEXT,
        started_at TEXT    DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transfers (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id    INTEGER,
        to_id      INTEGER,
        amount     INTEGER,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('usd_uzs','12700')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('rate_fetch','')")
    conn.commit(); conn.close()

def dbc(): return sqlite3.connect(DB)

def register(uid, username, full_name):
    conn = dbc()
    conn.execute("INSERT OR IGNORE INTO users (user_id,username,full_name) VALUES (?,?,?)",
                 (uid, username or "", full_name or ""))
    conn.commit(); conn.close()

def get_user(uid):
    conn = dbc(); r = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close(); return r

def get_pr(uid):   u = get_user(uid); return u[3] if u else 0
def get_lang(uid): u = get_user(uid); return u[5] if u else 'uz'
def get_wl(uid):   u = get_user(uid); return (u[6], u[7]) if u else (0, 0)

def set_lang(uid, lang):
    conn = dbc(); conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang,uid)); conn.commit(); conn.close()

def change_pr(uid, delta):
    conn = dbc(); conn.execute("UPDATE users SET pr=MAX(0,pr+?) WHERE user_id=?", (delta,uid)); conn.commit(); conn.close()

def add_win(uid):
    conn = dbc(); conn.execute("UPDATE users SET wins=wins+1 WHERE user_id=?", (uid,)); conn.commit(); conn.close()

def add_loss(uid):
    conn = dbc(); conn.execute("UPDATE users SET losses=losses+1 WHERE user_id=?", (uid,)); conn.commit(); conn.close()

def get_setting(k):
    conn = dbc(); r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    conn.close(); return r[0] if r else None

def set_setting(k, v):
    conn = dbc(); conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (k,str(v)))
    conn.commit(); conn.close()

# ── Transfer ─────────────────────────────────────────────
def do_transfer(from_id, to_id, amount):
    conn = dbc()
    fp = conn.execute("SELECT pr FROM users WHERE user_id=?", (from_id,)).fetchone()
    tu = conn.execute("SELECT user_id FROM users WHERE user_id=?", (to_id,)).fetchone()
    if not fp or fp[0] < amount or not tu:
        conn.close(); return False, "no_funds" if fp and fp[0] < amount else "no_user"
    conn.execute("UPDATE users SET pr=pr-? WHERE user_id=?", (amount, from_id))
    conn.execute("UPDATE users SET pr=pr+? WHERE user_id=?", (amount, to_id))
    conn.execute("INSERT INTO transfers (from_id,to_id,amount,created_at) VALUES (?,?,?,?)",
                 (from_id, to_id, amount, datetime.now().isoformat()))
    conn.commit(); conn.close(); return True, "ok"

# ── Bonus ────────────────────────────────────────────────
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
    conn = dbc()
    conn.execute("UPDATE users SET pr=pr+?,last_bonus=? WHERE user_id=?",
                 (amount, now.isoformat(), uid))
    conn.commit(); conn.close(); return True, amount

# ── USD kurs (kuniga 1 marta) ────────────────────────────
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
                d   = await r.json()
                uzs = int(d["rates"]["UZS"])
                set_setting("usd_uzs",   uzs)
                set_setting("rate_fetch", now.isoformat())
                return uzs
    except:
        return int(get_setting("usd_uzs") or 12700)

# ── Game DB ──────────────────────────────────────────────
def create_game(uid, stake):
    conn = dbc()
    cur  = conn.execute("INSERT INTO games (creator_id,stake,created_at) VALUES (?,?,?)",
                        (uid, stake, datetime.now().isoformat()))
    gid  = cur.lastrowid; conn.commit(); conn.close(); return gid

def get_waiting_games(exclude_uid=None):
    conn = dbc()
    q = "SELECT id,creator_id,stake FROM games WHERE status='waiting'"
    if exclude_uid: q += f" AND creator_id!={exclude_uid}"
    q += " ORDER BY created_at LIMIT 20"
    r = conn.execute(q).fetchall(); conn.close(); return r

def get_game(gid):
    conn = dbc(); r = conn.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
    conn.close(); return r

def start_game(gid, joiner_id):
    conn = dbc()
    conn.execute("UPDATE games SET joiner_id=?,status='p1_turn',started_at=? WHERE id=?",
                 (joiner_id, datetime.now().isoformat(), gid))
    conn.commit(); conn.close()

def set_p1_dice(gid, val):
    conn = dbc(); conn.execute("UPDATE games SET p1_dice=?,status='p2_turn' WHERE id=?", (val,gid))
    conn.commit(); conn.close()

def set_p2_dice(gid, val):
    conn = dbc(); conn.execute("UPDATE games SET p2_dice=?,status='resolving' WHERE id=?", (val,gid))
    conn.commit(); conn.close()

def finish_game_db(gid, winner_id):
    conn = dbc(); conn.execute("UPDATE games SET winner_id=?,status='finished' WHERE id=?", (winner_id,gid))
    conn.commit(); conn.close()

def cancel_game_db(gid):
    conn = dbc(); conn.execute("UPDATE games SET status='cancelled' WHERE id=?", (gid,))
    conn.commit(); conn.close()

def cancel_waiting(uid):
    conn = dbc(); conn.execute("DELETE FROM games WHERE creator_id=? AND status='waiting'", (uid,))
    conn.commit(); conn.close()

def has_waiting(uid):
    conn = dbc(); r = conn.execute("SELECT id FROM games WHERE creator_id=? AND status='waiting'", (uid,)).fetchone()
    conn.close(); return r[0] if r else None

def user_active_game(uid):
    conn = dbc()
    r = conn.execute(
        "SELECT * FROM games WHERE (creator_id=? OR joiner_id=?) AND status IN ('p1_turn','p2_turn')",
        (uid, uid)
    ).fetchone(); conn.close(); return r

# ════════════════════════════════════════════════════════
#  💬  MATNLAR
# ════════════════════════════════════════════════════════
T = {
"uz": {
"welcome":(
    "🎲 <b>PRm4u O'yin Botiga Xush Kelibsiz!</b>\n\n"
    "🎟 Sizga <b>1 000 PR</b> boshlang'ich balans berildi!\n\n"
    "👇 Menyudan foydalaning:"
),
"balance":(
    "👇 <b>Sizning balans PR va $</b>\n\n"
    "🎟 {pr:,} PR\n"
    "💰 {usd:.4f} $\n\n"
    "Kurs: 1$ = {uzs:,} so'm\n\n"
    "💡 PR sotib olish:\n{support}"
),
"profile":(
    "👤 <b>Profil</b>\n\n"
    "🆔 ID: <code>{uid}</code>\n"
    "📛 Ism: {name}\n"
    "🎟 Balans: <b>{pr:,} PR</b>\n"
    "🏆 G'alabalar: {wins}\n"
    "💀 Mag'lubiyatlar: {losses}"
),
"transfer_ask_id":    "💸 <b>PR Transfer</b>\n\nPR yubormoqchi bo'lgan foydalanuvchining <b>Telegram ID</b> sini kiriting:\n\n💡 ID ni bilish: @userinfobot",
"transfer_ask_amt":   "👤 Foydalanuvchi: <b>{name}</b>\n🆔 ID: <code>{uid}</code>\n\nQancha PR yubormoqchisiz?\n(Sizda: <b>{pr:,} PR</b>)",
"transfer_confirm":   "✅ Tasdiqlash:\n\n➡️ Kimga: <code>{to_id}</code>\n💸 Miqdor: <b>{amount:,} PR</b>\n💰 Komissiya: 0%\n\nDavom etasizmi?",
"transfer_ok":(
    "👍 <b>Transfer muvaffaqiyatli!</b>\n\n"
    "Foydalanuvchi <code>{to_id}</code> ga <b>{amount:,} PR</b>\n\n"
    "➖ Komissiya 0%, balansingizdan {amount:,} PR yechildi"
),
"transfer_recv":      "🎁 Sizga <code>{from_id}</code> dan <b>{amount:,} PR</b> transfer qilindi!",
"transfer_no_user":   "❌ Bu ID li foydalanuvchi topilmadi!",
"transfer_no_funds":  "❌ Yetarli PR yo'q! Sizda: <b>{pr:,} PR</b>",
"transfer_cancel":    "❌ Transfer bekor qilindi.",
"transfer_self":      "❌ O'zingizga transfer qila olmaysiz!",
"game_menu":          "🎲 <b>O'yin xonasi</b>\n\n💰 Balansingiz: <b>{pr:,} PR</b>",
"rooms_list":         "🎮 <b>Ochiq xonalar ({count} ta):</b>\n\nXona tanlang yoki yangi yarating:",
"rooms_empty":        "😔 Hozir ochiq xona yo'q.\nBirinchi bo'lib xona oching!",
"room_detail":(
    "🎮 <b>Xona #{gid}</b>\n\n"
    "👤 O'yinchi: <code>#{creator_id}</code>\n"
    "🎟 Stavka: <b>{stake:,} PR</b>\n\n"
    "Qo'shilasizmi?"
),
"already_wait":       "⏳ Siz allaqachon xona kutmoqdasiz!",
"not_enough":         "😞 <b>Yetarli PR yo'q!</b>\nStavka: <b>{stake:,} PR</b>\nSizda: <b>{pr:,} PR</b>\n\nPR sotib olish: {support}",
"room_created":       "⏳ <b>Xona yaratildi!</b>\n\n🆔 Xona ID: <code>#{gid}</code>\n🎟 Stavka: <b>{stake:,} PR</b>\n\nRaqib kutilmoqda... 👀",
"game_started":(
    "🎲 <b>O'yin boshlandi!</b>\n\n"
    "🆔 Xona: #{gid}\n"
    "🎟 Stavka: {stake:,} PR\n\n"
    "🔴 <code>#{p1}</code> vs 🔵 <code>#{p2}</code>\n\n"
    "⏱ {turn_name} tosh tashlaydi!"
),
"your_turn":          "🎲 Sizning navbatingiz! Tosh tashlang:",
"wait_turn":          "⏳ Raqib tashlashini kuting...",
"p1_threw":           "🎲 <code>#{p1}</code> tosh tashladi: <b>{val}</b>\n\n🔵 Endi <code>#{p2}</code> navbati!",
"your_turn_now":      "🎲 Endi sizning navbatingiz! Tosh tashlang:",
"timeout_cancel":     "⏰ <b>Vaqt tugadi!</b>\n\nO'yin bekor qilindi, PR lar qaytarildi.",
"win_text":(
    "😊 <b>Siz yutdingiz!</b>\n\n"
    "😍 Yutganingiz: <b>+{win:,} PR</b>\n"
    "💸 Komissiya (5%): <b>-{commission:,} PR</b>\n\n"
    "🆔 O'yin ID: #{gid}\n"
    "🎟 Stavka: {stake:,} PR\n"
    "✅ G'olib: <code>#{winner}</code> — 🎲 {w_dice}\n"
    "🔴 Mag'lub: <code>#{loser}</code> — 🎲 {l_dice}\n\n"
    "🎟 Balans: <b>{bal:,} PR</b>"
),
"loss_text":(
    "😢 <b>Siz yutqazdingiz!</b>\n\n"
    "🆔 O'yin ID: #{gid}\n"
    "🎟 Stavka: {stake:,} PR\n"
    "✅ G'olib: <code>#{winner}</code> — 🎲 {w_dice}\n"
    "🔴 Mag'lub: <code>#{loser}</code> — 🎲 {l_dice}\n\n"
    "🎟 Balans: <b>{bal:,} PR</b>"
),
"draw_text":(
    "🤝 <b>Durrang! PR lar qaytarildi.</b>\n\n"
    "🆔 O'yin ID: #{gid}\n"
    "🎟 Stavka: {stake:,} PR\n"
    "🎲 Ikkalangizda: {val}\n\n"
    "🎟 Balans: <b>{bal:,} PR</b>"
),
"bonus_spin":         "🎰 Kunlik bonus aylantirilmoqda...",
"bonus_win":          "🎉 <b>Kunlik bonus!</b>\n\nSlotda: <b>{amount} PR</b>\n🎟 Balans: <b>{bal:,} PR</b>",
"bonus_wait":         "⏳ Bonus olindi!\n🕐 <b>{h} soat {m} daqiqa</b> dan keyin qayta oling.",
"support_msg":        "💬 <b>Murojaat uchun:</b>\n\n{link}\n\nPR sotib olish va savollar uchun.",
"buy_pr":             "🛍 <b>PR sotib olish</b>\n\nNarxlar:\n🎟 10 000 PR = 0.5$\n🎟 50 000 PR = 2.5$\n🎟 100 000 PR = 5$\n\nTo'lov uchun adminga murojaat qiling:",
"cancel_ok":          "❌ Bekor qilindi.",
"lang_choose":        "🌐 Tilni tanlang:",
"lang_set":           "✅ Til: <b>O'zbekcha</b>",
"admin_ok":           "✅ {uid} ga {amount:,} PR berildi. Balans: {bal:,} PR",
"admin_rate":         "✅ Kurs: 1$ = {uzs:,} so'm",
"admin_only":         "❌ Faqat admin!",
"btn_game":    "🎲 O'yin xonasi",
"btn_balance": "🎟 Balans",
"btn_bonus":   "🎁 Kunlik bonus",
"btn_support": "💬 Murojaat",
"btn_buy":     "🛍 PR sotib olish",
"btn_lang":    "🌐 Til",
"btn_transfer":"💸 Transfer",
"btn_confirm": "✅ Tasdiqlash",
"btn_cancel":  "❌ Bekor",
"btn_throw":   "🎲 Tosh tashlash",
"btn_join":    "✅ Qo'shilish",
"btn_profile": "👤 Profil ko'rish",
"btn_rooms":   "🎮 Xonalar ro'yxati",
"btn_create":  "➕ Yangi xona",
"btn_back":    "🔙 Orqaga",
},

"ru": {
"welcome":(
    "🎲 <b>Добро пожаловать в PRm4u!</b>\n\n"
    "🎟 Вам начислено <b>1 000 PR</b>!\n\n"
    "👇 Используйте меню:"
),
"balance":(
    "👇 <b>Ваш баланс PR и $</b>\n\n"
    "🎟 {pr:,} PR\n"
    "💰 {usd:.4f} $\n\n"
    "Курс: 1$ = {uzs:,} сум\n\n"
    "💡 Купить PR:\n{support}"
),
"profile":(
    "👤 <b>Профиль</b>\n\n"
    "🆔 ID: <code>{uid}</code>\n"
    "📛 Имя: {name}\n"
    "🎟 Баланс: <b>{pr:,} PR</b>\n"
    "🏆 Победы: {wins}\n"
    "💀 Поражения: {losses}"
),
"transfer_ask_id":    "💸 <b>Перевод PR</b>\n\nВведите <b>Telegram ID</b> получателя:\n\n💡 ID узнать: @userinfobot",
"transfer_ask_amt":   "👤 Пользователь: <b>{name}</b>\n🆔 ID: <code>{uid}</code>\n\nСколько PR перевести?\n(У вас: <b>{pr:,} PR</b>)",
"transfer_confirm":   "✅ Подтверждение:\n\n➡️ Кому: <code>{to_id}</code>\n💸 Сумма: <b>{amount:,} PR</b>\n💰 Комиссия: 0%\n\nПодтвердить?",
"transfer_ok":(
    "👍 <b>Перевод выполнен!</b>\n\n"
    "Пользователю <code>{to_id}</code> — <b>{amount:,} PR</b>\n\n"
    "➖ Комиссия 0%, с баланса списано {amount:,} PR"
),
"transfer_recv":      "🎁 Вам переведено <b>{amount:,} PR</b> от <code>{from_id}</code>!",
"transfer_no_user":   "❌ Пользователь не найден!",
"transfer_no_funds":  "❌ Недостаточно PR! У вас: <b>{pr:,} PR</b>",
"transfer_cancel":    "❌ Перевод отменён.",
"transfer_self":      "❌ Нельзя переводить самому себе!",
"game_menu":          "🎲 <b>Игровой зал</b>\n\n💰 Баланс: <b>{pr:,} PR</b>",
"rooms_list":         "🎮 <b>Открытые комнаты ({count} шт.):</b>\n\nВыберите или создайте новую:",
"rooms_empty":        "😔 Нет открытых комнат.\nСоздайте первую!",
"room_detail":(
    "🎮 <b>Комната #{gid}</b>\n\n"
    "👤 Игрок: <code>#{creator_id}</code>\n"
    "🎟 Ставка: <b>{stake:,} PR</b>\n\n"
    "Войти в игру?"
),
"already_wait":       "⏳ Вы уже ожидаете в комнате!",
"not_enough":         "😞 <b>Недостаточно PR!</b>\nСтавка: <b>{stake:,} PR</b>\nУ вас: <b>{pr:,} PR</b>\n\nКупить PR: {support}",
"room_created":       "⏳ <b>Комната создана!</b>\n\n🆔 ID: <code>#{gid}</code>\n🎟 Ставка: <b>{stake:,} PR</b>\n\nОжидание соперника... 👀",
"game_started":(
    "🎲 <b>Игра началась!</b>\n\n"
    "🆔 Комната: #{gid}\n"
    "🎟 Ставка: {stake:,} PR\n\n"
    "🔴 <code>#{p1}</code> vs 🔵 <code>#{p2}</code>\n\n"
    "⏱ {turn_name} бросает кость!"
),
"your_turn":          "🎲 Ваш ход! Бросьте кость:",
"wait_turn":          "⏳ Ждите хода соперника...",
"p1_threw":           "🎲 <code>#{p1}</code> бросил: <b>{val}</b>\n\n🔵 Теперь ход <code>#{p2}</code>!",
"your_turn_now":      "🎲 Теперь ваш ход! Бросьте кость:",
"timeout_cancel":     "⏰ <b>Время вышло!</b>\n\nИгра отменена, ставки возвращены.",
"win_text":(
    "😊 <b>Вы победили!</b>\n\n"
    "😍 Выигрыш: <b>+{win:,} PR</b>\n"
    "💸 Комиссия (5%): <b>-{commission:,} PR</b>\n\n"
    "🆔 ID игры: #{gid}\n"
    "🎟 Ставка: {stake:,} PR\n"
    "✅ Победил: <code>#{winner}</code> — 🎲 {w_dice}\n"
    "🔴 Проиграл: <code>#{loser}</code> — 🎲 {l_dice}\n\n"
    "🎟 Баланс: <b>{bal:,} PR</b>"
),
"loss_text":(
    "😢 <b>Вы проиграли!</b>\n\n"
    "🆔 ID игры: #{gid}\n"
    "🎟 Ставка: {stake:,} PR\n"
    "✅ Победил: <code>#{winner}</code> — 🎲 {w_dice}\n"
    "🔴 Проиграл: <code>#{loser}</code> — 🎲 {l_dice}\n\n"
    "🎟 Баланс: <b>{bal:,} PR</b>"
),
"draw_text":(
    "🤝 <b>Ничья! Ставки возвращены.</b>\n\n"
    "🆔 ID игры: #{gid}\n"
    "🎟 Ставка: {stake:,} PR\n"
    "🎲 У обоих: {val}\n\n"
    "🎟 Баланс: <b>{bal:,} PR</b>"
),
"bonus_spin":         "🎰 Прокручиваем бонус...",
"bonus_win":          "🎉 <b>Ежедневный бонус!</b>\n\nВыпало: <b>{amount} PR</b>\n🎟 Баланс: <b>{bal:,} PR</b>",
"bonus_wait":         "⏳ Бонус уже получен!\n🕐 Через <b>{h} ч. {m} мин.</b>",
"support_msg":        "💬 <b>Поддержка:</b>\n\n{link}\n\nДля покупки PR и вопросов.",
"buy_pr":             "🛍 <b>Купить PR</b>\n\nЦены:\n🎟 10 000 PR = 0.5$\n🎟 50 000 PR = 2.5$\n🎟 100 000 PR = 5$\n\nОбратитесь к администратору:",
"cancel_ok":          "❌ Отменено.",
"lang_choose":        "🌐 Выберите язык:",
"lang_set":           "✅ Язык: <b>Русский</b>",
"admin_ok":           "✅ {uid} получил {amount:,} PR. Баланс: {bal:,} PR",
"admin_rate":         "✅ Курс: 1$ = {uzs:,} сум",
"admin_only":         "❌ Только для админов!",
"btn_game":    "🎲 Игровой зал",
"btn_balance": "🎟 Баланс",
"btn_bonus":   "🎁 Бонус",
"btn_support": "💬 Поддержка",
"btn_buy":     "🛍 Купить PR",
"btn_lang":    "🌐 Язык",
"btn_transfer":"💸 Перевод",
"btn_confirm": "✅ Подтвердить",
"btn_cancel":  "❌ Отмена",
"btn_throw":   "🎲 Бросить кость",
"btn_join":    "✅ Войти",
"btn_profile": "👤 Профиль",
"btn_rooms":   "🎮 Список комнат",
"btn_create":  "➕ Новая комната",
"btn_back":    "🔙 Назад",
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
        [KeyboardButton(text=tx(lang,"btn_game")),    KeyboardButton(text=tx(lang,"btn_balance"))],
        [KeyboardButton(text=tx(lang,"btn_bonus")),   KeyboardButton(text=tx(lang,"btn_buy"))],
        [KeyboardButton(text=tx(lang,"btn_support")), KeyboardButton(text=tx(lang,"btn_lang"))],
    ], resize_keyboard=True)

def balance_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_transfer"), callback_data="transfer_start"),
        InlineKeyboardButton(text=tx(lang,"btn_buy"),      callback_data="buy_pr"),
    ]])

def game_main_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tx(lang,"btn_rooms"),  callback_data="rooms_list"),
         InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room")],
    ])

def stakes_kb(lang):
    rows = []; row = []
    for s in STAKES:
        row.append(InlineKeyboardButton(text=f"{s:,} PR", callback_data=f"newroom_{s}"))
        if len(row) == 3: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_back"), callback_data="game_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rooms_kb(lang, rooms):
    rows = []
    for gid, cid, stake in rooms:
        rows.append([InlineKeyboardButton(
            text=f"🎮 {stake:,} PR | #{cid}",
            callback_data=f"room_{gid}"
        )])
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room")])
    rows.append([InlineKeyboardButton(text=tx(lang,"btn_back"),   callback_data="game_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def room_detail_kb(lang, gid, creator_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tx(lang,"btn_join"),    callback_data=f"join_{gid}"),
         InlineKeyboardButton(text=tx(lang,"btn_profile"), callback_data=f"profile_{creator_id}")],
        [InlineKeyboardButton(text=tx(lang,"btn_back"),    callback_data="rooms_list")],
    ])

def throw_kb(lang, gid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_throw"), callback_data=f"throw_{gid}")
    ]])

def transfer_confirm_kb(lang, to_id, amount):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(lang,"btn_confirm"), callback_data=f"tr_yes_{to_id}_{amount}"),
        InlineKeyboardButton(text=tx(lang,"btn_cancel"),  callback_data="tr_no"),
    ]])

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский",   callback_data="lang_ru"),
    ]])

def support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Admin — @mirodil_info", url=SUPPORT_LINK)
    ]])

# ════════════════════════════════════════════════════════
#  🎮  O'YIN YORDAMCHILARI
# ════════════════════════════════════════════════════════
async def send_gif_and_text(chat_id, is_win, text):
    gif = WIN_GIF_ID if is_win else LOSS_GIF_ID
    try:
        await bot_obj.send_animation(chat_id, animation=gif)
    except:
        try:
            await bot_obj.send_document(chat_id, document=gif)
        except:
            pass
    await bot_obj.send_message(chat_id, text, parse_mode="HTML")
    if not sent:
        try:
            await bot_obj.send_document(chat_id, document=gif)
            sent = True
        except: pass
    # 3-urinish: send_video
    if not sent:
        try:
            await bot_obj.send_video(chat_id, video=gif)
        except: pass
    await bot_obj.send_message(chat_id, text, parse_mode="HTML")

async def timeout_task(gid, stake, p1_id, p2_id):
    await asyncio.sleep(THROW_TIMEOUT)
    game = get_game(gid)
    if not game or game[4] not in ('p1_turn', 'p2_turn'):
        return
    # Bekor qilish va PR qaytarish
    cancel_game_db(gid)
    change_pr(p1_id, stake)
    change_pr(p2_id, stake)
    for uid in [p1_id, p2_id]:
        lang = get_lang(uid)
        try:
            await bot_obj.send_message(uid, tx(lang, "timeout_cancel"), parse_mode="HTML")
        except: pass

async def resolve_game(gid):
    """Ikki tosh ham tashlangandan keyin natijani hisobling"""
    game = get_game(gid)
    if not game: return
    gid_, p1, p2, stake = game[0], game[1], game[2], game[3]
    p1_val, p2_val = game[5], game[6]
    lang1, lang2   = get_lang(p1), get_lang(p2)
    commission     = int(stake * COMMISSION_PCT / 100)

    if p1_val == p2_val:
        # Durrang
        change_pr(p1, stake); change_pr(p2, stake)
        finish_game_db(gid, 0)
        for uid, lang in [(p1, lang1), (p2, lang2)]:
            bal = get_pr(uid)
            await send_gif_and_text(uid, False,
                tx(lang,"draw_text", gid=gid, stake=stake, val=p1_val, bal=bal))
    else:
        winner_id  = p1 if p1_val > p2_val else p2
        loser_id   = p2 if p1_val > p2_val else p1
        w_dice     = p1_val if p1_val > p2_val else p2_val
        l_dice     = p2_val if p1_val > p2_val else p1_val

        winnings   = (stake * 2) - commission
        change_pr(winner_id, winnings)
        # Komissiya adminga
        if ADMIN_IDS:
            change_pr(ADMIN_IDS[0], commission)

        add_win(winner_id); add_loss(loser_id)
        finish_game_db(gid, winner_id)

        winner_bal = get_pr(winner_id)
        loser_bal  = get_pr(loser_id)
        wlang      = get_lang(winner_id)
        llang      = get_lang(loser_id)

        await send_gif_and_text(winner_id, True,
            tx(wlang,"win_text", gid=gid, stake=stake, win=winnings-stake,
               commission=commission, winner=winner_id, loser=loser_id,
               w_dice=w_dice, l_dice=l_dice, bal=winner_bal))
        await send_gif_and_text(loser_id, False,
            tx(llang,"loss_text", gid=gid, stake=stake,
               winner=winner_id, loser=loser_id,
               w_dice=w_dice, l_dice=l_dice, bal=loser_bal))

# ════════════════════════════════════════════════════════
#  📩  HANDLERLAR
# ════════════════════════════════════════════════════════

# ── /start ───────────────────────────────────────────────
@dp.message(Command("start"))
async def h_start(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    await msg.answer(tx(lang,"welcome"), parse_mode="HTML", reply_markup=main_kb(lang))

# ── Balans ───────────────────────────────────────────────
@dp.message(F.text.in_(["🎟 Balans","🎟 Баланс"]))
async def h_balance(msg: types.Message):
    uid = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    pr   = get_pr(uid)
    usd  = pr / PR_PER_DOLLAR
    uzs  = await get_usd_uzs()
    await msg.answer(
        tx(lang,"balance", pr=pr, usd=usd, uzs=uzs, support=SUPPORT_LINK),
        parse_mode="HTML", reply_markup=balance_kb(lang)
    )

# ── Transfer boshlash ────────────────────────────────────
@dp.callback_query(F.data == "transfer_start")
async def cb_transfer_start(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    user_states[uid] = {'step': 'transfer_id'}
    await cb.message.answer(tx(lang,"transfer_ask_id"), parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data == "tr_no")
async def cb_tr_no(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    user_states.pop(uid, None)
    await cb.message.edit_text(tx(lang,"transfer_cancel"))
    await cb.answer()

@dp.callback_query(F.data.startswith("tr_yes_"))
async def cb_tr_yes(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    parts   = cb.data.split("_")
    to_id   = int(parts[2])
    amount  = int(parts[3])
    ok, reason = do_transfer(uid, to_id, amount)
    if ok:
        await cb.message.edit_text(
            tx(lang,"transfer_ok", to_id=to_id, amount=amount),
            parse_mode="HTML"
        )
        to_lang = get_lang(to_id)
        try:
            await bot_obj.send_message(to_id, tx(to_lang,"transfer_recv",
                                                  from_id=uid, amount=amount), parse_mode="HTML")
        except: pass
    else:
        pr = get_pr(uid)
        await cb.message.edit_text(tx(lang,"transfer_no_funds", pr=pr), parse_mode="HTML")
    user_states.pop(uid, None)
    await cb.answer()

# ── Buy PR ───────────────────────────────────────────────
@dp.callback_query(F.data == "buy_pr")
async def cb_buy_pr(cb: types.CallbackQuery):
    lang = get_lang(cb.from_user.id)
    await cb.message.answer(tx(lang,"buy_pr"), parse_mode="HTML", reply_markup=support_kb())
    await cb.answer()

# ── O'yin xonasi ─────────────────────────────────────────
@dp.message(F.text.in_(["🎲 O'yin xonasi","🎲 Игровой зал"]))
async def h_game(msg: types.Message):
    uid  = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    pr   = get_pr(uid)
    await msg.answer(tx(lang,"game_menu", pr=pr), parse_mode="HTML", reply_markup=game_main_kb(lang))

@dp.callback_query(F.data == "game_back")
async def cb_game_back(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    pr   = get_pr(uid)
    await cb.message.edit_text(tx(lang,"game_menu", pr=pr), parse_mode="HTML",
                                reply_markup=game_main_kb(lang))
    await cb.answer()

# ── Xonalar ro'yxati ─────────────────────────────────────
@dp.callback_query(F.data == "rooms_list")
async def cb_rooms(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    lang  = get_lang(uid)
    rooms = get_waiting_games(exclude_uid=uid)
    if not rooms:
        await cb.message.edit_text(tx(lang,"rooms_empty"), parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text=tx(lang,"btn_create"), callback_data="create_room")],
                                        [InlineKeyboardButton(text=tx(lang,"btn_back"),   callback_data="game_back")],
                                    ]))
    else:
        await cb.message.edit_text(
            tx(lang,"rooms_list", count=len(rooms)), parse_mode="HTML",
            reply_markup=rooms_kb(lang, rooms)
        )
    await cb.answer()

# ── Xona detali ──────────────────────────────────────────
@dp.callback_query(F.data.startswith("room_"))
async def cb_room_detail(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    gid  = int(cb.data.split("_")[1])
    game = get_game(gid)
    if not game or game[4] != 'waiting':
        await cb.answer("❌ Xona topilmadi yoki to'lgan!", show_alert=True); return
    await cb.message.edit_text(
        tx(lang,"room_detail", gid=gid, creator_id=game[1], stake=game[3]),
        parse_mode="HTML",
        reply_markup=room_detail_kb(lang, gid, game[1])
    )
    await cb.answer()

# ── Profil ko'rish ───────────────────────────────────────
@dp.callback_query(F.data.startswith("profile_"))
async def cb_profile(cb: types.CallbackQuery):
    lang    = get_lang(cb.from_user.id)
    view_id = int(cb.data.split("_")[1])
    u = get_user(view_id)
    if not u:
        await cb.answer("❌ Foydalanuvchi topilmadi!", show_alert=True); return
    wins, losses = u[6], u[7]
    pr   = u[3]
    name = u[2] or u[1] or f"#{view_id}"
    await cb.answer(
        tx(lang,"profile", uid=view_id, name=name, pr=pr, wins=wins, losses=losses),
        show_alert=True
    )

# ── Yangi xona yaratish ───────────────────────────────────
@dp.callback_query(F.data == "create_room")
async def cb_create_room(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    if has_waiting(uid):
        await cb.answer(tx(lang,"already_wait"), show_alert=True); return
    await cb.message.edit_text(
        tx(lang,"game_menu", pr=get_pr(uid)), parse_mode="HTML",
        reply_markup=stakes_kb(lang)
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("newroom_"))
async def cb_newroom(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    lang  = get_lang(uid)
    stake = int(cb.data.split("_")[1])
    pr    = get_pr(uid)
    if pr < stake:
        await cb.answer(tx(lang,"not_enough", stake=stake, pr=pr, support=SUPPORT_LINK),
                        show_alert=True); return
    gid = create_game(uid, stake)
    await cb.message.edit_text(
        tx(lang,"room_created", gid=gid, stake=stake), parse_mode="HTML"
    )
    await cb.answer()

# ── Xonaga qo'shilish ─────────────────────────────────────
@dp.callback_query(F.data.startswith("join_"))
async def cb_join(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    gid  = int(cb.data.split("_")[1])
    game = get_game(gid)

    if not game or game[4] != 'waiting':
        await cb.answer("❌ Xona mavjud emas!", show_alert=True); return

    p1, stake = game[1], game[3]

    if uid == p1:
        await cb.answer("❌ O'z xonangizga qo'shila olmaysiz!", show_alert=True); return

    pr = get_pr(uid)
    if pr < stake:
        await cb.answer(tx(lang,"not_enough", stake=stake, pr=pr, support=SUPPORT_LINK),
                        show_alert=True); return

    p1_pr = get_pr(p1)
    if p1_pr < stake:
        cancel_waiting(p1)
        await cb.answer("❌ Xona yaratuvchida PR yetarli emas, xona bekor qilindi.", show_alert=True)
        return

    # PRni ikkalasidan ayir
    change_pr(uid, -stake)
    change_pr(p1,  -stake)
    start_game(gid, uid)

    p1_lang = get_lang(p1)
    p2_lang = lang

    # Boshlash xabari
    started_text_p1 = tx(p1_lang,"game_started", gid=gid, stake=stake,
                          p1=p1, p2=uid, turn_name=f"#{p1}")
    started_text_p2 = tx(p2_lang,"game_started", gid=gid, stake=stake,
                          p1=p1, p2=uid, turn_name=f"#{p1}")

    # P1 ga throw tugmasi
    try:
        await bot_obj.send_message(p1, started_text_p1, parse_mode="HTML",
                                   reply_markup=throw_kb(p1_lang, gid))
    except: pass

    # P2 ga wait xabari
    await cb.message.answer(started_text_p2 + "\n\n" + tx(p2_lang,"wait_turn"),
                             parse_mode="HTML")

    # Timeout vazifasini boshlash
    task = asyncio.create_task(timeout_task(gid, stake, p1, uid))
    game_timers[gid] = task
    await cb.answer()

# ── Tosh tashlash ─────────────────────────────────────────
@dp.callback_query(F.data.startswith("throw_"))
async def cb_throw(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_lang(uid)
    gid  = int(cb.data.split("_")[1])
    game = get_game(gid)

    if not game:
        await cb.answer("❌ O'yin topilmadi!", show_alert=True); return

    status, p1, p2 = game[4], game[1], game[2]
    stake = game[3]

    is_p1 = (uid == p1)
    is_p2 = (uid == p2)

    if status == 'p1_turn' and not is_p1:
        await cb.answer("⏳ Hozir raqib navbati!", show_alert=True); return
    if status == 'p2_turn' and not is_p2:
        await cb.answer("⏳ Raqib allaqachon tashlamoqda!", show_alert=True); return
    if status not in ('p1_turn', 'p2_turn'):
        await cb.answer("❌ Noto'g'ri holat!", show_alert=True); return

    # Tugmani o'chirib qo'yamiz
    try: await cb.message.edit_reply_markup()
    except: pass

    # Dice tashlash
    dice_msg = await bot_obj.send_dice(cb.message.chat.id, emoji="🎲")
    val = dice_msg.dice.value
    await asyncio.sleep(4)  # animatsiya tugashini kutish

    if status == 'p1_turn':
        set_p1_dice(gid, val)
        p2_lang = get_lang(p2)
        # P1 ga faqat o'ziniki ko'rinadi
        await bot_obj.send_message(p1,
            f"✅ Siz tosh taShladingiz: <b>{val}</b>\n\n⏳ Raqib tashlashini kuting...",
            parse_mode="HTML")
        # P2 ga faqat navbat xabari — raqam ko'rinmaydi!
        try:
            await bot_obj.send_message(p2,
                tx(p2_lang,"your_turn_now"),
                parse_mode="HTML", reply_markup=throw_kb(p2_lang, gid))
        except: pass
        # Eski timeout ni bekor qilib yangi boshlash
        if gid in game_timers:
            game_timers[gid].cancel()
        task = asyncio.create_task(timeout_task(gid, stake, p1, p2))
        game_timers[gid] = task

    else:  # p2_turn
        set_p2_dice(gid, val)
        # P2 ga o'ziniki ko'rinadi
        await bot_obj.send_message(p2,
            f"✅ Siz tosh taShladingiz: <b>{val}</b>\n\n⏳ Natija hisoblanmoqda...",
            parse_mode="HTML")
        # Timeoutni bekor qil
        if gid in game_timers:
            game_timers[gid].cancel()
            del game_timers[gid]
        # Natijani hisobla
        await resolve_game(gid)

    await cb.answer()

# ── Kunlik bonus ──────────────────────────────────────────
@dp.message(F.text.in_(["🎁 Kunlik bonus","🎁 Бонус"]))
async def h_bonus(msg: types.Message):
    uid  = msg.from_user.id
    register(uid, msg.from_user.username, msg.from_user.full_name)
    lang = get_lang(uid)
    ok, result = claim_bonus(uid)
    if not ok:
        h, m = result
        await msg.answer(tx(lang,"bonus_wait", h=h, m=m), parse_mode="HTML"); return
    wait = await msg.answer(tx(lang,"bonus_spin"))
    await bot_obj.send_dice(msg.chat.id, emoji="🎰")
    await asyncio.sleep(3)
    await wait.delete()
    await msg.answer(tx(lang,"bonus_win", amount=result, bal=get_pr(uid)), parse_mode="HTML")

# ── PR sotib olish ────────────────────────────────────────
@dp.message(F.text.in_(["🛍 PR sotib olish","🛍 Купить PR"]))
async def h_buy(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"buy_pr"), parse_mode="HTML", reply_markup=support_kb())

# ── Murojaat ─────────────────────────────────────────────
@dp.message(F.text.in_(["💬 Murojaat","💬 Поддержка"]))
async def h_support(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"support_msg", link=SUPPORT_LINK),
                     parse_mode="HTML", reply_markup=support_kb())

# ── Til ──────────────────────────────────────────────────
@dp.message(F.text.in_(["🌐 Til","🌐 Язык"]))
async def h_lang(msg: types.Message):
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"lang_choose"), reply_markup=lang_kb())

@dp.callback_query(F.data.startswith("lang_"))
async def cb_lang(cb: types.CallbackQuery):
    lang = cb.data.split("_")[1]
    set_lang(cb.from_user.id, lang)
    await cb.message.delete()
    await cb.message.answer(tx(lang,"lang_set"), parse_mode="HTML", reply_markup=main_kb(lang))
    await cb.answer()

# ── Ko'p bosqichli matn (transfer) ────────────────────────
@dp.message(F.text)
async def h_text(msg: types.Message):
    uid   = msg.from_user.id
    lang  = get_lang(uid)
    state = user_states.get(uid)
    if not state: return

    text = msg.text.strip()

    if state['step'] == 'transfer_id':
        if not text.isdigit():
            await msg.answer("❌ Faqat raqam kiriting!"); return
        to_id = int(text)
        if to_id == uid:
            await msg.answer(tx(lang,"transfer_self")); user_states.pop(uid,None); return
        to_u = get_user(to_id)
        if not to_u:
            await msg.answer(tx(lang,"transfer_no_user"), parse_mode="HTML"); return
        user_states[uid] = {'step': 'transfer_amount', 'to_id': to_id}
        name = to_u[2] or to_u[1] or f"#{to_id}"
        await msg.answer(tx(lang,"transfer_ask_amt", name=name, uid=to_id, pr=get_pr(uid)),
                         parse_mode="HTML")

    elif state['step'] == 'transfer_amount':
        if not text.isdigit():
            await msg.answer("❌ Faqat raqam kiriting!"); return
        amount = int(text)
        to_id  = state['to_id']
        pr     = get_pr(uid)
        if amount <= 0:
            await msg.answer("❌ 0 dan katta raqam kiriting!"); return
        if amount > pr:
            await msg.answer(tx(lang,"transfer_no_funds", pr=pr), parse_mode="HTML"); return
        user_states.pop(uid, None)
        await msg.answer(tx(lang,"transfer_confirm", to_id=to_id, amount=amount),
                         parse_mode="HTML",
                         reply_markup=transfer_confirm_kb(lang, to_id, amount))

# ════════════════════════════════════════════════════════
#  👮  ADMIN BUYRUQLARI
# ════════════════════════════════════════════════════════
def is_admin(uid): return uid in ADMIN_IDS

@dp.message(Command("give"))
async def cmd_give(msg: types.Message):
    """  /give <user_id> <amount>  """
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    p = msg.text.split()
    if len(p) != 3 or not p[1].isdigit() or not p[2].isdigit():
        await msg.answer("❌ Format: /give <user_id> <miqdor>"); return
    uid, amount = int(p[1]), int(p[2])
    change_pr(uid, amount)
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"admin_ok", uid=uid, amount=amount, bal=get_pr(uid)), parse_mode="HTML")

@dp.message(Command("rate"))
async def cmd_rate(msg: types.Message):
    """  /rate <uzs>  """
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    p = msg.text.split()
    if len(p) != 2 or not p[1].isdigit():
        await msg.answer("❌ Format: /rate <kurs>"); return
    uzs = int(p[1])
    set_setting("usd_uzs", uzs)
    set_setting("rate_fetch", datetime.now().isoformat())
    lang = get_lang(msg.from_user.id)
    await msg.answer(tx(lang,"admin_rate", uzs=uzs), parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer(tx(get_lang(msg.from_user.id),"admin_only")); return
    conn  = dbc()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    games = conn.execute("SELECT COUNT(*) FROM games WHERE status='finished'").fetchone()[0]
    wait  = conn.execute("SELECT COUNT(*) FROM games WHERE status='waiting'").fetchone()[0]
    xfers = conn.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM transfers").fetchone()
    conn.close()
    await msg.answer(
        f"📊 <b>Statistika:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{users:,}</b>\n"
        f"🎲 Tugagan o'yinlar: <b>{games:,}</b>\n"
        f"⏳ Kutayotgan: <b>{wait}</b>\n"
        f"💸 Transferlar: <b>{xfers[0]:,}</b> ta / <b>{xfers[1]:,}</b> PR",
        parse_mode="HTML"
    )

# ════════════════════════════════════════════════════════
#  🚀  ISHGA TUSHIRISH
# ════════════════════════════════════════════════════════
async def main():
    init_db()
    print("=" * 50)
    print("  ✅  PRm4u Bot v2.0 ishga tushdi!")
    print(f"  👮  Admin: {ADMIN_IDS}")
    print(f"  💸  Komissiya: {COMMISSION_PCT}%")
    print(f"  ⏱   Tosh tashlash vaqti: {THROW_TIMEOUT}s")
    print("=" * 50)
    await dp.start_polling(bot_obj)

if __name__ == "__main__":
    asyncio.run(main())
