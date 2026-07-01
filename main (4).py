import os
import sys
import time
import logging
import threading
import warnings
import sqlite3
import requests

# 🛡️ GLOBAL ENVIRONMENT & SSL PATCHES
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='telebot')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ZyroVipEngine")

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton, ReplyKeyboardMarkup, KeyboardButton

# =====================================================================
# CONFIGURATIONS & CORE CREDENTIALS
# =====================================================================
BOT_TOKEN = "8571348311:AAEUCtJ20aG1MOYLPTP11SGpeOed__gMOOQ"
HERO_SMS_API_KEY = "A3dAc9766A04A98bf320fA7bA99f6994"
HERO_SMS_URL = "https://hero-sms.com/stubs/handler_api.php"
UPDATE_CHANNEL_URL = "https://t.me/ZyroUpdate"
CHANNEL_CHAT_ID = "@ZyroUpdate" 
HISTORY_CHANNEL_CHAT_ID = "@ZyroHistory"  # Naya channel jahan logs jayenge

# 👥 PUBLIC GROUP & ADMIN SETTINGS
PAYMENT_GROUP_CHAT_ID = "@ZyroPays"  
PRIMARY_ADMIN_ID = 7540007709  
SECONDARY_ADMIN_USERNAME = "@ZyroSMS"

# 🔑 AUTHORIZED PAYMENT ADMINS
ALLOWED_PAYMENT_ADMINS = ["awaisfs", "ZyroSMS"]

session = requests.Session()
session.verify = False

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

active_orders = {}         
server2_requests = {}      
payment_temp_cache = {}    
BOT_GLOBAL_STATUS = True 

# =====================================================================
# THREAD-SAFE SQLITE DATABASE ENGINE
# =====================================================================
db_lock = threading.Lock()

def run_query(query, params=(), is_select=False, fetch_all=True):
    with db_lock:
        conn = sqlite3.connect("zyro_bot.db", check_same_thread=False, timeout=60)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if is_select:
                return cursor.fetchall() if fetch_all else cursor.fetchone()
            conn.commit()
        except Exception as e:
            logger.error(f"Database Exception: {e}")
            return None
        finally:
            conn.close()

def init_db():
    run_query("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
    run_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, total_deposited REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, status TEXT DEFAULT 'active')")
    run_query("CREATE TABLE IF NOT EXISTS services (code TEXT PRIMARY KEY, name TEXT, api_code TEXT, status INTEGER DEFAULT 1)")
    run_query("CREATE TABLE IF NOT EXISTS service_countries (id INTEGER PRIMARY KEY AUTOINCREMENT, service_code TEXT, country_code TEXT, country_name TEXT, cc_prefix TEXT, price_usd TEXT, price_pkr TEXT, status INTEGER DEFAULT 1, UNIQUE(service_code, country_code))")
    run_query("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, number TEXT, otp TEXT, server TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    
    check_services = run_query("SELECT COUNT(*) FROM services", is_select=True, fetch_all=False)
    if check_services and check_services[0] == 0:
        default_services = [
            ("douyin", "Douyin", "lf"), 
            ("rednote", "Rednote", "qf"),
            ("bilibili", "Bilibili", "zs"), 
            ("whatsapp", "WhatsApp", "wa"), 
            ("telegram", "Telegram", "tg")
        ]
        for s in default_services:
            run_query("INSERT OR IGNORE INTO services VALUES (?, ?, ?, 1)", s)
        
    check_countries = run_query("SELECT COUNT(*) FROM service_countries", is_select=True, fetch_all=False)
    if check_countries and check_countries[0] == 0:
        default_mappings = [
            ("douyin", "4", "🇵🇭 Philippines", "+63", "0.05", "15"),
            ("douyin", "6", "🇮🇩 Indonesia", "+62", "0.07", "20"),
            ("rednote", "6", "🇮🇩 Indonesia", "+62", "0.04", "12"),
            ("rednote", "73", "🇧🇷 Brazil", "+55", "0.04", "12"),
            ("rednote", "14", "🇭🇰 Honkong", "+852", "0.17", "50"),
            ("bilibili", "4", "🇵🇭 Philippines", "+63", "0.06", "17"),
            ("bilibili", "6", "🇮🇩 Indonesia", "+62", "0.04", "12"),
            ("bilibili", "7", "🇲🇾 Malaysia", "+60", "0.07", "20"),
            ("bilibili", "14", "🇭🇰 Honkong", "+852", "0.17", "50"),
            ("whatsapp", "16", "🇬🇧 United Kingdom", "+44", "0.7", "200"),
            ("whatsapp", "14", "🇭🇰 Honkong", "+852", "0.5", "150"),
            ("whatsapp", "4", "🇵🇭 Philippines", "+63", "0.35", "100"),
            ("whatsapp", "6", "🇮🇩 Indonesia", "+62", "0.35", "100"),
            ("whatsapp", "8", "🇰🇪 Kenya", "+254", "0.35", "100"),
            ("whatsapp", "10", "🇻🇳 Vietnam", "+84", "0.35", "100"),
            ("telegram", "16", "🇬🇧 United Kingdom", "+44", "0.6", "170"),
            ("telegram", "14", "🇭🇰 Honkong", "+852", "0.7", "200"),
            ("telegram", "5", "🇲🇲 Myanmar", "+95", "0.35", "100"),
            ("telegram", "6", "🇮🇩 Indonesia", "+62", "0.35", "100"),
            ("telegram", "31", "🇿🇦 South Africa", "+27", "0.35", "100"),
            ("telegram", "10", "🇻🇳 Vietnam", "+84", "0.35", "100")
        ]
        for m in default_mappings:
            run_query("INSERT OR IGNORE INTO service_countries (service_code, country_code, country_name, cc_prefix, price_usd, price_pkr, status) VALUES (?, ?, ?, ?, ?, ?, 1)", m)

init_db()

def is_admin(user_id, username=None):
    if int(user_id) == PRIMARY_ADMIN_ID:
        return True
    if username and username.lower() == SECONDARY_ADMIN_USERNAME.lower():
        return True
    return False

def is_payment_admin(username):
    if username and username.lower() in ALLOWED_PAYMENT_ADMINS:
        return True
    return False

def is_user_joined_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_CHAT_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception:
        return False

def check_status(user_id, chat_id):
    if is_admin(user_id):
        return True
        
    if not BOT_GLOBAL_STATUS:
        try: bot.send_message(chat_id, "⚠️ Bot is currently Turned OFF by Admin.")
        except Exception: pass
        return False
        
    res = run_query("SELECT status FROM users WHERE user_id = ?", (user_id,), is_select=True, fetch_all=False)
    if res and res[0] == 'blocked':
        try: bot.send_message(chat_id, "❌ Your access is blocked.")
        except Exception: pass
        return False
        
    if not is_user_joined_channel(user_id):
        send_force_join_msg(chat_id)
        return False
        
    return True

def ensure_user(user_id):
    res = run_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), is_select=True, fetch_all=False)
    if not res: 
        run_query("INSERT INTO users (user_id, balance, total_deposited, total_spent, status) VALUES (?, 0.0, 0.0, 0.0, 'active')", (user_id,))

