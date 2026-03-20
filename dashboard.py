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

# --- 1. ЗАГРУЗКА НАСТРОЕК ---
load_dotenv()
st.set_page_config(page_title="Service Desk Mirsud", layout="wide")
import streamlit.components.v1 as components

# Вставляем JS, который достанет куки и передаст их Streamlit
components.html(
    """
    <script>
        // Получаем все куки
        var cookies = document.cookie;
        // Отправляем их в Streamlit через postMessage
        window.parent.postMessage({type: 'streamlit:setComponentValue', key: 'js_cookies', value: cookies}, '*');
    </script>
    """, height=0
)
# Инициализация кук
cookie_password = os.getenv('cookie_encryption_key')
cookies = EncryptedCookieManager(
    prefix="mirsud_app_",
    password=cookie_password
)
if not cookies.ready():
    st.stop()

# Загрузка Magic Keys из .env (JSON формат)
magic_keys_raw = os.getenv('MAGIC_KEYS_JSON', '{}')
try:
    MAGIC_KEYS = json.loads(magic_keys_raw)
except json.JSONDecodeError:
    st.error("Ошибка .env: Неверный формат MAGIC_KEYS_JSON")
    MAGIC_KEYS = {}

# --- 2. ФУНКЦИЯ ПРОВЕРКИ ЛОГИНА ---
def check_login():
    # А. Обработка Magic Link
    current_params = st.query_params
    auth_token = current_params.get("auth")

    if auth_token in MAGIC_KEYS and not st.session_state.get("logged_in"):
        target_login = MAGIC_KEYS[auth_token]
        
        # ИСПОЛЬЗУЕМ ФУНКЦИЮ ИЗ DB_UTILS
        user_db = get_user_by_login(target_login)
            
        if user_db:
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_db['login']
            st.session_state["user_role"] = user_db['role']
            
            cookies['auth_token'] = json.dumps({'login': user_db['login']})
            cookies.save()
            
            log_action(user_db['login'], 'LOGIN_MAGIC', 'Вход по Magic Link')
            
            del st.query_params["auth"]
            st.rerun()

    # Б. Проверка Кук (логика без изменений)
    auth_token_json = cookies.get("auth_token")
    if auth_token_json and not st.session_state.get("logged_in"):
        try:
            user_data = json.loads(auth_token_json)
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_data['login']
            st.rerun() 
        except Exception as e:
            if 'auth_token' in cookies:
                del cookies['auth_token']
                cookies.save()

    # В. Проверка активной сессии
    if st.session_state.get("logged_in"):
        login = st.session_state.get("user_login")
        
        # ИСПОЛЬЗУЕМ ФУНКЦИЮ ИЗ DB_UTILS
        role = get_user_role(login)
        
        if role:
            st.session_state["user_role"] = role
            return True
        else:
            st.session_state["logged_in"] = False
            st.error("Доступ запрещен или аккаунт удален.")
    
    # Г. Форма входа
    with st.form("login_form"):
        st.header("Вход в Service Desk")
        login_input = st.text_input("Логин")
        password_input = st.text_input("Пароль", type="password")
        
        if st.form_submit_button("Войти"):
            # ИСПОЛЬЗУЕМ ФУНКЦИЮ ИЗ DB_UTILS
            user_data = verify_user_credentials(login_input, password_input)
            
            if user_data:
                st.session_state["logged_in"] = True
                st.session_state["user_login"] = user_data['login']
                st.session_state["user_role"] = user_data['role']
                
                cookies['auth_token'] = json.dumps({'login': user_data['login']})
                cookies.save()
                
                log_action(user_data['login'], 'LOGIN', 'Ручной вход')
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
    return False

# --- 3. ГЛАВНЫЙ ЦИКЛ ПРИЛОЖЕНИЯ ---
if check_login():
    
    # Дебаг-блок для мониторинга iOS
    if 'debug_cookies' not in st.session_state:
        st.session_state.debug_cookies = True

    # Вывод статуса кук для отладки
    if st.session_state.debug_cookies:
        st.sidebar.warning(f"Cookies ready: {cookies.ready()}")
        st.sidebar.info(f"Auth token exists: {'auth_token' in cookies}")
    # Проверка готовности менеджера кук после авторизации
    if not cookies.ready():
        st.stop()
        
    with st.sidebar:
        st.success(f"Логин: **{st.session_state.get('user_login')}**")
        st.info(f"Роль: **{st.session_state.get('user_role')}**")
        
        if st.button("Выйти из системы"):
            # 1. Удаляем из session_state
            st.session_state.clear()
            st.query_params.clear()
            
            # 2. Удаляем из менеджера
            if 'auth_token' in cookies:
                del cookies['auth_token']
                cookies.save()
            
            # 3. Точечный JS (только для нашей куки, без перебора всего браузера)
            # Замените 'mirsud_app_auth_token' на точное имя куки, 
            # которое вы видите в инспекторе браузера (вкладка Application -> Cookies)
            js_logout = """
                <script>
                    document.cookie = "mirsud_app_auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                    window.location.reload();
                </script>
            """
            st.components.v1.html(js_logout, height=0)
            st.stop()

    # --- РОУТЕР (Управление отображением) ---
    # Получаем актуальный ID из URL
    url_params = st.query_params
    url_id = url_params.get("id")

    if url_id and url_id.isdigit():
        # Режим просмотра конкретной заявки
        current_id = int(url_id)
        st.session_state.selected_request_id = current_id # Синхронизируем стейт
        render_detail_view(current_id)
    else:
        # Главная страница (список заявок)
        st.session_state.selected_request_id = None
        render_main_view()