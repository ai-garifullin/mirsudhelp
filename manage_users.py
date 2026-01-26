import hashlib
import getpass # Для безопасного ввода пароля
from db_utils import * 
import os
from dotenv import load_dotenv
load_dotenv()
# --- НАСТРОЙКИ ---


def hash_password(password):
    """Хэширует пароль с использованием SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def add_user():
    """Интерактивная утилита для добавления нового пользователя."""
    print("--- Создание нового пользователя CRM ---")
    login = input("Введите логин: ").strip()
    
    # Безопасный ввод пароля (не будет отображаться на экране)
    password = getpass.getpass("Введите пароль: ")
    password_confirm = getpass.getpass("Повторите пароль: ")

    if password != password_confirm:
        print("❌ Пароли не совпадают!")
        return

    # Выбор роли
    print("Доступные роли: admin, user, dispatcher")
    role = input("Введите роль (например, dispatcher): ").strip()
    if role not in ['admin', 'dispatcher', 'user']:
        print("❌ Неверная роль!")
        return
        
    # Хэшируем пароль
    password_hash = hash_password(password)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = "INSERT INTO system_users (login, password_hash, role) VALUES (%s, %s, %s)"
        cursor.execute(sql, (login, password_hash, role))
        
        conn.commit()
        conn.close()
        print(f"✅ Пользователь '{login}' с ролью '{role}' успешно создан!")
        
    except mysql.connector.Error as err:
        print(f"❌ Ошибка базы данных: {err}")

if __name__ == "__main__":
    add_user()
