# payment.py

from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_API_KEY, DOMAIN
import uuid

# Настройка ЮKassa SDK
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY

# Создание платежа
def create_payment(total_amount, user_id):
    payment = Payment.create({
        "amount": {
            "value": f"{total_amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"{DOMAIN}/success"
        },
        "capture": True,
        "description": f"Заказ от Telegram user {user_id}",
        "metadata": {
            "tg_user_id": user_id
        }
    }, uuid.uuid4())

    return payment.confirmation.confirmation_url, str(payment.id)