def get_typing_area_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("Check Services"), KeyboardButton("Balance"))
    markup.add(KeyboardButton("Customer Service"))
    return markup

def send_force_join_msg(chat_id):
    text = "💪🏻 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐙𝐲𝐫𝐨𝐒𝐌𝐒\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n⚠️ *Aapne hamara update channel join nahi kiya hai!*\n\nBot use karne ke liye pehle niche click karke join karein aur Verify par click karein.\n\n💬 Telegram = @ZyroSMS\n\n━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📢 Join Update Channel", url=UPDATE_CHANNEL_URL),
        InlineKeyboardButton("✅ Verify Joining", callback_data="check_channel_joining")
    )
    try: bot.send_message(chat_id, text, reply_markup=markup)
    except Exception: pass

@bot.message_handler(commands=['start'])
def welcome_user(message):
    uid = message.chat.id
    uname = message.from_user.username
    ensure_user(uid)
    
    # 1. Agar admin hai to bina kisi restriction ke main menu dikhao
    if is_admin(uid, uname):
        send_main_menu_direct(uid, uname)
        return

    # 2. Agar user ne channel join nahi kiya to force join message bhejo aur ruk jao
    if not is_user_joined_channel(uid):
        send_force_join_msg(uid)
        return
        
    # 3. Agar join kiya hua hai to hi main menu pe bhejo
    send_main_menu_direct(uid, uname)

# 🛠️ TYPING AREA BUTTONS HANDLER
@bot.message_handler(func=lambda message: message.text in ["Check Services", "Balance", "Customer Service"])
def handle_typing_area_buttons(message):
    uid = message.chat.id
    uname = message.from_user.username
    if not check_status(uid, uid): return
    
    if message.text == "Check Services":
        user_service_menu_msg(uid, uname)
    elif message.text == "Balance":
        user_balance_panel_msg(uid)
    elif message.text == "Customer Service":
        bot.send_message(uid, f"💬 *Customer Service Contact:*\n\nTelegram: @{SECONDARY_ADMIN_USERNAME}")

def send_main_menu_direct(uid, uname=None):
    text = "💪🏻 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐙𝐲𝐫𝐨𝐒𝐌𝐒\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n🤝 𝗔𝗹𝗹 𝗧𝘆𝗽𝗲 𝗢𝗧𝗣 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗶𝗻 𝗖𝗵𝗲𝗮𝗽 𝗣𝗿𝗶𝗰𝗲𝘀\n\n💬 Contact Telegram = @ZyroSMS\n\n━━━━━━━━━━━━━━━━━━━━━━\n 𝐓𝐡𝐚𝐧𝐤 𝐲𝐨𝐮 𝐟𝐨𝐫 𝐜𝐡𝐨𝐨𝐬𝐢𝐧𝐠 𝐙𝐲𝐫𝐨𝐒𝐌𝐒 !:"
    
    inline_markup = InlineKeyboardMarkup(row_width=2)
    inline_markup.add(
        InlineKeyboardButton("📦 Check Service", callback_data="user_service_menu"),
        InlineKeyboardButton("💰 Balance", callback_data="user_balance_panel")
    )
    # Sirf ek message jayega jisme dashboard text hoga aur niche automatic buttons khul jayenge. No extra message, no emoji!
    bot.send_message(uid, text, reply_markup=get_typing_area_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "check_channel_joining")
