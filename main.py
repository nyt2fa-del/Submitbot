# main.py (পুরোপুরি ঠিক করা সংস্করণ)
import json
import os
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openpyxl import Workbook

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = 8770558084
ADMIN_PROFILE_URL = "https://t.me/Sefuax"

DATA_FILE = "user_data.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def load_user_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("user_data", {})

def save_user_data(user_data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"user_data": user_data}, f, ensure_ascii=False, indent=2)

user_storage = load_user_data()

def get_usernames(user_id: int):
    return user_storage.get(str(user_id), [])

def add_username(user_id: int, text: str):
    uid = str(user_id)
    if uid not in user_storage:
        user_storage[uid] = []
    user_storage[uid].append(text.strip())
    save_user_data(user_storage)

def delete_all_usernames(user_id: int) -> bool:
    uid = str(user_id)
    if uid in user_storage and user_storage[uid]:
        user_storage[uid] = []
        save_user_data(user_storage)
        return True
    return False

def create_excel_file(user_id: int, usernames: list) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "Usernames"
    ws.append(["𝙔𝙤𝙪𝙧 𝙎𝙖𝙫𝙚𝙙 𝙐𝙎𝙀𝙍𝙉𝘼𝙈𝙀'𝙨"])
    for uname in usernames:
        ws.append([uname])
    filename = f"usernames_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(filename)
    return filename

async def notify_admin(application, text: str):
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, disable_notification=True)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name
    username = user.username or "no_username"

    keyboard = [
        [KeyboardButton("📥 Download"), KeyboardButton("🔴 Reset")],
        [KeyboardButton("👤 Admin")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome_text = (
        f"🎉 স্বাগতম {first_name}!\n\n"
        f"🤖 আমি আপনার ইউজারনেম সংরক্ষণকারী বট।\n"
        f"📝 আপনি যা কিছু লিখবেন, তা এখানে সেভ হয়ে যাবে।\n\n"
        f"🔽 নিচের কীবোর্ড বাটন ব্যবহার করুন।"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    if str(user_id) not in user_storage:
        admin_msg = (
            f"🆕 **নতুন ইউজার জয়েন করেছে**\n"
            f"👤 নাম: {first_name}\n"
            f"🆔 আইডি: `{user_id}`\n"
            f"📛 ইউজারনাম: @{username}\n"
            f"🔗 লিংক: [লিংক](tg://user?id={user_id})"
        )
        await notify_admin(context.application, admin_msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাটন ছাড়া অন্য সব টেক্সট সেভ করবে"""
    user = update.effective_user
    text = update.message.text.strip()
    if not text:
        return
    add_username(user.id, text)
    await update.message.reply_text(f"✅ সেভ হয়েছে: `{text}`", parse_mode="Markdown")

    admin_msg = (
        f"💾 **নতুন সেভ**\n"
        f"👤 {user.first_name} (@{user.username or 'no_username'})\n"
        f"🆔 `{user.id}`\n"
        f"📝 টেক্সট:\n`{text}`"
    )
    await notify_admin(context.application, admin_msg)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply Keyboard বাটন গুলো হ্যান্ডেল করে"""
    user = update.effective_user
    text = update.message.text

    if text == "📥 Download":
        usernames = get_usernames(user.id)
        if not usernames:
            await update.message.reply_text("⚠️ আপনার কোনো সংরক্ষিত ইউজারনেম নেই। প্রথমে কিছু লিখুন।")
            return
        excel_file = create_excel_file(user.id, usernames)
        with open(excel_file, "rb") as f:
            await update.message.reply_document(document=f, filename=Path(excel_file).name, caption="📎 আপনার সংরক্ষিত ইউজারনেমের তালিকা।")
        os.remove(excel_file)

    elif text == "🔴 Reset":
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ হ্যাঁ, ডিলিট করুন", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_reset")]
        ])
        await update.message.reply_text(
            "⚠️ **সতর্কতা:** আপনার সব সংরক্ষিত ইউজারনেম স্থায়ীভাবে মুছে ফেলা হবে।\n\nআপনি কি নিশ্চিত?",
            reply_markup=confirm_keyboard,
            parse_mode="Markdown"
        )

    elif text == "👤 Admin":
        await update.message.reply_text(f"👤 অ্যাডমিন প্রোফাইল: [লিংকে ক্লিক করুন]({ADMIN_PROFILE_URL})", parse_mode="Markdown")

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "confirm_reset":
        if delete_all_usernames(user_id):
            await query.edit_message_text("🗑️ সব ইউজারনেম সফলভাবে ডিলিট করা হয়েছে।")
        else:
            await query.edit_message_text("❌ আপনার কোনো ইউজারনেম নেই।")
    elif query.data == "cancel_reset":
        await query.edit_message_text("🔁 রিসেট বাতিল করা হয়েছে। আপনার ডাটা নিরাপদ আছে।")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception:", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ কিছু সমস্যা হয়েছে, আবার চেষ্টা করুন।")
    except:
        pass

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set!")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(📥 Download|🔴 Reset|👤 Admin)$"), handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(reset_callback))
    app.add_error_handler(error_handler)

    logger.info("Bot started with Reply Keyboard...")
    app.run_polling()

if __name__ == "__main__":
    main()
