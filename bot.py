import os
import json
import re
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
    'cross': '✕',
    'clock': '🕐',
    'location': '📍'
}

# ============ GOOGLE SHEETS ============
def get_client():
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
    
    return gspread.authorize(creds)

def get_sheet(sheet_name='Ввод_бот'):
    """Получить конкретный лист"""
    try:
        client = get_client()
        return client.open_by_key(SHEET_ID).worksheet(sheet_name)
    except Exception as e:
        print(f"Error getting sheet {sheet_name}: {e}")
        return None

def get_all_records(sheet_name='Ввод_бот'):
    """Получить все записи из указанного листа"""
    try:
        sheet = get_sheet(sheet_name)
        if sheet:
            return sheet.get_all_records()
        return []
    except Exception as e:
        print(f"Error getting records from {sheet_name}: {e}")
        return []

# ============ ПОИСК ============
def search_all_sheets(query):
    """Поиск по всем листам таблицы"""
    query_lower = query.lower().strip()
    results = []
    
    # Ищем в листе Ввод_бот
    records = get_all_records('Ввод_бот')
    print(f"DEBUG: Total records in Ввод_бот: {len(records)}")
    
    for idx, record in enumerate(records):
        # Преобразуем всю запись в строку и ищем там
        record_str = json.dumps(record, ensure_ascii=False).lower()
        
        if query_lower in record_str:
            print(f"DEBUG: Match at row {idx + 2}: {record.get('Кличка', 'NO_NICKNAME')}")
            results.append({
                'source': 'Ввод_бот',
                'data': record
            })
    
    print(f"DEBUG: Total matches: {len(results)}")
    return results

def format_search_results(results):
    """Форматировать результаты поиска"""
    if not results:
        return f"{EMOJI['warning']} Ничего не найдено\n\nПопробуйте другой запрос или проверьте правильность написания."
    
    text = f"{EMOJI['search']} Найдено результатов: {len(results)}\n\n"
    
    for i, result in enumerate(results[:5], 1):
        record = result['data']
        
        # Получаем поля с подчёркиванием
        fio = record.get('Имя_владельца', 'Не указано')
        phone = record.get('Телефон', 'Не указан')
        pet = record.get('Кличка', 'Не указано')
        animal_type = record.get('Вид_животного', '')
        vaccine = record.get('Тип_прививки', '')
        date = record.get('Дата_прививки', '')
        status = record.get('Статус_обработки', 'Новый')
        
        text += f"{i}. {EMOJI['user']} {fio}\n"
        text += f"   {EMOJI['phone']} {phone}\n"
        text += f"   {EMOJI['paw']} {pet}"
        if animal_type:
            text += f" ({animal_type})"
        text += "\n"
        if vaccine:
            text += f"   {EMOJI['syringe']} {vaccine}"
            if date:
                text += f" ({date})"
            text += "\n"
        text += f"   Статус: {status}\n\n"
    
    if len(results) > 5:
        text += f"... и ещё {len(results) - 5} результатов"
    
    return text

# ============ МОИ ЗАПИСИ ============
def get_my_records(user_identifier):
    """Получить записи пользователя за сегодня из Ввод_бот"""
    records = get_all_records('Ввод_бот')
    today = datetime.now().strftime('%Y-%m-%d')
    
    my_records = []
    for record in records:
        staff = str(record.get('staff_tg', '')).lower()
        user_id = user_identifier.lower().replace('@', '')
        
        if staff == user_identifier.lower() or staff == f"@{user_id}" or user_id in staff:
            record_date = str(record.get('Дата_прививки', ''))
            if today in record_date:
                my_records.append(record)
    
    return my_records

def format_records_summary(records):
    """Форматировать сводку записей"""
    if not records:
        return f"{EMOJI['calendar']} Сегодня записей нет"
    
    total = len(records)
    return f"{EMOJI['calendar']} Сегодня: {total} приёмов\n{EMOJI['urgent']} Срочно: 0\n{EMOJI['warning']} Скоро: 0"

