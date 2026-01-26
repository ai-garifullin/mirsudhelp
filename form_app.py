import streamlit as st

from db_utils import *
from dotenv import load_dotenv
load_dotenv()
# --- 2. ЛОКАЛЬНЫЕ ФУНКЦИИ (только для этой формы) ---

def find_section_id(district_id, section_number):
    """Ищет ID участка по району и номеру."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    sql = "SELECT Section_ID FROM court_section WHERE District_ID = %s AND Section_Number = %s"
    cursor.execute(sql, (district_id, section_number))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def create_request(data):
    """Создает новую заявку в базе данных."""
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    
    try:
        # 1. Найти или создать пользователя
        cursor.execute("SELECT User_ID FROM user WHERE Full_Name = %s", (data['user_fullname'],))
        res = cursor.fetchone()
        user_id = res[0] if res else cursor.execute("INSERT INTO user (Full_Name) VALUES (%s)", (data['user_fullname'],)) or cursor.lastrowid

        # 2. Собрать полное описание
        full_description = f"{data['description']}\n\n--- Контакт для связи ---\nТелефон: {data['phone']}"
        
        # 3. Создать заявку
        sql = """
            INSERT INTO Request (Description, User_ID, Court_Section_ID, Request_Type_ID, Status)
            VALUES (%s, %s, %s, %s, '🔴 Новая')
        """
        cursor.execute(sql, (
            full_description,
            user_id,
            data['section_id'],
            data['request_type_id']
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка создания заявки: {e}")
        return False
    finally:
        conn.close()

# --- 3. ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---

st.set_page_config(page_title="Новая заявка", layout="centered")
st.title("📝 Форма создания заявки")
st.write("Пожалуйста, заполните все поля для регистрации вашего обращения.")

# Загружаем справочники, используя нашу функцию из db_utils
districts_map = get_lookup_options("district", "District_ID", "District_Name")
district_names = [""] + list(districts_map.keys())

types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
types_map = {name: id for name, id in types_map.items() if id not in [17, 18, 19, 20]}
type_names = [""] + list(types_map.keys())

# --- НАЧАЛО ФОРМЫ ---
with st.form("new_request_form"):
    
    st.subheader("1. Информация о заявителе")
    user_fullname = st.text_input("Ваши ФИО и должность:", placeholder="Иванов Иван Иванович, секретарь")
    phone = st.text_input("Ваш контактный телефон:", placeholder="+7 (900) 123-45-67")

    st.divider()

    st.subheader("2. Местоположение")
    col1, col2 = st.columns(2)
    with col1:
        selected_district_name = st.selectbox("Район:", options=district_names)
    with col2:
        section_number = st.number_input("Номер участка:", min_value=1, step=1)
        
    st.divider()

    st.subheader("3. Суть проблемы")
    selected_type_name = st.selectbox("Тип заявки:", options=type_names)
    description = st.text_area("Подробное описание проблемы:", height=150)
    
    # Кнопка отправки
    submit_button = st.form_submit_button("🚀 Отправить заявку", type="primary")

# --- 4. ЛОГИКА ПОСЛЕ НАЖАТИЯ КНОПКИ ---
if submit_button:
    # Простая валидация
    if not all([user_fullname, phone, selected_district_name, section_number, selected_type_name, description]):
        st.error("❌ Пожалуйста, заполните все поля.")
    else:
        # Ищем ID района и типа заявки
        district_id = districts_map.get(selected_district_name)
        request_type_id = types_map.get(selected_type_name)
        
        # Проверяем, существует ли такой участок
        section_id = find_section_id(district_id, section_number)
        
        if not section_id:
            st.error(f"❌ Ошибка: Судебный участок №{section_number} не найден в районе '{selected_district_name}'. Проверьте данные.")
        else:
            # Собираем все данные в один словарь
            request_data = {
                'user_fullname': user_fullname,
                'phone': phone,
                'section_id': section_id,
                'request_type_id': request_type_id,
                'description': description
            }
            
            # Отправляем в базу
            success = create_request(request_data)
            
            if success:
                st.success("✅ Ваша заявка успешно зарегистрирована!")
                st.balloons()
            else:
                st.error("Произошла системная ошибка при сохранении. Пожалуйста, попробуйте позже.")
