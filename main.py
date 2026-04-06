import logging
import os
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes, CallbackQueryHandler

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()


def save_message_id(message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO messages (id) VALUES (%s) ON CONFLICT DO NOTHING", (message_id,))
    conn.commit()
    conn.close()


def get_random_message_id() -> int | None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM messages ORDER BY RANDOM() LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def delete_message_id(message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE id = %s", (message_id,))
    conn.commit()
    conn.close()


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if message and str(message.chat.id) == CHANNEL_ID:
        save_message_id(message.message_id)
        logger.info(f"Saved message_id: {message.message_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("⚡️Random Motivation⚡️", callback_data="get_random")]]
    await update.message.reply_text(
        "Добро пожаловать! Нажми кнопку ниже, чтобы получить мотивацию:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Начинаю синхронизацию постов из канала...")
    count = 0
    try:
        async for message in context.bot.get_chat_history(chat_id=CHANNEL_ID):
            save_message_id(message.message_id)
            count += 1
    except Exception as e:
        # get_chat_history недоступен, используем forward перебором
        pass

    if count == 0:
        # Альтернатива: перебираем ID вручную
        await update.message.reply_text(
            "⚠️ Автосинхронизация недоступна через Telegram Bot API.\n\n"
            "Просто опубликуй любой новый пост в канале — бот его подхватит автоматически.\n"
            "Или перешли (forward) посты из канала боту вручную командой /addpost."
        )
        return

    await update.message.reply_text(f"✅ Синхронизировано {count} постов!")


async def addpost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить пост вручную: переслать сообщение из канала боту и написать /addpost"""
    if update.message.forward_from_chat and str(update.message.forward_from_chat.id) == CHANNEL_ID:
        save_message_id(update.message.forward_from_message_id)
        await update.message.reply_text(f"✅ Пост #{update.message.forward_from_message_id} добавлен!")
    else:
        await update.message.reply_text(
            "Перешли сюда пост из своего канала, затем напиши /addpost.\n"
            "Или просто публикуй новые посты — бот будет сохранять их автоматически."
        )


async def _forward_random(chat_id, bot):
    for _ in range(5):
        message_id = get_random_message_id()
        if not message_id:
            return None
        try:
            await bot.forward_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=message_id)
            return message_id
        except Exception as e:
            logger.warning(f"Message {message_id} not found, removing. Error: {e}")
            delete_message_id(message_id)
    return None


async def send_random_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = await _forward_random(update.effective_chat.id, context.bot)
    if result is None:
        await update.message.reply_text("Нет сохранённых постов.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "get_random":
        result = await _forward_random(query.message.chat.id, context.bot)
        if result is None:
            await query.edit_message_text("Нет сохранённых постов.")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("random", send_random_post))
    app.add_handler(CommandHandler("addpost", addpost))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
