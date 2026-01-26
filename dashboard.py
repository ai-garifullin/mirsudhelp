import streamlit as st
import hashlib
import json
from streamlit_cookies_manager import EncryptedCookieManager # <--- 1. ДОБАВИТЬ

from db_utils import * 
from main_view import render_main_view
from views import render_detail_view

import os
from dotenv import load_dotenv
load_dotenv()

# --- 2. НАСТРОЙКИ ---
st.set_page_config(page_title="Диспетчер Service Desk", layout="wide")

# Инициализация менеджера Cookies
# Пароль может быть любой секретной строкой, он нужен для шифрования
cookie_password=os.getenv('cookie_encryption_key')
cookies = EncryptedCookieManager(
    prefix="mirsud_app_",
    password=cookie_password
)
if not cookies.ready():
    # Ожидание, пока cookies не будут готовы к использованию
    st.stop()
    st.rerun()

# --- 3. ОБНОВЛЕННАЯ ФУНКЦИЯ ПРОВЕРКИ ЛОГИНА ---
def check_login():
    """Проверяет логин через cookies, а затем через session_state."""
    
    # 1. СНАЧАЛА ПРОВЕРЯЕМ COOKIE
    auth_token_json = cookies.get("auth_token")
    if auth_token_json:
        try:
            # Превращаем строку из cookie обратно в словарь
            user_data = json.loads(auth_token_json)
            # "Запоминаем" пользователя в сессии
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_data['login']
            st.session_state["user_role"] = user_data['role']
            return True
        except:
            # Если cookie "битый" или не парсится, удаляем его
            del cookies['auth_token']
            cookies.save()

    # 2. ЕСЛИ COOKIE НЕТ, ПРОВЕРЯЕМ СЕССИЮ (для первого входа)
    if st.session_state.get("logged_in"):
        return True

    # 3. ЕСЛИ НИЧЕГО НЕ ПОМОГЛО - ПОКАЗЫВАЕМ ФОРМУ ВХОДА
    with st.form("login_form"):
        st.header("Вход в Service Desk")
        login = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")

        if submitted:
            conn = get_db_connection()
            if not conn: return False
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM system_users WHERE login = %s", (login,))
            user_data = cursor.fetchone()
            conn.close()
            
            if not user_data:
                st.error("Пользователь не найден")
                return False

            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if user_data['password_hash'] == password_hash:
                st.session_state["logged_in"] = True
                st.session_state["user_login"] = user_data['login']
                st.session_state["user_role"] = user_data['role']
                
                # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: СОХРАНЯЕМ ДАННЫЕ В COOKIE ---
                cookie_value = json.dumps({
                    'login': user_data['login'],
                    'role': user_data['role']
                })
                # Устанавливаем cookie на 30 дней
                cookies['auth_token'] = cookie_value # <--- ПРАВИЛЬНО
                cookies.save() # Сохраняем изменения
                log_action(user_data['login'], 'LOGIN', 'Успешный вход')
                st.rerun()
            else:
                st.error("Неверный пароль")
    return False

# --- 4. ГЛАВНЫЙ КОД ПРИЛОЖЕНИЯ ---

if check_login():
    
    # --- НОВАЯ КНОПКА ВЫХОДА ---
    with st.sidebar:
        st.success(f"Вы вошли как: **{st.session_state['user_login']}**")
        st.info(f"Ваша роль: **{st.session_state['user_role']}**")
        
        if st.button("Выйти из системы"):
            # Удаляем "запоминание" из сессии
            st.session_state["logged_in"] = False
            # Удаляем cookie
            if 'auth_token' in cookies:
                del cookies['auth_token']
                cookies.save()
            st.rerun() # Перезагружаем, чтобы показать форму входа
    
    # --- "РОУТЕР" (остается без изменений) ---
    if 'selected_request_id' not in st.session_state:
        st.session_state.selected_request_id = None

    if st.session_state.selected_request_id is None:
        render_main_view()
    else:
        render_detail_view(st.session_state.selected_request_id)
