import streamlit as st
import os
import time
from db_utils import get_lookup_options, get_db_connection, add_request_message
from dotenv import load_dotenv
import json
load_dotenv()

if "show_expert_system" not in st.session_state:
    st.session_state.show_expert_system = False

def load_kb():
    with open("knowledge_base.json", "r", encoding="utf-8") as f:
        return json.load(f)

def run_expert_system():
    st.title("🛠 Вопросы - ответы")
    if st.button("Назад к главному меню"):
        st.session_state.show_expert_system = False
        st.rerun()
    st.info("Ответьте на вопросы, чтобы получить рекомендацию по устранению проблемы.")

    kb = load_kb()
    
    # Инициализация состояния сессии для отслеживания пути
    if 'current_node' not in st.session_state:
        st.session_state.current_node = 'start'
    
    node = kb.get(st.session_state.current_node)

    # Если это узел с решением (финал)
    if "solution" in node:
        st.success("### Рекомендация:")
        st.write(node["solution"])
        if st.button("Начать сначала"):
            st.session_state.current_node = 'start'
            st.rerun()
            
    # Если это узел с вопросом (выбор)
    else:
        st.write(f"### {node['question']}")
        
        # Создаем кнопки для каждого варианта ответа
        for option_text, next_node in node["options"].items():
            if st.button(option_text):
                st.session_state.current_node = next_node
                st.rerun()

    # Боковая панель с полезными ссылками
    with st.sidebar:
        st.header("Полезные контакты")
        st.write("📞 Внутренний номер: 102")
        st.write("✉️ Эл. почта: support@corp.local")

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


if st.session_state.show_expert_system:
    # Если кнопка была нажата, запускаем только функцию
    run_expert_system()
else:
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

    st.set_page_config(page_title="Новая заявка", layout="centered")
    st.title("📝 Форма создания заявки")
    if st.button("Часто возникающие проблемы", use_container_width=True, type="primary"):
        st.session_state.show_expert_system = True
        st.rerun()
    else:
        st.info("""
        **Информация**

        Заявки по технической поддержке инфраструктуры Мировых судей РТ принимаются с 8:00 до 17:00 по МСК (сб и вс выходной)\n
            - по электронной почте ask@mirsudhelp.ru
            - с помощью формы электронной заявки
            - с помощью telegram-бота @mirsudrt_help_bot (доступен чат с оператором в рабочие часы)
            - по телефону + 7(843)296-02-17\n
        Контактная информация других служб технической поддержки:\n
            ГИСТ РТ: +7(843)264-73-33 (Если не работает интернет во всем здании)\n
            КРОК: +7(800)200-22-74, e-mail Sd-pkmir@croc.ru (Если ПК МС запускается без ошибок, но происходят внутренние ошибки, не связанные с ЭЦП)\n
            По вопросам ПТК ВИВ + 7(843)222-60-58 - Отдел правовой информатизации и компьютерных систем Минюст РТ\n
        """)


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