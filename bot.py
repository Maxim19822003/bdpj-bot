import os
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
        'reply_markup': keyboard if keyboard else {'remove_keyboard': True}
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def send_animation(chat_id, gif_path, caption=None, keyboard=None):
    """Отправка GIF (анимации)"""
    url = f'https://api.telegram.org/bot{TOKEN}/sendAnimation'
    
    with open(gif_path, 'rb') as gif_file:
        files = {'animation': gif_file}
        data = {
            'chat_id': chat_id,
            'caption': caption or '',
            'parse_mode': 'HTML'
        }
        if keyboard:
            data['reply_markup'] = json.dumps(keyboard)
        
        try:
            response = requests.post(url, files=files, data=data, timeout=10)
            result = response.json()
            if not result.get('ok'):
                print(f"Telegram API error: {result}")
            return result
        except Exception as e:
            print(f"Error sending animation: {e}")
            return None

# ============ INLINE КЛАВИАТУРЫ ============
def main_inline_keyboard():
    """Главное меню - inline кнопки под сообщением"""
    return {
        'inline_keyboard': [
            [{'text': f"{EMOJI['plus']} Новая запись", 'callback_data': 'new_record'}],
            [
                {'text': f"{EMOJI['search']} Поиск", 'callback_data': 'search'},
                {'text': f"{EMOJI['list']} Мои записи", 'callback_data': 'my_records'}
            ],
            [{'text': f"{EMOJI['phone']} Контакты клиники", 'callback_data': 'contacts'}]
        ]
    }

def yes_no_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': f"{EMOJI['check']} Да", 'callback_data': 'yes'},
                {'text': f"{EMOJI['cross']} Нет", 'callback_data': 'no'}
            ],
            [{'text': f"{EMOJI['cancel']} Отмена", 'callback_data': 'cancel'}]
        ]
    }

def animal_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': f"{EMOJI['dog']} Собака", 'callback_data': 'dog'},
                {'text': f"{EMOJI['cat']} Кошка", 'callback_data': 'cat'}
            ],
            [{'text': f"{EMOJI['rabbit']} Другое", 'callback_data': 'other'}],
            [{'text': f"{EMOJI['cancel']} Отмена", 'callback_data': 'cancel'}]
        ]
    }

def sex_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': "♂ М", 'callback_data': 'male'},
                {'text': "♀ Ж", 'callback_data': 'female'}
            ],
            [{'text': f"{EMOJI['cancel']} Отмена", 'callback_data': 'cancel'}]
        ]
    }

def channel_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': f"{EMOJI['bell']} SMS", 'callback_data': 'sms'},
                {'text': f"{EMOJI['paw']} Telegram", 'callback_data': 'telegram'}
            ],
            [{'text': f"{EMOJI['cancel']} Отмена", 'callback_data': 'cancel'}]
        ]
    }

# ============ ДАННЫЕ ОПРОСА ============
STEPS = [
    {'key': 'fio', 'ask': f"{EMOJI['user']} <b>ФИО владельца</b>\n\nВведите полностью фамилию, имя и отчество", 'kb': None},
    {'key': 'phone', 'ask': f"{EMOJI['phone']} <b>Телефон</b>\n\nВведите номер для связи:\n• +79001234567\n• 89001234567", 'kb': None},
    {'key': 'telegram', 'ask': f"{EMOJI['paw']} <b>Telegram</b> (необязательно)\n\nВведите @username или напишите <b>-</b> если нет", 'kb': None},
    {'key': 'address', 'ask': f"{EMOJI['home']} <b>Адрес</b>\n\nГде проживаете?\n(улица, дом, квартира)", 'kb': None},
    {'key': 'consent', 'ask': f"{EMOJI['bell']} <b>Согласие на уведомления</b>\n\nМожем ли мы присылать напоминания о прививках?", 'kb': 'yes_no'},
    {'key': 'animal_type', 'ask': f"{EMOJI['paw']} <b>Вид животного</b>", 'kb': 'animal'},
    {'key': 'nickname', 'ask': f"{EMOJI['heart']} <b>Кличка питомца</b>", 'kb': None},
    {'key': 'sex', 'ask': f"<b>Пол</b>", 'kb': 'sex'},
    {'key': 'age_or_dob', 'ask': f"{EMOJI['calendar']} <b>Возраст или дата рождения</b>\n\nПримеры:\n• 3 года\n• 2020-05-15", 'kb': None},
    {'key': 'vaccine_type', 'ask': f"{EMOJI['syringe']} <b>Тип прививки</b>\n\n• Бешенство\n• Комплексная\n• Другое", 'kb': None},
    {'key': 'vaccine_date', 'ask': f"{EMOJI['calendar']} <b>Дата прививки</b>\n\n• Сегодня\n• 2025-02-13", 'kb': None},
    {'key': 'term_months', 'ask': f"<b>Срок действия</b> (месяцев)\n\n• 12 — бешенство\n• 36 — комплексная", 'kb': None},
    {'key': 'channel', 'ask': f"{EMOJI['bell']} <b>Канал напоминаний</b>", 'kb': 'channel'},
]