def get_records_details(records):
    """Получить детали записей"""
    if not records:
        return "Записей пока нет"
    
    details = []
    for i, record in enumerate(records[:10], 1):
        pet = record.get('Кличка', 'Не указано')
        animal = record.get('Вид_животного', '')
        vaccine = record.get('Тип_прививки', '')
        date = record.get('Дата_прививки', '')
        
        details.append(f"{i}. {pet} ({animal}) - {vaccine}, {date}")
    
    return "\n".join(details)

# ============ TELEGRAM API ============
def send_message(chat_id, text, keyboard=None, parse_mode=None):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'reply_markup': keyboard if keyboard else {'remove_keyboard': True}
    }
    if parse_mode:
        payload['parse_mode'] = parse_mode
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"send_message: chat={chat_id}, status={response.status_code}")
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def send_animation(chat_id, gif_path, caption=None, keyboard=None):
    url = f'https://api.telegram.org/bot{TOKEN}/sendAnimation'
    
    with open(gif_path, 'rb') as gif_file:
        files = {'animation': gif_file}
        data = {
            'chat_id': chat_id,
            'caption': caption or '',
        }
        if keyboard:
            data['reply_markup'] = json.dumps(keyboard)
        
        try:
            response = requests.post(url, files=files, data=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error sending animation: {e}")
            return None

# ============ INLINE КЛАВИАТУРЫ ============
def main_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': f"{EMOJI['plus']} Новая запись", 'callback_data': 'new_record'},
                {'text': f"{EMOJI['search']} Поиск", 'callback_data': 'search'}
            ],
            [
                {'text': f"{EMOJI['list']} Мои записи", 'callback_data': 'my_records'},
                {'text': f"{EMOJI['phone']} Контакты клиники", 'callback_data': 'contacts'}
            ]
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
            [{'text': f"{EMOJI['rabbit']} Другое", 'callback_data': 'other_animal'}],
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

def vaccine_type_inline_keyboard():
    return {
        'inline_keyboard': [
            [
                {'text': 'Бешенство', 'callback_data': 'vaccine_rabies'},
                {'text': 'Комплексная', 'callback_data': 'vaccine_complex'}
            ],
            [{'text': 'Другое', 'callback_data': 'vaccine_other'}],
            [{'text': f"{EMOJI['cancel']} Отмена", 'callback_data': 'cancel'}]
        ]
    }

# ============ ДАННЫЕ ОПРОСА ============
STEPS = [
    {'key': 'fio', 'ask': f"{EMOJI['user']} ФИО владельца\n\nВведите полностью фамилию, имя и отчество", 'kb': None},
    {'key': 'phone', 'ask': f"{EMOJI['phone']} Телефон\n\nНапример:\n• +79001234567\n• 89001234567", 'kb': None},
    {'key': 'telegram', 'ask': f"{EMOJI['paw']} Telegram (необязательно)\n\nВведите @username или напишите «-» если нет", 'kb': None},
    {'key': 'address', 'ask': f"{EMOJI['home']} Адрес\n\nГде проживаете?\nГород, улица, дом, квартира", 'kb': None},
    {'key': 'consent', 'ask': f"{EMOJI['bell']} Согласие на уведомления\n\nМожем ли мы присылать напоминания о прививках?", 'kb': 'yes_no'},
    {'key': 'animal_type', 'ask': f"{EMOJI['paw']} Вид животного", 'kb': 'animal'},
    {'key': 'nickname', 'ask': f"{EMOJI['heart']} Кличка питомца", 'kb': None},
    {'key': 'sex', 'ask': "Пол", 'kb': 'sex'},
    {'key': 'age_or_dob', 'ask': f"{EMOJI['calendar']} Возраст или дата рождения\n\nПримеры:\n• 3 года\n• 2020-05-15", 'kb': None},
    {'key': 'vaccine_type', 'ask': f"{EMOJI['syringe']} Тип прививки", 'kb': 'vaccine'},
    {'key': 'vaccine_date', 'ask': f"{EMOJI['calendar']} Дата прививки\n\n• Сегодня\n• 2025-02-13", 'kb': None},
    {'key': 'term_months', 'ask': f"Срок действия (месяцев)\n\n• 12 — бешенство\n• 36 — комплексная", 'kb': None},
    {'key': 'channel', 'ask': f"{EMOJI['bell']} Канал напоминаний", 'kb': 'channel'},
]

