# -*- coding: utf-8 -*-
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import ConversationHandler
from config import (
    OPERATOR_CHAT_ID, QR_IMAGE_URL, QR_REMINDER_MINUTES, QR_CANCEL_MINUTES,
    MSK_TZ, EARLY_PAYMENT_HOUR, LATE_PAYMENT_HOUR
)
from ui import base_reply_markup, delete_all_bot_messages
from cart_manager import get_cart, clear_cart, set_last_order
from payment import create_payment

ASK_NAME, ASK_PHONE, ASK_ADDRESS, ASK_COMMENT, ASK_PAYMENT = range(5)

def _cancel_only_kb() -> ReplyKeyboardMarkup:
    """Reply-клавиатура только с кнопкой Отмена."""
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)

# ---------- Moscow time helpers ----------

def _msk_now() -> datetime:
    """
    Возвращает текущее время в Москве.
    Пытаемся через ZoneInfo(MSK_TZ), если БД tzdata недоступна — фолбэк UTC+3.
    """
    try:
        return datetime.now(ZoneInfo(MSK_TZ))
    except Exception:
        # В Москве нет сезонных переводов (UTC+3 круглый год) — фолбэк безопасен
        return datetime.now(timezone.utc) + timedelta(hours=3)

def _is_qr_only_now() -> bool:
    """
    True, если сейчас действует окно 'только QR':
    с LATE_PAYMENT_HOUR до EARLY_PAYMENT_HOUR следующего дня (22:00–10:00 по умолчанию).
    """
    now = _msk_now()
    return (now.hour >= LATE_PAYMENT_HOUR) or (now.hour < EARLY_PAYMENT_HOUR)

# ---------- QR reminder/timeout jobs ----------

async def _qr_reminder_job(context):
    data = context.job.data or {}
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    if chat_id is None or user_id is None:
        return
    ud = context.application.user_data.get(user_id, {})
    if not ud or not ud.get("awaiting_qr_confirm"):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Я отправил подтверждение оплаты!", callback_data="qr_confirm")],
        [InlineKeyboardButton("🔁 Показать QR ещё раз", callback_data="qr_repeat"),
         InlineKeyboardButton("❌ Отменить оплату", callback_data="qr_cancel")]
    ])
    sent = await context.bot.send_message(
        chat_id,
        "⏰ Напоминание: после оплаты нажмите кнопку ниже, чтобы отправить заказ оператору.",
        reply_markup=kb
    )
    ud.setdefault("message_ids", []).append(sent.message_id)

async def _qr_timeout_job(context):
    data = context.job.data or {}
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    if chat_id is None or user_id is None:
        return
    ud = context.application.user_data.get(user_id, {})
    if not ud or not ud.get("awaiting_qr_confirm"):
        return
    qr_msg_id = ud.get("qr_message_id")
    if qr_msg_id:
        try:
            await context.bot.delete_message(chat_id, qr_msg_id)
        except Exception:
            pass
    ud["awaiting_qr_confirm"] = False
    ud.pop("pending_order_text", None)
    ud.pop("qr_message_id", None)
    for j in ud.get("qr_jobs", []):
        try:
            j.schedule_removal()
        except Exception:
            pass
    ud["qr_jobs"] = []
    sent = await context.bot.send_message(
        chat_id,
        "⏳ Время на подтверждение оплаты истекло. Сессия оплаты отменена. "
        "Вы можете оформить заказ заново из меню.",
        reply_markup=base_reply_markup()
    )
    ud.setdefault("message_ids", []).append(sent.message_id)

def _schedule_qr_jobs(context, chat_id: int, user_id: int):
    reminder = context.job_queue.run_once(_qr_reminder_job, when=QR_REMINDER_MINUTES * 60,
                                          data={"chat_id": chat_id, "user_id": user_id})
    cancel = context.job_queue.run_once(_qr_timeout_job, when=QR_CANCEL_MINUTES * 60,
                                        data={"chat_id": chat_id, "user_id": user_id})
    ud = context.user_data
    ud["qr_jobs"] = [reminder, cancel]