user_states = {}

def get_step_keyboard(step_type):
    """Возвращает inline клавиатуру для шага"""
    if step_type == 'yes_no':
        return yes_no_inline_keyboard()
    elif step_type == 'animal':
        return animal_inline_keyboard()
    elif step_type == 'sex':
        return sex_inline_keyboard()
    elif step_type == 'channel':
        return channel_inline_keyboard()
    return None

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
        if not data:
            return 'ok'
        
        # Обработка callback (нажатие на inline кнопку)
        if 'callback_query' in data:
            return handle_callback(data['callback_query'])
        
        # Обработка обычного сообщения
        if 'message' not in data:
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
            
            gif_path = os.path.join(os.path.dirname(__file__), 'images', 'logo.gif')
            
            welcome_caption = f"""{EMOJI['logo']} <b>БДПЖ Боровск</b>

База данных привитых животных

Выберите действие 👇"""
            
            if os.path.exists(gif_path):
                send_animation(chat_id, gif_path, welcome_caption, main_inline_keyboard())
            else:
                send_message(chat_id, welcome_caption, main_inline_keyboard())
            return 'ok'
        
        # Отмена через текст
        if text == '/cancel':
            user_states.pop(chat_id, None)
            send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
            return 'ok'
        
        # Проверка состояния (ввод данных)
        if chat_id in user_states:
            return handle_input(chat_id, text, user)
        
        # Если нет состояния - показываем меню
        send_message(chat_id, f"{EMOJI['paw']} Нажмите кнопку в меню выше или отправьте /start", main_inline_keyboard())
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return 'ok'