user_states = {}

def get_step_keyboard(step_type):
    if step_type == 'yes_no':
        return yes_no_inline_keyboard()
    elif step_type == 'animal':
        return animal_inline_keyboard()
    elif step_type == 'sex':
        return sex_inline_keyboard()
    elif step_type == 'channel':
        return channel_inline_keyboard()
    elif step_type == 'vaccine':
        return vaccine_type_inline_keyboard()
    return None

# ============ СОХРАНЕНИЕ ============
def save_to_sheet(data):
    try:
        sheet = get_sheet('Ввод_бот')
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
        print(f"Webhook received: {json.dumps(data, ensure_ascii=False)[:500]}")
        
        if not data:
            return 'ok'
        
        # Обработка callback
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
        
        print(f"Message from {user}: {text}")
        
        # /start
        if text == '/start':
            user_states.pop(chat_id, None)
            
            url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
            try:
                requests.post(url, json={
                    'chat_id': chat_id,
                    'text': '⌛',
                    'reply_markup': {'remove_keyboard': True}
                }, timeout=5)
            except Exception as e:
                print(f"Error removing keyboard: {e}")
            
            gif_path = os.path.join(os.path.dirname(__file__), 'images', 'logo.mp4')
            
            welcome_caption = f"""{EMOJI['logo']} БДПЖ Боровск

База данных привитых животных

Выберите действие 👇"""
            
            if os.path.exists(gif_path):
                send_animation(chat_id, gif_path, welcome_caption, main_inline_keyboard())
            else:
                send_message(chat_id, welcome_caption, main_inline_keyboard())
            return 'ok'
        
        # Отмена
        if text == '/cancel':
            user_states.pop(chat_id, None)
            send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
            return 'ok'
        
        # Обработка поиска
        if chat_id in user_states and user_states[chat_id].get('mode') == 'search':
            del user_states[chat_id]['mode']
            print(f"Searching for: {text}")
            results = search_all_sheets(text)
            send_message(chat_id, format_search_results(results), main_inline_keyboard())
            return 'ok'
        
        # Проверка состояния
        if chat_id in user_states:
            return handle_input(chat_id, text, user)
        
        # Если нет состояния
        send_message(chat_id, f"{EMOJI['paw']} Нажмите кнопку в меню выше или отправьте /start", main_inline_keyboard())
        
    except Exception as e:
        print(f"Error in webhook: {e}")
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
    
    print(f"Callback from {user}: data={data}")
    
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
        user_states[chat_id] = {'mode': 'search'}
        send_message(chat_id, f"{EMOJI['search']} Поиск\n\nВведите телефон или кличку:")
        return 'ok'
    
    if data == 'my_records':
        records = get_my_records(user)
        summary = format_records_summary(records)
        details = get_records_details(records)
        
        text = f"{EMOJI['list']} Мои записи\n\n{summary}\n\n{details}"
        send_message(chat_id, text, main_inline_keyboard())
        return 'ok'
    
    if data == 'contacts':
        send_message(chat_id, f"{EMOJI['paw']} Ветеринарная клиника\n\n{EMOJI['phone']} +7 (XXX) XXX-XX-XX\n{EMOJI['clock']} Пн-Пт: 9:00-18:00\n{EMOJI['clock']} Сб: 9:00-14:00")
        return 'ok'
    
    # Отмена
    if data == 'cancel':
        user_states.pop(chat_id, None)
        send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
        return 'ok'
    
    # Обработка шагов опроса
    if chat_id in user_states and 'step' in user_states[chat_id]:
        state = user_states[chat_id]
        step_idx = state['step']
        
        if step_idx < len(STEPS):
            step = STEPS[step_idx]
            
            if step['kb'] == 'yes_no':
                if data in ['yes', 'no']:
                    state['data'][step['key']] = 'Да' if data == 'yes' else 'Нет'
                    state['step'] += 1
            elif step['kb'] == 'animal':
                if data == 'dog':
                    state['data'][step['key']] = 'Собака'
                    state['step'] += 1
                elif data == 'cat':
                    state['data'][step['key']] = 'Кошка'
                    state['step'] += 1
                elif data == 'other_animal':
                    state['waiting_for'] = 'other_animal'
                    send_message(chat_id, f"{EMOJI['paw']} Укажите вид животного\n\nНапример: кролик, хомяк, попугай...")
                    return 'ok'
            elif step['kb'] == 'sex':
                if data in ['male', 'female']:
                    state['data'][step['key']] = 'М' if data == 'male' else 'Ж'
                    state['step'] += 1
            elif step['kb'] == 'vaccine':
                if data == 'vaccine_rabies':
                    state['data'][step['key']] = 'Бешенство'
                    state['step'] += 1
                elif data == 'vaccine_complex':
                    state['data'][step['key']] = 'Комплексная'
                    state['step'] += 1
                elif data == 'vaccine_other':
                    state['waiting_for'] = 'other_vaccine'
                    send_message(chat_id, f"{EMOJI['syringe']} Укажите тип прививки")
                    return 'ok'
            elif step['kb'] == 'channel':
                if data in ['sms', 'telegram']:
                    channel_map = {'sms': 'SMS', 'telegram': 'Telegram'}
                    state['data'][step['key']] = channel_map[data]
                    state['step'] += 1
            
            # Следующий шаг или завершение
            if state['step'] >= len(STEPS):
                return finish_record(chat_id, state)
            else:
                next_step = STEPS[state['step']]
                kb = get_step_keyboard(next_step['kb'])
                send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def handle_input(chat_id, text, user):
    """Обработка текстового ввода"""
    state = user_states[chat_id]
    
    # Проверяем специальные режимы ввода
    if state.get('waiting_for') == 'other_animal':
        state['data']['animal_type'] = text
        state.pop('waiting_for')
        state['step'] += 1
        
        if state['step'] >= len(STEPS):
            return finish_record(chat_id, state)
        else:
            next_step = STEPS[state['step']]
            kb = get_step_keyboard(next_step['kb'])
            send_message(chat_id, next_step['ask'], kb)
        return 'ok'
    
    if state.get('waiting_for') == 'other_vaccine':
        state['data']['vaccine_type'] = text
        state.pop('waiting_for')
        state['step'] += 1
        
        if state['step'] >= len(STEPS):
            return finish_record(chat_id, state)
        else:
            next_step = STEPS[state['step']]
            kb = get_step_keyboard(next_step['kb'])
            send_message(chat_id, next_step['ask'], kb)
        return 'ok'
    
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
        return finish_record(chat_id, state)
    else:
        next_step = STEPS[state['step']]
        kb = get_step_keyboard(next_step['kb'])
        send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def finish_record(chat_id, state):
    """Завершение записи"""
    if save_to_sheet(state['data']):
        success_text = f"""{EMOJI['ok']} Записано!

Питомец: {state['data'].get('nickname', '')}
Прививка: {state['data'].get('vaccine_type', '')}
Срок: {state['data'].get('term_months', '')} мес.

{EMOJI['bell']} Напоминание придёт за 3 дня до окончания срока."""
        send_message(chat_id, success_text, main_inline_keyboard())
    else:
        send_message(chat_id, f"{EMOJI['cross']} Ошибка записи. Попробуйте позже.", main_inline_keyboard())
    user_states.pop(chat_id, None)
    return 'ok'

def answer_callback(callback_id):
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
