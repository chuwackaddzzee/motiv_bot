import logging
import os
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes, CallbackQueryHandler

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_pool = None


async def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
    return db_pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY)")


async def save_message_id(message_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO messages (id) VALUES ($1) ON CONFLICT DO NOTHING", message_id)


async def get_random_message_id():
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM messages ORDER BY RANDOM() LIMIT 1")
        return row["id"] if row else None


async def delete_message_id(message_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM messages WHERE id = $1", message_id)


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if message and str(message.chat.id) == CHANNEL_ID:
        await save_message_id(message.message_id)
        logger.info(f"Saved message_id: {message.message_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("⚡️Random Motivation⚡️", callback_data="get_random")]]
    await update.message.reply_text(
        "Добро пожаловать! Нажми кнопку ниже, чтобы получить мотивацию:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _forward_random(chat_id, bot):
    for _ in range(5):
        message_id = await get_random_message_id()
        if not message_id:
            return None
        try:
            await bot.forward_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=message_id)
            return message_id
        except Exception as e:
            logger.warning(f"Message {message_id} not found, removing. Error: {e}")
            await delete_message_id(message_id)
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


async def post_init(application):
    await init_db()


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("random", send_random_post))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
