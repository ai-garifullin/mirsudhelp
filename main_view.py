import streamlit as st
import time
from datetime import datetime
from db_utils import * 
import io

def render_main_view():
    st.title("Service Desk Mirsud")
    
    executors_map = get_lookup_options("executor", "Executor_ID", "Full_Name")
    types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
    conn = get_db_connection()
    all_addresses = pd.read_sql("SELECT Address_Name FROM locations ORDER BY Address_Name", conn)['Address_Name'].tolist()
    conn.close()

    # Делим строку на 5 колонок с разными пропорциями
    col1, col2, col3, col4, col5, col6 = st.columns([2.5, 1.5, 1.5, 1, 1, 0.5])

    with col1:
        f_addr = st.multiselect("📍 Адрес:", options=all_addresses, placeholder="Выберите адрес")
    with col2:
        f_exec = st.multiselect("👤 Исполнитель:", options=list(executors_map.keys()), placeholder="Выберите")
    with col3:
        f_service = st.multiselect("🛠 Вид работ:", options=["Удаленно", "Выезд"], placeholder="Выберите")
    with col4:
        f_status = st.multiselect("Статус:", options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], placeholder="Выберите")
    with col5:
        st.write("") 
        st.write("") 
        st.link_button("➕ Создать заявку", "https://mirsudhelp.ru")
        
    st.divider() # Разделитель под фильтрами

    active_filters = {'address': f_addr, 'executor': f_exec, 'service_type': f_service, 'status': f_status}
    
    data = fetch_main_data(active_filters)
    
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        return output.getvalue()

    excel_data = to_excel(data)
    st.download_button(
            label="📥 Скачать в Excel", # Укоротил текст для компактности
            data=excel_data,
            file_name='report.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    # ТАБЛИЦА
    data['ID'] = "?id=" + data['ID'].astype(str)
    st.dataframe(
        data,
        height=600,
        use_container_width=True,
        hide_index=True,
        column_order=("ID", "Статус", "Дата", "Исполнитель", "Адрес", "Район", "Уч.", "Вид работ", "Тип", "Описание", "Закрыта"),
        column_config={
            "ID": st.column_config.LinkColumn(
                label="ID",
                display_text=r"\?id=(.*)", # Магия регулярных выражений: показывает только цифры после ?id=
                width=50,
            ),
            "Статус": st.column_config.SelectboxColumn(options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], required=True, width=110),
            "Дата": st.column_config.TextColumn(width="small"),
            "Исполнитель": st.column_config.SelectboxColumn(options=list(executors_map.keys()), width=120),
            "Вид работ": st.column_config.SelectboxColumn(options=["Удаленно", "Выезд"], required=True, width="small"),
            "Тип": st.column_config.SelectboxColumn(options=list(types_map.keys()), width="medium"),
            "Описание": st.column_config.TextColumn(width="large"),
            "Адрес": st.column_config.TextColumn(width="medium"),
            "Район": st.column_config.TextColumn(disabled=True),
            "Уч.": st.column_config.NumberColumn(width=40),
            "Закрыта":st.column_config.TextColumn(width="small"),
        }
    )

    