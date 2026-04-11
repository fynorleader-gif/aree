import logging
import sqlite3
import re
import os
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- WEB SERVER FOR 24/7 KEEP ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    # Replit/Koyeb port handling
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- CONFIGURATION ---
TOKEN = os.environ.get('8662822210:AAG0QlH6p5o4Ba-sXhw62wpl1fD0o_7RaZQ')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('fynor_premium.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (user_id INTEGER PRIMARY KEY, admin_list TEXT, waiting_for TEXT, 
                  v TEXT, i TEXT, d TEXT, c TEXT, do TEXT)''')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('fynor_premium.db')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

init_db()

def get_session(user_id):
    res = db_query("SELECT * FROM sessions WHERE user_id=?", (user_id,), fetch=True)
    if not res:
        db_query("INSERT INTO sessions (user_id, admin_list, waiting_for, v, i, d, c, do) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                 (user_id, '', '', '', '', '', '', ''))
        return {'admin_list': '', 'waiting_for': '', 'v': '', 'i': '', 'd': '', 'c': '', 'do': ''}
    r = res[0]
    return {'admin_list': r[1], 'waiting_for': r[2], 'v': r[3], 'i': r[4], 'd': r[5], 'c': r[6], 'do': r[7]}

def update_session(user_id, data):
    fields = ", ".join([f"{k}=?" for k in data.keys()])
    db_query(f"UPDATE sessions SET {fields} WHERE user_id=?", (*data.values(), user_id))

# --- UTILS ---
def is_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['Start'],
        ['Post Valid Check', 'Duplicate Check'],
        ['Comment List Check']
    ], resize_keyboard=True, persistent=True)

# --- CORE FUNCTIONS ---

async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "✨ *Welcome to Fynor Services* ✨\n\n"
        "We provide fast, reliable & high-quality solutions.\n\n"
        "👤 *Bot Creator:* Muhammad Awais\n"
        "📞 *Direct Contact:* +92 315 7703599\n\n"
        "👉 Please choose an option below!"
    )
    target = update.message if update.message else update.callback_query.message
    await target.reply_text(welcome, reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = get_session(user_id)
    text = update.message.text

    if text in ["Start", "/start"]:
        update_session(user_id, {'waiting_for': ''})
        await start_menu(update, context)
        return

    if text == "Post Valid Check":
        update_session(user_id, {'waiting_for': 'wait_admin'})
        await update.message.reply_text("📥 Send Original *Admin List*:", reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return
    elif text == "Duplicate Check":
        update_session(user_id, {'waiting_for': 'wait_only_dup'})
        await update.message.reply_text("📥 Send List:", reply_markup=get_main_keyboard())
        return
    elif text == "Comment List Check":
        update_session(user_id, {'waiting_for': 'wait_comment_admin'})
        await update.message.reply_text("Send Admin List", reply_markup=get_main_keyboard())
        return

    # --- POST VALID CHECK ---
    if session['waiting_for'] == 'wait_admin':
        update_session(user_id, {'admin_list': text, 'waiting_for': 'wait_member'})
        await update.message.reply_text("Send Your List")

    elif session['waiting_for'] == 'wait_member':
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        admin_data = {}
        for line in session['admin_list'].split('\n'):
            parts = line.strip().split()
            if not parts: continue
            uid = parts[0].lower()
            extra = " ".join(parts[1:]).lower()
            if is_chinese(extra) or "invalid" in extra: admin_data[uid] = False
            elif any(x in extra for x in ["valid", "✅", "good"]): admin_data[uid] = True
            else: admin_data[uid] = True

        input_ids = [l.strip() for l in text.split('\n') if l.strip()]
        v, i, d, seen, report_lines = [], [], [], set(), []
        for uid in input_ids:
            low_uid = uid.lower()
            if low_uid in seen:
                d.append(f"{uid} Duplicate")
                report_lines.append(f"`{uid}` ⚠️")
            else:
                seen.add(low_uid)
                if low_uid in admin_data and admin_data[low_uid] is True:
                    v.append(f"{uid} ✅")
                    report_lines.append(f"`{uid}` ✅")
                else:
                    i.append(f"{uid} ❌")
                    report_lines.append(f"`{uid}` ❌")

        update_session(user_id, {'v': "\n".join(v), 'i': "\n".join(i), 'd': "\n".join(d), 'waiting_for': ''})
        report = "📊 *FYNOR CHECK RESULTS*\n━━━━━━━━━━━━━━\n" + "\n".join(report_lines)
        kb = [[InlineKeyboardButton("Valid List", callback_data="v"), InlineKeyboardButton("invalid List", callback_data="i")]]
        if d: kb.append([InlineKeyboardButton("Duplicate List", callback_data="d")])
        await update.message.reply_text(report, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    # --- DUPLICATE CHECK (FIXED: SHOWS BOTH CLEAN AND DUPLICATE) ---
    elif session['waiting_for'] == 'wait_only_dup':
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        input_ids = [l.strip() for l in text.split('\n') if l.strip()]
        clean, dups, seen = [], [], set()
        for uid in input_ids:
            if uid.lower() in seen:
                dups.append(uid)
            else:
                seen.add(uid.lower())
                clean.append(uid)

        update_session(user_id, {'c': "\n".join(clean), 'do': "\n".join(dups), 'waiting_for': ''})
        
        # Displaying main report with Clean List
        report = f"💎 *CLEAN LIST:*\n━━━━━━━━━━━━━━\n`{chr(10).join(clean)}`"
        
        kb = [[InlineKeyboardButton("Clean List", callback_data="c")]]
        if dups:
            kb.append([InlineKeyboardButton("Duplicate List", callback_data="do")])
            report += f"\n\n⚠️ *Duplicates Found:* {len(dups)}"
            
        await update.message.reply_text(report, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    # --- COMMENT LIST CHECK ---
    elif session['waiting_for'] == 'wait_comment_admin':
        update_session(user_id, {'admin_list': text, 'waiting_for': 'wait_comment_list'})
        await update.message.reply_text("Your List")

    elif session['waiting_for'] == 'wait_comment_list':
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        admin_data = {}
        for line in session['admin_list'].split('\n'):
            parts = line.strip().split(maxsplit=1)
            if not parts: continue
            admin_data[parts[0].lower()] = parts[1] if len(parts) > 1 else ""

        input_ids = [l.strip() for l in text.split('\n') if l.strip()]
        final_list = []
        for uid in input_ids:
            low_uid = uid.lower()
            if low_uid in admin_data:
                final_list.append(f"{uid} {admin_data[low_uid]}".strip())
            else:
                final_list.append(f"{uid} ❌")

        res_text = "\n".join(final_list)
        update_session(user_id, {'waiting_for': ''})
        await update.message.reply_text(f"📊 *Fynor Services Report*\n━━━━━━━━━━━━━━\n`{res_text}`", parse_mode=ParseMode.MARKDOWN)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session(query.from_user.id)
    await query.answer()
    
    headers = {"v": "Valid List", "i": "invalid List", "d": "Duplicate List", "c": "Clean List", "do": "Duplicate List"}
    mapping = {"v": session['v'], "i": session['i'], "d": session['d'], "c": session['c'], "do": session['do']}
    
    content = mapping.get(query.data, "")
    header = headers.get(query.data, "List")
    
    if content:
        await query.message.reply_text(f"*{header}*\n\n`{content}`", parse_mode=ParseMode.MARKDOWN)

def main():
    if not TOKEN:
        print("Error: No BOT_TOKEN found in environment variables.")
        return

    keep_alive()

    app_tg = Application.builder().token(TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_menu))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    app_tg.add_handler(CallbackQueryHandler(callback_handler))
    
    print("Bot is running...")
    app_tg.run_polling()

if __name__ == '__main__':
    main()
  
