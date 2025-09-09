# config.py — безопасный вариант для публичного репозитория
import os

def _getenv(name: str, *, required: bool, cast=None, default=None):
    raw = os.getenv(name, None)
    if raw is None or raw == "":
        if required:
            raise RuntimeError(f"Environment variable {name} is required but not set")
        return default
    return cast(raw) if cast else raw

# === Telegram / Sheets ===
BOT_TOKEN        = _getenv("BOT_TOKEN",        required=True)
OPERATOR_CHAT_ID = _getenv("OPERATOR_CHAT_ID", required=True, cast=int)
SPREADSHEET_ID   = _getenv("SPREADSHEET_ID",   required=True)

# === YooKassa / Webhook (опционально) ===
YOOKASSA_SHOP_ID = _getenv("YOOKASSA_SHOP_ID", required=False)
YOOKASSA_API_KEY = _getenv("YOOKASSA_API_KEY", required=False)
DOMAIN           = _getenv("DOMAIN",           required=False)

# === QR ===
QR_IMAGE_URL          = _getenv("QR_IMAGE_URL",          required=True)
QR_REMINDER_MINUTES   = _getenv("QR_REMINDER_MINUTES",   required=False, cast=int, default=10)
QR_CANCEL_MINUTES     = _getenv("QR_CANCEL_MINUTES",     required=False, cast=int, default=30)

# === Кэш меню / блюд ===
SHEETS_CACHE_TTL_SECONDS = _getenv("SHEETS_CACHE_TTL_SECONDS", required=False, cast=int, default=600)

# === Ограничения оплаты по времени (МСК) ===
MSK_TZ            = _getenv("MSK_TZ",            required=False, default="Europe/Moscow")
EARLY_PAYMENT_HOUR= _getenv("EARLY_PAYMENT_HOUR",required=False, cast=int, default=10)  # 10:00
LATE_PAYMENT_HOUR = _getenv("LATE_PAYMENT_HOUR", required=False, cast=int, default=22)  # 22:00