def check_channel_joining(call):
    uid = call.message.chat.id
    if is_user_joined_channel(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ Thank you! Access granted.", show_alert=False)
        try: bot.delete_message(uid, call.message.message_id)
        except Exception: pass
        send_main_menu_direct(uid, call.from_user.username)
    else:
        bot.answer_callback_query(call.id, "❌ Aapne abhi tak channel join nahi kiya! Pehle join karein.", show_alert=True)

# =====================================================================
# 👑 /ADMIN PLATFORM INTERFACE
# =====================================================================
@bot.message_handler(commands=['admin'])
def advanced_admin_hub(message):
    uid = message.chat.id
    uname = message.from_user.username
    if not is_admin(uid, uname): return
    
    text = "💪🏻 *𝐀𝐝𝐯𝐚𝐧𝐜𝐞 𝐂𝐨𝐧𝐭𝐫𝐨𝐥 𝐇𝐮𝐛*\n━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Add Balance", callback_data="adm_panel_addbal"),
        InlineKeyboardButton("Remove Balance", callback_data="adm_panel_rembal"),
        InlineKeyboardButton("Bot On/Off", callback_data="adm_panel_togglebot"),
        InlineKeyboardButton("🙈 Hide Server (S1/S2)", callback_data="adm_panel_hidesrv"), # New Button
        InlineKeyboardButton("Alert Message", callback_data="adm_panel_alert"),
        InlineKeyboardButton("User History", callback_data="adm_panel_uhistory"),
        InlineKeyboardButton("Pay History", callback_data="adm_panel_phistory")
    )
    bot.send_message(uid, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_panel_"))
def handle_admin_panel_clicks(call):
    bot.answer_callback_query(call.id)
    action = call.data.replace("adm_panel_", "")
    uid = call.message.chat.id
    uname = call.from_user.username
    if not is_admin(uid, uname): return
    global BOT_GLOBAL_STATUS

    if action == "addbal":
        msg = bot.send_message(uid, "Enter target User ID and Amount to ADD:\nFormat: `user_id,amount` (e.g., `7540007709,5.00`)")
        bot.register_next_step_handler(msg, process_admin_add_balance)
    elif action == "rembal":
        msg = bot.send_message(uid, "Enter target User ID and Amount to REMOVE:\nFormat: `user_id,amount` (e.g., `7540007709,2.50`)")
        bot.register_next_step_handler(msg, process_admin_remove_balance)
    elif action == "togglebot":
        BOT_GLOBAL_STATUS = not BOT_GLOBAL_STATUS
        status_str = "ON" if BOT_GLOBAL_STATUS else "OFF"
        bot.send_message(uid, f"⚙️ Bot status globally updated to: *{status_str}*")
    elif action == "hidesrv":
        # New Step Handler for Hiding Servers
        msg = bot.send_message(uid, "⌨️ *Kis Server ko HIDE/SHOW karna chahte hain?*\n\n👉🏻 Only Server 1 Hide karne ke liye: `1` likhein\n👉🏻 Only Server 2 Hide karne ke liye: `2` likhein\n👉🏻 Dono Servers wapas SHOW karne ke liye: `0` likhein")
        bot.register_next_step_handler(msg, process_admin_hide_server)
    elif action == "alert":
        msg = bot.send_message(uid, "Enter global alert message text to broadcast:")
        bot.register_next_step_handler(msg, process_admin_broadcast_alert)
    elif action in ["uhistory", "phistory"]:
        hist = run_query("SELECT id, user_id, service, number, server FROM history ORDER BY id DESC LIMIT 5", is_select=True)
        if not hist:
            bot.send_message(uid, "No log records found in history table database tracker.")
            return
        text = "📋 *System Logs Tracker:*\n"
        for item in hist:
            text += f"ID: {item[0]} | User: {item[1]} | {item[2]} | `{item[3]}`\n"
        bot.send_message(uid, text)

# New Function to Save Configuration in DB
def process_admin_hide_server(message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    choice = message.text.strip()
    
    if choice in ['1', '2', '0']:
        run_query("INSERT OR REPLACE INTO sys_config (key, value) VALUES ('hidden_server', ?)", (choice,))
        if choice == '0':
            bot.send_message(message.chat.id, "✅ All Servers are now *VISIBLE* to users.")
        else:
            bot.send_message(message.chat.id, f"✅ *Server {choice}* successfully *HIDDEN* from all regular users!")
    else:
        bot.send_message(message.chat.id, "❌ Invalid input. Please reply with `1`, `2`, or `0` only.")

def process_admin_add_balance(message):
    try:
        target, amt = message.text.split(",")
        target, amt = int(target.strip()), float(amt.strip())
        ensure_user(target)
        run_query("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?", (amt, amt, target))
        bot.send_message(message.chat.id, f"✅ Done. Deposited ${amt:.2f} into ledger target ID `{target}`.")
    except Exception: bot.send_message(message.chat.id, "❌ Formatting split exception mismatch.")

def process_admin_remove_balance(message):
    try:
        target, amt = message.text.split(",")
        target, amt = int(target.strip()), float(amt.strip())
        ensure_user(target)
        run_query("UPDATE users SET balance = MAX(0.0, balance - ?) WHERE user_id = ?", (amt, target))
        bot.send_message(message.chat.id, f"✅ Done. Removed ${amt:.2f} from ledger target ID `{target}`.")
    except Exception: bot.send_message(message.chat.id, "❌ Formatting split exception mismatch.")

def process_admin_broadcast_alert(message):
    users = run_query("SELECT user_id FROM users", is_select=True)
    for u in users:
        try: bot.send_message(u[0], f"📢 *𝐀𝐝𝐦𝐢𝐧 𝐍𝐨𝐭𝐢𝐟𝐢𝐜𝐚𝐭𝐢𝐨𝐧 𝐔𝐩𝐝𝐚𝐭𝐞:*\n\n{message.text}")
        except Exception: pass
    bot.send_message(message.chat.id, "✅ Global alert message dispatched.")

# =====================================================================
# USER SERVICE MENU FLOW INTERFACES
# =====================================================================
def user_service_menu_msg(uid, uname=None):
    text = "📦 𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞 𝐒𝐞𝐫𝐯𝐢𝐜𝐞𝐬\n━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    
    if is_admin(uid, uname):
        services = run_query("SELECT code, name, status FROM services", is_select=True)
        buttons = []
        for s in services:
            status_tag = "" if s[2] == 1 else " 🛑"
            buttons.append(InlineKeyboardButton(f"{s[1]}{status_tag}", callback_data=f"usr_view_app_{s[0]}"))
    else:
        services = run_query("SELECT code, name FROM services WHERE status = 1", is_select=True)
        buttons = [InlineKeyboardButton(s[1], callback_data=f"usr_view_app_{s[0]}") for s in services]
        
    markup.add(*buttons)
    
    if is_admin(uid, uname):
        markup.row(InlineKeyboardButton("➕ Add Service", callback_data="manage_srv_add"))
        markup.row(InlineKeyboardButton("➖ Remove Service", callback_data="manage_srv_remove"))
    
    bot.send_message(uid, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "user_service_menu")
def user_service_menu_callback(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    try: bot.delete_message(uid, call.message.message_id)
    except Exception: pass
    user_service_menu_msg(uid, call.from_user.username)

@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_view_app_"))
def user_view_app(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    app_code = call.data.split("_")[3]
    uname = call.from_user.username
    
    serv_data = run_query("SELECT name, status FROM services WHERE code = ?", (app_code,), is_select=True, fetch_all=False)
    if not serv_data: return
    app_name = serv_data[0]
    current_status = serv_data[1]
    
    if not is_admin(uid, uname) and current_status == 0:
        bot.send_message(uid, "⚠️ This service is temporarily disabled by Admin.")
        return

    status_str = " Active" if current_status == 1 else " Stopped"
    text = f"{app_name} ({status_str})\n\n💪🏻 𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞 𝐂𝐨𝐮𝐧𝐭𝐫𝐢𝐞𝐬 \n━━━━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    
    countries = run_query("SELECT country_code, country_name, price_usd, price_pkr FROM service_countries WHERE service_code = ? AND status = 1", (app_code,), is_select=True)
    for c_code, c_name, p_usd, p_pkr in countries:
        markup.add(InlineKeyboardButton(f"{c_name} {p_usd} $ ( {p_pkr} pkr )", callback_data=f"choose_srv_{app_code}_{c_code}"))
    
    if is_admin(uid, uname):
        markup.add(InlineKeyboardButton("💰 Edit Price", callback_data=f"manage_srv_price_{app_code}"))
        markup.row(
            InlineKeyboardButton("🛑 Stop Service", callback_data=f"manage_srv_stop_{app_code}"),
            InlineKeyboardButton("🟢 On Service", callback_data=f"manage_srv_on_{app_code}")
        )
        
    markup.add(InlineKeyboardButton("🔙 Back Menu", callback_data="user_service_menu"))
    try: bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup)
    except Exception: pass

# =====================================================================
# 🛠️ REALTIME ADMIN DYNAMIC SERVICE MANAGEMENT HANDLERS
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_srv_"))
def handle_service_management_ops(call):
    bot.answer_callback_query(call.id)
    uid = call.message.chat.id
    uname = call.from_user.username
    if not is_admin(uid, uname): return
    
    parts = call.data.split("_")
    action = parts[2]
    
    if action == "add":
        msg = bot.send_message(uid, "✨ *Add New Service*\nSend details in this exact format:\n`code,name,api_code` (e.g., `imo,IMO,im`)")
        bot.register_next_step_handler(msg, process_admin_add_service)
    elif action == "remove":
        msg = bot.send_message(uid, "➖ *Remove Service*\nEnter the unique `code` of the service to delete permanently:")
        bot.register_next_step_handler(msg, process_admin_remove_service)
    elif action == "stop":
        app_code = parts[3]
        run_query("UPDATE services SET status = 0 WHERE code = ?", (app_code,))
        bot.send_message(uid, f"✅ Service `{app_code}` has been successfully *STOPPED* 🛑")
        call.data = f"usr_view_app_{app_code}"
        user_view_app(call)
    elif action == "on":
        app_code = parts[3]
        run_query("UPDATE services SET status = 1 WHERE code = ?", (app_code,))
        bot.send_message(uid, f"✅ Service `{app_code}` has been successfully turned *ON* 🟢")
        call.data = f"usr_view_app_{app_code}"
        user_view_app(call)
    elif action == "price":
        app_code = parts[3]
        msg = bot.send_message(uid, f"💰 *Edit Country Price for Service [{app_code}]*\nSend details in this format:\n`country_code,price_usd,price_pkr` (e.g., `4,0.40,120`)\n\n_Note: Country code 4=Philippines, 6=Indonesia, 14=Hongkong, 16=UK_")
        bot.register_next_step_handler(msg, process_admin_edit_price, app_code)

def process_admin_add_service(message):
    try:
        code, name, api_code = message.text.split(",")
        run_query("INSERT OR REPLACE INTO services (code, name, api_code, status) VALUES (?, ?, ?, 1)", (code.strip(), name.strip(), api_code.strip()))
        bot.send_message(message.chat.id, f"✅ Successfully added dynamic service: *{name.strip()}*")
    except Exception: bot.send_message(message.chat.id, "❌ Invalid inputs pattern mismatch.")

def process_admin_remove_service(message):
    code = message.text.strip()
    run_query("DELETE FROM services WHERE code = ?", (code,))
    run_query("DELETE FROM service_countries WHERE service_code = ?", (code,))
    bot.send_message(message.chat.id, f"✅ Service `{code}` and its prices removed successfully.")

def process_admin_edit_price(message, app_code):
    try:
        c_code, p_usd, p_pkr = message.text.split(",")
        res = run_query("SELECT id FROM service_countries WHERE service_code = ? AND country_code = ?", (app_code, c_code.strip()), is_select=True)
        if not res:
            run_query("INSERT INTO service_countries (service_code, country_code, country_name, cc_prefix, price_usd, price_pkr, status) VALUES (?, ?, 'Custom Country', '+00', ?, ?, 1)", (app_code, c_code.strip(), p_usd.strip(), p_pkr.strip()))
        else:
            run_query("UPDATE service_countries SET price_usd = ?, price_pkr = ? WHERE service_code = ? AND country_code = ?", (p_usd.strip(), p_pkr.strip(), app_code, c_code.strip()))
        bot.send_message(message.chat.id, f"✅ Price updated for Service `{app_code}`, Country `{c_code.strip()}` -> ${p_usd} ({p_pkr} PKR)")
    except Exception: bot.send_message(message.chat.id, "❌ Error parsing updates layout structure.")


        
    cost = float(price_res[0])
# =====================================================================
# CHOOSE AND RUN ENGINES (DYNAMIC HIDDEN SERVER CONTROLLER)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("choose_srv_"))
def choose_srv(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    _, _, app_code, country_code = call.data.split("_")
    
    text = "🧘🏻 𝐒𝐞𝐥𝐞𝐜𝐭 𝐒𝐞𝐫𝐯𝐞𝐫 \n━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    
    # Check DB if any server is configured to be hidden
    hidden_cfg = run_query("SELECT value FROM sys_config WHERE key = 'hidden_server'", is_select=True, fetch_all=False)
    hidden_server = hidden_cfg[0] if hidden_cfg else "0"
    
    buttons = []
    
    # If the user is Admin, they should see both servers regardless of configuration
    if is_admin(uid, call.from_user.username):
        buttons.append(InlineKeyboardButton("💪🏻 Server No 01", callback_data=f"run_s1_srv1_{app_code}_{country_code}"))
        buttons.append(InlineKeyboardButton("🌡️ Server No 02", callback_data=f"run_s2_srv2_{app_code}_{country_code}"))
    else:
        # For regular users, apply the visibility rules dynamically
        if hidden_server != "1":
            buttons.append(InlineKeyboardButton("💪🏻 Server No 01", callback_data=f"run_s1_srv1_{app_code}_{country_code}"))
        if hidden_server != "2":
            buttons.append(InlineKeyboardButton("🌡️ Server No 02", callback_data=f"run_s2_srv2_{app_code}_{country_code}"))
            
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("🔙 Back", callback_data=f"usr_view_app_{app_code}"))
    
    try: 
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup)
    except Exception: 
        pass

# =====================================================================
# RUN SERVER 01 ENGINE (WITH FIXED CONNECTION ERROR HANDLER)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("run_s1_"))
def run_s1(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    
    try:
        _, _, _, app_code, country_code = call.data.split("_")
    except Exception as e:
        logger.error(f"Callback split mismatch error on Server 1: {e}")
        return

    user_id = call.message.chat.id
    
    # Aapka exact stylish out-of-stock aur error text message
    error_text = (
        "🩷 𝐒𝐨𝐫𝐫𝐲 \n"
        "_________________________________________\n"
        "𝗔𝗯𝗵𝗶 𝗶𝘀 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 𝗸𝘆 𝗡𝘂𝗺𝗯𝗲𝗿 𝗸𝗮 𝗦𝘁𝗼𝗰𝗸 𝗞𝗵𝗮𝘁𝘁𝗮𝗺 𝗵𝗼 𝗚𝘆𝗮 𝗵𝗮𝗶  🌶️\n\n"
        "🔄 𝐓𝐡𝐨𝐫𝐢 𝐃𝐞𝐞𝐫 𝐭𝐚𝐤 𝐇𝐮𝐦 𝐚𝐮𝐫 𝐍𝐮𝐦𝐛𝐞𝐫 𝐚𝐝𝐝 𝐤𝐚𝐫 𝐝𝐞 𝐆𝐚 \n\n"
        "𝗔𝗻𝘆 𝗜𝘀𝘀𝘂𝗲 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 = @ZyroSMS\n"
        "__________________________________________\n"
        "🩷 𝐓𝐡𝐚𝐧𝐤 𝐬𝐟𝐨𝐫  𝐜𝐡𝐨𝐨𝐬𝐢𝐧𝐠 𝐅𝐲𝐧𝐨𝐫 𝐒𝐞𝐫𝐯𝐢𝐜𝐞𝐬 !"
    )
    
    price_res = run_query("SELECT price_usd FROM service_countries WHERE service_code = ? AND country_code = ?", (app_code, country_code), is_select=True, fetch_all=False)
    if not price_res: 
        bot.send_message(user_id, error_text)
        return
        
    cost = float(price_res[0])
    
    if not is_admin(user_id, call.from_user.username):
        bal_res = run_query("SELECT balance FROM users WHERE user_id = ?", (user_id,), is_select=True, fetch_all=False)
        balance = bal_res[0] if bal_res else 0.0
        if balance < cost:
            bot.send_message(user_id, f"♎  𝐋𝐨𝐰 𝐰𝐚𝐥𝐥𝐞𝐭 𝐛𝐚𝐥𝐚𝐧𝐜𝐞! 𝐏𝐫𝐢𝐜𝐞 𝐫𝐞𝐪𝐮𝐢𝐫𝐞𝐝: ${cost:.2f}")
            return
        
    api_res = run_query("SELECT api_code, name FROM services WHERE code = ?", (app_code,), is_select=True, fetch_all=False)
    if not api_res:
        bot.send_message(user_id, error_text)
        return
        
    api_service, app_name = api_res[0], api_res[1]
    
    payload = {"api_key": HERO_SMS_API_KEY, "action": "getNumber", "service": api_service, "country": country_code}
    try:
        response = session.get(HERO_SMS_URL, params=payload, timeout=15)
        res_text = response.text.strip()
        
        if res_text.startswith("ACCESS_NUMBER"):
            _, activation_id, phone_number = res_text.split(":")
            active_orders[activation_id] = {
                "user_id": user_id, "phone": phone_number, "service": app_code, "cost": cost, 
                "app_name": app_name, "timestamp": time.time(), "msg_id": call.message.message_id
            }
            
            text = f"💪🏻 𝐒𝐞𝐫𝐯𝐞𝐫 𝟏 \n\nService = {app_name}\n━━━━━━━━━━━━━━━━━━━━━━\n🧾 𝐍𝐮𝐦𝐛𝐞𝐫 \n\n`+{phone_number}`\n\n━━━━━━━━━━━━━━━━━━━━━━\n⏳ 𝐖𝐚𝐢𝐭𝐢𝐧𝐠 𝐟𝐨𝐫 𝐎𝐓𝐏..."
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("📋 Copy Number", copy_text=CopyTextButton(text=f"+{phone_number}")), 
                InlineKeyboardButton("❌ Cancel Number", callback_data=f"cancel_s1_{activation_id}")
            )
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=poll_s1, args=(user_id, call.message.message_id, activation_id, phone_number, app_name, cost)).start()
        
        elif "NO_NUMBERS" in res_text or "NO_BALANCE" in res_text:
            bot.send_message(user_id, error_text)
        else:
            # Kisi bhi aur unexpected API response par bhi yahi message jaye
            bot.send_message(user_id, error_text)
            
    except Exception as e:
        logger.error(f"API Connection Error: {e}")
        try:
            # Ab agar communication failure (timeout/network issue) hoga, to yeh text trigger hoga
            bot.send_message(user_id, error_text)
        except Exception:
            pass

def poll_s1(user_id, message_id, activation_id, phone_number, app_name, cost):
    start_time = time.time()
    while time.time() - start_time < 1200:
        time.sleep(5)
        if activation_id not in active_orders: return
        try:
            res = session.get(HERO_SMS_URL, params={"api_key": HERO_SMS_API_KEY, "action": "getStatus", "id": activation_id}, timeout=10)
            res_text = res.text.strip()
            
            if res_text.startswith("STATUS_OK"):
                otp_code = res_text.split(":")[1]
                
                if not is_admin(user_id):
                    run_query("UPDATE users SET balance = MAX(0.0, balance - ?), total_spent = total_spent + ? WHERE user_id = ?", (cost, cost, user_id))
                
                run_query("INSERT INTO history (user_id, service, number, otp, server) VALUES (?, ?, ?, ?, 'Server 1')", (user_id, app_name, phone_number, otp_code))
                text = f"💪🏻 𝐎𝐓𝐏 𝐑e𝐜e𝐢𝐯e𝐝\n\nService : {app_name}\n━━━━━━━━━━━━━━━━━━━━━━\n🧾 𝐍𝐮𝐦𝐛𝐞𝐫\n\n`+{phone_number}`\n\n━━━━━━━━━━━━━━━━━━━━━━\n🔐 OTP\n\n`{otp_code}`"
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    InlineKeyboardButton("📋 Copy OTP", copy_text=CopyTextButton(text=otp_code)), 
                    InlineKeyboardButton("🔄 Get Again OTP", callback_data=f"again_s1_{activation_id}")
                )
                bot.send_message(user_id, text, reply_markup=markup)
                session.get(HERO_SMS_URL, params={"api_key": HERO_SMS_API_KEY, "action": "setStatus", "status": "6", "id": activation_id})
                
                try:
                    user_info = bot.get_chat(user_id)
                    u_name = f"@{user_info.username}" if user_info.username else f"User [{user_id}]"
                    
                    group_design = (
                        "💪🏻 𝐎𝐓𝐏 𝐑𝐞𝐜𝐞𝐢𝐯𝐞𝐝\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💪🏻 𝐒e𝐫𝐯𝐢𝐜𝐞 = {app_name}\n"
                        f"🌍 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 = Server 1 🏳️\n"
                        f"👤 𝐔𝐬𝐞𝐫 = {u_name}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🧾 𝐍𝐮𝐦𝐛𝐞𝐫 = `+{phone_number}`\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🔐 𝐎𝐓𝐏 = `{otp_code}`\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🩷 𝐓𝐡𝐚𝐧𝐤 𝐲𝐨𝐮 𝐟𝐨𝐫 𝐜𝐡𝐨𝐨𝐬𝐢𝐧𝐠 𝐙𝐲𝐫𝐨𝐒𝐌𝐒"
                    )
                    bot.send_message("@FynorOtps", group_design, parse_mode="Markdown")
                except Exception:
                    pass
                
                if activation_id in active_orders: del active_orders[activation_id]
                return
            elif res_text in ["STATUS_CANCEL", "STATUS_REFUND"]:
                if activation_id in active_orders: del active_orders[activation_id]
                bot.send_message(user_id, "❌ Order session terminated.")
                return
        except Exception: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_s1_"))
