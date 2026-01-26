import streamlit as st
from db_utils import get_lookup_options, get_db_connection
from dotenv import load_dotenv

load_dotenv()

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
        return request_id
    except Exception as e:
        print(f"Ошибка создания заявки: {e}")
        return None
    finally:
        conn.close()

# --- 3. ИНТЕРФЕЙС ---

st.set_page_config(page_title="Новая заявка", layout="centered")
st.title("📝 Форма создания заявки")
st.info("""
**Информация**

Заявки по технической поддержке инфраструктуры Мировых судей РТ принимаются: \n
    - по электронной почте ask@mirsudhelp.ru\n
    - с помощью формы электронной заявки\n
    - с помощью telegram-бота @mirsudrt_help_bot
    - по телефону + 7 (843) 296-02-17\n
Контактная информация других служб технической поддержки:\n
    ГИСТ РТ: +7 (843) 264-73-33 (Если не работает интернер во всем здании)\n
    КРОК: +7 (000) 000-00-00 (Если ПК МС запускается без ошибок, но происходят внутренние ошибки, не связанные с ЭЦП)\n
    По вопросам ПТК ВИВ + 7 (843) 222-60-58 - Отдел правовой информатизации и компьютерных систем Минюст РТ\n
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
        selected_district_name = st.selectbox("Район:", options=district_names, key="f_dist")
    with col2:
        section_number = st.number_input("Номер участка:", min_value=1, step=1, key="f_sec")
        
    st.divider()

    st.subheader("3. Суть проблемы")
    selected_type_name = st.selectbox("Тип заявки:", options=type_names, key="f_type")
    description = st.text_area("Подробное описание проблемы:", height=150, key="f_desc")
    
    submit_button = st.form_submit_button("🚀 Отправить заявку", type="primary")

if submit_button:
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
