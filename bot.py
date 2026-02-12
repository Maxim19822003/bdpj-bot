import os
import json
from datetime import datetime
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

app = Flask(__name__)

# ============ НАСТРОЙКИ ============
TOKEN = os.environ ['BOT_TOKEN']
SECRET = os.environ.get('WEBHOOK_SECRET', '')
SHEET_ID = os.environ['SHEET_ID']
GOOGLE_CREDS = os.environ.get('GOOGLE_CREDS_JSON', '')

# ============ GOOGLE SHEETS ============
def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 
             'https://www.googleapis.com/auth/drive']
    
    # Если credentials в переменной окружения
    if GOOGLE_CREDS:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(GOOGLE_CREDS)
            creds_path = f.name
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    else:
        # Иначе из файла
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet('Ввод_бот')

# ============ TELEGRAM API ============
def send_message(chat_id, text, keyboard=None):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': keyboard or {'remove_keyboard': True}
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# ============ ДАННЫЕ ОПРОСА ============
STEPS = [
    {'key': 'fio', 'ask': 'Введите <b>ФИО</b> владельца.'},
    {'key': 'phone', 'ask': 'Введите <b>телефон</b> (например +79001234567).'},
    {'key': 'telegram', 'ask': 'Введите <b>Telegram</b> (например @name) или "-" если нет.'},
    {'key': 'address', 'ask': 'Введите <b>адрес</b>.'},
    {'key': 'consent', 'ask': 'Есть <b>согласие на уведомления</b>?', 
     'kb': {'keyboard': [[{'text': 'Да'}, {'text': 'Нет'}], [{'text': '❌ Отмена'}]], 'resize_keyboard': True}},
    {'key': 'animal_type', 'ask': 'Выберите <b>вид животного</b>.', 
     'kb': {'keyboard': [[{'text': 'Собака'}, {'text': 'Кошка'}], [{'text': 'Другое'}], [{'text': '❌ Отмена'}]], 'resize_keyboard': True}},
    {'key': 'nickname', 'ask': 'Введите <b>кличку</b>.'},
    {'key': 'sex', 'ask': 'Выберите <b>пол</b>.', 
     'kb': {'keyboard': [[{'text': 'М'}, {'text': 'Ж'}], [{'text': '❌ Отмена'}]], 'resize_keyboard': True}},
    {'key': 'age_or_dob', 'ask': 'Введите <b>дату рождения</b> (гггг-мм-дд) или возраст (например "3 года").'},
    {'key': 'vaccine_type', 'ask': 'Введите <b>тип прививки</b> (Бешенство/Комплекс...).'},
    {'key': 'vaccine_date', 'ask': 'Введите <b>дату прививки</b> (гггг-мм-дд) или "сегодня".'},
    {'key': 'term_months', 'ask': 'Введите <b>срок</b> в месяцах (12/36...).'},
    {'key': 'channel', 'ask': 'Выберите <b>канал</b> (SMS/Telegram).', 
     'kb': {'keyboard': [[{'text': 'SMS'}, {'text': 'Telegram'}], [{'text': '❌ Отмена'}]], 'resize_keyboard': True}},
]

# Хранилище состояний (в памяти)
user_states = {}

# ============ ОБРАБОТКА ============
def save_to_sheet(data):
    try:
        sheet = get_sheet()
        row = [
            data.get('date_visit', ''),
            data.get('staff_tg', ''),
            data.get('fio', ''),
            data.get('phone', ''),
            data.get('telegram', ''),
            data.get('address', ''),
            data.get('consent', ''),
            data.get('animal_type', ''),
            data.get('nickname', ''),
            data.get('sex', ''),
            data.get('age_or_dob', ''),
            data.get('vaccine_type', ''),
            data.get('vaccine_date', ''),
            data.get('term_months', ''),
            data.get('channel', ''),
            'Новый',
            data.get('comment', '')
        ]
        sheet.append_row(row)
        print(f"Saved row: {row}")
        return True
    except Exception as e:
        print(f"Error saving to sheet: {e}")
        return False

