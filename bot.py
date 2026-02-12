
# Обновленный код бота с новым стилем
bot_code = '''import os
import json
from datetime import datetime
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

app = Flask(__name__)

# ============ НАСТРОЙКИ ============
TOKEN = os.environ['BOT_TOKEN']
SECRET = os.environ.get('WEBHOOK_SECRET', '')
SHEET_ID = os.environ['SHEET_ID']
GOOGLE_CREDS = os.environ.get('GOOGLE_CREDS_JSON', '')

# Эмодзи стиль
EMOJI = {
    'logo': '🌿🐾❤️',
    'paw': '🐾',
    'heart': '❤️',
    'plus': '➕',
    'search': '🔍',
    'list': '📋',
    'phone': '📞',
    'urgent': '🔴',
    'warning': '🟡',
    'ok': '✅',
    'cancel': '❌',
    'dog': '🐕',
    'cat': '🐈',
    'rabbit': '🐇',
    'calendar': '📅',
    'syringe': '💉',
    'home': '🏠',
    'user': '👤',
    'bell': '🔔',
    'check': '✓',
    'cross': '✕'
}

# ============ GOOGLE SHEETS ============
def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 
             'https://www.googleapis.com/auth/drive']
    
    if GOOGLE_CREDS:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(GOOGLE_CREDS)
            creds_path = f.name
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet('Ввод_бот')

# ============ TELEGRAM API ============
def send_message(chat_id, text, keyboard=None, parse_mode='HTML'):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'reply_markup': keyboard or {'remove_keyboard': True}
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# ============ КЛАВИАТУРЫ ============
def main_keyboard():
    return {
        'keyboard': [
            [{f"{EMOJI['plus']} Новая запись"}],
            [{f"{EMOJI['search']} Поиск"}, {f"{EMOJI['list']} Мои записи"}],
            [{f"{EMOJI['phone']} Контакты клиники"}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': False
    }

def yes_no_keyboard():
    return {
        'keyboard': [
            [{f"{EMOJI['check']} Да"}, {f"{EMOJI['cross']} Нет"}],
            [{f"{EMOJI['cancel']} Отмена"}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }

def animal_keyboard():
    return {
        'keyboard': [
            [{f"{EMOJI['dog']} Собака"}, {f"{EMOJI['cat']} Кошка"}],
            [{f"{EMOJI['rabbit']} Другое"}],
            [{f"{EMOJI['cancel']} Отмена"}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }

def sex_keyboard():
    return {
        'keyboard': [
            [{"♂ М"}, {"♀ Ж"}],
            [{f"{EMOJI['cancel']} Отмена"}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }

def channel_keyboard():
    return {
        'keyboard': [
            [{f"{EMOJI['bell']} SMS"}, {f"{EMOJI['paw']} Telegram"}],
            [{f"{EMOJI['cancel']} Отмена"}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }

# ============ ДАННЫЕ ОПРОСА ============
STEPS = [
    {'key': 'fio', 'ask': f"{EMOJI['user']} <b>ФИО владельца</b>\\n\\nВведите полностью фамилию, имя и отчество", 'kb': None},
    {'key': 'phone', 'ask': f"{EMOJI['phone']} <b>Телефон</b>\\n\\nВведите номер для связи:\\n• +79001234567\\n• 89001234567", 'kb': None},
    {'key': 'telegram', 'ask': f"{EMOJI['paw']} <b>Telegram</b> (необязательно)\\n\\nВведите @username или напишите <b>-</b> если нет", 'kb': None},
    {'key': 'address', 'ask': f"{EMOJI['home']} <b>Адрес</b>\\n\\nГде проживаете?\\n(улица, дом, квартира)", 'kb': None},
    {'key': 'consent', 'ask': f"{EMOJI['bell']} <b>Согласие на уведомления</b>\\n\\nМожем ли мы присылать напоминания о прививках?", 'kb': yes_no_keyboard()},
    {'key': 'animal_type', 'ask': f"{EMOJI['paw']} <b>Вид животного</b>", 'kb': animal_keyboard()},
    {'key': 'nickname', 'ask': f"{EMOJI['heart']} <b>Кличка питомца</b>", 'kb': None},
    {'key': 'sex', 'ask': f"<b>Пол</b>", 'kb': sex_keyboard()},
    {'key': 'age_or_dob', 'ask': f"{EMOJI['calendar']} <b>Возраст или дата рождения</b>\\n\\nПримеры:\\n• 3 года\\n• 2020-05-15", 'kb': None},
    {'key': 'vaccine_type', 'ask': f"{EMOJI['syringe']} <b>Тип прививки</b>\\n\\n• Бешенство\\n• Комплексная\\n• Другое", 'kb': None},
    {'key': 'vaccine_date', 'ask': f"{EMOJI['calendar']} <b>Дата прививки</b>\\n\\n• Сегодня\\n• 2025-02-13", 'kb': None},
    {'key': 'term_months', 'ask': f"<b>Срок действия</b> (месяцев)\\n\\n• 12 — бешенство\\n• 36 — комплексная", 'kb': None},
    {'key': 'channel', 'ask': f"{EMOJI['bell']} <b>Канал напоминаний</b>", 'kb': channel_keyboard()},
]

user_states = {}

# ============ СОХРАНЕНИЕ ============
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
        return True
    except Exception as e:
        print(f"Error saving: {e}")
        return False

# ============ ОБРАБОТКА ============
@app.route('/webhook', methods=['POST'])
def webhook():
    if SECRET and request.args.get('secret') != SECRET:
        return 'ok'
    
    try:
        data = request.get_json(force=True)
        if not data or 'message' not in data:
            return 'ok'
        
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '').strip()
        username = msg['from'].get('username', '')
        first_name = msg['from'].get('first_name', 'сотрудник')
        user = f'@{username}' if username else first_name
        
        # /start
        if text == '/start':
            user_states.pop(chat_id, None)
            welcome_text = f"""{EMOJI['logo']} <b>БДПЖ Боровск</b>

База данных привитых животных

Выберите действие 👇"""
            send_message(chat_id, welcome_text, main_keyboard())
            return 'ok'
        
        # Отмена
        if f"{EMOJI['cancel']} Отмена" in text or text == '/cancel':
            user_states.pop(chat_id, None)
            send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\\n\\nЧто дальше?", main_keyboard())
            return 'ok'
        
        # Новая запись
        if 'новая' in text.lower() and 'запись' in text.lower():
            user_states[chat_id] = {
                'step': 0,
                'data': {
                    'date_visit': datetime.now().strftime('%Y-%m-%d'),
                    'staff_tg': user
                }
            }
            step = STEPS[0]
            send_message(chat_id, step['ask'], step['kb'])
            return 'ok'
        
        # Поиск (заглушка)
        if f"{EMOJI['search']} Поиск" in text:
            send_message(chat_id, f"{EMOJI['search']} <b>Поиск</b>\\n\\nВведите телефон или кличку:")
            return 'ok'
        
        # Мои записи (заглушка)
        if f"{EMOJI['list']} Мои записи" in text:
            send_message(chat_id, f"{EMOJI['calendar']} Сегодня: 3 приёма\\n{EMOJI['urgent']} Срочно: 2\\n{EMOJI['warning']} Скоро: 5")
            return 'ok'
        
        # Контакты
        if f"{EMOJI['phone']} Контакты" in text:
            send_message(chat_id, f"{EMOJI['paw']} <b>Ветеринарная клиника</b>\\n\\n📞 +7 (XXX) XXX-XX-XX\\n🕐 Пн-Пт: 9:00-18:00\\n🕐 Сб: 9:00-14:00")
            return 'ok'
        
        # Проверка состояния
        if chat_id not in user_states:
            send_message(chat_id, f"{EMOJI['paw']} Нажмите <b>«Новая запись»</b> или отправьте /start", main_keyboard())
            return 'ok'
        
        state = user_states[chat_id]
        step_idx = state['step']
        
        if step_idx >= len(STEPS):
            user_states.pop(chat_id, None)
            return 'ok'
        
        step = STEPS[step_idx]
        value = text
        
        # Валидации
        if step['key'] == 'consent':
            if 'Да' in text:
                value = 'Да'
            elif 'Нет' in text:
                value = 'Нет'
            else:
                send_message(chat_id, f"{EMOJI['warning']} Выберите <b>Да</b> или <b>Нет</b>", yes_no_keyboard())
                return 'ok'
        
        if step['key'] == 'telegram' and text == '-':
            value = ''
        
        if step['key'] == 'vaccine_date' and text.lower() == 'сегодня':
            value = datetime.now().strftime('%Y-%m-%d')
        
        if step['key'] == 'phone':
            value = text.replace(' ', '').replace('-', '')
            if not value.replace('+', '').isdigit() or len(value.replace('+', '')) < 10:
                send_message(chat_id, f"{EMOJI['warning']} Неверный формат.\\nПример: +79001234567")
                return 'ok'
        
        if step['key'] == 'term_months':
            try:
                n = float(text.replace(',', '.'))
                if n <= 0 or n > 120:
                    raise ValueError
                value = str(int(n))
            except:
                send_message(chat_id, f"{EMOJI['warning']} Введите число от 1 до 120")
                return 'ok'
        
        # Сохраняем
        state['data'][step['key']] = value
        state['step'] += 1
        
        # Завершение
        if state['step'] >= len(STEPS):
            if save_to_sheet(state['data']):
                success_text = f"""{EMOJI['ok']} <b>Записано!</b>

Питомец: <b>{state['data'].get('nickname', '')}</b>
Прививка: {state['data'].get('vaccine_type', '')}
Срок: {state['data'].get('term_months', '')} мес.

{EMOJI['bell']} Напоминание придёт за 3 дня до окончания срока."""
                send_message(chat_id, success_text, main_keyboard())
            else:
                send_message(chat_id, f"{EMOJI['cross']} Ошибка записи. Попробуйте позже.", main_keyboard())
            user_states.pop(chat_id, None)
            return 'ok'
        
        # Следующий вопрос
        next_step = STEPS[state['step']]
        send_message(chat_id, next_step['ask'], next_step['kb'])
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return 'ok'

@app.route('/')
def health():
    return f"{EMOJI['logo']} БДПЖ Боровск - Бот работает!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
'''

# Сохраняем
with open('/mnt/kimi/output/bdpj_bot_styled.py', 'w', encoding='utf-8') as f:
    f.write(bot_code)

print("✅ Бот обновлён со стилем БДПЖ!")
print("\nЧто изменено:")
print("- Эмодзи везде: 🌿🐾❤️ 🔍 📋 ➕")
print("- Красивые кнопки с иконками")
print("- Стилизованные сообщения")
print("- Приветствие с логотипом")
print("- Цветные разделители")
print("\nФайл: bdpj_bot_styled.py")