def _cancel_qr_jobs(ud: dict):
    for j in ud.get("qr_jobs", []):
        try:
            j.schedule_removal()
        except Exception:
            pass
    ud["qr_jobs"] = []

# ---------- Conversation entry ----------

async def start_checkout(update, context):
    """Старт оформления: вызывается при нажатии inline-кнопки '✅ Оформить заказ'."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    context.user_data['in_checkout'] = True
    sent = await context.bot.send_message(
        chat_id, "👤 Введите ваше имя:", reply_markup=_cancel_only_kb()
    )
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ASK_NAME

# ---------- Conversation: ask_* ----------

async def ask_name(update, context):
    text = update.message.text
    if text == "❌ Отмена":
        return await cancel_checkout_msg(update, context)
    if "order_id" not in context.user_data:
        context.user_data["order_id"] = datetime.now().strftime("%y%m%d-%H%M%S")
    context.user_data["name"] = text
    sent = await update.message.reply_text(
        "📞 Введите номер телефона в формате +7XXXXXXXXXX:", reply_markup=_cancel_only_kb()
    )
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ASK_PHONE

async def ask_phone(update, context):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel_checkout_msg(update, context)
    if not re.fullmatch(r"\+7\d{10}", text):
        sent = await update.message.reply_text(
            "❗ Неверный формат. Введите телефон вида +7XXXXXXXXXX:",
            reply_markup=_cancel_only_kb()
        )
        context.user_data.setdefault("message_ids", []).append(sent.message_id)
        return ASK_PHONE
    context.user_data["phone"] = text
    sent = await update.message.reply_text(
        "📍 Введите адрес доставки (доставка осуществляется только в пределах г.Керчь):", reply_markup=_cancel_only_kb()
    )
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ASK_ADDRESS

async def ask_address(update, context):
    text = update.message.text
    if text == "❌ Отмена":
        return await cancel_checkout_msg(update, context)
    context.user_data["address"] = text
    # На шаге комментария — «Пропустить» и «Отменить»
    skip_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("⏭️ Пропустить")], [KeyboardButton("❌ Отмена")]],
        resize_keyboard=True
    )
    sent = await update.message.reply_text(
        "💬 Комментарий к заказу (опционально):", reply_markup=skip_kb
    )
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ASK_COMMENT

async def ask_comment(update, context):
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel_checkout_msg(update, context)
    context.user_data["comment"] = "" if text == "⏭️ Пропустить" else text

    # Проверяем окно оплаты по МСК: с 22:00 до 10:00 — только QR
    qr_only = _is_qr_only_now()
    now_msk = _msk_now().strftime("%H:%M")
    note = f"ℹ️ С {LATE_PAYMENT_HOUR:02d}:00 до {EARLY_PAYMENT_HOUR:02d}:00 по МСК доступна только оплата по QR."

    if qr_only:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 Оплата по QR", callback_data="pay:qr")]
        ])
        text_msg = f"💳 Выберите способ оплаты:\n{note}\nСейчас (МСК {now_msk}) доступна только оплата по QR."
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💵 Наличные", callback_data="pay:cash")],
            [InlineKeyboardButton("📷 Оплата по QR", callback_data="pay:qr")],
            [InlineKeyboardButton("🌐 Онлайн (В РАЗРАБОТКЕ! ^_^)", callback_data="pay:online")],
        ])
        text_msg = f"💳 Выберите способ оплаты:\n{note}"

    sent = await update.message.reply_text(text_msg, reply_markup=kb)
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ASK_PAYMENT

async def ask_payment(update, context):
    query = update.callback_query
    await query.answer()
    method = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # Повторная защита на случай «перескока» времени между шагами
    if _is_qr_only_now() and method != "qr":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 Оплата по QR", callback_data="pay:qr")]
        ])
        sent = await query.message.reply_text(
            f"⏰ С {LATE_PAYMENT_HOUR:02d}:00 до {EARLY_PAYMENT_HOUR:02d}:00 по МСК доступна только оплата по QR. "
            "Пожалуйста, выберите QR-оплату.",
            reply_markup=kb
        )
        context.user_data.setdefault("message_ids", []).append(sent.message_id)
        return ASK_PAYMENT

    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    address = context.user_data.get("address", "")
    comment = context.user_data.get("comment", "")
    order_id = context.user_data.get("order_id", datetime.now().strftime("%y%m%d-%H%M%S"))

    cart = get_cart(user_id)
    total = sum(int(i.get("Цена", 0)) for i in cart)

    # группируем позиции
    grouped = {}
    for item in cart:
        dish = item["Название блюда"]
        price = int(item.get("Цена", 0))
        grouped.setdefault((dish, price), 0)
        grouped[(dish, price)] += 1

    order_items = []
    for (dish, price), cnt in grouped.items():
        sum_price = cnt * price
        order_items.append(f"- {cnt} X {dish} — {price}₽ = {sum_price}₽")

    base_order_text = (
        f"🧾 Заказ #{order_id}\n"
        f"👤 {name}\n"
        f"📞 {phone}\n"
        f"📍 {address}\n"
        + (f"💬 {comment}\n" if comment else "")
        + "🛒 Позиции:\n"
        + "\n".join(order_items)
        + f"\n💰 Итого: {total}₽"
    )

    now_str = _msk_now().strftime("%d.%m %H:%M МСК")

    if method == "cash":
        await query.message.reply_text("✅ Ваш заказ принят!", reply_markup=base_reply_markup())
        await context.bot.send_message(
            OPERATOR_CHAT_ID, f"📦 Новый заказ (Наличные)\n{base_order_text}\n⏱ {now_str}"
        )
        set_last_order(user_id, cart)
        clear_cart(user_id)
        context.user_data['in_checkout'] = False
        return ConversationHandler.END

    if method == "qr":
        context.user_data["pending_order_text"] = base_order_text
        context.user_data["awaiting_qr_confirm"] = True

        caption = (
            f"Отсканируйте QR-код для оплаты на сумму {total}₽.\n"
            f"После оплаты нажмите кнопку ниже, чтобы отправить заказ оператору."
        )
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я отправил подтверждение оплаты!", callback_data="qr_confirm")],
            [InlineKeyboardButton("❌ Отменить оплату", callback_data="qr_cancel")]
        ])
        if QR_IMAGE_URL:
            sent = await query.message.reply_photo(photo=QR_IMAGE_URL, caption=caption, reply_markup=confirm_kb)
        else:
            sent = await query.message.reply_text(
                "QR_IMAGE_URL не задан. Укажите ссылку в config.py\n\n" + caption, reply_markup=confirm_kb
            )

        context.user_data["qr_message_id"] = sent.message_id
        context.user_data.setdefault("message_ids", []).append(sent.message_id)
        _schedule_qr_jobs(context, chat_id, user_id)
        return ConversationHandler.END

    # Онлайн-оплата
    url, _ = create_payment(total, user_id)
    await query.message.reply_text(f"✅ Перейдите для оплаты:\n{url}", reply_markup=base_reply_markup())
    await context.bot.send_message(
        OPERATOR_CHAT_ID, f"📦 Новый заказ (Онлайн)\n{base_order_text}\n🔗 {url}\n⏱ {now_str}"
    )
    set_last_order(user_id, cart)
    clear_cart(user_id)
    context.user_data['in_checkout'] = False
    return ConversationHandler.END

# ---------- inline: qr_confirm / qr_repeat / qr_cancel ----------

async def qr_inline_callbacks(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data
    ud = context.user_data

    if data == "qr_confirm":
        pending = ud.get("pending_order_text")
        qr_msg_id = ud.get("qr_message_id")
        if not pending:
            sent = await query.message.reply_text(
                "Кажется, активного заказа для подтверждения нет.", reply_markup=base_reply_markup()
            )
            ud.setdefault("message_ids", []).append(sent.message_id)
            return

        username = ("@" + query.from_user.username) if query.from_user.username else "—"
        # ИСПРАВЛЕНО: латинская 'm' в формате даты
        now_str = _msk_now().strftime("%d.%m %H:%M МСК")
        operator_text = (
            "📦 Новый заказ (QR-код)\n"
            + pending
            + f"\n💳 Оплата: QR — клиент подтвердил оплату"
            + f"\n⏱ {now_str}"
            + f"\n👤 Telegram: {username} (id {user_id})"
        )
        await context.bot.send_message(OPERATOR_CHAT_ID, operator_text)

        # удалить QR
        if qr_msg_id:
            try:
                await context.bot.delete_message(chat_id, qr_msg_id)
            except Exception:
                pass

        # сохранить «последний заказ», очистить корзину и флаги
        set_last_order(user_id, get_cart(user_id))
        clear_cart(user_id)
        ud["awaiting_qr_confirm"] = False
        ud.pop("pending_order_text", None)
        ud.pop("qr_message_id", None)
        for j in ud.get("qr_jobs", []):
            try:
                j.schedule_removal()
            except Exception:
                pass
        ud["qr_jobs"] = []

        sent = await query.message.reply_text(
            "✅ Спасибо! Подтверждение получено. Заказ отправлен оператору. Ожидайте звонка.",
            reply_markup=base_reply_markup()
        )
        ud.setdefault("message_ids", []).append(sent.message_id)
        return

    if data == "qr_repeat":
        ud["awaiting_qr_confirm"] = True
        caption = ("Отсканируйте QR-код для оплаты.\nПосле оплаты нажмите кнопку ниже, чтобы отправить заказ оператору.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я отправил подтверждение оплаты!", callback_data="qr_confirm")],
            [InlineKeyboardButton("❌ Отменить оплату", callback_data="qr_cancel")]
        ])
        old = ud.get("qr_message_id")
        if old:
            try:
                await context.bot.delete_message(chat_id, old)
            except Exception:
                pass
        if QR_IMAGE_URL:
            sent = await query.message.reply_photo(photo=QR_IMAGE_URL, caption=caption, reply_markup=kb)
        else:
            sent = await query.message.reply_text("QR_IMAGE_URL не задан. Укажите ссылку в config.py", reply_markup=kb)
        ud["qr_message_id"] = sent.message_id
        ud.setdefault("message_ids", []).append(sent.message_id)
        return

    if data == "qr_cancel":
        old = ud.get("qr_message_id")
        if old:
            try:
                await context.bot.delete_message(chat_id, old)
            except Exception:
                pass
        ud["awaiting_qr_confirm"] = False
        ud.pop("pending_order_text", None)
        ud.pop("qr_message_id", None)
        for j in ud.get("qr_jobs", []):
            try:
                j.schedule_removal()
            except Exception:
                pass
        ud["qr_jobs"] = []
        sent = await query.message.reply_text(
            "❌ Оплата по QR отменена. Вы можете выбрать другой способ оплаты или оформить заказ заново.",
            reply_markup=base_reply_markup()
        )
        ud.setdefault("message_ids", []).append(sent.message_id)
        return

# ---------- cancel ----------

async def cancel_checkout_msg(update, context):
    chat_id = update.effective_chat.id
    await delete_all_bot_messages(context, chat_id)
    context.user_data['in_checkout'] = False
    sent = await update.message.reply_text(
        "Оформление заказа отменено.", reply_markup=base_reply_markup()
    )
    context.user_data.setdefault("message_ids", []).append(sent.message_id)
    return ConversationHandler.END