@app.route('/')
def health():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    # Проверка секрета
    if SECRET and request.args.get('secret') != SECRET:
        print("Invalid secret")
        return 'ok'
    
    try:
        data = request.get_json(force=True)
        print(f"Received: {json.dumps(data, ensure_ascii=False)}")
        
        if not data or 'message' not in data:
            return 'ok'
        
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '').strip()
        username = msg['from'].get('username', '')
        first_name = msg['from'].get('first_name', 'сотрудник')
        user = f'@{username}' if username else first_name
        
        print(f"Message from {user}: {text}")
        
        # /start
        if text == '/start':
            user_states.pop(chat_id, None)
            send_message(chat_id, 'Меню:', {
                'keyboard': [[{'text': '➕ Новая запись'}], [{'text': '❌ Отмена'}]],
                'resize_keyboard': True
            })
            return 'ok'
        
        # Отмена
        if text in ['❌ Отмена', '/cancel']:
            user_states.pop(chat_id, None)
            send_message(chat_id, 'Ок, отменено.', {
                'keyboard': [[{'text': '➕ Новая запись'}], [{'text': '❌ Отмена'}]],
                'resize_keyboard': True
            })
            return 'ok'
        
        # Новая запись
        is_new = 'новая' in text.lower() and 'запись' in text.lower()
        if is_new:
            user_states[chat_id] = {
                'step': 0,
                'data': {
                    'date_visit': datetime.now().strftime('%Y-%m-%d'),
                    'staff_tg': user
                }
            }
            step = STEPS[0]
            send_message(chat_id, step['ask'], step.get('kb'))
            return 'ok'
        
        # Проверка состояния
        if chat_id not in user_states:
            send_message(chat_id, 'Нажмите "Новая запись" или /start', {
                'keyboard': [[{'text': '➕ Новая запись'}], [{'text': '❌ Отмена'}]],
                'resize_keyboard': True
            })
            return 'ok'
        
        state = user_states[chat_id]
        step_idx = state['step']
        
        if step_idx >= len(STEPS):
            user_states.pop(chat_id, None)
            return 'ok'
        
        step = STEPS[step_idx]
        value = text
        
        # Валидации
        if step['key'] == 'consent' and text not in ['Да', 'Нет']:
            send_message(chat_id, 'Выберите "Да" или "Нет".', step.get('kb'))
            return 'ok'
        
        if step['key'] == 'telegram' and text == '-':
            value = ''
        
        if step['key'] == 'vaccine_date' and text.lower() == 'сегодня':
            value = datetime.now().strftime('%Y-%m-%d')
        
        if step['key'] == 'phone':
            value = text.replace(' ', '').replace('-', '')
            if not value.replace('+', '').isdigit() or len(value.replace('+', '')) < 10:
                send_message(chat_id, 'Неверный формат. Пример: +79001234567 или 89001234567')
                return 'ok'
        
        if step['key'] == 'term_months':
            try:
                n = float(text.replace(',', '.'))
                if n <= 0 or n > 120:
                    raise ValueError
                value = str(int(n))
            except:
                send_message(chat_id, 'Нужно число месяцев от 1 до 120 (например 12 или 36).')
                return 'ok'
        
        # Сохраняем ответ
        state['data'][step['key']] = value
        state['step'] += 1
        
        # Проверяем, закончен ли опрос
        if state['step'] >= len(STEPS):
            if save_to_sheet(state['data']):
                send_message(chat_id, '✅ Записано в Ввод_бот (Статус: Новый).', {
                    'keyboard': [[{'text': '➕ Новая запись'}], [{'text': '❌ Отмена'}]],
                    'resize_keyboard': True
                })
            else:
                send_message(chat_id, '❌ Ошибка записи в таблицу. Попробуйте позже.')
            user_states.pop(chat_id, None)
            return 'ok'
        
        # Следующий вопрос
        next_step = STEPS[state['step']]
        send_message(chat_id, next_step['ask'], next_step.get('kb'))
        
    except Exception as e:
        print(f"Error in webhook: {e}")
        import traceback
        traceback.print_exc()
    
    return 'ok'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)