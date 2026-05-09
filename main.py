# ============================================================
# Telegram Bot — Instagram Account Collector
# Single-file implementation using pyTelegramBotAPI + gspread
# ============================================================

import os
import json
import logging
import random
import string
from datetime import datetime

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import gspread
from google.oauth2.service_account import Credentials   # ← Fixed
from dotenv import load_dotenv

# ── Load environment variables from .env (local dev only) ──
load_dotenv()

# ── Logging setup ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN            = os.environ.get("BOT_TOKEN", "")
ADMIN_USERNAME       = os.environ.get("ADMIN_USERNAME", "@Sefuax")
ADMIN_ID             = int(os.environ.get("ADMIN_ID", "0"))
SPREADSHEET_ID       = os.environ.get("SPREADSHEET_ID", "1fOEBy1EQrjE8qbjQpRPIWK83QsMG_z2F3divgumqvaU")
GOOGLE_CREDENTIALS   = os.environ.get("GOOGLE_CREDENTIALS", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set.")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID is not set.")
if not GOOGLE_CREDENTIALS:
    raise ValueError("GOOGLE_CREDENTIALS is not set.")

# ============================================================
# GOOGLE SHEETS SETUP (IMPROVED WITH BETTER ERROR)
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheet():
    """Connect to Google Sheets with detailed error"""
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        print("✅ GOOGLE_CREDENTIALS JSON Loaded")
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        print("✅ Service Account Credentials Created")
        
        client = gspread.authorize(credentials)
        print("✅ gspread Authorized")
        
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"✅ Spreadsheet Opened: {spreadsheet.title}")
        
        worksheet = spreadsheet.sheet1
        print("✅ Worksheet Ready")
        
        logger.info("✅ Google Sheets Connected Successfully!")
        return worksheet
        
    except Exception as e:
        logger.error(f"❌ Google Sheets Error: {type(e).__name__} - {e}")
        print(f"❌ Full Error: {type(e).__name__} - {e}")
        raise

# ============================================================
# APPROVED USERS
# ============================================================

APPROVED_FILE = "approved_users.json"

def load_approved() -> dict:
    if os.path.exists(APPROVED_FILE):
        with open(APPROVED_FILE, "r") as f:
            return json.load(f)
    return {}

def save_approved(data: dict):
    with open(APPROVED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_approved(user_id: int) -> bool:
    data = load_approved()
    return str(user_id) in data

def approve_user(user_id: int):
    data = load_approved()
    data[str(user_id)] = True
    save_approved(data)
    logger.info(f"✅ User {user_id} approved.")

# ============================================================
# FAKE INFO GENERATOR
# ============================================================

FIRST_NAMES = ["Alex", "Jordan", "Morgan", "Casey", "Riley", "Taylor",
               "Blake", "Quinn", "Avery", "Cameron", "Logan", "Reese"]
LAST_NAMES  = ["Carter", "Brooks", "Hayes", "Morgan", "Reyes", "Flynn",
               "Stone", "Chase", "Walsh", "Grant", "Sloane", "Cruz"]
GENDERS     = ["Male", "Female"]

def generate_fake_info() -> dict:
    first  = random.choice(FIRST_NAMES)
    last   = random.choice(LAST_NAMES)
    gender = random.choice(GENDERS)

    prefix   = first[:3].lower()
    suffix   = last[:4].lower()
    numbers  = str(random.randint(100, 999))
    username = f"{prefix}{numbers}{suffix}"

    return {
        "name":     f"{first} {last}",
        "username": username,
        "gender":   gender
    }

# ============================================================
# CONVERSATION STATE
# ============================================================

user_state = {}
user_data  = {}

def set_state(user_id: int, state: str | None):
    user_state[user_id] = state

def get_state(user_id: int) -> str | None:
    return user_state.get(user_id)

def store_temp(user_id: int, key: str, value: str):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value

def get_temp(user_id: int, key: str) -> str:
    return user_data.get(user_id, {}).get(key, "")

def clear_temp(user_id: int):
    user_data.pop(user_id, None)
    user_state.pop(user_id, None)

# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("1️⃣ Submit Account ✅"),
        KeyboardButton("2️⃣ Fake - Info 🎫"),
        KeyboardButton("3️⃣ 👤 Admin")
    )
    return kb

def approve_inline(user_id: int, username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Deny",    callback_data=f"deny_{user_id}")
    )
    return kb

# ============================================================
# BOT INSTANCE
# ============================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ============================================================
# /start COMMAND
# ============================================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id  = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    logger.info(f"/start from user {user_id} (@{username})")

    if is_approved(user_id):
        bot.send_message(
            user_id,
            f"👋 <b>Welcome back, {message.from_user.first_name}!</b>\n\n"
            "Use the buttons below to get started. 👇",
            reply_markup=main_keyboard()
        )
    else:
        bot.send_message(
            user_id,
            "⏳ <b>Approval request was sent to the admin.</b>\n\n"
            "Please wait while your access is reviewed. You'll be notified once approved. 🔐"
        )

        try:
            bot.send_message(
                ADMIN_ID,
                f"🔔 <b>New Access Request</b>\n\n"
                f"👤 <b>Name:</b> {message.from_user.full_name}\n"
                f"🔖 <b>Username:</b> @{username}\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n\n"
                f"Approve or deny this user:",
                reply_markup=approve_inline(user_id, username)
            )
        except Exception as e:
            logger.error(f"Could not send approval request to admin: {e}")

