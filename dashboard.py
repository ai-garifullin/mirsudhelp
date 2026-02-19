import streamlit as st
import hashlib
import json
from streamlit_cookies_manager import EncryptedCookieManager

from db_utils import * 
from main_view import render_main_view
from views import render_detail_view

import os
from dotenv import load_dotenv
load_dotenv()

# --- 2. НАСТРОЙКИ ---
st.set_page_config(page_title="Service Desk Mirsud", layout="wide")

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
    """Проверяет логин и АКТУАЛЬНОСТЬ пользователя в базе."""
    
    # 1. Сначала пытаемся восстановить данные из Cookie
    auth_token_json = cookies.get("auth_token")
    if auth_token_json and not st.session_state.get("logged_in"):
        try:
            user_data = json.loads(auth_token_json)
            st.session_state["logged_in"] = True
            st.session_state["user_login"] = user_data['login']
            # Роль пока не пишем, возьмем свежую из базы
        except:
            del cookies['auth_token']
            cookies.save()

    # 2. Если пользователь считается "вошедшим" (из cookie или сессии)
    if st.session_state.get("logged_in"):
        login = st.session_state.get("user_login")
        
        # --- ВАЖНАЯ ПРОВЕРКА: СУЩЕСТВУЕТ ЛИ ОН ЕЩЕ? ---
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role FROM system_users WHERE login = %s", (login,))
            user_in_db = cursor.fetchone()
            conn.close()
            
            if user_in_db:
                # Все ок, обновляем роль (вдруг её поменяли)
                st.session_state["user_role"] = user_in_db['role']
                return True
            else:
                # ПОЛЬЗОВАТЕЛЬ УДАЛЕН ИЗ БАЗЫ!
                # Сбрасываем всё и выкидываем его
                st.session_state["logged_in"] = False
                st.session_state["user_login"] = None
                if 'auth_token' in cookies:
                    del cookies['auth_token']
                    cookies.save()
                st.error("Ваша учетная запись была удалена или заблокирована.")
                # st.rerun() не делаем, чтобы показать ошибку
    
    # 3. Если проверки не пройдены - показываем форму входа
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
                
                cookie_value = json.dumps({
                    'login': user_data['login'],
                    # Роль в куки можно не писать, мы её все равно проверяем по базе
                })
                cookies['auth_token'] = cookie_value
                cookies.save()
                
                log_action(user_data['login'], 'LOGIN', 'Успешный вход')
                st.rerun()
            else:
                st.error("Неверный пароль")
    return False


if check_login():
    
    # --- НОВАЯ КНОПКА ВЫХОДА ---
    with st.sidebar:
        st.success(f"Вы вошли как: **{st.session_state.get('user_login')}**")
        st.info(f"Ваша роль: **{st.session_state.get('user_role')}**")
        
        # --- JS-КНОПКА ВЫХОДА ---
        # Мы создаем невидимый контейнер с HTML/JS кодом
        
        if st.button("Выйти из системы"):
            # 1. Удаляем сессию на сервере
            st.session_state.clear()
            
            # 2. Выполняем JS для удаления куки в браузере
            # document.cookie = ... устанавливает срок жизни куки в прошлом, чтобы браузер их удалил
            js_code = """
                <script>
                    function deleteAllCookies() {
                        var cookies = document.cookie.split(";");
                        for (var i = 0; i < cookies.length; i++) {
                            var cookie = cookies[i];
                            var eqPos = cookie.indexOf("=");
                            var name = eqPos > -1 ? cookie.substr(0, eqPos) : cookie;
                            document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT";
                        }
                    }
                    deleteAllCookies();
                    window.location.reload();
                </script>
            """
            # Вставляем JS и он выполняется мгновенно
            st.components.v1.html(js_code)
            st.stop()
    
    # --- "РОУТЕР" (остается без изменений) ---
    # --- ОБНОВЛЕННЫЙ "РОУТЕР" ---
    if 'selected_request_id' not in st.session_state:
        st.session_state.selected_request_id = None

    # 1. Перехватываем ID из прямой ссылки (если есть)
    if "id" in st.query_params:
        url_id = st.query_params["id"]
        if url_id.isdigit():
            st.session_state.selected_request_id = int(url_id)

    # 2. Отрисовка нужного экрана
    if st.session_state.selected_request_id is None:
        # Если заявка не выбрана, на всякий случай подчищаем URL 
        # (чтобы там не висел старый id)
        if "id" in st.query_params:
            del st.query_params["id"]
        
        render_main_view()
    else:
        # Принудительно записываем ID в URL, чтобы пользователь 
        # всегда мог скопировать актуальную ссылку из адресной строки
        st.query_params["id"] = st.session_state.selected_request_id
        
        render_detail_view(st.session_state.selected_request_id)
