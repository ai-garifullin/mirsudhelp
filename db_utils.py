import mysql.connector
import pandas as pd
import streamlit as st
import math
import os
import dotenv
dotenv.load_dotenv()
import time


DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')         
DB_PASSWORD = os.getenv('DB_PASSWORD', 'vesna2321') 
DB_NAME = os.getenv('DB_NAME', 'service_desk_db')   
# ------- ФУНКЦИИ РАБОТЫ С ДАННЫМИ ---

def get_db_connection():
    """Пытается подключиться к БД несколько раз перед тем, как сдаться."""
    
    attempts = 5
    for i in range(attempts):
        try:
            # ПОтладка
            # print(f"🔌 ПОПЫТКА ПОДКЛЮЧЕНИЯ: Host={DB_HOST}, User={DB_USER}, DB={DB_NAME}")
            #     # --- ТЕСТ: КУДА МЫ ПОПАЛИ? ---
            # temp_conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
            # temp_cursor = temp_conn.cursor()
            # temp_cursor.execute("SELECT @@hostname;")
            # print(f"🌍 Я ПОПАЛ НА ХОСТ: {temp_cursor.fetchone()[0]}")
            # temp_cursor.execute("SHOW DATABASES;")
            # print(f"📂 БАЗЫ ДАННЫХ ЗДЕСЬ: {[x[0] for x in temp_cursor.fetchall()]}")
            # temp_conn.close()
            # -----------------------------
            conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
            # Если получилось, выходим из функции
            return conn
            
        except mysql.connector.Error as e:
            # Если не получилось, ждем и пробуем снова
            print(f"⚠️ Ошибка подключения к БД (попытка {i+1}/{attempts}): {e}")
            print("Жду 5 секунд перед повторной попыткой...")
            time.sleep(5)
            
    # Если все попытки провалились
    st.error("НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ К БАЗЕ ДАННЫХ ПОСЛЕ НЕСКОЛЬКИХ ПОПЫТОК.")
    return None

def fetch_main_data(filters):
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
        
    base_query = """
    SELECT
        r.Request_ID        AS 'ID',
        r.Date_Received     AS 'Дата',
        
        -- УМНАЯ ЛОГИКА СТАТУСА:
        -- Понимаем и старый текстовый формат, и новый с иконками
        CASE 
            WHEN r.Status IS NULL OR r.Status = '' OR r.Status = 'Новая' THEN '🔴 Новая'
            WHEN r.Status = 'В работе' THEN '⚙️ В работе'
            WHEN r.Status = 'Выполнена' THEN '✅ Выполнена'
            ELSE r.Status -- Если уже с иконкой, оставляем как есть
        END AS 'Статус',
        
        e.Full_Name         AS 'Исполнитель',
        l.Address_Name      AS 'Адрес',
        d.District_Name     AS 'Район',
        cs.Section_Number   AS 'Уч.',
        u.Full_Name         AS 'Заявитель',
        r.Service_Type      AS 'Вид работ',
        rt.Type_Name        AS 'Тип',
        r.Description       AS 'Описание',
        cs.Landline_Phone   AS 'Тел. участка',
        cs.Email            AS 'Email',
        r.Result            AS 'Результат',
        r.Time_Spent        AS 'Минут',
        r.Closed_At         AS 'Закрыта',
        
        COALESCE(dr.Mileage, 0)          AS 'Пробег',
        COALESCE(dr.Fuel_Consumption, 0) AS 'Расход',
        COALESCE(dr.Fuel_Price, 0)       AS 'Цена'
        
    FROM request r
    LEFT JOIN user u ON r.User_ID = u.User_ID
    LEFT JOIN court_section cs ON r.Court_Section_ID = cs.Section_ID
    LEFT JOIN locations l ON cs.Location_ID = l.Location_ID
    LEFT JOIN district d ON cs.District_ID = d.District_ID
    LEFT JOIN request_type rt ON r.Request_Type_ID = rt.Type_ID
    LEFT JOIN executor e ON r.Assigned_Executor_ID = e.Executor_ID
    LEFT JOIN departure_record dr ON r.Request_ID = dr.Request_ID
    """
    
    where_clauses = []
    params = []

    if filters.get('address'):
        where_clauses.append(f"l.Address_Name IN ({','.join(['%s']*len(filters['address']))})")
        params.extend(filters['address'])

    if filters.get('executor'):
        where_clauses.append(f"e.Full_Name IN ({','.join(['%s']*len(filters['executor']))})")
        params.extend(filters['executor'])

    if filters.get('service_type'):
        where_clauses.append(f"r.Service_Type IN ({','.join(['%s']*len(filters['service_type']))})")
        params.extend(filters['service_type'])
    
    # --- НОВЫЙ ФИЛЬТР ПО СТАТУСУ ---
    if filters.get('status'):
        # Если включен режим "только выполненные"
        where_clauses.append("r.Status = '✅ Выполнена'")
    else:
        # Иначе показываем все, кроме выполненных
        where_clauses.append("(r.Status != '✅ Выполнена' OR r.Status IS NULL)")    
        
    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)
        
    base_query += " ORDER BY r.Request_ID DESC;"
    
    df = pd.read_sql(base_query, conn, params=params)
    conn.close()
    
    if not df.empty:
        df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m %H:%M')
        df['Закрыта'] = pd.to_datetime(df['Закрыта']).dt.strftime('%d.%m %H:%M').fillna('')
    return df

