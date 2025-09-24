import json
import os
from datetime import datetime, timedelta
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_NAME = os.getenv("GOOGLE_SHEETS_SPREADSHEET_NAME", "Requests")
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
DEFAULT_DAYS_AHEAD = int(os.getenv("DEFAULT_DAYS_AHEAD", "60"))

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN environment variable")

# ---------- Google Sheets setup ----------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Підтримка і файлу, і JSON-рядка в змінній середовища
if SERVICE_ACCOUNT_JSON.strip().startswith("{"):
    info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
else:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
gc = gspread.authorize(creds)

# Sheets
ss = gc.open(SPREADSHEET_NAME)
requests_ws = ss.worksheet("Requests")
try:
    managers_ws = ss.worksheet("Managers")
except gspread.WorksheetNotFound:
    managers_ws = None

# Column indexes (1-based) for Requests
COL_ID = 1
COL_MANAGER_TG_ID = 2
COL_STORE = 3
COL_DATE = 4
COL_TIME_FROM = 5
COL_TIME_TO = 6
COL_NEED = 7
COL_BOOKED = 8
COL_STATUS = 9
COL_NOTE = 10

STATUS_PENDING = "Pending"
STATUS_CONFIRMED = "Confirmed"

# ---------- Helpers ----------
def parse_date(date_str: str) -> Optional[datetime]:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def get_manager_id_for_store(store_name: str) -> Optional[int]:
    if not managers_ws or not store_name:
        return None
    rows = managers_ws.get_all_records()
    for r in rows:
        if str(r.get("Магазин", "")).strip() == str(store_name).strip():
            try:
                return int(r.get("Manager_TG_ID"))
            except (TypeError, ValueError):
                return None
    return None

async def send_dm(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str, reply_markup=None):
    try:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
    except Exception as e:
        print(f"Failed to DM {user_id}: {e}")

def format_shift_row(row: list) -> str:
    store = row[COL_STORE - 1]
    date = row[COL_DATE - 1]
    t_from = row[COL_TIME_FROM - 1]
    t_to = row[COL_TIME_TO - 1]
    need = row[COL_NEED - 1]
    status = row[COL_STATUS - 1]
    return (
        f"📍 Магазин: {store}\n"
        f"📅 Дата: {date}\n"
        f"🕒 {t_from}–{t_to}\n"
        f"👥 Потрібно: {need}\n"
        f"📌 Статус: {status}"
    )

# ---------- Command handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Це бот для бронювання змін.\n"
        "Команди:\n"
        "• /shifts — показати доступні зміни\n"
        "• /ping — перевірка роботи"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong 🏓")

async def shifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_values = requests_ws.get_all_values()
    if not all_values or len(all_values) < 2:
        await update.message.reply_text("Поки немає змін.")
        return

    rows = all_values[1:]
    today = datetime.now().date()
    cutoff = today + timedelta(days=DEFAULT_DAYS_AHEAD)
    shown = 0

    for idx, row in enumerate(rows, start=2):
        status = (row[COL_STATUS - 1] or "").strip() or STATUS_PENDING
        booked = (row[COL_BOOKED - 1] or "").strip()
        date_str = (row[COL_DATE - 1] or "").strip()
        dt = parse_date(date_str)

        if dt:
            if dt.date() < today or dt.date() > cutoff:
                continue

        if status != STATUS_PENDING or booked:
            continue

        text = format_shift_row(row)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Забронювати", callback_data=f"book:{idx}")]
        ])
        await update.message.reply_text(text, reply_markup=kb)
        shown += 1

    if shown == 0:
        await update.message.reply_text("Немає доступних змін.")

# ---------- Callback handler ----------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("book:"):
        row_idx = int(data.split(":")[1])
        row = requests_ws.row_values(row_idx)
        status = (row[COL_STATUS - 1] or "").strip() or STATUS_PENDING
        booked = (row[COL_BOOKED - 1] or "").strip()

        if status != STATUS_PENDING or booked:
            await query.edit_message_text("На жаль, цю зміну вже заброньовано або підтверджено.")
            return

        user = query.from_user
        full_name = (user.full_name or "").strip()
        username = f"@{user.username}" if user.username else ""
        user_id = user.id
        booked_payload = f"{full_name}||{user_id}||{username}"

        current_booked = requests_ws.cell(row_idx, COL_BOOKED).value or ""
        if current_booked.strip():
            await query.edit_message_text("Хтось щойно забронював цю зміну. Спробуйте іншу.")
            return

        requests_ws.update_cell(row_idx, COL_BOOKED, booked_payload)

        manager_id_cell = requests_ws.cell(row_idx, COL_MANAGER_TG_ID).value
        if not manager_id_cell:
            manager_id = get_manager_id_for_store(row[COL_STORE - 1])
        else:
            try:
                manager_id = int(manager_id_cell)
            except (TypeError, ValueError):
                manager_id = get_manager_id_for_store(row[COL_STORE - 1])

        shift_text = format_shift_row(row)
        await query.edit_message_text(
            f"✅ Ви забронювали зміну:\n{shift_text}\n\nОчікується підтвердження керівника."
        )

        if manager_id:
            confirm_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("Підтвердити бронювання", callback_data=f"confirm:{row_idx}")
            ]])
            await send_dm(context, manager_id,
                          text=(
                              "🟢 Нове бронювання від співробітника:\n\n"
                              f"{shift_text}\n\n"
                              f"👤 {full_name} {username}\n\n"
                              "Підтвердити бронювання?"
                          ),
                          reply_markup=confirm_kb
                          )
        else:
            await send_dm(context, user_id, "⚠️ Не вдалося знайти керівника для цієї зміни.")

    elif data.startswith("confirm:"):
        row_idx = int(data.split(":")[1])
        row = requests_ws.row_values(row_idx)
        status = (row[COL_STATUS - 1] or "").strip() or STATUS_PENDING
        booked = (row[COL_BOOKED - 1] or "").strip()

        if not booked:
            await update.effective_message.edit_text("Бронювання ще ніхто не зробив.")
            return
        if status == STATUS_CONFIRMED:
            await update.effective_message.edit_text("Цю зміну вже підтверджено.")
            return

        requests_ws.update_cell(row_idx, COL_STATUS, STATUS_CONFIRMED)

        parts = booked.split("||")
        user_id = None
        if len(parts) >= 2:
            try:
                user_id = int(parts[1])
            except ValueError:
                user_id = None

        shift_text = format_shift_row(row)
        await update.effective_message.edit_text("✅ Бронювання підтверджено. Повідомлення співробітнику надіслано.")

        if user_id:
            await send_dm(context, user_id,
                          text=f"🎉 Вашу зміну підтверджено!\n\n{shift_text}")

# ---------- Main ----------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("shifts", shifts))
    app.add_handler(CallbackQueryHandler(on_callback))
    print("Bot is running (polling)...")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()