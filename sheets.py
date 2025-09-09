import os
import json
from typing import List, Dict
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import SPREADSHEET_ID

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

def _load_credentials() -> Credentials:

    json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if json_str:
        try:
            data = json.loads(json_str)
            return Credentials.from_service_account_info(data, scopes=SCOPES)
        except Exception:
            pass  # попробуем другие варианты

def _service():
    creds = _load_credentials()
    # cache_discovery=False — чтобы клиент не пытался писать в файловую систему контейнера
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def get_sheet_names() -> List[str]:
    """Возвращает список названий листов таблицы."""
    svc = _service()
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]

def get_dishes_by_sheet(sheet_name: str) -> List[Dict[str, str]]:
    """
    Возвращает строки листа как список словарей.
    Первая строка — заголовки. Если колонки 'ID' нет — генерируем её как номер строки.
    """
    svc = _service()
    rng = f"{sheet_name}!A1:Z1000"
    res = svc.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=rng).execute()
    values = res.get("values", [])
    if not values:
        return []

    headers = [h.strip() for h in values[0]]
    data: List[Dict[str, str]] = []
    for idx, row in enumerate(values[1:], start=1):
        item = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        if not item.get("ID"):
            item["ID"] = str(idx)
        data.append(item)
    return data
