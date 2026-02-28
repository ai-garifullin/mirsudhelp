import streamlit as st
import hashlib
import json
import os
import time
from dotenv import load_dotenv
from streamlit_cookies_manager import EncryptedCookieManager

from db_utils import * 
from main_view import render_main_view
from views import render_detail_view

load_dotenv()

# --- 2. НАСТРОЙКИ ---
st.set_page_config(page_title="Service Desk Mirsud", layout="wide")

# Инициализация менеджера Cookies
cookie_password = os.getenv('cookie_encryption_key')
cookies = EncryptedCookieManager(
    prefix="mirsud_app_",
    password=cookie_password
)
if not cookies.ready():
    st.stop()

# Конфигурация Magic Keys (Токен в URL : Логин в БД)
magic_keys_raw = os.getenv('MAGIC_KEYS_JSON', '{}')
try:
    MAGIC_KEYS = json.loads(magic_keys_raw)
except json.JSONDecodeError:
    st.error("Ошибка: Неверный формат MAGIC_KEYS_JSON в файле .env")
    MAGIC_KEYS = {}
    
# --- 3. ФУНКЦИЯ ПРОВЕРКИ ЛОГИНА ---
def check_login():
    """Управляет входом: Magic Link -> Cookies -> Session -> Form"""
    
    # 1. Проверка Magic Link в URL (Приоритет для iOS)
    query_params = st.query_params
    auth_token = query_params.get("auth")

    if auth_token in MAGIC_KEYS and not st.session_state.get("logged_in"):
        target_login = MAGIC_KEYS[auth_token]
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT login, role FROM system_users WHERE login = %s", (target_login,))
            user_db = cursor.fetchone()
            conn.close()
            
            if user_db:
                # Авторизуем
                st.session_state["logged_in"] = True
                st.session_state["user_login"] = user_db['login']
                st.session_state["user_role"] = user_db['role']
                
                # Сохраняем куку на будущее (для Windows/Android)
                cookie_value = json.dumps({'login': user_db['login']})
                cookies['auth_token'] = cookie_value
                cookies.save()
                
                log_action(user_db['login'], 'LOGIN_MAGIC', 'Вход по ссылке')
                # Удаляем auth из URL, чтобы ссылка стала "чистой"
                del st.query_params["auth"]
                st.rerun()

    # 2. Восстановление из Cookie
    auth_token_json = cookies.get("auth_token")
    if auth_token_json and not st.session_state.get("logged_in"):
        try:
            user_data = json.loads(auth_token_json)
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_data['login']
        except:
            if 'auth_token' in cookies:
                del cookies['auth_token']
                cookies.save()

    # 3. Проверка актуальности (если залогинен через Cookie или Magic)
    if st.session_state.get("logged_in"):
        login = st.session_state.get("user_login")
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role FROM system_users WHERE login = %s", (login,))
            user_in_db = cursor.fetchone()
            conn.close()
            
            if user_in_db:
                st.session_state["user_role"] = user_in_db['role']
                return True
            else:
                st.session_state["logged_in"] = False
                if 'auth_token' in cookies:
                    del cookies['auth_token']
                    cookies.save()
                st.error("Аккаунт заблокирован или удален.")
    
    # 4. Форма входа (Резерв)
    with st.form("login_form"):
        st.header("Вход в Service Desk")
        login_input = st.text_input("Логин")
        password_input = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")

        if submitted:
            conn = get_db_connection()
            if not conn: return False
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM system_users WHERE login = %s", (login_input,))
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data:
                pwd_hash = hashlib.sha256(password_input.encode()).hexdigest()
                if user_data['password_hash'] == pwd_hash:
                    st.session_state["logged_in"] = True
                    st.session_state["user_login"] = user_data['login']
                    st.session_state["user_role"] = user_data['role']
                    
                    cookie_value = json.dumps({'login': user_data['login']})
                    cookies['auth_token'] = cookie_value
                    cookies.save()
                    
                    log_action(user_data['login'], 'LOGIN', 'Ручной вход')
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Неверный пароль")
            else:
                st.error("Пользователь не найден")
    return False

# --- 4. ЗАПУСК ПРИЛОЖЕНИЯ ---
if check_login():
    if not cookies.ready():
        st.stop()
        
    with st.sidebar:
        st.success(f"Вы вошли как: **{st.session_state.get('user_login')}**")
        st.info(f"Ваша роль: **{st.session_state.get('user_role')}**")
        
        if st.button("Выйти из системы"):
            st.session_state.clear()
            st.query_params.clear()
            # Очистка кук через JS (надежно для всех браузеров)
            js_logout = """
                <script>
                    document.cookie.split(";").forEach(function(c) { 
                        document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
                    });
                    window.location.reload();
                </script>
            """
            st.components.v1.html(js_logout)
            st.stop()
    
    # Роутер заявок
    if 'selected_request_id' not in st.session_state:
        st.session_state.selected_request_id = None

    if "id" in st.query_params:
        url_id = st.query_params["id"]
        if url_id.isdigit():
            st.session_state.selected_request_id = int(url_id)

    if st.session_state.selected_request_id is None:
        if "id" in st.query_params:
            del st.query_params["id"]
        render_main_view()
    else:
        st.query_params["id"] = st.session_state.selected_request_id
        render_detail_view(st.session_state.selected_request_id)