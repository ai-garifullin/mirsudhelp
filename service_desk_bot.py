import telebot
import os
import dotenv
from db_utils import get_db_connection

# --- 1. НАСТРОЙКИ ---
dotenv.load_dotenv()

bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
user_data = {}

# --- 3. ЛОГИКА ---

@bot.message_handler(commands=['start', 'cancel'])
def start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {}
    
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT District_ID, District_Name FROM District ORDER BY District_Name")
    districts = cursor.fetchall()
    conn.close()

    # Формируем список-меню
    menu_text = "👋 **Выберите ваш район из списка:**\n(Нажмите на синюю команду слева)\n\n"
    
    for d in districts:
        # Формат: /d_ID - Название
        menu_text += f"/d_{d['District_ID']}  —  {d['District_Name']}\n"

    bot.send_message(chat_id, menu_text)

# --- ОБРАБОТКА НАЖАТИЯ НА РАЙОН (/d_...) ---
# Ловим любые сообщения, начинающиеся с "/d_"
@bot.message_handler(regexp=r"^/d_\d+$")
def handle_district_command(message):
    chat_id = message.chat.id
    
    # Вытаскиваем ID из текста команды "/d_35" -> "35"
    try:
        district_id = int(message.text.replace("/d_", ""))
    except:
        bot.send_message(chat_id, "Ошибка выбора.")
        return

    # Получаем имя района для подтверждения
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT District_Name FROM District WHERE District_ID = %s", (district_id,))
    res = cursor.fetchone()
    conn.close()

    if res:
        dist_name = res[0]
        user_data[chat_id] = {'district_id': district_id, 'step': 'section'}
        
        bot.send_message(chat_id, f"✅ Выбран район: **{dist_name}**\n\n"
                                  "Теперь введите **Номер судебного участка** (просто число).", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "Район не найден.")

# --- ОБРАБОТКА ОСТАЛЬНОГО ТЕКСТА ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    step = user_data.get(chat_id, {}).get('step')
    text = message.text.strip()

    if step == 'section':
        process_section(message, text)
    elif step == 'fio':
        process_fio(message, text)
    elif step == 'desc':
        process_description(message, text)
    else:
        bot.send_message(chat_id, "Нажмите /start для выбора района.")

# --- 1. ПРОВЕРКА УЧАСТКА ---
def process_section(message, text):
    chat_id = message.chat.id
    if not text.isdigit():
        bot.send_message(chat_id, "Введите только цифру.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """SELECT s.Section_ID, l.Address_Name 
             FROM Court_Section s JOIN Locations l ON s.Location_ID = l.Location_ID
             WHERE s.District_ID = %s AND s.Section_Number = %s"""
    cursor.execute(sql, (user_data[chat_id]['district_id'], text))
    res = cursor.fetchone()
    conn.close()

    if res:
        user_data[chat_id]['section_id'] = res['Section_ID']
        user_data[chat_id]['step'] = 'fio'
        bot.send_message(chat_id, f"🏠 Адрес: {res['Address_Name']}\n\n"
                                  "Введите ваше **ФИО и Должность**.")
    else:
        bot.send_message(chat_id, "❌ Участок не найден в этом районе. Проверьте номер.")

# --- 2. ФИО ---
def process_fio(message, text):
    chat_id = message.chat.id
    user_data[chat_id]['fio'] = text
    user_data[chat_id]['step'] = 'desc'
    bot.send_message(chat_id, "Опишите проблему и укажите **контактный телефон**.")

# --- 3. СОХРАНЕНИЕ ---
def process_description(message, text):
    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor()

    # Юзер
    cursor.execute("SELECT User_ID FROM User WHERE Full_Name = %s", (user_data[chat_id]['fio'],))
    res = cursor.fetchone()
    user_id = res[0] if res else cursor.execute("INSERT INTO User (Full_Name) VALUES (%s)", (user_data[chat_id]['fio'],)) or cursor.lastrowid

    # Заявка
    sql = "INSERT INTO Request (Description, User_ID, Court_Section_ID, Request_Type_ID, Service_Type, Status) VALUES (%s, %s, %s, 21, 'Удаленно', 'Новая')"
    cursor.execute(sql, (text, user_id, user_data[chat_id]['section_id']))
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    bot.send_message(chat_id, f"✅ Заявка №{req_id} принята!")
    user_data[chat_id] = {}

print("Бот запущен...")
bot.infinity_polling()
