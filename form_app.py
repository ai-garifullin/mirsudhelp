import streamlit as st
import os
import time
from db_utils import get_lookup_options, get_db_connection, add_request_message, verify_user_credentials
from dotenv import load_dotenv
import json
load_dotenv()
# --- 3. ИНТЕРФЕЙС ---
st.markdown("""
        <style>
            #root > div:nth-child(1) > div > div > div > div > section > div {
                padding-top: 0rem !important;
                padding-bottom: 0rem !important;
            }
            .stAppHeader {
                display: none !important;
            }
            h1 {
                margin-top: 0px !important;
                padding-top: 0 !important;
            }   
        </style>
    """, unsafe_allow_html=True)

if "show_expert_system" not in st.session_state:
    st.session_state.show_expert_system = False

def load_kb():
    with open("knowledge_base.json", "r", encoding="utf-8") as f:
        return json.load(f)

def run_expert_system():
    st.title("🛠 Экспертная система тех. поддержки Мировых Судей РТ")
    
    # Сетка для кнопок управления
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("⬅️ Назад"):
            # Проверяем, есть ли куда возвращаться
            if 'history' in st.session_state and st.session_state.history:
                st.session_state.current_node = st.session_state.history.pop()
                st.rerun()
            else:
                st.warning("Вы в самом начале.")

    with col2:
        if st.button("🏠 В главное меню"):
            st.session_state.show_expert_system = False
            # При выходе в меню стоит очистить историю
            st.session_state.history = []
            st.session_state.current_node = 'start'
            st.rerun()

    st.info("Ответьте на вопросы, чтобы получить рекомендацию по устранению проблемы.")

    kb = load_kb()
    
    # Инициализация состояния сессии
    if 'current_node' not in st.session_state:
        st.session_state.current_node = 'start'
    
    # Инициализация истории (стека)
    if 'history' not in st.session_state:
        st.session_state.history = []
    
    node = kb.get(st.session_state.current_node)

    # Если это узел с решением (финал)
    if "solution" in node:
        st.success("### Рекомендация:")
        st.write(node["solution"])
        if "image" in node:
            st.image(node["image"], use_container_width=True)

        if st.button("🔄 Начать сначала"):
            st.session_state.current_node = 'start'
            st.session_state.history = [] # Очищаем историю при сбросе
            st.rerun()
            
    # Если это узел с вопросом (выбор)
    else:
        st.write(f"### {node['question']}")
        
        # Создаем кнопки для каждого варианта ответа
        for option_text, next_node in node["options"].items():
            if st.button(option_text):
                # ПЕРЕД переходом сохраняем текущий узел в историю
                st.session_state.history.append(st.session_state.current_node)
                st.session_state.current_node = next_node
                st.rerun()

    # Боковая панель
    with st.sidebar:
        st.header("Полезные контакты")
        st.write("📞 Телефон тех. поддержки: + 7(843)296-02-17")
        st.write("✉️ Эл. почта: ask@mirsudhelp.ru")
# --- 2. ЛОКАЛЬНЫЕ ФУНКЦИИ ---

