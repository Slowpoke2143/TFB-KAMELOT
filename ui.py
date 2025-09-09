from telegram import ReplyKeyboardMarkup, KeyboardButton

# Базовая клавиатура в одном месте
BASE_KEYBOARD = [
    [KeyboardButton("📋 Меню"), KeyboardButton("🛒 Корзина")],
    [KeyboardButton("📞 Контакты")],
    [KeyboardButton("🔁 Повторить заказ")]
]

def base_reply_markup():
    return ReplyKeyboardMarkup(BASE_KEYBOARD, resize_keyboard=True)

async def delete_all_bot_messages(context, chat_id: int):
    """Удаляем все сохранённые ботом сообщения для чистоты чата."""
    for msg_id in context.user_data.get("message_ids", []):
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    context.user_data["message_ids"] = []
