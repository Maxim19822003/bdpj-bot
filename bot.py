import os
import json
import re
import sys
from datetime import datetime, timedelta
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

app = Flask(__name__)

print("BOT STARTING", flush=True)

# ============ НАСТРОЙКИ ============
TOKEN = os.environ['BOT_TOKEN']
SECRET = os.environ.get('WEBHOOK_SECRET', '')
SHEET_ID = os.environ['SHEET_ID']
GOOGLE_CREDS = os.environ.get('GOOGLE_CREDS_JSON', '')

print(f"TOKEN loaded: {bool(TOKEN)}", flush=True)
print(f"SHEET_ID loaded: {bool(SHEET_ID)}", flush=True)
print(f"GOOGLE_CREDS loaded: {bool(GOOGLE_CREDS)}", flush=True)

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

# ============ ВАЛИДАТОРЫ ДАННЫХ ============
class DataValidator:
    """Класс для валидации всех входных данных"""
    
    @staticmethod
    def clean_text(text):
        """Очистка текста от лишних пробелов и спецсимволов"""
        if not text:
            return ''
        # Убираем лишние пробелы, табы, переносы строк
        text = ' '.join(text.split())
        # Убираем опасные символы для Excel/Sheets
        text = text.replace('=', '').replace('+', '').replace('-', ' ').replace("'", "")
        return text.strip()
    
    @staticmethod
    def validate_fio(fio):
        """Валидация ФИО"""
        fio = DataValidator.clean_text(fio)
        if not fio:
            return None, "ФИО не может быть пустым"
        
        # Убираем цифры и спецсимволы
        fio = re.sub(r'[^а-яА-ЯёЁa-zA-Z\s\-\.]', '', fio)
        
        # Проверяем минимальную длину
        if len(fio) < 3:
            return None, "ФИО слишком короткое (минимум 3 символа)"
        
        # Проверяем что есть хотя бы одна буква
        if not re.search(r'[а-яА-ЯёЁa-zA-Z]', fio):
            return None, "В ФИО должны быть буквы"
        
        # Нормализуем регистр (первая буква заглавная)
        parts = fio.split()
        normalized_parts = []
        for part in parts:
            if part:
                # Обработка двойных фамилий (Иванов-Петров)
                if '-' in part:
                    subparts = part.split('-')
                    normalized_parts.append('-'.join(p.capitalize() for p in subparts))
                else:
                    normalized_parts.append(part.capitalize())
        
        return ' '.join(normalized_parts), None
    
    @staticmethod
    def validate_phone(phone):
        """Валидация телефона - принимает любой формат, возвращает +7XXXXXXXXXX"""
        if not phone:
            return None, "Телефон не может быть пустым"
        
        # Убираем всё кроме цифр
        digits = re.sub(r'\D', '', phone)
        
        # Если пусто
        if not digits:
            return None, "В телефоне нет цифр"
        
        # Если начинается с 8 и 11 цифр → меняем на 7
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        # Если 10 цифр → добавляем 7
        elif len(digits) == 10:
            digits = '7' + digits
        # Если начинается с 9 и 11 цифр (ошибка) → меняем на 7
        elif digits.startswith('9') and len(digits) == 11:
            digits = '7' + digits[1:]
        
        # Проверяем что получилось 11 цифр и начинается с 7
        if len(digits) != 11:
            return None, f"Неверное количество цифр ({len(digits)}, нужно 11)"
        
        if not digits.startswith('7'):
            return None, "Номер должен начинаться с 7 или 8"
        
        # Проверяем код оператора (не 7**0000000)
        if digits[1:4] == '000':
            return None, "Неверный код оператора"
        
        return '+' + digits, None
    
    @staticmethod
    def validate_telegram(username):
        """Валидация Telegram username"""
        if not username or username.strip() in ['-', 'нет', 'не', 'no', '0']:
            return '', None  # Необязательное поле
        
        username = username.strip()
        
        # Если это число (chat_id)
        if username.isdigit():
            return username, None
        
        # Убираем @ если есть
        if username.startswith('@'):
            username = username[1:]
        
        # Проверяем формат username
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$', username):
            return None, "Неверный формат. Примеры: @username или 123456789"
        
        return username, None
    
    @staticmethod
    def validate_address(address):
        """Валидация адреса"""
        address = DataValidator.clean_text(address)
        if not address:
            return None, "Адрес не может быть пустым"
        
        if len(address) < 5:
            return None, "Адрес слишком короткий"
        
        # Проверяем что есть хотя бы одна цифра (номер дома)
        if not re.search(r'\d', address):
            return None, "В адресе должен быть номер дома"
        
        return address, None
    
    @staticmethod
    def validate_nickname(nickname):
        """Валидация клички питомца"""
        nickname = DataValidator.clean_text(nickname)
        if not nickname:
            return None, "Кличка не может быть пустой"
        
        # Убираем цифры в начале
        nickname = re.sub(r'^\d+', '', nickname).strip()
        
        if len(nickname) < 2:
            return None, "Кличка слишком короткая (минимум 2 буквы)"
        
        # Первая буква заглавная
        return nickname.capitalize(), None
    
    @staticmethod
    def validate_age(age):
        """Валидация возраста или даты рождения"""
        age = DataValidator.clean_text(age)
        if not age:
            return None, "Возраст не может быть пустым"
        
        # Пробуем распарсить как дату
        date_patterns = [
            r'(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})',  # ДД.ММ.ГГГГ или ДД/ММ/ГГ
            r'(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})',     # ГГГГ.ММ.ДД
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, age)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[2]) == 2:  # ДД.ММ.ГГ
                        day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                        year += 2000 if year < 50 else 1900
                    elif int(groups[0]) > 31:  # ГГГГ.ММ.ДД
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:
                        day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                    
                    # Проверяем корректность даты
                    birth_date = datetime(year, month, day)
                    if birth_date > datetime.now():
                        return None, "Дата рождения не может быть в будущем"
                    if birth_date < datetime(1990, 1, 1):
                        return None, "Слишком старая дата (до 1990)"
                    
                    return f"{day:02d}.{month:02d}.{year}", None
                except ValueError:
                    pass
        
        # Если не дата, проверяем как текст возраста
        # Ищем числа
        numbers = re.findall(r'\d+', age)
        if numbers:
            num = int(numbers[0])
            if num > 50:
                return None, "Слишком большой возраст (максимум 50 лет)"
            if num == 0:
                return None, "Возраст не может быть 0"
        
        # Нормализуем текст
        age = re.sub(r'[^а-яА-ЯёЁa-zA-Z0-9\s]', '', age)
        return age.lower().strip(), None
    
    @staticmethod
    def validate_vaccine_date(date_str):
        """Валидация даты прививки"""
        date_str = DataValidator.clean_text(date_str).lower()
        
        if date_str in ['сегодня', 'today', 'сейчас']:
            return datetime.now().strftime('%Y-%m-%d'), None
        
        # Пробуем разные форматы
        formats = ['%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m.%d.%Y']
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Проверяем что дата не в будущем
                if dt > datetime.now() + timedelta(days=1):
                    return None, "Дата прививки не может быть в будущем"
                # Проверяем что не слишком старая
                if dt < datetime.now() - timedelta(days=365*5):
                    return None, "Слишком старая дата прививки (более 5 лет назад)"
                return dt.strftime('%Y-%m-%d'), None
            except ValueError:
                continue
        
        return None, "Неверный формат даты. Примеры: 15.02.2025, 2025-02-15, сегодня"
    
    @staticmethod
    def validate_term_months(term):
        """Валидация срока действия в месяцах"""
        term = DataValidator.clean_text(term)
        
        # Заменяем запятую на точку
        term = term.replace(',', '.')
        
        # Ищем число
        match = re.search(r'(\d+\.?\d*)', term)
        if not match:
            return None, "Введите число месяцев"
        
        try:
            num = float(match.group(1))
            if num <= 0:
                return None, "Срок должен быть больше 0"
            if num > 120:
                return None, "Срок слишком большой (максимум 120 месяцев = 10 лет)"
            
            # Округляем до целого
            return str(int(num)), None
        except ValueError:
            return None, "Неверное число"

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
        print(f"Error getting sheet {sheet_name}: {e}", flush=True)
        return None