def cancel_s1_(call):
    bot.answer_callback_query(call.id)
    act_id = call.data.split("_")[2]
    if act_id not in active_orders: return
    
    order = active_orders[act_id]
    elapsed = time.time() - order["timestamp"]
    
    if elapsed < 120:
        bot.send_message(order["user_id"], "Service Delete after 2 minutes")
        return
        
    del active_orders[act_id]
    session.get(HERO_SMS_URL, params={"api_key": HERO_SMS_API_KEY, "action": "setStatus", "status": "8", "id": act_id})
    bot.edit_message_text("❌ Request successfully cancelled.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("again_s1_"))
def again_s1(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🔄 Fetching another dynamic OTP sequence context...")

# =====================================================================
# 👑 SERVER 2 (MANUAL ROUTING PROCESSOR)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("run_s2_"))
def run_s2(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    
    try:
        # Fixed alignment split pattern here as well to balance execution
        _, _, _, app_code, country_code = call.data.split("_")
    except Exception as e:
        logger.error(f"Callback split mismatch error on Server 2: {e}")
        return

    user_id = call.message.chat.id
    req_id = str(int(time.time() * 100))
    
    app_name_data = run_query("SELECT name FROM services WHERE code = ?", (app_code,), is_select=True, fetch_all=False)
    c_name_data = run_query("SELECT country_name FROM service_countries WHERE service_code = ? AND country_code = ?", (app_code, country_code), is_select=True, fetch_all=False)
    app_name = app_name_data[0] if app_name_data else "Unknown"
    c_name = c_name_data[0] if c_name_data else "Unknown"
    
    server2_requests[req_id] = {
        "user_id": user_id, "username": call.from_user.username or "No_Username", "app_code": app_code, 
        "app_name": app_name, "country_name": c_name, "msg_id": call.message.message_id, "number": None
    }
    bot.edit_message_text("⏳ Request sent safely to administrative desk. Waiting for approval update...", user_id, call.message.message_id)
    
    adm_text = f"⚠️ Server 2 Admin Request\n\n📥 New OTP Request\n━━━━━━━━━━━━━━━━━━━━━━\n\nService = {app_name}\n\n🌍 Country\n{c_name}\n\n👤 User\n@{call.from_user.username or 'No_Username'}"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Done", callback_data=f"s2a_done_{req_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"s2a_cancel_{req_id}")
    )
    bot.send_message(PRIMARY_ADMIN_ID, adm_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("s2a_"))
def s2a_actions(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id, call.from_user.username): return
    action = call.data.split("_")[1]
    req_id = call.data.split("_")[2]
    if req_id not in server2_requests: return
    ord_data = server2_requests[req_id]
    
    if action == "cancel":
        bot.send_message(ord_data["user_id"], "❌ Your Server 2 manual request details were rejected by admin desk.")
        del server2_requests[req_id]
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif action == "done":
        msg = bot.send_message(call.message.chat.id, "Admin Enter Number\n\nSend Number\n\nExample\n\n+636577655678\n━━━━━━━━━━━━━━━━━━━━━━")
        bot.register_next_step_handler(msg, admin_submits_s2_number, req_id)

def admin_submits_s2_number(message, req_id):
    if not is_admin(message.from_user.id, message.from_user.username) or req_id not in server2_requests: return
    num = message.text.strip()
    ord_data = server2_requests[req_id]
    ord_data["number"] = num
    
    user_text = f"Service = {ord_data['app_name']}\n━━━━━━━━━━━━━━━━━━━━━━\n\n📱 Number\n\n`{num}`\n\n━━━━━━━━━━━━━━━━━━━━━━\n⏳ Waiting for OTP..."
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📋 Copy Number", copy_text=CopyTextButton(text=num)), 
        InlineKeyboardButton("❌ Cancel Number", callback_data=f"cancel_s2_{req_id}")
    )
    bot.edit_message_text(user_text, ord_data["user_id"], ord_data["msg_id"], reply_markup=markup)
    
    adm_text = f"Service = {ord_data['app_name']}\n━━━━━━━━━━━━━━━━━━━━━━\n\n📱 Number\n\n`{num}`\n\n👤 User\n@{ord_data['username']}"
    markup_adm = InlineKeyboardMarkup()
    markup_adm.add(InlineKeyboardButton("📨 Send OTP", callback_data=f"s2s_promptotp_{req_id}"))
    bot.send_message(message.chat.id, adm_text, reply_markup=markup_adm)

@bot.callback_query_handler(func=lambda call: call.data.startswith("s2s_promptotp_"))
def s2s_promptotp(call):
    bot.answer_callback_query(call.id)
    req_id = call.data.split("_")[2]
    msg = bot.send_message(call.message.chat.id, "⌨️ Enter the verification OTP string code safely:")
    bot.register_next_step_handler(msg, admin_sends_s2_otp, req_id)

def admin_sends_s2_otp(message, req_id):
    if not is_admin(message.from_user.id, message.from_user.username) or req_id not in server2_requests: return
    otp_val = message.text.strip()
    ord_data = server2_requests[req_id]
    
    price_res = run_query("SELECT price_usd FROM service_countries WHERE service_code = ?", (ord_data["app_code"],), is_select=True, fetch_all=False)
    cost = float(price_res[0]) if price_res else 0.0
    if not is_admin(ord_data["user_id"]):
        run_query("UPDATE users SET balance = MAX(0.0, balance - ?), total_spent = total_spent + ? WHERE user_id = ?", (cost, cost, ord_data["user_id"]))

    user_text = f"Service = {ord_data['app_name']} \n━━━━━━━━━━━━━━━━━━━━━━\n\n📱 Number\n\n`{ord_data['number']}`\n\n━━━━━━━━━━━━━━━━━━━━━━\n🔐 OTP\n\n`{otp_val}`"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📋 Copy OTP", copy_text=CopyTextButton(text=otp_val)), 
        InlineKeyboardButton("🔄 Get Again OTP", callback_data=f"again_s2_{req_id}")
    )
    bot.send_message(ord_data["user_id"], user_text, reply_markup=markup)
    bot.send_message(message.chat.id, "🟢 OTP routed successfully.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_s2_"))
