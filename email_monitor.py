import imaplib
import email
from email.header import decode_header
from db_utils import get_db_connection
import time
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import mimetypes
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# --- 1. НАСТРОЙКИ ЛОГИРОВАНИЯ ---
# Логи сохраняются в файл и выводятся в консоль
# Создаем папку logs, если её нет (важно для Docker!)
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# Полный путь к файлу
log_file = os.path.join(log_dir, "email_monitor.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # Пишем в папку logs
        logging.FileHandler(log_file, encoding='utf-8'), 
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# --- 2. КОНФИГУРАЦИЯ ПОЧТЫ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS') # Здесь должен быть Пароль Приложения!
IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))

# --- 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def send_email(recipient_email, subject, body, attachment=None):
    """Отправляет email с поддержкой вложений."""
    if not recipient_email:
        return "Ошибка: Email получателя не найден."
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        # Добавляем текст письма
        msg.attach(MIMEText(body, 'plain'))

        # Логика работы с вложением
        if attachment and os.path.exists(attachment):
            try:
                # Определяем тип файла (MIME-тип)
                ctype, encoding = mimetypes.guess_type(attachment)
                if ctype is None or encoding is not None:
                    ctype = 'application/octet-stream'
                
                maintype, subtype = ctype.split('/', 1)
                
                # Читаем файл в бинарном режиме
                with open(attachment, "rb") as f:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(f.read())
                
                # Кодируем в base64 для передачи по почте
                encoders.encode_base64(part)
                
                # Добавляем заголовок с именем файла
                # Используем os.path.basename, чтобы в письме было только имя "image.png", а не весь путь
                filename = os.path.basename(attachment)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                
                msg.attach(part)
            except Exception as file_err:
                logger.error(f"Не удалось прикрепить файл {attachment}: {file_err}")
                # Продолжаем отправку письма даже если файл не прикрепился, 
                # либо можно прервать и вернуть ошибку

        # Отправка
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
            
        return "✅ Сообщение успешно отправлено!"
        
    except Exception as e:
        logger.error(f"Ошибка отправки письма на {recipient_email}: {e}")
        return f"❌ Ошибка отправки: {e}"

def clean_text(text):
    if not text: return ""
    decoded_list = decode_header(text)
    parts = []
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or 'utf-8', 'ignore'))
        else:
            parts.append(str(content))
    return "".join(parts).strip()

def normalize_subject(subject):
    """
    Очищает тему для сравнения строк.
    Удаляет Re:, Fwd:, а также любые упоминания номеров заявок, 
    чтобы сравнить именно суть проблемы.
    """
    # 1. Удаляем любые вариации "Заявка №...", "по заявке №..."
    # r'заявк[а-я]*' - найдет заявкА, заявкЕ, заявкИ и т.д.
    s = re.sub(r'заявк[а-я]*\s+№\s*\d+', '', subject, flags=re.IGNORECASE)
    
    # 2. Удаляем префиксы ответов (Re:, На:, Ответ: ...)
    s = re.sub(r'^\s*(re|fwd|fw|aw|ответ|на|service desk)\s*[:\-]\s*', '', s, flags=re.IGNORECASE)
    
    # 3. Удаляем лишние пробелы и приводим к нижнему регистру
    return s.strip().lower()

def get_email_body(msg):
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    text = part.get_payload(decode=True).decode()
                except:
                    text = part.get_payload(decode=True).decode('cp1251', 'ignore')
                break
    else:
        try:
            text = msg.get_payload(decode=True).decode()
        except:
            text = msg.get_payload(decode=True).decode('cp1251', 'ignore')
    return text

def extract_email_address(raw_from):
    match = re.search(r'<(.+?)>', raw_from)
    return match.group(1).strip() if match else raw_from.strip()

# --- 3. ЛОГИКА ОБРАБОТКИ ---