def get_all_records(sheet_name='Ввод_бот'):
    """Получить все записи из указанного листа"""
    try:
        sheet = get_sheet(sheet_name)
        if sheet:
            return sheet.get_all_records()
        return []
    except Exception as e:
        print(f"Error getting records from {sheet_name}: {e}", flush=True)
        return []

# ============ ПОИСК ============
def search_all_sheets(query):
    """Глобальный поиск по всем полям таблицы"""
    query_lower = query.lower().strip()
    results = []
    
    records = get_all_records('Ввод_бот')
    print(f"DEBUG: Total records in Ввод_бот: {len(records)}", flush=True)
    
    for idx, record in enumerate(records):
        record_str = json.dumps(record, ensure_ascii=False).lower()
        
        if query_lower in record_str:
            print(f"DEBUG: Match at row {idx + 2}", flush=True)
            results.append({
                'source': 'Ввод_бот',
                'data': record
            })
    
    print(f"DEBUG: Total matches: {len(results)}", flush=True)
    return results

def format_search_results(results):
    """Форматировать результаты поиска"""
    if not results:
        return f"{EMOJI['warning']} Ничего не найдено\n\nПопробуйте другой запрос."
    
    text = f"{EMOJI['search']} Найдено результатов: {len(results)}\n\n"
    
    for i, result in enumerate(results[:5], 1):
        record = result['data']
        
        fio = record.get('ФИО', 'Не указано')
        phone = record.get('Телефон', '')
        telegram = record.get('Telegram', '')
        address = record.get('Адрес', '')
        pet = record.get('Кличка', 'Не указано')
        animal_type = record.get('Вид_животного', '')
        sex = record.get('Пол', '')
        age = record.get('Возраст_или_ДР', '')
        vaccine = record.get('Тип_прививки', '')
        vaccine_date = record.get('Дата_прививки', '')
        term = record.get('Срок_мес', '')
        channel = record.get('Канал', '')
        status = record.get('Статус_обработки', 'Новый')
        
        text += f"{i}. {EMOJI['user']} {fio}\n"
        
        if phone:
            text += f"   {EMOJI['phone']} {phone}\n"
        if telegram:
            text += f"   Telegram: {telegram}\n"
        if address:
            text += f"   {EMOJI['home']} {address}\n"
        
        text += f"   {EMOJI['paw']} {pet}"
        if animal_type:
            text += f" ({animal_type}"
            if sex:
                text += f", {sex}"
            text += ")"
        text += "\n"
        
        if age:
            text += f"   {EMOJI['calendar']} {age}\n"
        
        if vaccine:
            text += f"   {EMOJI['syringe']} {vaccine}"
            if vaccine_date:
                text += f" ({vaccine_date})"
            if term:
                text += f" — {term} мес."
            text += "\n"
        
        if channel:
            text += f"   {EMOJI['bell']} Канал: {channel}\n"
        
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
        staff = str(record.get('Сотрудник_TG', record.get('staff_tg', ''))).lower()
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
        print(f"send_message: chat={chat_id}, status={response.status_code}", flush=True)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}", flush=True)
        return None