def cancel_s2_(call):
    bot.answer_callback_query(call.id)
    req_id = call.data.split("_")[2]
    bot.edit_message_text("❌ Session closed.", call.message.chat.id, call.message.message_id)
    if req_id in server2_requests: del server2_requests[req_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith("again_s2_"))
def again_s2_trigger(call):
    bot.answer_callback_query(call.id)
    req_id = call.data.split("_")[2]
    if req_id not in server2_requests: return
    ord_data = server2_requests[req_id]
    
    adm_text = f"⚠️ Server 2 Admin Request (Get Again Triggered)\n\n📥 New OTP Request\n━━━━━━━━━━━━━━━━━━━━━━\n\nService = {ord_data['app_name']}\n\n🌍 Country\n{ord_data['country_name']}\n\n👤 User\n@{ord_data['username']}"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Done", callback_data=f"s2a_done_{req_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"s2a_cancel_{req_id}")
    )
    bot.send_message(PRIMARY_ADMIN_ID, adm_text, reply_markup=markup)
    bot.send_message(ord_data["user_id"], "🔄 Get Again Request forwarded to Admin successfully.")


# =====================================================================
# 💳 ADVANCED DYNAMIC USER PAYMENT ENGINE (WORKING FLOW)
# =====================================================================
def user_balance_panel_msg(uid):
    res = run_query("SELECT balance, total_deposited, total_spent FROM users WHERE user_id = ?", (uid,), is_select=True, fetch_all=False)
    current_bal, total_dep, spent = res if res else (0.0, 0.0, 0.0)
    text = f"💳 *𝐘𝐨𝐮𝐫 𝐁𝐚𝐥𝐚𝐧𝐜𝐞*\n━━━━━━━━━━━━━━━━━━━━━━\n\n💰 *𝗧𝗼𝘁𝗮𝗹 𝗗𝗲𝗽𝗼𝘀𝗶𝘁𝗲𝗱:* ${total_dep:.2f}\n📉 *𝗧𝗼𝘁𝗮𝗹 𝗦𝗽𝗲𝗻𝘁:* ${spent:.2f}\n💵 *𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗪𝗮𝗹𝗹𝗲𝘁:* ${current_bal:.2f}\n━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("♎ Add Balance", callback_data="add_balance_direct_methods"),
        InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_welcome")
    )
    bot.send_message(uid, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "user_balance_panel")
