# -*- coding: utf-8 -*-
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

from config import BOT_TOKEN
from ui import base_reply_markup, delete_all_bot_messages
from cart_manager import add_to_cart, get_cart, replace_cart
from handlers import cart as cart_h
from handlers import menu as menu_h
from handlers import order as order_h
from sheets_async import get_sheet_names

logging.basicConfig(level=logging.INFO)

ASK_NAME, ASK_PHONE, ASK_ADDRESS, ASK_COMMENT, ASK_PAYMENT = (
    order_h.ASK_NAME,
    order_h.ASK_PHONE,
    order_h.ASK_ADDRESS,
    order_h.ASK_COMMENT,
    order_h.ASK_PAYMENT,
)

# -------------------- /start --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.user_data["message_ids"] = []
    context.user_data['in_categories'] = False
    context.user_data['in_dishes'] = False
    context.user_data['in_checkout'] = False

    await delete_all_bot_messages(context, chat_id)
    sent = await update.message.reply_text(
        "Добро пожаловать в доставку еды!\n\nВыберите действие:",
        reply_markup=base_reply_markup()
    )
    context.user_data["message_ids"].append(sent.message_id)

# -------------------- TEXT HANDLER --------------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    # Отмена оформления заказа
    if text == "❌ Отмена" and context.user_data.get('in_checkout'):
        return await order_h.cancel_checkout_msg(update, context)

    # Назад
    if text == "⬅️ Назад":
        if context.user_data.get('in_dishes'):
            # Назад к категориям
            context.user_data['in_dishes'] = False
            context.user_data['in_categories'] = True
            await delete_all_bot_messages(context, chat_id)
            cats = await get_sheet_names()
            rows = [cats[i:i+2] for i in range(0, len(cats), 2)]
            rows.append(["⬅️ Назад"])
            sent = await update.message.reply_text(
                "Выберите категорию:",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            context.user_data["message_ids"].append(sent.message_id)
            return
        # Иначе — в главное
        context.user_data['in_categories'] = False
        await delete_all_bot_messages(context, chat_id)
        sent = await update.message.reply_text("Выберите действие:", reply_markup=base_reply_markup())
        context.user_data["message_ids"].append(sent.message_id)
        return

    # Меню
    if text == "📋 Меню":
        return await menu_h.show_categories(update, context)

    # Корзина
    if text == "🛒 Корзина":
        return await cart_h.show_cart_message(update, context)

    # Повторить заказ
    if text == "🔁 Повторить заказ":
        from cart_manager import get_last_order
        items = get_last_order(update.effective_user.id)
        await delete_all_bot_messages(context, chat_id)
        if not items:
            sent = await update.message.reply_text(
                "Пока нечего повторять — оформите первый заказ 😊",
                reply_markup=base_reply_markup()
            )
            context.user_data.setdefault("message_ids", []).append(sent.message_id)
            return
        replace_cart(update.effective_user.id, items)
        # сразу показываем корзину
        return await cart_h.show_cart_message(update, context)

    # Контакты
    if text == "📞 Контакты":
        await delete_all_bot_messages(context, chat_id)
        sent = await update.message.reply_text(
            "📞 Телефон для связи: +7 900 000-00-00",
            reply_markup=base_reply_markup()
        )
        context.user_data["message_ids"].append(sent.message_id)
        return

    # Если мы в меню категорий — трактуем текст как выбор категории
    if context.user_data.get('in_categories'):
        return await menu_h.show_dishes_for_text(update, context, text)

# -------------------- INLINE HANDLERS --------------------

async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # Кнопки QR (подтверждение/повтор/отмена)
    if data in ("qr_confirm", "qr_repeat", "qr_cancel"):
        from handlers import order as order_h  # локальный импорт чтобы избежать циклов
        return await order_h.qr_inline_callbacks(update, context)

    # Добавление позиции в корзину
    if data.startswith("add:"):
        await query.answer()
        _, sheet_name, dish_id = data.split(":", 2)

        # Найдём блюдо
        from sheets_async import get_dishes_by_sheet
        dishes = await get_dishes_by_sheet(sheet_name)
        dish = next((item for item in dishes if str(item.get("ID")) == dish_id), None)
        if dish:
            name = dish.get("Название блюда", "Без названия")
            price = dish.get("Цена", "0")
            add_to_cart(query.from_user.id, {
                "Название блюда": name,
                "Цена": price,
                "sheet_name": sheet_name,
                "dish_id": dish_id
            })
        sent = await query.message.reply_text("✅ Добавлено в корзину.", reply_markup=base_reply_markup())
        context.user_data.setdefault("message_ids", []).append(sent.message_id)
        return

    # Остальное (del/clear/back) — корзина
    if data in ("clear", "back") or data.startswith("del:"):
        return await cart_h.inline_cart_handler(update, context)

    # data == "checkout" сюда НЕ попадёт — ConversationHandler перехватит

# -------------------- main --------------------

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(10)
        .connection_pool_size(20)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_h.start_checkout, pattern="^checkout$")],
        states={
            ASK_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, order_h.ask_name)],
            ASK_PHONE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, order_h.ask_phone)],
            ASK_ADDRESS:[MessageHandler(filters.TEXT & ~filters.COMMAND, order_h.ask_address)],
            ASK_COMMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND, order_h.ask_comment)],
            ASK_PAYMENT:[CallbackQueryHandler(order_h.ask_payment, pattern="^pay:(cash|qr|online)$")],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), order_h.cancel_checkout_msg)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(inline_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
