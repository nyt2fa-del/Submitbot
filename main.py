# main.py
import json
import os
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openpyxl import Workbook

# ========== কনফিগারেশন ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Railway এ Environment variable সেট করুন
ADMIN_CHAT_ID = 8770558084          # আপনার দেওয়া অ্যাডমিন আইডি
ADMIN_PROFILE_URL = "https://t.me/Sefuax"

DATA_FILE = "user_data.json"

# লগিং সেটআপ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ডাটা ম্যানেজমেন্ট ==========
def load_user_data():
    """user_data.json ফাইল থেকে ডাটা লোড করে"""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("user_data", {})

def save_user_data(user_data):
    """ডাটা JSON ফাইলে সেভ করে"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"user_data": user_data}, f, ensure_ascii=False, indent=2)

# গ্লোবাল ডাটা (RAM + ফাইল সাপোর্ট)
user_storage = load_user_data()

def get_usernames(user_id: int):
    """ইউজারের সেভ করা ইউজারনেম লিস্ট রিটার্ন করে"""
    return user_storage.get(str(user_id), [])

def add_username(user_id: int, username_text: str):
    """নতুন ইউজারনেম যোগ করে"""
    user_id_str = str(user_id)
    if user_id_str not in user_storage:
        user_storage[user_id_str] = []
    user_storage[user_id_str].append(username_text.strip())
    save_user_data(user_storage)

def delete_all_usernames(user_id: int):
    """ইউজারের সব ইউজারনেম ডিলিট করে"""
    user_id_str = str(user_id)
    if user_id_str in user_storage:
        user_storage[user_id_str] = []
        save_user_data(user_storage)
        return True
    return False

# ========== ইউটিলিটি ফাংশন ==========
def create_excel_file(user_id: int, usernames: list) -> str:
    """ইউজারনেম লিস্ট থেকে Excel ফাইল তৈরি করে, ফাইলের পাথ রিটার্ন করে"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Usernames"
    ws.append(["Saved Usernames"])  # হেডার
    for uname in usernames:
        ws.append([uname])
    filename = f"usernames_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(filename)
    return filename

async def notify_admin(application: Application, text: str):
    """অ্যাডমিনকে মেসেজ পাঠায় (নীরব মোডে)"""
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, disable_notification=True)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")

# ========== হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড - স্বাগতম + বাটন + নতুন ইউজার নোটিফিকেশন"""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name
    username = user.username if user.username else "No username"

    # স্বাগতম মেসেজ
    welcome_text = (
        f"🎉 স্বাগতম {first_name}!\n\n"
        f"🤖 আমি আপনার ইউজারনেম সংরক্ষণকারী বট।\n"
        f"📝 আপনি যা কিছু লিখবেন, তা এখানে সেভ হয়ে যাবে।\n\n"
        f"🔽 নিচের বাটনগুলো ব্যবহার করে ডাউনলোড বা রিসেট করতে পারেন।"
    )

    # Inline Keyboard তৈরি
    keyboard = [
        [InlineKeyboardButton("📥 Download", callback_data="download")],
        [InlineKeyboardButton("🔴 Reset", callback_data="reset")],
        [InlineKeyboardButton("👤 Admin", url=ADMIN_PROFILE_URL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    # নতুন ইউজার চিহ্নিত করলে অ্যাডমিনকে জানান
    if str(user_id) not in user_storage:
        admin_msg = (
            f"🆕 **নতুন ইউজার জয়েন করেছে**\n"
            f"👤 নাম: {first_name}\n"
            f"🆔 আইডি: `{user_id}`\n"
            f"📛 ইউজারনেম: @{username}\n"
            f"🔗 লিংক: [লিংক](tg://user?id={user_id})"
        )
        await notify_admin(context.application, admin_msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সাধারণ টেক্সট মেসেজ - ইউজারনেম হিসেবে সেভ করে"""
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    if not text:
        return

    # ইউজারনেম সেভ
    add_username(user_id, text)
    await update.message.reply_text(f"✅ সেভ হয়েছে: `{text}`", parse_mode="Markdown")

    # অ্যাডমিনকে নোটিফাই
    admin_msg = (
        f"💾 **নতুন সেভ**\n"
        f"👤 {user.first_name} (@{user.username or 'no_username'})\n"
        f"🆔 `{user_id}`\n"
        f"📝 সেভ করা টেক্সট:\n`{text}`"
    )
    await notify_admin(context.application, admin_msg)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটনের কলব্যাক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()  # লোডিং ইফেক্ট দূর করতে

    user_id = query.from_user.id
    data = query.data

    if data == "download":
        usernames = get_usernames(user_id)
        if not usernames:
            await query.edit_message_text("⚠️ আপনার কোনো সংরক্ষিত ইউজারনেম নেই। প্রথমে কিছু লিখুন।")
            return

        # Excel তৈরি করুন
        excel_file = create_excel_file(user_id, usernames)
        with open(excel_file, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=Path(excel_file).name,
                caption="📎 আপনার সংরক্ষিত ইউজারনেমের তালিকা সংযুক্ত করা হলো।"
            )
        os.remove(excel_file)  # ফাইল ডিলিট করে দিন
        await query.edit_message_text("✅ ফাইল প্রস্তুত! উপরের মেসেজে ডাউনলোড লিংক পাবেন।")

    elif data == "reset":
        # নিশ্চিতকরণ জিজ্ঞেস করুন
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ হ্যাঁ, ডিলিট করুন", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_reset")]
        ])
        await query.edit_message_text(
            "⚠️ **সতর্কতা:** আপনার সব সংরক্ষিত ইউজারনেম স্থায়ীভাবে মুছে ফেলা হবে।\n\nআপনি কি নিশ্চিত?",
            reply_markup=confirm_keyboard,
            parse_mode="Markdown"
        )

    elif data == "confirm_reset":
        if delete_all_usernames(user_id):
            await query.edit_message_text("🗑️ সব ইউজারনেম সফলভাবে ডিলিট করা হয়েছে।")
        else:
            await query.edit_message_text("❌ আপনার কোনো ইউজারনেম নেই।")

    elif data == "cancel_reset":
        await query.edit_message_text("🔁 রিসেট বাতিল করা হয়েছে। আপনার ডাটা নিরাপদ আছে।")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """গ্লোবাল এরর হ্যান্ডলার"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ কিছু একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।")
    except:
        pass

# ========== মেইন ফাংশন ==========
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলার যোগ করুন
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))

    # এরর হ্যান্ডলার
    app.add_error_handler(error_handler)

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