def user_balance_panel_callback(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    try: bot.delete_message(uid, call.message.message_id)
    except Exception: pass
    user_balance_panel_msg(uid)

@bot.callback_query_handler(func=lambda call: call.data == "add_balance_direct_methods")
def add_balance_direct_methods_callback(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    try: bot.delete_message(uid, call.message.message_id)
    except Exception: pass
    
    text = "✨ *𝐏𝐚𝐲𝐦𝐞𝐧𝐭 𝐌𝐞𝐭𝐡𝐨𝐝𝐬* ✨\n━━━━━━━━━━━━━━━━━━━━━━\n\nSelect your preferred payment method below:\n\n🔹 *Minimum Deposit 💸:* 0.5 USDT / 100 PKR\n━━━━━━━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Easypaisa", callback_data="pgate_easypaisa"),
        InlineKeyboardButton("Jazzcash", callback_data="pgate_jazzcash"),
        InlineKeyboardButton("Binance", callback_data="pgate_binance"),
        InlineKeyboardButton("🔙 Back Menu", callback_data="user_balance_panel")
    )
    bot.send_message(uid, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pgate_"))
def pay_gate_init(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    try: bot.delete_message(uid, call.message.message_id)
    except Exception: pass
    
    gateway = call.data.split("_")[1]
    
    if gateway == "easypaisa":
        text = "<b>𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐃𝐞𝐭𝐚𝐢𝐥𝐬 </b> 📃 \n\n<b>𝗔𝗰𝗰𝗼𝘂𝗻𝘁 :</b> Easypaisa\n<b>𝗡𝗮𝗺𝗲 :</b> Saira Bibi\n<b>𝗡𝘂𝗺𝗯𝗲𝗿 :</b> <code>03087886967</code>\n\n⚠️ <i>𝐏𝐥𝐞𝐚𝐬𝐞 𝐭𝐚𝐤𝐞 𝐚 𝐒𝐜𝐫𝐞𝐞𝐧𝐬𝐡𝐨𝐭 𝐚𝐟𝐭𝐞𝐫 𝐦𝐚𝐤𝐢𝐧𝐠 𝐭𝐡𝐞 𝐏𝐚𝐲𝐦𝐞𝐧𝐭:</i>"
    elif gateway == "jazzcash":
        text = "<b>𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐃𝐞𝐭𝐚𝐢𝐥𝐬 </b> 📃 \n\n<b>𝗔𝗰𝗰𝗼𝘂𝗻𝘁 :</b> Jazzcash\n<b>𝗡𝗮𝗺𝗲 :</b> Saira Bibi\n<b>𝗡𝘂𝗺𝗯𝗲𝗿 :</b> <code>03087886967</code>\n\n⚠️ <i>𝐏𝐥𝐞𝐚𝐬𝐞 𝐭𝐚𝐤𝐞 𝐚 𝐒𝐜𝐫𝐞𝐞𝐧𝐬𝐡𝐨𝐭 𝐚𝐟𝐭𝐞𝐫 𝐦𝐚𝐤𝐢𝐧𝐠 𝐭𝐡𝐞 𝐏𝐚𝐲𝐦𝐞𝐧𝐭:</i>"
    elif gateway == "binance":
        text = "<b>𝐀𝐜𝐜𝐨𝐮𝐧𝐭 𝐃𝐞𝐭𝐚𝐢𝐥𝐬 </b> 📃 \n\n<b>𝗔𝗰𝗰𝗼𝘂𝗻𝘁 :</b> Binance Pay\n<b>𝗨𝘀𝗲𝗿:</b> <code>Zayan_2662</code>\n<b>𝗕𝗶𝗻𝗮𝗻𝗰𝗲 𝗜𝗗:</b> <code>1178891914</code>\n\n⚠️ <i>𝐏𝐥𝐞𝐚𝐬𝐞 𝐭𝐚𝐤𝐞 𝐚 𝐒𝐜𝐫𝐞𝐞𝐧𝐬𝐡𝐨𝐭 𝐚𝐟𝐭𝐞𝐫 𝐦𝐚𝐤𝐢𝐧𝐠 𝐭𝐡𝐞 𝐏𝐚𝐲𝐦𝐞𝐧𝐭:</i>"
    else:
        text = "Invalid gateway."
               
    msg = bot.send_message(uid, text, parse_mode="HTML")
    bot.register_next_step_handler(msg, collect_payment_screenshot, gateway)

def collect_payment_screenshot(message, gateway):
    uid = message.chat.id
    if not check_status(message.from_user.id, uid): return
    username = message.from_user.username or "No_Username"
    
    if not message.photo:
        msg = bot.send_message(uid, "𝐒𝐞𝐧𝐝 𝐏𝐚𝐲𝐦𝐞𝐧𝐭 𝐒𝐜𝐫𝐞𝐞𝐧𝐬𝐡𝐨𝐭 🧾:")
        bot.register_next_step_handler(msg, collect_payment_screenshot, gateway)
        return
        
    file_id = message.photo[-1].file_id
    ticket_id = str(int(time.time() * 100))
    payment_temp_cache[ticket_id] = {"user_id": uid, "username": username, "gateway": gateway, "file_id": file_id}
    
    bot.send_message(uid, "⏳ 𝐘𝐨𝐮𝐫 𝐩𝐚𝐲𝐦𝐞𝐧𝐭 𝐢𝐬 𝐮𝐧𝐝𝐞𝐫 𝐫𝐞𝐯𝐢𝐞𝐰. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐰𝐚𝐢𝐭.")
    
    grp_text = f"User id: <code>{uid}</code>\nUser name: @{username}\nGateway: {gateway.upper()}"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Send Pay", callback_data=f"grp_receive_{ticket_id}"),
        InlineKeyboardButton("❌ Rejected", callback_data=f"grp_cancel_{ticket_id}")
    )
    
    try:
        bot.send_photo(PAYMENT_GROUP_CHAT_ID, file_id, caption=grp_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Group forward error: {e}")
        bot.send_message(uid, "⚠️ System error: Tumhara screenshot admin tak pohanchanay mein masla aya. Support se rabta karo.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("grp_"))
def group_payment_verdict(call):
    if not is_payment_admin(call.from_user.username):
        bot.answer_callback_query(call.id, "❌ Aap is payment ko approve/reject nahi kar sakte! Only @AwaisFS & @FynorAdmin allowed.", show_alert=True)
        return
        
    bot.answer_callback_query(call.id)
    parts = call.data.split("_", 2)
    action = parts[1]
    ticket_id = parts[2]
    
    if ticket_id not in payment_temp_cache: 
        bot.answer_callback_query(call.id, "❌ Ticket expired or already processed.", show_alert=True)
        return
        
    ticket = payment_temp_cache[ticket_id]
    
    if action == "cancel":
        bot.send_message(ticket["user_id"], "❌ Your uploaded transaction ticket reference proof has been rejected by management.")
        try: bot.edit_message_caption("❌ <b>Transaction REJECTED by Admin.</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")
        except Exception: pass
        if ticket_id in payment_temp_cache: del payment_temp_cache[ticket_id]
        
    elif action == "receive":
        msg = bot.send_message(PAYMENT_GROUP_CHAT_ID, f"⌨️ @{call.from_user.username}, please enter amount to add for user @{ticket['username']}:")
        bot.register_next_step_handler(msg, group_finalizes_credit_load, ticket_id)

def group_finalizes_credit_load(message, ticket_id):
    if ticket_id not in payment_temp_cache:
        return
        
    # 🔍 Check real-time if the message sender is an admin/creator in the group
    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        is_group_admin = member.status in ['administrator', 'creator']
    except Exception:
        is_group_admin = False

    if not is_group_admin:
        bot.send_message(message.chat.id, "❌ Only Group Admins can enter the amount.")
        return
        
    try:
        final_credit = float(message.text.strip())
        ticket = payment_temp_cache[ticket_id]
        target_uid = ticket["user_id"]
        ensure_user(target_uid)
        
        # Database Ledger Update
        run_query("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?", (final_credit, final_credit, target_uid))
        
        success_receipt = f"💳 *𝐏𝐚𝐲𝐦𝐞𝐧𝐭 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐲 𝐀𝐝𝐝𝐞𝐝*\n━━━━━━━━━━━━━━━━━━━━━━\n\n𝗬𝗼𝘂𝗿 𝗣𝗮𝘆𝗺𝗲𝗻𝘁 𝗵𝗮𝘀 𝗯𝗲𝗲𝗻 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝒅 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 ✅\n\nAdded Balance Amount = *${final_credit:.2f}*\n\n🩷 𝐓𝐡𝐚𝐧𝐤 𝐲𝐨𝐮 𝐟𝐨𝐫 𝐜𝐡𝐨𝐨𝐬𝐢𝐧𝐠 𝐙𝐲𝐫𝐨𝐒𝐌𝐒 !\n━━━━━━━━━━━━━━━━━━━━━━"
        
        bot.send_message(target_uid, success_receipt, parse_mode="Markdown")
        bot.send_message(PAYMENT_GROUP_CHAT_ID, f"✅ Successfully authorized and added <b>${final_credit:.2f}</b> wallet balance to user @{ticket['username']}.", parse_mode="HTML")
        
        # 📢 Send Log to @ZyroHistory for Approval
        try:
            from datetime import datetime
            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%I:%M %p")
            
            user_username = f"@{ticket['username']}" if ticket['username'] != "No_Username" else f"User [{ticket['user_id']}]"
            
            approve_log = (
                "✅ 𝐏𝐚𝐲𝐦𝐞𝐧𝐭 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 𝐔𝐬𝐞𝐫 \n➜ {user_username}\n\n"
                f"💵 𝐀𝐦𝐨𝐮𝐧𝐭\n➜ ${final_credit:.2f}\n\n"
                f"📅 𝐃𝐚𝐭𝐞\n➜ {current_date}\n\n"
                f"🕒 𝐓𝐢𝐦𝐞\n➜ {current_time}\n\n"
                "📌 𝐒𝐭𝐚𝐭𝐮𝐬\n➜ Successfully Added\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🩷 𝐙𝐲𝐫𝐨𝐒𝐌𝐒"
            )
            bot.send_message(HISTORY_CHANNEL_CHAT_ID, approve_log)
        except Exception as e:
            logger.error(f"Error sending approve log to channel: {e}")

        # Cache memory clear
        if ticket_id in payment_temp_cache:
            del payment_temp_cache[ticket_id]

    except Exception:
        msg = bot.send_message(PAYMENT_GROUP_CHAT_ID, "❌ Parsing numeric entity failure. Send exact numeric input value (e.g., 5.0):")
        bot.register_next_step_handler(msg, group_finalizes_credit_load, ticket_id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_welcome")
def back_to_welcome(call):
    uid = call.message.chat.id
    if not check_status(call.from_user.id, uid): return
    bot.answer_callback_query(call.id)
    try: bot.delete_message(uid, call.message.message_id)
    except Exception: pass
    send_main_menu_direct(uid, call.from_user.username)

if __name__ == "__main__":
    logger.info("👑 ZyroSMS Multi-Admin Native Enterprise Engine Online.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
