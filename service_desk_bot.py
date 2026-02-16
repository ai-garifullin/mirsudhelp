import telebot
import os
import dotenv
import time
from db_utils import get_db_connection

# --- 1. НАСТРОЙКИ ---
dotenv.load_dotenv()

bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
user_data = {}

# --- 2. ЛОГИКА КОМАНД ---

@bot.message_handler(commands=['start', 'cancel'])
def start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {}
    
    conn = get_db_connection()
    if not conn: 
        bot.send_message(chat_id, "Ошибка подключения к базе данных.")
        return
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT District_ID, District_Name FROM district ORDER BY District_Name")
    districts = cursor.fetchall()
    conn.close()

    # Переходим на HTML разметку, она меньше конфликтует с символами _
    menu_text = "<b>👋 Выберите ваш район из списка:</b>\n<i>(Нажмите на синюю команду слева)</i>\n\n"
    
    for d in districts:
        # Экранируем название на случай, если там есть < > &
        dist_name = d['District_Name'].replace('<', '&lt;').replace('>', '&gt;')
        # Формат: /d_ID — Название
        menu_text += f"/d_{d['District_ID']}  —  {dist_name}\n"

    # Используем parse_mode='HTML'
    try:
        bot.send_message(chat_id, menu_text, parse_mode='HTML')
    except Exception as e:
        # Если список слишком длинный (ТГ ограничивает сообщение 4096 символами)
        # Отправляем без разметки в случае ошибки
        bot.send_message(chat_id, menu_text)

# --- ОБРАБОТКА НАЖАТИЯ НА РАЙОН (/d_...) ---
@bot.message_handler(regexp=r"^/d_\d+$")
def handle_district_command(message):
    chat_id = message.chat.id
    
    try:
        district_id = int(message.text.replace("/d_", ""))
    except:
        bot.send_message(chat_id, "Ошибка выбора.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT District_Name FROM district WHERE District_ID = %s", (district_id,))
    res = cursor.fetchone()
    conn.close()

    if res:
        dist_name = res[0]
        user_data[chat_id] = {'district_id': district_id, 'step': 'section'}
        bot.send_message(chat_id, f"✅ Выбран район: **{dist_name}**\n\n"
                                  "Теперь введите **Номер судебного участка** (просто число).", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "Район не найден.")

# --- УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК (ТЕКСТ + ФАЙЛЫ) ---
@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_all_steps(message):
    chat_id = message.chat.id
    state = user_data.get(chat_id, {})
    step = state.get('step')

    # 1. Проверка участка
    if step == 'section':
        if message.content_type == 'text':
            process_section(message, message.text.strip())
        else:
            bot.send_message(chat_id, "Пожалуйста, введите номер участка цифрами.")

    # 2. Ввод ФИО
    elif step == 'fio':
        if message.content_type == 'text':
            process_fio(message, message.text.strip())
        else:
            bot.send_message(chat_id, "Пожалуйста, введите ваше ФИО текстом.")

    # 3. Описание проблемы (Тут принимаем и файлы)
    elif step == 'desc':
        process_description(message)
    
    else:
        bot.send_message(chat_id, "Нажмите /start для начала оформления заявки.")

# --- ШАГ 1: ПРОВЕРКА УЧАСТКА ---
def process_section(message, text):
    chat_id = message.chat.id
    if not text.isdigit():
        bot.send_message(chat_id, "Введите только цифру.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """SELECT s.Section_ID, l.Address_Name 
             FROM court_section s JOIN locations l ON s.Location_ID = l.Location_ID
             WHERE s.District_ID = %s AND s.Section_Number = %s"""
    cursor.execute(sql, (user_data[chat_id]['district_id'], text))
    res = cursor.fetchone()
    conn.close()

    if res:
        user_data[chat_id]['section_id'] = res['Section_ID']
        user_data[chat_id]['step'] = 'fio'
        bot.send_message(chat_id, f"🏠 Адрес: {res['Address_Name']}\n\nВведите ваше **ФИО и Должность**.", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ Участок не найден в этом районе. Проверьте номер.")

# --- ШАГ 2: ФИО ---
def process_fio(message, text):
    chat_id = message.chat.id
    user_data[chat_id]['fio'] = text
    user_data[chat_id]['step'] = 'desc'
    bot.send_message(chat_id, "Опишите проблему и укажите **контактный телефон**. Вы также можете прикрепить ОДНО фото или документ.", parse_mode='Markdown')

# --- ШАГ 3: СОХРАНЕНИЕ ЗАЯВКИ И ФАЙЛА ---
def process_description(message):
    chat_id = message.chat.id
    # В ТГ текст при файле лежит в caption, а просто текст в text
    input_text = message.caption if message.caption else message.text
    file_save_path = None

    # Обработка вложения
    if message.content_type in ['photo', 'document']:
        try:
            os.makedirs("attachments", exist_ok=True)
            
            if message.content_type == 'photo':
                # Берем самое качественное фото из списка
                file_id = message.photo[-1].file_id
                ext = ".jpg"
            else:
                file_id = message.document.file_id
                ext = os.path.splitext(message.document.file_name)[1]

            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            filename = f"tg_{int(time.time())}_{chat_id}{ext}"
            file_save_path = os.path.join("attachments", filename)

            with open(file_save_path, 'wb') as f:
                f.write(downloaded_file)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Ошибка загрузки файла: {e}")

    if not input_text and not file_save_path:
        bot.send_message(chat_id, "Пожалуйста, напишите описание или пришлите файл.")
        return

    # Сохранение в БД
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Работа с пользователем
        cursor.execute("SELECT User_ID FROM user WHERE Full_Name = %s", (user_data[chat_id]['fio'],))
        res = cursor.fetchone()
        if res:
            user_id = res[0]
        else:
            cursor.execute("INSERT INTO user (Full_Name) VALUES (%s)", (user_data[chat_id]['fio'],))
            user_id = cursor.lastrowid

        # 2. Создание заявки (request)
        final_desc = input_text if input_text else "[Вложение]"
        sql_req = """INSERT INTO request (Description, User_ID, Court_Section_ID, Request_Type_ID, Service_Type, Status) 
                     VALUES (%s, %s, %s, 21, 'Удаленно', 'Новая')"""
        cursor.execute(sql_req, (final_desc, user_id, user_data[chat_id]['section_id']))
        req_id = cursor.lastrowid

        # 3. Если был файл — пишем его в историю сообщений (request_message)
        if file_save_path:
            sql_msg = """INSERT INTO request_message (Request_ID, Sender_Type, Message_Text, Attachment_Path, Created_At) 
                         VALUES (%s, 'Client', %s, %s, NOW())"""
            # Фиксируем в чате, что это файл из заявки
            msg_note = f"Файл к заявке: {input_text}" if input_text else "Первичное вложение"
            cursor.execute(sql_msg, (req_id, msg_note, file_save_path))

        conn.commit()
        bot.send_message(chat_id, f"✅ Заявка №{req_id} принята! Специалисты скоро свяжутся с вами.")
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка при сохранении: {e}")
    finally:
        conn.close()
        user_data[chat_id] = {}

print("Бот успешно запущен и готов к работе...")
bot.infinity_polling()