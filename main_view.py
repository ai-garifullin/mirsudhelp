import streamlit as st
import time
from datetime import datetime
from db_utils import * 
import io
import pandas as pd

def render_main_view():
    st.title("Service Desk Mirsud")
    
    # 1. ЗАГРУЗКА СПРАВОЧНИКОВ
    executors_map = get_lookup_options("executor", "Executor_ID", "Full_Name")
    types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
    
    conn = get_db_connection()
    if conn:
        all_addresses = pd.read_sql("SELECT Address_Name FROM locations ORDER BY Address_Name", conn)['Address_Name'].tolist()
        conn.close()
    else:
        all_addresses = []

    # --- БЛОК ФИЛЬТРОВ ---
    col1, col2, col3, col4 = st.columns([2.5, 1.5, 1.5, 1.5])

    with col1:
        f_addr = st.multiselect("📍 Адрес:", options=all_addresses, placeholder="Выберите адрес")
    with col2:
        f_exec = st.multiselect("👤 Исполнитель:", options=list(executors_map.keys()), placeholder="Выберите")
    with col3:
        f_service = st.multiselect("🛠 Вид работ:", options=["Удаленно", "Выезд"], placeholder="Выберите")
    with col4:
        f_status = st.multiselect("Статус:", options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], placeholder="Выберите")
    st.divider() 

    # --- ПОЛУЧЕНИЕ ДАННЫХ ---
    active_filters = {'address': f_addr, 'executor': f_exec, 'service_type': f_service, 'status': f_status}
    data = fetch_main_data(active_filters)
    
    if data.empty:
        st.warning("Заявки не найдены")
        return

    # ЭКСПОРТ В EXCEL
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        return output.getvalue()

    # Добавляем параметр gap="small" для минимизации расстояния
    col_excel, col5, col6, col7, spacer = st.columns([1, 2, 1, 1.2, 9], gap="small")

    with col_excel:
        st.download_button(
            label="📥 Excel", # Немного сократил текст для экономии места
            data=to_excel(data),
            file_name=f'report_{datetime.now().strftime("%d_%m")}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    with col5:
        # label_visibility="collapsed" — это правильно, убирает лишнее место сверху
        quick_id = st.text_input("ID", placeholder="Введите ID", label_visibility="collapsed")

    with col6:
        if st.button("Открыть") and quick_id:
            if quick_id.isdigit():
                st.query_params["id"] = quick_id
                st.rerun()

    with col7:
        st.link_button("➕ Создать", "https://mirsudhelp.ru", use_container_width=True)
        

    # --- ПОДГОТОВКА ТАБЛИЦЫ ---
    # Мы делаем относительную ссылку. В Safari на iOS это сработает как переход внутри сайта.
    data['ID_LINK'] = "/?id=" + data['ID'].astype(str)

    # Выводим таблицу
    st.dataframe(
        data,
        height=600,
        use_container_width=True,
        hide_index=True,
        column_order=("ID_LINK", "Статус", "Дата", "Исполнитель", "Адрес", "Район", "Уч.", "Вид работ", "Тип", "Описание", "Закрыта"),
        column_config={
            "ID_LINK": st.column_config.LinkColumn(
                label="ID",
                display_text=r"id=(\d+)", # Показывает только цифры
                width=60,
            ),
            "Статус": st.column_config.SelectboxColumn(options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], width=110),
            "Дата": st.column_config.TextColumn(width="small"),
            "Исполнитель": st.column_config.SelectboxColumn(options=list(executors_map.keys()), width=120),
            "Вид работ": st.column_config.SelectboxColumn(options=["Удаленно", "Выезд"], width="small"),
            "Тип": st.column_config.SelectboxColumn(options=list(types_map.keys()), width="medium"),
            "Описание": st.column_config.TextColumn(width="large"),
            "Адрес": st.column_config.TextColumn(width="medium"),
            "Район": st.column_config.TextColumn(disabled=True),
            "Уч.": st.column_config.NumberColumn(width=40),
            "Закрыта": st.column_config.TextColumn(width="small"),
        }
    )