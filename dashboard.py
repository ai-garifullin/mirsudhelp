import streamlit as st
import json
import os
import time
import streamlit.components.v1 as components
from dotenv import load_dotenv

from db_utils import get_user_by_login, get_user_role, verify_user_credentials, log_action
from main_view import render_main_view
from views import render_detail_view

# --- 1. ЗАГРУЗКА НАСТРОЕК ---
load_dotenv()
st.set_page_config(page_title="Service Desk Mirsud", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

magic_keys_raw = os.getenv('MAGIC_KEYS_JSON', '{}')
try:
    MAGIC_KEYS = json.loads(magic_keys_raw)
except json.JSONDecodeError:
    MAGIC_KEYS = {}

# --- 2. УПРАВЛЕНИЕ КУКИ ЧЕРЕЗ JS (Только запись и удаление) ---
def set_auth_cookie(login_val):
    
    js_code = f"""
        <script>
            var d = new Date();
            d.setTime(d.getTime() + (30*24*60*60*1000)); // 30 дней
            document.cookie = "mirsud_user={login_val}; expires=" + d.toUTCString() + "; path=/;";
        </script>
    """
    components.html(js_code, height=0)

def clear_auth_cookie():
    js_code = """
        <script>
            document.cookie = "mirsud_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        </script>
    """
    components.html(js_code, height=0)

# --- 3. ФУНКЦИЯ ПРОВЕРКИ ЛОГИНА ---
def check_login():
    # А. Проверка активной сессии в памяти Python
    if st.session_state.get("logged_in"):
        role = get_user_role(st.session_state["user_login"])
        if role:
            st.session_state["user_role"] = role
            return True
        else:
            st.session_state["logged_in"] = False
            st.error("Доступ запрещен или аккаунт удален.")
            return False

    # Б. НАТИВНОЕ ЧТЕНИЕ КУКИ (Streamlit 1.38+)
    if hasattr(st, "context") and hasattr(st.context, "cookies"):
        saved_login = st.context.cookies.get("mirsud_user")
        if saved_login:
            user_db = get_user_by_login(saved_login)
            if user_db:
                st.session_state["logged_in"] = True
                st.session_state["user_login"] = user_db['login']
                st.session_state["user_role"] = user_db['role']
                return True # Сразу пускаем внутрь, форма входа даже не мелькнет

    # В. Обработка Magic Link
    auth_token = st.query_params.get("auth")
    if auth_token in MAGIC_KEYS:
        target_login = MAGIC_KEYS[auth_token]
        user_db = get_user_by_login(target_login)
            
        if user_db:
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_db['login']
            st.session_state["user_role"] = user_db['role']
            
            set_auth_cookie(user_db['login'])
            log_action(user_db['login'], 'LOGIN_MAGIC', 'Вход по Magic Link')
            
            del st.query_params["auth"]
            time.sleep(0.5) # Даем браузеру долю секунды на сохранение куки
            st.rerun()

    # Г. Форма входа
    with st.form("login_form"):
        st.header("Вход в Service Desk")
        login_input = st.text_input("Логин")
        password_input = st.text_input("Пароль", type="password")
        
        if st.form_submit_button("Войти"):
            user_data = verify_user_credentials(login_input, password_input)
            
            if user_data:
                st.session_state["logged_in"] = True
                st.session_state["user_login"] = user_data['login']
                st.session_state["user_role"] = user_data['role']
                
                set_auth_cookie(user_data['login'])
                log_action(user_data['login'], 'LOGIN', 'Ручной вход')
                
                time.sleep(0.5) # Ждем запись куки
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
    return False

# --- 4. ГЛАВНЫЙ ЦИКЛ ПРИЛОЖЕНИЯ ---
if check_login():
        
    with st.sidebar:
        st.success(f"Логин: **{st.session_state.get('user_login')}**")
        st.info(f"Роль: **{st.session_state.get('user_role')}**")
        
        if st.button("Выйти из системы"):
            st.session_state.clear()
            st.query_params.clear()
            clear_auth_cookie()
            time.sleep(0.5)
            st.rerun()

    # --- РОУТЕР ---
    url_id = st.query_params.get("id")

    if url_id and url_id.isdigit():
        current_id = int(url_id)
        st.session_state.selected_request_id = current_id
        render_detail_view(current_id)
    else:
        st.session_state.selected_request_id = None
        render_main_view()