def handle_callback(callback):
    """Обработка нажатий на inline кнопки"""
    chat_id = callback['message']['chat']['id']
    data = callback['data']
    username = callback['from'].get('username', '')
    first_name = callback['from'].get('first_name', 'сотрудник')
    user = f'@{username}' if username else first_name
    
    # Ответ на callback (убирает "часики" на кнопке)
    answer_callback(callback['id'])
    
    # Главное меню
    if data == 'new_record':
        user_states[chat_id] = {
            'step': 0,
            'data': {
                'date_visit': datetime.now().strftime('%Y-%m-%d'),
                'staff_tg': user
            }
        }
        step = STEPS[0]
        kb = get_step_keyboard(step['kb'])
        send_message(chat_id, step['ask'], kb)
        return 'ok'
    
    if data == 'search':
        send_message(chat_id, f"{EMOJI['search']} <b>Поиск</b>\n\nВведите телефон или кличку:")
        return 'ok'
    
    if data == 'my_records':
        send_message(chat_id, f"{EMOJI['calendar']} Сегодня: 3 приёма\n{EMOJI['urgent']} Срочно: 2\n{EMOJI['warning']} Скоро: 5")
        return 'ok'
    
    if data == 'contacts':
        send_message(chat_id, f"{EMOJI['paw']} <b>Ветеринарная клиника</b>\n\n📞 +7 (XXX) XXX-XX-XX\n🕐 Пн-Пт: 9:00-18:00\n🕐 Сб: 9:00-14:00")
        return 'ok'
    
    # Отмена
    if data == 'cancel':
        user_states.pop(chat_id, None)
        send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
        return 'ok'
    
    # Обработка шагов опроса
    if chat_id in user_states:
        state = user_states[chat_id]
        step_idx = state['step']
        
        if step_idx < len(STEPS):
            step = STEPS[step_idx]
            
            # Обработка выбора из inline кнопок
            if step['kb'] == 'yes_no':
                if data in ['yes', 'no']:
                    state['data'][step['key']] = 'Да' if data == 'yes' else 'Нет'
                    state['step'] += 1
            elif step['kb'] == 'animal':
                if data in ['dog', 'cat', 'other']:
                    animal_map = {'dog': 'Собака', 'cat': 'Кошка', 'other': 'Другое'}
                    state['data'][step['key']] = animal_map[data]
                    state['step'] += 1
            elif step['kb'] == 'sex':
                if data in ['male', 'female']:
                    state['data'][step['key']] = 'М' if data == 'male' else 'Ж'
                    state['step'] += 1
            elif step['kb'] == 'channel':
                if data in ['sms', 'telegram']:
                    channel_map = {'sms': 'SMS', 'telegram': 'Telegram'}
                    state['data'][step['key']] = channel_map[data]
                    state['step'] += 1
            
            # Следующий шаг или завершение
            if state['step'] >= len(STEPS):
                if save_to_sheet(state['data']):
                    success_text = f"""{EMOJI['ok']} <b>Записано!</b>

Питомец: <b>{state['data'].get('nickname', '')}</b>
Прививка: {state['data'].get('vaccine_type', '')}
Срок: {state['data'].get('term_months', '')} мес.

{EMOJI['bell']} Напоминание придёт за 3 дня до окончания срока."""
                    send_message(chat_id, success_text, main_inline_keyboard())
                else:
                    send_message(chat_id, f"{EMOJI['cross']} Ошибка записи. Попробуйте позже.", main_inline_keyboard())
                user_states.pop(chat_id, None)
            else:
                next_step = STEPS[state['step']]
                kb = get_step_keyboard(next_step['kb'])
                send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def handle_input(chat_id, text, user):
    """Обработка текстового ввода"""
    state = user_states[chat_id]
    step_idx = state['step']
    
    if step_idx >= len(STEPS):
        user_states.pop(chat_id, None)
        return 'ok'
    
    step = STEPS[step_idx]
    value = text
    
    # Валидации
    if step['key'] == 'telegram' and text == '-':
        value = ''
    
    if step['key'] == 'vaccine_date' and text.lower() == 'сегодня':
        value = datetime.now().strftime('%Y-%m-%d')
    
    if step['key'] == 'phone':
        value = text.replace(' ', '').replace('-', '')
        if not value.replace('+', '').isdigit() or len(value.replace('+', '')) < 10:
            send_message(chat_id, f"{EMOJI['warning']} Неверный формат.\nПример: +79001234567")
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
    
    # Завершение или следующий вопрос
    if state['step'] >= len(STEPS):
        if save_to_sheet(state['data']):
            success_text = f"""{EMOJI['ok']} <b>Записано!</b>

Питомец: <b>{state['data'].get('nickname', '')}</b>
Прививка: {state['data'].get('vaccine_type', '')}
Срок: {state['data'].get('term_months', '')} мес.

{EMOJI['bell']} Напоминание придёт за 3 дня до окончания срока."""
            send_message(chat_id, success_text, main_inline_keyboard())
        else:
            send_message(chat_id, f"{EMOJI['cross']} Ошибка записи. Попробуйте позже.", main_inline_keyboard())
        user_states.pop(chat_id, None)
    else:
        next_step = STEPS[state['step']]
        kb = get_step_keyboard(next_step['kb'])
        send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def answer_callback(callback_id):
    """Ответ на callback query (убирает часики на кнопке)"""
    url = f'https://api.telegram.org/bot{TOKEN}/answerCallbackQuery'
    try:
        requests.post(url, json={'callback_query_id': callback_id}, timeout=5)
    except Exception as e:
        print(f"Error answering callback: {e}")

@app.route('/')
def health():
    return f"{EMOJI['logo']} БДПЖ Боровск - Бот работает!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