def process_emails():
    logger.info("🔄 Проверка почты...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
    except Exception as e:
        logger.critical(f"❌ Ошибка IMAP: {e}")
        return

    status, messages = mail.search(None, "UNSEEN")
    email_ids = messages[0].split()

    if not email_ids:
        logger.info("📭 Новых писем нет.")
        mail.logout()
        return

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Нет связи с БД")
        mail.logout()
        return
    cursor = conn.cursor()

    for e_id in email_ids:
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            raw_subject = clean_text(msg.get("Subject", "Без темы"))
            raw_from = clean_text(msg.get("From", ""))
            sender_email = extract_email_address(raw_from)
            body = get_email_body(msg).strip()

            logger.info(f"📨 От: {sender_email} | Тема: {raw_subject}")

            # 1. ПРОВЕРКА ОТПРАВИТЕЛЯ
            cursor.execute("SELECT Section_ID FROM court_section WHERE Email = %s", (sender_email,))
            section_res = cursor.fetchone()

            if not section_res:
                logger.warning(f"⛔ Отказ: {sender_email} не найден.")
                send_email(sender_email, "Ошибка доступа", "Ваш email не зарегистрирован в системе.")
                continue

            section_id = section_res[0]

            # 2. ПОИСК ПОЛЬЗОВАТЕЛЯ
            cursor.execute("SELECT User_ID FROM user WHERE Full_Name = %s", (raw_from,))
            user_res = cursor.fetchone()
            user_id = user_res[0] if user_res else None
            
            if not user_id:
                cursor.execute("INSERT INTO user (Full_Name) VALUES (%s)", (raw_from,))
                user_id = cursor.lastrowid

            # --- ГЛАВНАЯ ЛОГИКА МАРШРУТИЗАЦИИ ---
            
            # А) ПОИСК ПО ID (Самый приоритетный)
            # Ищем "Заявк" + любое окончание (а-я) + пробелы + № + цифры
            # Пример: "по заявке №10", "Заявка № 10", "ЗАЯВКИ №10"
            match_id = re.search(r'заявк[а-я]*\s+№\s*(\d+)', raw_subject, re.IGNORECASE)
            
            target_request_id = None

            if match_id:
                potential_id = int(match_id.group(1))
                # Проверяем, существует ли такая заявка реально
                cursor.execute("SELECT Request_ID FROM request WHERE Request_ID = %s", (potential_id,))
                if cursor.fetchone():
                    target_request_id = potential_id
                    #logger.info(f"   -> 📎 Найден ID {target_request_id} (из темы письма).")
                else:
                    logger.warning(f"   -> ⚠️ В теме есть ID {potential_id}, но в базе его нет.")

            # Б) ЕСЛИ ID НЕ НАЙДЕН -> Ищем по совпадению текста темы (Threading)
            if not target_request_id:
                clean_subj = normalize_subject(raw_subject)
                
                # Ищем открытые заявки этого пользователя
                sql_search = """
                    SELECT Request_ID, Description FROM request 
                    WHERE User_ID = %s 
                    AND Status NOT LIKE '🟢%' 
                    AND Status NOT LIKE '%Закрыт%'
                """
                cursor.execute(sql_search, (user_id,))
                active_requests = cursor.fetchall()
                
                for req_id, desc in active_requests:
                    # Берем первую строку описания (там всегда "Тема: ...")
                    first_line = desc.split('\n')[0] 
                    stored_subj = normalize_subject(first_line.replace('Тема:', ''))
                    
                    # Если очищенные темы совпадают
                    if stored_subj and stored_subj == clean_subj:
                        target_request_id = req_id
                        #logger.info(f"   -> 📎 Найдена ветка по теме: '{clean_subj}' -> ID {target_request_id}")
                        break

            # --- ВЫПОЛНЕНИЕ ДЕЙСТВИЯ ---
            if target_request_id:
                update_existing_ticket(cursor, conn, target_request_id, body)
            else:
                create_new_ticket(cursor, conn, raw_subject, body, user_id, section_id, sender_email)

        except Exception as e:
            logger.error(f"❌ Сбой обработки письма: {e}", exc_info=True)

    conn.close()
    mail.logout()

def update_existing_ticket(cursor, conn, request_id, body):
    """
    Добавляет сообщение в НОВУЮ таблицу request_message.
    Саму таблицу Request мы не трогаем (там лежит только первое письмо).
    """
    # Проверяем существование заявки
    cursor.execute("SELECT Request_ID FROM request WHERE Request_ID = %s", (request_id,))
    if not cursor.fetchone():
        logger.warning(f"   -> ⚠️ Заявка №{request_id} не найдена в базе.")
        return

    # Вставляем сообщение. Sender_Type = 'Client', т.к. пришло письмо
    sql = """
        INSERT INTO request_message (Request_ID, Sender_Type, Message_Text, Created_At) 
        VALUES (%s, 'Client', %s, NOW())
    """
    cursor.execute(sql, (request_id, body))
    conn.commit()
    
    # Можно обновить статус заявки, чтобы поднять её вверх в списке
    # cursor.execute("UPDATE request SET Status = '🔴 Открыта' WHERE Request_ID = %s", (request_id,))
    # conn.commit()
    
    #logger.info(f"   -> ✅ Сообщение добавлено в чат заявки №{request_id}.")

def create_new_ticket(cursor, conn, subject, body, user_id, section_id, sender_email):
    """
    Создает заявку в таблице Request.
    В поле Description записываем суть первого письма.
    """
    #logger.info("   -> 🆕 Новая заявка.")
    
    full_desc = f"Тема: {subject}\n\n{body}"
    
    # Создаем саму заявку
    sql = """
        INSERT INTO request 
        (Description, User_ID, Court_Section_ID, Status, Request_Type_ID, Date_Received) 
        VALUES (%s, %s, %s, '🔴 Новая', NULL, NOW())
    """
    cursor.execute(sql, (full_desc, user_id, section_id))
    new_id = cursor.lastrowid
    conn.commit()
    
    #logger.info(f"   -> ✅ Заявка №{new_id} создана.")
    
    # Отправляем автоответ
    reply_subj = f"Заявка №{new_id} принята"
    reply_body = f"Ваше обращение зарегистрировано под номером {new_id}.\nТема: {subject}"
    send_email(sender_email, reply_subj, reply_body)

if __name__ == "__main__":
    #logger.info("🚀 Monitor v3 (Regex Fixed) запущен")
    while True:
        try:
            process_emails()
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.critical(f"Critical Error: {e}")
            time.sleep(300)
    