def find_section_id(district_id, section_number):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    sql = "SELECT Section_ID FROM court_section WHERE District_ID = %s AND Section_Number = %s"
    cursor.execute(sql, (district_id, section_number))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def create_request(data):
    """Создает заявку и возвращает ее ID."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT User_ID FROM user WHERE Full_Name = %s", (data['user_fullname'],))
        res = cursor.fetchone()
        user_id = res[0] if res else cursor.execute("INSERT INTO user (Full_Name) VALUES (%s)", (data['user_fullname'],)) or cursor.lastrowid

        full_description = f"{data['description']}\n\n--- Контакт для связи ---\nТелефон: {data['phone']}"
        
        sql = """INSERT INTO request (Description, User_ID, Court_Section_ID, Request_Type_ID, Status)
                VALUES (%s, %s, %s, %s, '🔴 Новая')"""
        cursor.execute(sql, (full_description, user_id, data['section_id'], data['request_type_id']))
        request_id = cursor.lastrowid
        conn.commit()

        if uploaded_file and request_id:
            os.makedirs("attachments", exist_ok=True)
            file_path = os.path.join("attachments", f"web_{int(time.time())}_{uploaded_file.name}")
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Записываем файл в таблицу сообщений
            add_request_message(conn, request_id, 'Client', "Вложение к новой заявке", 'Portal', file_path)
        return request_id
    except Exception as e:
        print(f"Ошибка создания заявки: {e}")
        return None
    finally:
        conn.close()

def load_info():
    if os.path.exists("info.json"):
        with open("info.json", "r", encoding="utf-8") as f:
            return json.load(f).get("info_text", "")
    return "Текст не найден"

def save_info(new_text):
    with open("info.json", "w", encoding="utf-8") as f:
        json.dump({"info_text": new_text}, f, ensure_ascii=False, indent=4)

CONFIG_FILE = "info.json"

def load_main_info():
    # Пытаемся прочитать из файла
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("info_text", "Текст не задан")
        except Exception as e:
            return f"Ошибка чтения конфига: {e}"
    
    # Если файла нет, возвращаем стандартный текст (тот, что был в коде)
    return """**Информация**
    Заявки по технической поддержке инфраструктуры Мировых судей РТ принимаются..."""

def save_main_info(new_text):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"info_text": new_text}, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        st.error(f"Ошибка записи: {e}")
        return False

if st.session_state.show_expert_system:
    # Если кнопка была нажата, запускаем только функцию
    run_expert_system()
else:

    st.set_page_config(page_title="Новая заявка", layout="centered")
    st.title("📝 Форма создания заявки")
    if st.button("Часто возникающие проблемы", use_container_width=True, type="primary"):
        st.session_state.show_expert_system = True
        st.rerun()
    else:
        if st.query_params.get("admin") == "true":
            with st.expander("🔐 Режим редактирования", expanded=not st.session_state.get("admin_logged_in")):
                if not st.session_state.get("admin_logged_in"):
                    login_inp = st.text_input("Логин")
                    pass_inp = st.text_input("Пароль", type="password")
                    
                    if st.button("Войти в админку"):
                        # Используем вашу функцию из db_utils
                        user_data = verify_user_credentials(login_inp, pass_inp)
                        if user_data:
                            st.session_state["admin_logged_in"] = True
                            st.rerun()
                        else:
                            st.error("Неверные данные")
                else:
                    # Интерфейс правки
                    current_txt = load_main_info()
                    new_txt = st.text_area("Текст на главной:", value=current_txt, height=300)
                    if st.button("Сохранить"):
                        if save_main_info(new_txt):
                            st.success("Сохранено!")
                            time.sleep(1)
                            st.rerun()

        # 2. Обычный вывод текста
        st.info(load_main_info())


        st.write("Пожалуйста, заполните все поля для регистрации вашего обращения.")

        districts_map = get_lookup_options("district", "District_ID", "District_Name")
        district_names = [""] + list(districts_map.keys())
        types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
        types_map = {name: id for name, id in types_map.items() if id not in [17, 18, 19, 20]}
        type_names = [""] + list(types_map.keys())

        # Инициализация ключей сессии для очистки (если их нет)
        keys_to_clear = ["f_name", "f_phone", "f_dist", "f_sec", "f_type", "f_desc"]
        for k in keys_to_clear:
            if k not in st.session_state:
                st.session_state[k] = None # Или начальные значения

        with st.form("new_request_form", clear_on_submit=True): # clear_on_submit очищает некоторые поля, но не все надежно
            
            st.subheader("1. Информация о заявителе")
            # Добавляем key для каждого поля
            user_fullname = st.text_input("Ваши ФИО и должность:", placeholder="Иванов Иван Иванович, секретарь", key="f_name")
            phone = st.text_input("Ваш контактный телефон:", placeholder="+7 (900) 123-45-67", key="f_phone")

            st.divider()

            st.subheader("2. Местоположение")
            col1, col2 = st.columns(2)
            with col1:
                selected_district_name = st.selectbox("Район:", options=district_names, placeholder='Выбрать из списка', key="f_dist")
            with col2:
                section_number = st.number_input("Номер участка:", min_value=1, step=1, key="f_sec")
                
            st.divider()

            st.subheader("3. Суть проблемы")
            selected_type_name = st.selectbox("Тип заявки:", options=type_names, placeholder='Выбрать из списка', key="f_type")
            description = st.text_area("Подробное описание проблемы:", height=150, key="f_desc")
            
            uploaded_file = st.file_uploader("Прикрепить скриншот или документ (необязательно):", 
                                            type=['png', 'jpg', 'jpeg', 'pdf', 'zip'], 
                                            key="f_file")
            submit_button = st.form_submit_button("🚀 Отправить заявку", type="primary")

        if submit_button:
            if uploaded_file:
                st.write(f"Файл получен: {uploaded_file.name}, размер: {uploaded_file.size}")
            if not all([user_fullname, phone, selected_district_name, section_number, selected_type_name, description]):
                st.error("❌ Пожалуйста, заполните все поля.")
            else:
                district_id = districts_map.get(selected_district_name)
                request_type_id = types_map.get(selected_type_name)
                section_id = find_section_id(district_id, section_number)
                
                if not section_id:
                    st.error(f"❌ Ошибка: Судебный участок №{section_number} не найден в районе '{selected_district_name}'.")
                else:
                    request_data = {
                        'user_fullname': user_fullname,
                        'phone': phone,
                        'section_id': section_id,
                        'request_type_id': request_type_id,
                        'description': description
                    }
                    
                    new_id = create_request(request_data)
                    
                    if new_id:
                        st.success(f"✅ Заявка №{new_id} успешно зарегистрирована!")
                        st.balloons()
                    else:
                        st.error("Произошла ошибка при сохранении.")