def send_animation(chat_id, animation_path, caption=None, keyboard=None):
    """Отправить анимацию (GIF/MP4)"""
    url = f'https://api.telegram.org/bot{TOKEN}/sendAnimation'
    
    try:
        with open(animation_path, 'rb') as animation_file:
            files = {'animation': animation_file}
            data = {
                'chat_id': chat_id,
                'caption': caption or '',
            }
            if keyboard:
                data['reply_markup'] = json.dumps(keyboard)
            
            response = requests.post(url, files=files, data=data, timeout=30)
            print(f"send_animation: chat={chat_id}, status={response.status_code}", flush=True)
            return response.json()
    except FileNotFoundError:
        print(f"Error: Animation file not found: {animation_path}", flush=True)
        return None
    except Exception as e:
        print(f"Error sending animation: {e}", flush=True)
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
                {'text': "М", 'callback_data': 'male'},
                {'text': "Ж", 'callback_data': 'female'}
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
    {'key': 'fio', 'ask': f"{EMOJI['user']} ФИО владельца\n\nВведите полностью фамилию, имя и отчество", 'kb': None, 'validate': 'fio'},
    {'key': 'phone', 'ask': f"{EMOJI['phone']} Телефон\n\nНапример:\n• +79001234567\n• 89001234567\n• 7-900-123-45-67", 'kb': None, 'validate': 'phone'},
    {'key': 'telegram', 'ask': f"{EMOJI['paw']} Telegram (необязательно)\n\nВведите @username или напишите «-» если нет", 'kb': None, 'validate': 'telegram'},
    {'key': 'address', 'ask': f"{EMOJI['home']} Адрес\n\nГде проживаете?\nГород, улица, дом, квартира", 'kb': None, 'validate': 'address'},
    {'key': 'consent', 'ask': f"{EMOJI['bell']} Согласие на уведомления\n\nМожем ли мы присылать напоминания о прививках?", 'kb': 'yes_no', 'validate': None},
    {'key': 'animal_type', 'ask': f"{EMOJI['paw']} Вид животного", 'kb': 'animal', 'validate': None},
    {'key': 'nickname', 'ask': f"{EMOJI['heart']} Кличка питомца", 'kb': None, 'validate': 'nickname'},
    {'key': 'sex', 'ask': "Пол", 'kb': 'sex', 'validate': None},
    {'key': 'age_or_dob', 'ask': f"{EMOJI['calendar']} Возраст или дата рождения\n\nПримеры:\n• 3 года\n• 2.5 месяца\n• 15.05.2020\n• 2020-05-15", 'kb': None, 'validate': 'age'},
    {'key': 'vaccine_type', 'ask': f"{EMOJI['syringe']} Тип прививки", 'kb': 'vaccine', 'validate': None},
    {'key': 'vaccine_date', 'ask': f"{EMOJI['calendar']} Дата прививки\n\n• Сегодня\n• 15.02.2025\n• 2025-02-15", 'kb': None, 'validate': 'vaccine_date'},
    {'key': 'term_months', 'ask': f"Срок действия (месяцев)\n\n• 12 — бешенство\n• 36 — комплексная\n• Можно дробные: 6, 12, 18", 'kb': None, 'validate': 'term_months'},
    {'key': 'channel', 'ask': f"{EMOJI['bell']} Канал напоминаний", 'kb': 'channel', 'validate': None},
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
        print(f"Error saving: {e}", flush=True)
        return False

