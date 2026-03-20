import imaplib
import email
from email.header import decode_header
from db_utils import (
    get_db_connection, get_section_id_by_email, get_or_create_user,
    check_request_exists, get_active_user_requests, 
    db_add_request_message, db_create_new_request
)
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

    for e_id in email_ids:
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            raw_subject = clean_text(msg.get("Subject", "Без темы"))
            raw_from = clean_text(msg.get("From", ""))
            sender_email = extract_email_address(raw_from)
            body = get_email_body(msg).strip()

            logger.info(f"📨 От: {sender_email} | Тема: {raw_subject}")

            # 1. ПРОВЕРКА ОТПРАВИТЕЛЯ (Через БД-утилиту)
            section_id = get_section_id_by_email(sender_email)
            if not section_id:
                logger.warning(f"⛔ Отказ: {sender_email} не найден.")
                send_email(sender_email, "Ошибка доступа", "Ваш email не зарегистрирован в системе.")
                continue

            # 2. ПОИСК ИЛИ СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ
            user_id = get_or_create_user(raw_from)

            # --- ГЛАВНАЯ ЛОГИКА МАРШРУТИЗАЦИИ ---
            target_request_id = None

            # А) ПОИСК ПО ID В ТЕМЕ
            match_id = re.search(r'заявк[а-я]*\s+№\s*(\d+)', raw_subject, re.IGNORECASE)
            if match_id:
                potential_id = int(match_id.group(1))
                if check_request_exists(potential_id):
                    target_request_id = potential_id
                else:
                    logger.warning(f"   -> ⚠️ В теме есть ID {potential_id}, но в базе его нет.")

            # Б) ПОИСК ПО СОВПАДЕНИЮ ТЕМЫ (Threading)
            if not target_request_id:
                clean_subj = normalize_subject(raw_subject)
                active_requests = get_active_user_requests(user_id)
                
                for req_id, desc in active_requests:
                    first_line = desc.split('\n')[0] 
                    stored_subj = normalize_subject(first_line.replace('Тема:', ''))
                    
                    if stored_subj and stored_subj == clean_subj:
                        target_request_id = req_id
                        break

            # --- ВЫПОЛНЕНИЕ ДЕЙСТВИЯ ---
            if target_request_id:
                # Обновляем существующую
                db_add_request_message(target_request_id, body)
                logger.info(f" ✅ Добавлено сообщение в заявку №{target_request_id}")
            else:
                # Создаем новую
                new_id = db_create_new_request(raw_subject, body, user_id, section_id)
                if new_id:
                    logger.info(f" ✅ Создана новая заявка №{new_id}")
                    # Отправляем автоответ
                    reply_subj = f"Заявка №{new_id} принята"
                    reply_body = f"Ваше обращение зарегистрировано под номером {new_id}.\nТема: {raw_subject}"
                    send_email(sender_email, reply_subj, reply_body)

        except Exception as e:
            logger.error(f"❌ Сбой обработки письма: {e}", exc_info=True)

    mail.logout()

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
    