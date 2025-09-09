from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from ui import delete_all_bot_messages
from sheets_async import get_sheet_names, get_dishes_by_sheet

async def show_categories(update, context):
    chat_id = update.effective_chat.id
    await delete_all_bot_messages(context, chat_id)

    cats = await get_sheet_names()
    rows = [cats[i:i+2] for i in range(0, len(cats), 2)]
    rows.append(["⬅️ Назад"])
    sent = await update.message.reply_text(
        "Выберите категорию:",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )
    context.user_data["message_ids"].append(sent.message_id)
    context.user_data['in_categories'] = True
    context.user_data['in_dishes'] = False

async def show_dishes_for_text(update, context, text):
    """
    Реакция на выбор категории (текстом) — ищем лист, показываем блюда.
    """
    chat_id = update.effective_chat.id
    sheet_names = await get_sheet_names()

    if text in sheet_names:
        sheet_name = text
    else:
        matches = [name for name in sheet_names if name.endswith(text)]
        sheet_name = matches[0] if matches else None

    if not sheet_name:
        return  # игнорируем незнакомый текст

    await delete_all_bot_messages(context, chat_id)
    context.user_data['in_categories'] = False
    context.user_data['in_dishes'] = True

    dishes = await get_dishes_by_sheet(sheet_name)
    for d in dishes:
        dish_id = d.get("ID")
        name = d.get("Название блюда", "Без названия")
        price = d.get("Цена", "0")
        grams = d.get("Граммы", "")
        desc = d.get("Описание", "")
        photo = d.get("Ссылка на изображение", "")
        caption = f"<b>{name}</b> — {price} ₽\n{grams}\n{desc}"
        cb_data = f"add:{sheet_name}:{dish_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Добавить в корзину", callback_data=cb_data)]])
        if str(photo).startswith("http"):
            sent = await context.bot.send_photo(chat_id, photo=photo, caption=caption, parse_mode="HTML", reply_markup=kb)
        else:
            sent = await context.bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=kb)
        context.user_data["message_ids"].append(sent.message_id)

    # Показать Reply-клавиатуру «Назад/Корзина» в конце
    back_markup = ReplyKeyboardMarkup([["⬅️ Назад", "🛒 Корзина"]], resize_keyboard=True)
    tail = await context.bot.send_message(chat_id, "⬇️", reply_markup=back_markup)
    context.user_data["message_ids"].append(tail.message_id)
