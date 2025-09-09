from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from cart_manager import get_cart, remove_from_cart, clear_cart
from ui import base_reply_markup, delete_all_bot_messages

def build_cart_view(user_id: int):
    """
    Возвращает (text, InlineKeyboardMarkup) для текущей корзины пользователя.
    """
    cart = get_cart(user_id)
    if not cart:
        return "🛒 Ваша корзина пуста.", None

    # Группируем по листу и ID блюда
    grouped = {}
    for item in cart:
        sheet = item.get("sheet_name")
        d_id = str(item.get("dish_id"))
        name = item.get("Название блюда", "Без названия")
        price = int(item.get("Цена", 0))
        key = (sheet, d_id, name, price)
        grouped.setdefault(key, 0)
        grouped[key] += 1

    lines = []
    buttons = []
    for (sheet, d_id, name, price), count in grouped.items():
        total = count * price
        lines.append(f"{count} X {name} — {price}₽ = {total}₽")
        buttons.append([
            InlineKeyboardButton(f"❌ Удалить {name}", callback_data=f"del:{sheet}:{d_id}")
        ])

    # Очистка/Оформление/Назад
    buttons.append([
        InlineKeyboardButton("🧹 Очистить корзину", callback_data="clear"),
        InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="back")
    ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)

async def show_cart_message(update, context):
    """
    Удобный помощник — очищает чат и показывает корзину.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await delete_all_bot_messages(context, chat_id)

    text, markup = build_cart_view(user_id)
    sent = await update.message.reply_text(text, reply_markup=markup or base_reply_markup(), parse_mode="HTML")
    context.user_data.setdefault("message_ids", []).append(sent.message_id)

async def inline_cart_handler(update, context):
    """
    Обрабатывает inline-кнопки корзины: del:/clear/back.
    """
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    # Подкорректировать состав
    if data.startswith("del:"):
        _, sheet_name, dish_id = data.split(":", 2)
        cart = get_cart(user_id)
        for idx, item in enumerate(cart):
            if item.get("sheet_name") == sheet_name and str(item.get("dish_id")) == dish_id:
                remove_from_cart(user_id, idx)
                break

    elif data == "clear":
        clear_cart(user_id)

    elif data == "back":
        await delete_all_bot_messages(context, chat_id)
        sent = await context.bot.send_message(chat_id, "Выберите действие:", reply_markup=base_reply_markup())
        context.user_data.setdefault("message_ids", []).append(sent.message_id)
        return

    # Показать актуальную корзину
    await delete_all_bot_messages(context, chat_id)
    text, markup = build_cart_view(user_id)
    sent = await context.bot.send_message(chat_id, text, reply_markup=markup or base_reply_markup(), parse_mode="HTML")
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
