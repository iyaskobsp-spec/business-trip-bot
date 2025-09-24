# BusinessTripBot — бронювання змін (Telegram + Google Sheets)

Повний робочий приклад бота для бронювання змін зі сповіщеннями керівнику і підтвердженням.

## 🚀 Можливості
- Перегляд доступних змін (/shifts)
- Бронювання зміни працівником (inline-кнопки)
- Автозбереження ПІБ/username/Telegram ID працівника
- Сповіщення керівнику з кнопкою **Підтвердити**
- Підтвердження: статус змінюється на `Confirmed`, працівник отримує повідомлення
- Антидублювання: перевірка, що зміна ще вільна
- Мапінг керівника з окремого аркуша **Managers**

## 🧱 Структура Google Sheets
Створіть Google Spreadsheet з 2 аркушами:

### 1) `Requests`
| ID | Manager_TG_ID | Магазин | Дата | Час_початку | Час_закінчення | Потрібно | Заброньовано | Статус | Примітки |
|----|---------------|---------|------|-------------|----------------|----------|--------------|--------|----------|
- `ID` — формула `=ROW()-1`
- `Статус`: `Pending` за замовчуванням
- `Заброньовано`: формат `Full Name||UserID||@username`

### 2) `Managers`
| Магазин | Manager_TG_ID |
|---------|---------------|
- Якщо у `Requests` поле `Manager_TG_ID` порожнє — бот підтягує з `Managers`.

> Поділіться Spreadsheet з email вашого Service Account (Editor).

## 🔐 Налаштування секретів
Створіть файл `.env` (за зразком `.env.example`):
TELEGRAM_TOKEN=put_your_token_here
GOOGLE_SHEETS_SPREADSHEET_NAME=RequestsSpreadsheetName
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json

shell
Копировать код

## ▶️ Запуск
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python bot.py

markdown
Копировать код

## ☁️ Деплой
- Render / Railway / VPS
- Додайте Environment Variables з `.env`