# ============================================================
# ADMIN APPROVAL CALLBACK
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("deny_"))
def handle_approval(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ You are not authorized.")
        return

    parts     = call.data.split("_")
    action    = parts[0]
    target_id = int(parts[1])

    if action == "approve":
        approve_user(target_id)
        try:
            bot.send_message(
                target_id,
                "✅ <b>Your access has been approved!</b>\n\n"
                "Welcome aboard! Use the buttons below to get started. 🎉",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.error(f"Could not notify approved user {target_id}: {e}")

        bot.edit_message_text(
            f"✅ <b>User {target_id} approved.</b>",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "✅ User approved!")

    elif action == "deny":
        try:
            bot.send_message(
                target_id,
                "❌ <b>Your access request was denied.</b>\n\n"
                "Contact the admin for more information."
            )
        except Exception as e:
            logger.error(f"Could not notify denied user {target_id}: {e}")

        bot.edit_message_text(
            f"❌ <b>User {target_id} denied.</b>",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "❌ User denied.")

# ============================================================
# MAIN MESSAGE HANDLER
# ============================================================

@bot.message_handler(func=lambda msg: True)
def handle_messages(message):
    user_id = message.from_user.id
    text    = message.text.strip()

    if not is_approved(user_id):
        bot.send_message(
            user_id,
            "⏳ <b>Your access is still pending admin approval.</b>\n"
            "Please wait or contact @Sefuax."
        )
        return

    state = get_state(user_id)

    if state == "awaiting_username":
        store_temp(user_id, "ig_username", text)
        set_state(user_id, "awaiting_password")
        bot.send_message(
            user_id,
            "🔑 <b>Step 2 of 3</b>\n\n"
            "Please enter the <b>account password</b>:"
        )
        return

    if state == "awaiting_password":
        store_temp(user_id, "password", text)
        set_state(user_id, "awaiting_2fa")
        bot.send_message(
            user_id,
            "🛡️ <b>Step 3 of 3</b>\n\n"
            "Please enter the <b>2FA code or Authenticator Key</b>:\n"
            "<i>(If none, type: none)</i>"
        )
        return

    if state == "awaiting_2fa":
        store_temp(user_id, "twofa", text)

        ig_user  = get_temp(user_id, "ig_username")
        password = get_temp(user_id, "password")
        twofa    = get_temp(user_id, "twofa")

        try:
            save_to_sheet(ig_user, password, twofa, user_id)
            bot.send_message(
                user_id,
                "✅ <b>Account information saved successfully.</b>\n\n"
                "Thank you! Your submission has been recorded. 📋",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            bot.send_message(
                user_id,
                "⚠️ <b>Failed to save data.</b>\n\n"
                f"Error: <code>{e}</code>",
                reply_markup=main_keyboard()
            )

        clear_temp(user_id)
        return

    if "Submit Account" in text:
        set_state(user_id, "awaiting_username")
        bot.send_message(
            user_id,
            "📋 <b>Submit Account — Step 1 of 3</b>\n\n"
            "Please enter your <b>Instagram username</b>:\n"
            "<i>(without the @ symbol)</i>"
        )
        return

    if "Fake" in text:
        info = generate_fake_info()
        bot.send_message(
            user_id,
            f"🎫 <b>Generated Fake Profile</b>\n\n"
            f"👤 <b>Name:</b> {info['name']}\n"
            f"🔖 <b>Username:</b> <code>{info['username']}</code>\n"
            f"⚧ <b>Gender:</b> {info['gender']}\n\n"
            f"<i>Tap the username to copy it.</i>"
        )
        return

    if "Admin" in text:
        bot.send_message(
            user_id,
            f"👤 <b>Admin Contact</b>\n\n"
            f"📩 Reach the admin at: {ADMIN_USERNAME}\n\n"
            f"<i>Click the username above to open a chat.</i>"
        )
        return

    bot.send_message(
        user_id,
        "❓ <b>Unknown command.</b>\n\n"
        "Please use the buttons on your keyboard. 👇",
        reply_markup=main_keyboard()
    )

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    logger.info("🤖 Bot is starting...")
    logger.info(f"Admin ID: {ADMIN_ID} | Admin Username: {ADMIN_USERNAME}")

    try:
        sheet = get_sheet()
        logger.info(f"📊 Google Sheet connected: {sheet.title}")
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets not connected on startup: {e}")

    logger.info("✅ Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
