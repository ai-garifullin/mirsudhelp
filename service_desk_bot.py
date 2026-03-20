import telebot
import os
import dotenv
import time
import threading
from db_utils import get_db_connection

dotenv.load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
user_data = {}

# --- ФОНОВЫЙ ПРОЦЕСС ОТПРАВКИ ОТВЕТОВ ИЗ CRM ---
def telegram_sender_worker():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Выбираем сообщения от саппорта, которые еще не ушли
            cursor.execute("""
                SELECT rm.*, u.Chat_ID 
                FROM request_message rm
                JOIN request r ON rm.Request_ID = r.Request_ID
                JOIN user u ON r.User_ID = u.User_ID
                WHERE rm.Sender_Type = 'Support' AND rm.Is_Sent = 0
                FOR UPDATE
            """)
            messages = cursor.fetchall()
            
            for msg in messages:
                try:
                    chat_id = msg['Chat_ID']
                    text = f"💬 Ответ по заявке №{msg['Request_ID']}:\n{msg['Message_Text']}"
                    file_path = msg.get('Attachment_Path')

                    # ЛОГИКА ОТПРАВКИ
                    if file_path and os.path.exists(file_path):
                        # Определяем тип файла
                        ext = file_path.lower().split('.')[-1]
                        
                        with open(file_path, 'rb') as f:
                            if ext in ['jpg', 'jpeg', 'png']:
                                # Отправляем как фото
                                bot.send_photo(chat_id, f, caption=text)
                            else:
                                # Отправляем как документ (для docx, rar, pdf и прочих)
                                bot.send_document(chat_id, f, caption=text)
                    else:
                        # Если файла нет, просто шлем текст
                        bot.send_message(chat_id, text)

                    # Помечаем как отправленное
                    cursor.execute("UPDATE request_message SET Is_Sent = 1 WHERE Message_ID = %s", (msg['Message_ID'],))
                    conn.commit() # Коммитим каждое успешно отправленное
                    
                except Exception as e:
                    print(f"Ошибка отправки сообщения ID {msg.get('Message_ID')}: {e}")
            
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка воркера: {e}")
        
        time.sleep(3)

threading.Thread(target=telegram_sender_worker, daemon=True).start()

# --- ЛОГИКА КОМАНД ---

@bot.message_handler(commands=['start', 'cancel'])
def start(message):
    chat_id = message.chat.id
    user_data[chat_id] = {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT District_ID, District_Name FROM district ORDER BY District_Name")
    districts = cursor.fetchall()
    conn.close()

    menu_text = "<b>👋 Выберите ваш район:</b>\n\n"
    for d in districts:
        menu_text += f"/d_{d['District_ID']}  —  {d['District_Name']}\n"
    bot.send_message(chat_id, menu_text, parse_mode='HTML')

@bot.message_handler(regexp=r"^/d_\d+$")
def handle_district_command(message):
    chat_id = message.chat.id
    district_id = int(message.text.replace("/d_", ""))
    user_data[chat_id] = {'district_id': district_id, 'step': 'section'}
    bot.send_message(chat_id, "✅ Район выбран. Введите номер судебного участка (цифрами):")

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

@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_all_steps(message):
    chat_id = message.chat.id
    
    # 1. Сначала проверяем: находится ли пользователь в процессе оформления?
    state = user_data.get(chat_id, {})
    if state.get('step'):
        # Если есть активный шаг оформления (section, fio, desc) — не блокируем!
        # Переходим к стандартной логике обработки шагов ниже
        pass
    else:
        # 2. ЕСЛИ НЕ ОФОРМЛЯЕТ ЗАЯВКУ — Проверяем активную заявку для переписки
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.Request_ID, r.Status 
            FROM request r 
            JOIN user u ON r.User_ID = u.User_ID 
            WHERE u.Chat_ID = %s 
            ORDER BY r.Request_ID DESC LIMIT 1
        """, (chat_id,))
        active_req = cursor.fetchone()
        conn.close()

        if active_req and active_req['Status'] == '✅ Выполнена':
            # Блокируем только если это просто сообщение, а не команда /start
            if message.text != '/start':
                bot.reply_to(message, "⚠️ У вас нет активных заявок. Чтобы создать новую, введите /start.")
                return
        
        # 3. ЕСЛИ ЗАЯВКА НЕ ВЫПОЛНЕНА — Сохраняем сообщение
        file_path = None
        # Сохранение файла, если прислали
        if message.content_type in ['photo', 'document']:
            # Получаем file_id
            file_id = message.photo[-1].file_id if message.photo else message.document.file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            os.makedirs("attachments", exist_ok=True)
            file_ext = file_info.file_path.split('.')[-1]
            file_name = f"cli_{int(time.time())}.{file_ext}"
            file_path = os.path.join("attachments", file_name)
            
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
        
        text = message.caption or message.text or "[Файл]"
        
        # Сохранение в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO request_message 
            (Request_ID, Sender_Type, Message_Text, Attachment_Path, Is_Sent, Created_At) 
            VALUES (%s, 'Client', %s, %s, 1, NOW())
        """, (active_req['Request_ID'], text, file_path))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, "✅ Ваше сообщение и файл переданы.")
        return # Выходим, так как сообщение обработано как ответ по заявке

    # 4. СТАНДАРТНЫЕ ШАГИ ОФОРМЛЕНИЯ (если активной заявки нет)
    state = user_data.get(chat_id, {})
    step = state.get('step')
    if step == 'section': process_section(message, message.text.strip())
    elif step == 'fio': process_fio(message, message.text.strip())
    elif step == 'desc': process_description(message)

def process_fio(message, text):
    chat_id = message.chat.id
    user_data[chat_id]['fio'] = text
    # Сохраняем или обновляем Chat_ID в базе
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT User_ID FROM user WHERE Full_Name = %s", (text,))
    res = cursor.fetchone()
    if res: cursor.execute("UPDATE user SET Chat_ID = %s WHERE User_ID = %s", (chat_id, res[0]))
    else: cursor.execute("INSERT INTO user (Full_Name, Chat_ID) VALUES (%s, %s)", (text, chat_id))
    conn.commit()
    conn.close()
    
    user_data[chat_id]['step'] = 'desc'
    bot.send_message(chat_id, "Опишите проблему и укажите контактный телефон. Вы можете прикрепить 1 файл.")

print("Бот запущен...")
bot.infinity_polling()