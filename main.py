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
from oauth2client.service_account import ServiceAccountCredentials
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
# CONFIGURATION — pulled from environment variables
# ============================================================

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@Sefuax")
ADMIN_ID       = int(os.environ.get("ADMIN_ID", "0"))
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1raKo528RX1ExRDBBYCUzcjhMG6VsVS7x")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set. Add it to your .env or Railway environment variables.")

if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID is not set. Add your Telegram numeric user ID.")

# ============================================================
# GOOGLE SHEETS SETUP
# How it works:
#   1. credentials.json sits in the same folder as main.py
#   2. We pass SPREADSHEET_ID to open the exact sheet
#   3. gspread uses oauth2client to authenticate
# ============================================================

SCOPES = [
    "[spreadsheets.google.com](https://spreadsheets.google.com/feeds)",
    "[googleapis.com](https://www.googleapis.com/auth/drive)"
]

def get_sheet():
    """
    Connect to Google Sheets and return the first worksheet.
    credentials.json must be in the same directory as main.py.
    On Railway, upload credentials.json as a file or use a base64 env var (see guide below).
    """
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1  # First sheet tab
        logger.info("✅ Connected to Google Sheets successfully.")
        return worksheet
    except FileNotFoundError:
        logger.error("credentials.json not found. Place it in the same folder as main.py.")
        raise
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {e}")
        raise

def save_to_sheet(username: str, password: str, twofa: str, user_id: int):
    """
    Append a new row to the Google Sheet.
    Columns: A=Username | B=Password | C=2FA Key | D=Telegram User ID | E=Submission Time
    """
    try:
        sheet = get_sheet()
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        sheet.append_row([username, password, twofa, str(user_id), timestamp])
        logger.info(f"📋 Data saved for Telegram user {user_id}.")
    except Exception as e:
        logger.error(f"Failed to save data to sheet: {e}")
        raise

# ============================================================
# APPROVED USERS — stored locally in approved_users.json
# Format: { "user_id": true, ... }
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
    """Generate a random name, stylish username with numbers in the middle, and gender."""
    first  = random.choice(FIRST_NAMES)
    last   = random.choice(LAST_NAMES)
    gender = random.choice(GENDERS)

    # Build username: first 3 letters + 3 random digits + last 4 letters
    prefix  = first[:3].lower()
    suffix  = last[:4].lower()
    numbers = str(random.randint(100, 999))
    username = f"{prefix}{numbers}{suffix}"

    return {
        "name":     f"{first} {last}",
        "username": username,
        "gender":   gender
    }

# ============================================================
# CONVERSATION STATE
# Tracks multi-step form for each user.
# States: None | "awaiting_username" | "awaiting_password" | "awaiting_2fa"
# ============================================================

user_state = {}    # { user_id: "state_string" }
user_data  = {}    # { user_id: { "ig_username": ..., "password": ... } }

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
    """Main reply keyboard shown to approved users."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("1️⃣ Submit Account ✅"),
        KeyboardButton("2️⃣ Fake - Info 🎫"),
        KeyboardButton("3️⃣ 👤 Admin")
    )
    return kb

def approve_inline(user_id: int, username: str) -> InlineKeyboardMarkup:
    """Inline keyboard sent to admin for approval."""
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "✅ Approve",
            callback_data=f"approve_{user_id}"
        ),
        InlineKeyboardButton(
            "❌ Deny",
            callback_data=f"deny_{user_id}"
        )
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
    user_id   = message.from_user.id
    username  = message.from_user.username or message.from_user.first_name

    logger.info(f"/start from user {user_id} (@{username})")

    if is_approved(user_id):
        # ── Already approved: show main keyboard ──
        bot.send_message(
            user_id,
            f"👋 <b>Welcome back, {message.from_user.first_name}!</b>\n\n"
            "Use the buttons below to get started. 👇",
            reply_markup=main_keyboard()
        )
    else:
        # ── Not approved: send waiting message + notify admin ──
        bot.send_message(
            user_id,
            "⏳ <b>Approval request was sent to the admin.</b>\n\n"
            "Please wait while your access is reviewed. You'll be notified once approved. 🔐"
        )

        # Send approval request to admin
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
            logger.info(f"Approval request sent to admin for user {user_id}.")
        except Exception as e:
            logger.error(f"Could not send approval request to admin: {e}")

# ============================================================
# ADMIN: APPROVAL CALLBACK
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("deny_"))
def handle_approval(call):
    """Handle admin's approve/deny decision."""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ You are not authorized.")
        return

    parts     = call.data.split("_")
    action    = parts[0]   # "approve" or "deny"
    target_id = int(parts[1])

    if action == "approve":
        approve_user(target_id)

        # Notify approved user
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
# Handles keyboard buttons + multi-step conversation states
# ============================================================

@bot.message_handler(func=lambda msg: True)
def handle_messages(message):
    user_id = message.from_user.id
    text    = message.text.strip()

    # ── Block unapproved users ──
    if not is_approved(user_id):
        bot.send_message(
            user_id,
            "⏳ <b>Your access is still pending admin approval.</b>\n"
            "Please wait or contact @Sefuax."
        )
        return

    state = get_state(user_id)

    # ─────────────────────────────────
    # MULTI-STEP FORM: Submit Account
    # ─────────────────────────────────

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
                f"Error: <code>{e}</code>\n"
                "Please try again or contact the admin.",
                reply_markup=main_keyboard()
            )

        clear_temp(user_id)
        return

    # ─────────────────────────────────
    # KEYBOARD BUTTON HANDLERS
    # ─────────────────────────────────

    # ── 1️⃣ Submit Account ──
    if "Submit Account" in text:
        set_state(user_id, "awaiting_username")
        bot.send_message(
            user_id,
            "📋 <b>Submit Account — Step 1 of 3</b>\n\n"
            "Please enter your <b>Instagram username</b>:\n"
            "<i>(without the @ symbol)</i>"
        )
        return

    # ── 2️⃣ Fake Info ──
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

    # ── 3️⃣ Admin ──
    if "Admin" in text:
        bot.send_message(
            user_id,
            f"👤 <b>Admin Contact</b>\n\n"
            f"📩 Reach the admin at: {ADMIN_USERNAME}\n\n"
            f"<i>Click the username above to open a chat.</i>"
        )
        return

    # ── Unknown input ──
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

    # Verify Google Sheets connection on startup
    try:
        sheet = get_sheet()
        logger.info(f"📊 Google Sheet connected: {sheet.title}")
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets not connected on startup: {e}")

    logger.info("✅ Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
