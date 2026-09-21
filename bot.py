import threading
from flask import Flask

web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot is alive!"

def keep_alive():
    t = threading.Thread(target=lambda: web_app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()
import os
import re
import random
import sqlite3
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
DB_PATH = os.environ.get("DB_PATH", "naiza.db")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID environment variable is missing.")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

def db(sql, params=(), fetch=False, many=False):
    cur = conn.cursor()
    if many:
        cur.executemany(sql, params)
    else:
        cur.execute(sql, params)
    conn.commit()
    if fetch:
        return cur.fetchall()
    return cur.lastrowid

def init_db():
    db("""CREATE TABLE IF NOT EXISTS tournament(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        size INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'registration'
    )""")
    db("""CREATE TABLE IF NOT EXISTS players(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        UNIQUE(tournament_id, name)
    )""")
    db("""CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        round_no INTEGER NOT NULL,
        position INTEGER NOT NULL,
        p1 TEXT,
        p2 TEXT,
        s1 INTEGER,
        s2 INTEGER,
        winner TEXT,
        UNIQUE(tournament_id, round_no, position)
    )""")

init_db()

def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

async def need_admin(update):
    if not is_admin(update):
        await update.message.reply_text("⛔ Бұл команда тек турнир админіне арналған.")
        return False
    return True

def active():
    rows = db("SELECT * FROM tournament WHERE status != 'finished' ORDER BY id DESC LIMIT 1", fetch=True)
    return rows[0] if rows else None

def player_names(tid):
    return [r["name"] for r in db("SELECT name FROM players WHERE tournament_id=? ORDER BY id", (tid,), fetch=True)]

def round_name(r, total):
    names = {1:"1/16 ФИНАЛ",2:"1/8 ФИНАЛ",3:"1/4 ФИНАЛ",4:"1/2 ФИНАЛ",5:"ФИНАЛ"}
    if total == 1:
        return "ФИНАЛ"
    return names.get(r, f"{r}-РАУНД")

def bracket_text(tid):
    t = db("SELECT * FROM tournament WHERE id=?", (tid,), fetch=True)[0]
    matches = db("SELECT * FROM matches WHERE tournament_id=? ORDER BY round_no, position", (tid,), fetch=True)
    if not matches:
        return "📋 Турнир сеткасы әлі жасалған жоқ."
    max_round = max(m["round_no"] for m in matches)
    out = [f"🏆 {t['name']}\n"]
    for r in range(1, max_round + 1):
        rm = [m for m in matches if m["round_no"] == r]
        out.append(f"\n<b>{round_name(r, max_round)}</b>")
        for m in rm:
            p1, p2 = m["p1"] or "—", m["p2"] or "—"
            if m["winner"]:
                score = f"{m['s1']}:{m['s2']}" if m["s1"] is not None else "BYE"
                out.append(f"#{m['id']}  {p1} {score} {p2}  ✅ {m['winner']}")
            else:
                out.append(f"#{m['id']}  {p1}  —  {p2}")
    return "\n".join(out)

def propagate_winner(tid, round_no, position, winner):
    next_row = db("""SELECT * FROM matches
                     WHERE tournament_id=? AND round_no=? AND position=?""",
                  (tid, round_no + 1, (position + 1) // 2), fetch=True)
    if not next_row:
        return
    m = next_row[0]
    if position % 2 == 1:
        db("UPDATE matches SET p1=? WHERE id=?", (winner, m["id"]))
    else:
        db("UPDATE matches SET p2=? WHERE id=?", (winner, m["id"]))

def maybe_auto_byes(tid):
    changed = True
    while changed:
        changed = False
        matches = db("""SELECT * FROM matches WHERE tournament_id=? AND winner IS NULL
                        ORDER BY round_no, position""", (tid,), fetch=True)
        for m in matches:
            p1, p2 = m["p1"], m["p2"]
            if p1 and not p2:
                db("UPDATE matches SET winner=?, s1=1, s2=0 WHERE id=?", (p1, m["id"]))
                propagate_winner(tid, m["round_no"], m["position"], p1)
                changed = True
            elif p2 and not p1:
                db("UPDATE matches SET winner=?, s1=0, s2=1 WHERE id=?", (p2, m["id"]))
                propagate_winner(tid, m["round_no"], m["position"], p2)
                changed = True

def create_bracket(tid, size):
    names = player_names(tid)
    random.shuffle(names)
    while len(names) < size:
        names.append(None)

    total_rounds = size.bit_length() - 1
    for pos in range(1, size // 2 + 1):
        p1, p2 = names[(pos-1)*2], names[(pos-1)*2+1]
        db("""INSERT INTO matches(tournament_id,round_no,position,p1,p2)
              VALUES(?,?,?,?,?)""", (tid, 1, pos, p1, p2))
    for r in range(2, total_rounds + 1):
        for pos in range(1, size // (2**r) + 1):
            db("""INSERT INTO matches(tournament_id,round_no,position)
                  VALUES(?,?,?)""", (tid, r, pos))
    db("UPDATE tournament SET status='active' WHERE id=?", (tid,))
    maybe_auto_byes(tid)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏆 <b>NAIZA Tournament Bot</b>\n\n"
        "/new 16 — жаңа турнир ашу\n"
        "/add Ойыншы — ойыншы қосу\n"
        "/players — ойыншылар\n"
        "/draw — жеребе және сетка\n"
        "/bracket — турнир сеткасы\n"
        "/result ID 2-1 — матч нәтижесі\n"
        "/status — турнир статусы\n"
        "/cancel — турнирді жабу\n"
        "/id — Telegram ID\n\n"
        "Тек админ турнирді басқара алады.",
        parse_mode="HTML"
    )

async def my_id(update, context):
    await update.message.reply_text(f"🆔 Сіздің Telegram ID: <code>{update.effective_user.id}</code>", parse_mode="HTML")

async def new(update, context):
    if not await need_admin(update):
        return
    db("UPDATE tournament SET status='finished' WHERE status='active'")
    if not context.args or context.args[0] not in {"4", "8", "16", "32"}:
        await update.message.reply_text("Қолдану: /new 16")
        return

    size = int(context.args[0])
    name = "NAIZA League"
    if len(context.args) > 1:
        name = " ".join(context.args[1:])
    tid = db("INSERT INTO tournament (name, size) VALUES (?, ?)", (name, size))
    await update.effective_message.reply_text(
        f"🏆 <b>{name}</b> ашылды!\n"
        f"👥 Қатысушы саны: {size}\n\n"
        f"Ойыншыларды қосу: <code>/add Ойыншы</code>\n"
        f"Барлығы жиналған соң: <code>/draw</code>",
        parse_mode="HTML"
    )
    return

async def add(update, context):
    #if not await need_admin(update): return
    t = active()
    if not t or t["status"] != "registration":
        await update.effective_message.reply_text("Tirkeu zhabyq.")
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.effective_message.reply_text("Aty-joninizdi zhazynyz.")
        return
    if name in player_names(t["id"]):
        await update.effective_message.reply_text("Bul oiynshy tizimde bar.")
        return
    count = len(player_names(t["id"]))
    if count >= t["size"]:
        await update.effective_message.reply_text("Oiynshy limiti toldy.")
        return
    try:
        db("INSERT INTO players(tournament_id,name) VALUES(?,?)", (t["id"], name))
    except sqlite3.IntegrityError:
        await update.effective_message.reply_text("Bul oiynshy buryn qosylgan.")
        return
    count += 1
    await update.effective_message.reply_text(f"Qosylshysy: {name} ({count}/{t['size']})")
async def players(update, context):
    t = active()
    if not t:
        await update.effective_message.reply_text("Белсенді турнир табылған жоқ.")
        return

    rows = db("SELECT name FROM players WHERE tournament_id = ?", (t["id"],))
    if not rows:
        await update.effective_message.reply_text("Турнирде әлі ойыншылар жоқ.")
        return

    text = "<b>Қатысушылар тізімі:</b>\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r['name']}\n"

    await update.effective_message.reply_text(text, parse_mode="HTML")

        
async def draw(update, context):
    t = active()
    if not t:
        await update.message.reply_text("Қазір белсенді турнир жоқ.")
        return
    ps = player_names(t["id"])
    if not ps:
        await update.message.reply_text("Ойыншылар әлі жоқ.")
        return
    text = "\n".join(f"{i+1}. {p}" for i,p in enumerate(ps))
    await update.message.reply_text(f"👥 <b>Ойыншылар {len(ps)}/{t['size']}</b>\n\n{text}", parse_mode="HTML")

async def draw(update, context):
    if not await need_admin(update): return
    t = active()
    if not t or t["status"] != "registration":
        await update.message.reply_text("⚠️ Жеребе жасауға дайын турнир жоқ.")
        return
    ps = player_names(t["id"])
    if len(ps) < 2:
        await update.message.reply_text("❌ Кемінде 2 ойыншы керек.")
        return
    if len(ps) > t["size"]:
        await update.message.reply_text("❌ Ойыншы саны лимиттен асып кетті.")
        return
    db("DELETE FROM matches WHERE tournament_id=?", (t["id"],))
    create_bracket(t["id"], t["size"])
    await update.message.reply_text("🎲 Жеребе дайын!\n\n" + bracket_text(t["id"]), parse_mode="HTML")

async def bracket(update, context):
    t = active()
    if not t:
        await update.message.reply_text("Қазір турнир жоқ.")
        return
    await update.message.reply_text(bracket_text(t["id"]), parse_mode="HTML")

async def result(update, context):
    #if not await need_admin(update): return
    t = active()
    if not t or t["status"] != "active":
        await update.message.reply_text("⚠️ Белсенді матчтар жоқ.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Қолдану: /result 3 2-1")
        return
    try:
        mid = int(context.args[0])
        a, b = map(int, context.args[1].split("-"))
    except Exception:
        await update.message.reply_text("❌ Формат: /result 3 2-1")
        return
    if a == b:
        await update.message.reply_text("❌ Тең есеп қабылданбайды. Жеңімпаз анықталған есеп енгізіңіз.")
        return
    rows = db("SELECT * FROM matches WHERE id=? AND tournament_id=?", (mid,t["id"]), fetch=True)
    if not rows:
        await update.message.reply_text("❌ Матч табылмады.")
        return
    m = rows[0]
    if m["winner"]:
        await update.message.reply_text("⚠️ Бұл матчтың нәтижесі бұрын енгізілген.")
        return
    if not m["p1"] or not m["p2"]:
        await update.message.reply_text("⚠️ Бұл матчта екі ойыншы да жоқ.")
        return
    winner = m["p1"] if a > b else m["p2"]
    db("UPDATE matches SET s1=?,s2=?,winner=? WHERE id=?", (a,b,winner,mid))
    propagate_winner(t["id"], m["round_no"], m["position"], winner)

    # Finish if this was the final.
    final_rows = db("""SELECT * FROM matches WHERE tournament_id=? ORDER BY round_no DESC LIMIT 1""", (t["id"],), fetch=True)
    if final_rows and final_rows[0]["id"] == mid:
        db("UPDATE tournament SET status='finished' WHERE id=?", (t["id"],))
        await update.message.reply_text(
            f"🏆🏆🏆 <b>NAIZA CHAMPION!</b>\n\n👑 {winner}\n\n"
            + bracket_text(t["id"]), parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"✅ Нәтиже қабылданды!\n🏅 Жеңімпаз: {winner}\n\n" + bracket_text(t["id"]),
        parse_mode="HTML"
    )

async def status(update, context):
    t = active()
    if not t:
        await update.message.reply_text("Белсенді турнир жоқ.")
        return
    ps = len(player_names(t["id"]))
    await update.message.reply_text(f"🏆 {t['name']}\n📌 Статус: {t['status']}\n👥 {ps}/{t['size']}")

async def cancel(update, context):
    if not await need_admin(update): return
    t = active()
    if not t:
        await update.message.reply_text("Белсенді турнир жоқ.")
        return
    db("UPDATE tournament SET status='finished' WHERE id=?", (t["id"],))
    await update.message.reply_text("🛑 Турнир жабылды.")

def main():
    keep_alive()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("players", players))
    app.add_handler(CommandHandler("draw", draw))
    app.add_handler(CommandHandler("bracket", bracket))
    app.add_handler(CommandHandler("result", result))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("cancel", cancel))
    print("NAIZA Tournament Bot is running on Render webhook...")
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if not external_url:
        raise RuntimeError("RENDER_EXTERNAL_URL is missing. This bot must run as a Render Web Service.")

    port = int(os.environ.get("PORT", "10000"))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",
        webhook_url=f"{external_url}/webhook",
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
    

