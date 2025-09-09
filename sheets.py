import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import SPREADSHEET_ID

# Получаем строку из переменной окружения или путь к файлу
if os.getenv("GOOGLE_CREDENTIALS_JSON"):
    # ✅ Читаем из переменной окружения
    json_keyfile_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
else:
    # ✅ Fallback: читаем из локального файла
    with open("data/credentials.json", "r", encoding="utf-8") as f:
        json_keyfile_dict = json.load(f)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_keyfile_dict, scope)
client = gspread.authorize(creds)

def get_sheet_names():
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return [sheet.title for sheet in spreadsheet.worksheets()]

def get_dishes_by_sheet(sheet_name):
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    return sheet.get_all_records()
