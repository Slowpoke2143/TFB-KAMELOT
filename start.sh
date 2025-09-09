#!/usr/bin/env bash
set -e

# Если секрет с Google-ключом передан как переменная — запишем во временный файл
if [ -n "$GOOGLE_CREDENTIALS_JSON" ]; then
  echo "$GOOGLE_CREDENTIALS_JSON" > /tmp/credentials.json
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/credentials.json
fi

# На всякий случай выводим версию питона и список пакетов (полезно при отладке)
python -V || true
pip list || true

# Запуск бота (long polling)
python -u bot.py
