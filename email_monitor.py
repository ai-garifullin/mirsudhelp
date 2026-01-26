import imaplib
import email
from email.header import decode_header
from db_utils import *
import time
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()
# --- 1. НАСТРОЙКИ ПОЧТЫ ---

EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = os.getenv('IMAP_PORT')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = os.getenv('SMTP_PORT')


def send_email(recipient_email, subject, body):
    """Отправляет email от имени системы."""
    if not recipient_email: return "Ошибка: Email получателя не найден."
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return "✅ Сообщение успешно отправлено!"
    except Exception as e:
        return f"❌ Ошибка отправки: {e}"

def clean_text(text):
    decoded_list = decode_header(text)
    parts = []
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or 'utf-8', 'ignore'))
        else:
            parts.append(str(content))
    return "".join(parts)

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode()
                except:
                    return part.get_payload(decode=True).decode('cp1251', 'ignore')
    else:
        try:
            return msg.get_payload(decode=True).decode()
        except:
            return msg.get_payload(decode=True).decode('cp1251', 'ignore')
    return ""

def extract_email_address(raw_from):
    match = re.search(r'<(.+?)>', raw_from)
    return match.group(1).strip() if match else raw_from.strip()

# --- 4. ОСНОВНАЯ ЛОГИКА ---

def process_emails():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 Проверяю почту...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    status, messages = mail.search(None, "UNSEEN")
    email_ids = messages[0].split()

    if not email_ids:
        print("📭 Новых писем нет.")
        mail.logout()
        return

    print(f"📬 Найдено новых писем: {len(email_ids)}")

    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    for e_id in email_ids:
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = clean_text(msg.get("Subject", "Без темы"))
            raw_from = clean_text(msg.get("From", ""))
            sender_email = extract_email_address(raw_from)
            body = get_email_body(msg).strip()
            
            print(f"--- 📨 Обработка письма от {sender_email} с темой: {subject} ---")

            # --- ГЛАВНАЯ ЛОГИКА: ОБНОВЛЕНИЕ ИЛИ СОЗДАНИЕ? ---
            
            # Ищем номер в теме (например, "RE: ... Заявка №51")
            match = re.search(r'Заявка\s+№(\d+)', subject, re.IGNORECASE)

            if match:
                # --- ЭТО ОБНОВЛЕНИЕ СУЩЕСТВУЮЩЕЙ ЗАЯВКИ ---
                request_id = int(match.group(1))
                print(f"  -> 🔍 Это ответ по заявке №{request_id}.")
                
                # 1. Получаем старое описание
                cursor.execute("SELECT Description FROM Request WHERE Request_ID = %s", (request_id,))
                res = cursor.fetchone()
                
                if res:
                    old_description = res[0]
                    # 2. Добавляем новый текст
                    new_description = f"{old_description}\n\n--- [ОТВЕТ ЗАЯВИТЕЛЯ {datetime.now().strftime('%d.%m %H:%M')}] ---\n{body}"
                    # 3. Сохраняем
                    cursor.execute("UPDATE Request SET Description = %s WHERE Request_ID = %s", (new_description, request_id))
                    conn.commit()
                    print(f"  -> ✅ 'Чат' в заявке №{request_id} обновлен.")
                else:
                    print(f"  -> ⚠️ Заявка №{request_id} не найдена в базе. Создаю новую.")
                    # Если заявка не найдена, переходим к логике создания
                    create_new_request(cursor, conn, subject, raw_from, sender_email, body)
                    
            else:
                # --- ЭТО СОЗДАНИЕ НОВОЙ ЗАЯВКИ ---
                create_new_request(cursor, conn, subject, raw_from, sender_email, body)

        except Exception as e:
            print(f"  -> ❌ Ошибка обработки письма: {e}")
            
    conn.close()
    mail.close()
    mail.logout()

def create_new_request(cursor, conn, subject, raw_from, sender_email, body):
    """Отдельная функция для создания новой заявки."""
    print(f"  -> 🆕 Это новая заявка.")
    
    # 1. Ищем участок по email
    cursor.execute("SELECT Section_ID FROM Court_Section WHERE Email = %s", (sender_email,))
    section_res = cursor.fetchone()

    if section_res:
        section_id = section_res[0]
        
        # 2. Ищем или создаем пользователя
        cursor.execute("SELECT User_ID FROM User WHERE Full_Name = %s", (raw_from,))
        user_res = cursor.fetchone()
        user_id = user_res[0] if user_res else cursor.execute("INSERT INTO User (Full_Name) VALUES (%s)", (raw_from,)) or cursor.lastrowid
        
        # 3. Собираем описание
        full_description = f"Тема: {subject}\n\n{body}"
        
        # 4. Создаем заявку
        sql = "INSERT INTO Request (Description, User_ID, Court_Section_ID, Status, Request_Type_ID) VALUES (%s, %s, %s, '🔴 Новая', 5)"
        cursor.execute(sql, (full_description, user_id, section_id))
        request_id = cursor.lastrowid
        conn.commit()
        print(f"  -> ✅ Заявка №{request_id} успешно создана.")
        
        # 5. ОТПРАВЛЯЕМ АВТООТВЕТ
        auto_reply_subject = f"Ваша заявка №{request_id} принята"
        auto_reply_body = f"Здравствуйте!\n\nВаше обращение зарегистрировано в системе Service Desk под номером {request_id}.\n\nТема: {subject}"
        send_status = send_email(sender_email, auto_reply_subject, auto_reply_body)
        print(f"  -> {send_status}")
        
    else:
        print(f"  -> ⚠️ Email отправителя {sender_email} не найден в справочнике участков. Заявка не создана.")


# --- 5. ЦИКЛ ЗАПУСКА ---
if __name__ == "__main__":
    print("🚀 Монитор почты запущен (Ctrl+C для выхода)")
    while True:
        try:
            process_emails()
            print(f"⏳ Следующая проверка через 60 секунд...")
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nВыход...")
            break
        except Exception as e:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА в главном цикле: {e}")
            time.sleep(300) # Ждем 5 минут перед повторной попыткой