def fetch_single_request(request_id):
    conn = get_db_connection()
    if not conn: return None
    query = """
    SELECT
        r.Request_ID, r.Date_Received, r.Status, r.Service_Type, r.Description,
        r.Result, r.Time_Spent, r.Closed_At,
        u.Full_Name AS User_Name, cs.Section_Number, d.District_Name, l.Address_Name,
        cs.Landline_Phone, cs.Email,
        e.Full_Name AS Executor_Name, rt.Type_Name,
        dr.Mileage, dr.Fuel_Consumption, dr.Fuel_Price
    FROM request r
    LEFT JOIN user u ON r.User_ID = u.User_ID
    LEFT JOIN court_section cs ON r.Court_Section_ID = cs.Section_ID
    LEFT JOIN locations l ON cs.Location_ID = l.Location_ID
    LEFT JOIN district d ON cs.District_ID = d.District_ID
    LEFT JOIN request_type rt ON r.Request_Type_ID = rt.Type_ID
    LEFT JOIN executor e ON r.Assigned_Executor_ID = e.Executor_ID
    LEFT JOIN departure_record dr ON r.Request_ID = dr.Request_ID
    WHERE r.Request_ID = %s
    """
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, (int(request_id),))
    data = cursor.fetchone()
    conn.close()
    return data

@st.cache_data
def get_lookup_options(table, key_col, val_col):
    conn = get_db_connection()
    if not conn: return {}
    cols = list(set([key_col, val_col]))
    query = f"SELECT {key_col}, {val_col} FROM {table} ORDER BY {key_col}"
    df = pd.read_sql(query, conn)
    conn.close()
    return pd.Series(df[key_col].values, index=df[val_col].values).to_dict()

def clean_value(val):
    if hasattr(val, 'item'): val = val.item()
    if isinstance(val, float) and math.isnan(val): return None
    return val

def update_db_field(request_id, db_column, new_value):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    sql = f"UPDATE request SET {db_column} = %s WHERE Request_ID = %s"
    cursor.execute(sql, (clean_value(new_value), int(request_id)))
    conn.commit()
    conn.close()

def update_fuel_record(request_id, col_name, value):
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    value = clean_value(value)
    if value is None: value = 0.0
    cursor.execute("SELECT Record_ID FROM departure_record WHERE Request_ID = %s", (int(request_id),))
    if cursor.fetchone():
        sql = f"UPDATE departure_record SET {col_name} = %s WHERE Request_ID = %s"
        cursor.execute(sql, (value, int(request_id)))
    else:
        defaults = {'Mileage': 0, 'Fuel_Price': 0, 'Fuel_Consumption': 0}
        defaults[col_name] = value 
        sql = "INSERT INTO departure_record (Request_ID, Mileage, Fuel_Price, Fuel_Consumption) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (int(request_id), defaults['Mileage'], defaults['Fuel_Price'], defaults['Fuel_Consumption']))
    conn.commit()
    conn.close()

def update_closed_date(request_id, is_closing):

    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    if is_closing: sql = "UPDATE request SET Closed_At = NOW() WHERE Request_ID = %s"
    else: sql = "UPDATE request SET Closed_At = NULL WHERE Request_ID = %s"
    cursor.execute(sql, (int(request_id),))
    conn.commit()
    conn.close()


def add_request_message(conn, request_id, sender_type, message_text, author, attachment_path=None):
    """
    Добавляет сообщение в БД с указанием автора (логина).
    """
    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO request_message (Request_ID, Sender_Type, Author, Message_Text, Created_At, Attachment_Path)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """
        cursor.execute(sql, (request_id, sender_type, author, message_text, attachment_path))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()

def log_action(login, action, details):
    """Записывает действие пользователя в лог."""
    try:
        conn = get_db_connection()
        if not conn: return
        
        cursor = conn.cursor()
        sql = "INSERT INTO action_log (user_login, action_type, details) VALUES (%s, %s, %s)"
        cursor.execute(sql, (login, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        # В реальном приложении здесь лучше писать в отдельный файл логов,
        # чтобы не зациклиться, если сама база упала.
        print(f"!!! ОШИБКА ЛОГИРОВАНИЯ: {e}")