# ============ ОБРАБОТКА ============
@app.route('/webhook', methods=['POST'])
def webhook():
    sys.stdout.flush()
    print("=" * 50, flush=True)
    print("WEBHOOK CALLED", flush=True)
    
    try:
        data = request.get_json(force=True)
        print(f"Received data: {json.dumps(data, ensure_ascii=False)}", flush=True)
        
        if not data:
            print("Empty data received", flush=True)
            return 'ok'
        
        if 'callback_query' in data:
            print("Processing callback_query", flush=True)
            return handle_callback(data['callback_query'])
        
        if 'message' not in data:
            print(f"No 'message' in data. Keys: {list(data.keys())}", flush=True)
            return 'ok'
        
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '').strip()
        username = msg['from'].get('username', '')
        first_name = msg['from'].get('first_name', 'сотрудник')
        user = f'@{username}' if username else first_name
        
        print(f"Message from {user} (chat_id: {chat_id}): '{text}'", flush=True)
        
        if text == '/start':
            print("Processing /start command", flush=True)
            user_states.pop(chat_id, None)
            
            # Отправляем песочные часы
            url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
            try:
                resp = requests.post(url, json={
                    'chat_id': chat_id,
                    'text': '⌛️',
                    'reply_markup': {'remove_keyboard': True}
                }, timeout=5)
                print(f"Remove keyboard response: {resp.status_code}", flush=True)
            except Exception as e:
                print(f"Error removing keyboard: {e}", flush=True)
            
            # Отправляем logo.mp4
            logo_path = 'images/logo.mp4'
            print(f"Sending logo animation from {logo_path}", flush=True)
            send_animation(chat_id, logo_path)
            
            # Отправляем приветственное сообщение с меню
            welcome_caption = f"""{EMOJI['logo']} БДПЖ Боровск

База данных привитых животных

Выберите действие 👇"""
            
            print(f"Sending welcome message to {chat_id}", flush=True)
            result = send_message(chat_id, welcome_caption, main_inline_keyboard())
            print(f"Welcome message result: {result}", flush=True)
            return 'ok'
        
        if text == '/cancel':
            print("Processing /cancel command", flush=True)
            user_states.pop(chat_id, None)
            send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
            return 'ok'
        
        if chat_id in user_states and user_states[chat_id].get('mode') == 'search':
            print(f"Processing search query: {text}", flush=True)
            del user_states[chat_id]['mode']
            results = search_all_sheets(text)
            print(f"Search results: {len(results)} found", flush=True)
            send_message(chat_id, format_search_results(results), main_inline_keyboard())
            return 'ok'
        
        if chat_id in user_states:
            print(f"Processing input for state: {user_states[chat_id]}", flush=True)
            return handle_input(chat_id, text, user)
        
        print("No state found, showing main menu", flush=True)
        send_message(chat_id, f"{EMOJI['paw']} Нажмите кнопку в меню выше или отправьте /start", main_inline_keyboard())
        
    except Exception as e:
        print(f"CRITICAL ERROR in webhook: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    print("=" * 50, flush=True)
    return 'ok'

def handle_callback(callback):
    """Обработка нажатий на inline кнопки"""
    chat_id = callback['message']['chat']['id']
    data = callback['data']
    username = callback['from'].get('username', '')
    first_name = callback['from'].get('first_name', 'сотрудник')
    user = f'@{username}' if username else first_name
    
    print(f"Callback from {user}: data={data}", flush=True)
    
    answer_callback(callback['id'])
    
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
        send_message(chat_id, f"{EMOJI['search']} Поиск")
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
    
    if data == 'cancel':
        user_states.pop(chat_id, None)
        send_message(chat_id, f"{EMOJI['ok']} Ок, отменено.\n\nЧто дальше?", main_inline_keyboard())
        return 'ok'
    
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
            
            if state['step'] >= len(STEPS):
                return finish_record(chat_id, state)
            else:
                next_step = STEPS[state['step']]
                kb = get_step_keyboard(next_step['kb'])
                send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def handle_input(chat_id, text, user):
    """Обработка текстового ввода с валидацией"""
    state = user_states[chat_id]
    validator = DataValidator()
    
    # Обработка специальных ожиданий (другой вид/прививка)
    if state.get('waiting_for') == 'other_animal':
        animal_type = validator.clean_text(text)
        if len(animal_type) < 2:
            send_message(chat_id, f"{EMOJI['warning']} Слишком коротко. Введите вид животного полностью.")
            return 'ok'
        state['data']['animal_type'] = animal_type.capitalize()
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
        vaccine_type = validator.clean_text(text)
        if len(vaccine_type) < 2:
            send_message(chat_id, f"{EMOJI['warning']} Слишком коротко. Введите тип прививки полностью.")
            return 'ok'
        state['data']['vaccine_type'] = vaccine_type.capitalize()
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
    validate_type = step.get('validate')
    
    # Валидация данных
    value = None
    error = None
    
    if validate_type == 'fio':
        value, error = validator.validate_fio(text)
    elif validate_type == 'phone':
        value, error = validator.validate_phone(text)
    elif validate_type == 'telegram':
        value, error = validator.validate_telegram(text)
    elif validate_type == 'address':
        value, error = validator.validate_address(text)
    elif validate_type == 'nickname':
        value, error = validator.validate_nickname(text)
    elif validate_type == 'age':
        value, error = validator.validate_age(text)
    elif validate_type == 'vaccine_date':
        value, error = validator.validate_vaccine_date(text)
    elif validate_type == 'term_months':
        value, error = validator.validate_term_months(text)
    else:
        value = validator.clean_text(text)
    
    # Если есть ошибка валидации
    if error:
        send_message(chat_id, f"{EMOJI['warning']} {error}\n\nПопробуйте ещё раз:")
        return 'ok'
    
    # Сохраняем валидированное значение
    state['data'][step['key']] = value
    state['step'] += 1
    
    if state['step'] >= len(STEPS):
        return finish_record(chat_id, state)
    else:
        next_step = STEPS[state['step']]
        kb = get_step_keyboard(next_step['kb'])
        send_message(chat_id, next_step['ask'], kb)
    
    return 'ok'

def format_fio_short(fio):
    """Преобразует ФИО в формат: Фамилия И.О. (с инициалами)"""
    if not fio or fio == 'Не указано':
        return fio
    
    # Убираем лишние пробелы
    fio = ' '.join(fio.split())
    parts = fio.split()
    
    if len(parts) == 1:
        # Только фамилия
        return parts[0]
    elif len(parts) == 2:
        # Фамилия Имя → Иванов В.
        return f"{parts[0]} {parts[1][0]}."
    elif len(parts) >= 3:
        # Фамилия Имя Отчество → Иванов В.А.
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    
    return fio

def finish_record(chat_id, state):
    """Завершение записи"""
    if save_to_sheet(state['data']):
        # Получаем данные для форматирования
        fio_raw = state['data'].get('fio', 'Не указано')
        fio = format_fio_short(fio_raw)
        
        nickname = state['data'].get('nickname', 'Не указано')
        animal_type = state['data'].get('animal_type', '')
        vaccine_type = state['data'].get('vaccine_type', 'Не указано')
        term_months = state['data'].get('term_months', '')
        
        # Формируем строку с питомцем: "Вид Кличка" или просто "Кличка"
        pet_full = f"{animal_type} {nickname}" if animal_type else nickname
        
        success_text = f"""{EMOJI['ok']} Записано!

Владелец: {fio}
Питомец: {pet_full}
Прививка: {vaccine_type}
Срок: {term_months} мес.

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
        print(f"Error answering callback: {e}", flush=True)

# ============ WEBHOOK SETUP ============
def set_webhook():
    """Устанавливает вебхук в Telegram при старте сервера"""
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not render_url:
        render_url = 'https://bdpj-bot.onrender.com'
    
    webhook_url = f"{render_url}/webhook?secret={SECRET}" if SECRET else f"{render_url}/webhook"
    
    api_url = f'https://api.telegram.org/bot{TOKEN}/setWebhook'
    payload = {
        'url': webhook_url,
        'drop_pending_updates': True
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        result = response.json()
        print(f"✅ Webhook set: {webhook_url}", flush=True)
        print(f"Response: {result}", flush=True)
        return result.get('ok', False)
    except Exception as e:
        print(f"❌ Error setting webhook: {e}", flush=True)
        return False

@app.route('/')
def health():
    return f"{EMOJI['logo']} БДПЖ Боровск - Бот работает!"

if __name__ == '__main__':
    set_webhook()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

