import threading
import telebot
import os
import dotenv
import time
from db_utils import get_user_tg_id

dotenv.load_dotenv()
# Вставьте сюда токен, полученный в BotFather
bot = telebot.TeleBot(os.getenv('NOT_BOT_TOKEN'))

def send_tg_notification(user_name, message):
    #print(f"DEBUG: Пытаюсь отправить сообщение для '{user_name}'...")
    tg_id = get_user_tg_id(user_name)
    #print(f"DEBUG: Найденный TG_ID: {tg_id}")
    
    if tg_id:
        try:
            bot.send_message(tg_id, message, parse_mode="HTML")
            #print(f"DEBUG: Сообщение успешно отправлено в Telegram!")
            return True
        except Exception as e:
            #print(f"DEBUG: КРИТИЧЕСКАЯ ОШИБКА TELEGRAM: {e}")
            return False
    else:
        #print(f"DEBUG: Не удалось найти TG_ID для пользователя '{user_name}'!")
        return False

def format_request_message(data, title):
    """Красивое форматирование данных заявки для Telegram"""
    return (
        f"🔔 <b>{title}</b>\n\n"
        f"🆔 <b>Заявка:</b> #{data.get('Request_ID', 'N/A')}\n"
        f"📅 <b>Дата:</b> {data.get('Created_At', 'Не указана')}\n"
        f"📍 <b>Район:</b> {data.get('District_Name', 'Не указан')}\n"
        f"🏠 <b>Участок:</b> {data.get('Section_Number', 'Не указан')}\n"
        f"📞 <b>Заявитель:</b> {data.get('User_Name', 'Не указан')}\n"
        f"📱 <b>Тел:</b> {data.get('Landline_Phone', 'Не указан')}\n\n"
        f"📝 <b>Описание:</b>\n{data.get('Description', 'Нет описания')}"
    )


def cleanup_old_attachments(directory="attachments", days_old=30):
    """
    Удаляет файлы из указанной директории, которые старше days_old дней.
    """
    if not os.path.exists(directory):
        return

    now = time.time()
    seconds_in_day = 86400
    files_deleted = 0

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        
        # Проверяем, является ли путь файлом (а не папкой)
        if os.path.isfile(file_path):
            # Получаем время последнего изменения файла
            file_age = os.path.getmtime(file_path)
            
            # Если файл старше установленного срока — удаляем
            if (now - file_age) > (days_old * seconds_in_day):
                try:
                    os.remove(file_path)
                    files_deleted += 1
                except Exception as e:
                    print(f"Ошибка при удалении файла {filename}: {e}")
    
    if files_deleted > 0:
        print(f"Очистка: удалено {files_deleted} старых файлов.")

def cleanup_worker():
    while True:
        cleanup_old_attachments(days_old=30)
        # Спим 24 часа (86400 секунд)
        time.sleep(86400)

# Запуск в потоке при старте бота
threading.Thread(target=cleanup_worker, daemon=True).start()

if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)