import streamlit as st
import time
from datetime import datetime
from db_utils import * 
import io
import pandas as pd

def render_main_view():
   
    st.markdown("""
        <style>
        /* 1. Общие отступы страницы */
        .block-container { padding-top: 2rem !important; }
        h1 { padding-top: 0px !important; margin-top: 0px !important; margin-bottom: 0.5rem !important; }
        [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
        
        /* 2. Высота кнопок */
        .stButton > button, .stDownloadButton > button, .stLinkButton > a {
            height: 38px !important;
            display: flex !important;
            align-items: center !important;
        }

        /* 3. МОБИЛЬНАЯ ВЕРСТКА */
        @media (max-width: 640px) {
            /* Принудительная сетка для фильтров */
            .mobile-flex [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: repeat(4, 1fr) !important;
                gap: 5px !important;
            }
            /* Адрес и Исполнитель - на всю ширину (занимают 4 ячейки из 4) */
            .mobile-flex [data-testid="column"]:nth-child(1),
            .mobile-flex [data-testid="column"]:nth-child(2) {
                grid-column: span 4 !important;
            }
            /* Вид работ и Статус - в одну строку (занимают по 2 ячейки из 4) */
            .mobile-flex [data-testid="column"]:nth-child(3),
            .mobile-flex [data-testid="column"]:nth-child(4) {
                grid-column: span 2 !important;
            }

            /* Кнопки в одну строку */
            .button-row [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: 1fr 2fr 1fr 1fr !important;
                gap: 5px !important;
            }
            /* Скрываем ненужный spacer */
            .button-row [data-testid="column"]:nth-child(5) { display: none !important; }
        }
        </style>
    """, unsafe_allow_html=True)

    # --- ЗАГОЛОВОК ---
    st.title("Service Desk Mirsud")

    # 1. ЗАГРУЗКА СПРАВОЧНИКОВ (логика остается прежней)
    executors_map = get_lookup_options("executor", "Executor_ID", "Full_Name")
    types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")

    conn = get_db_connection()
    if conn:
        all_addresses = pd.read_sql("SELECT Address_Name FROM locations ORDER BY Address_Name", conn)['Address_Name'].tolist()
        conn.close()
    else:
        all_addresses = []

    # --- БЛОК ФИЛЬТРОВ ---
    st.markdown('<div class="mobile-flex">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([2.5, 1.5, 1.5, 1.5])

    with col1:
        f_addr = st.multiselect("📍 Адрес:", options=all_addresses, placeholder="Выберите адрес")
    with col2:
        f_exec = st.multiselect("👤 Исполнитель:", options=list(executors_map.keys()), placeholder="Выберите")
    with col3:
        f_service = st.multiselect("🛠 Вид работ:", options=["Удаленно", "Выезд"], placeholder="Выберите")
    with col4:
        f_status = st.multiselect("Статус:", options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], placeholder="Выберите")
    st.markdown('</div>', unsafe_allow_html=True)

    # Уменьшенный разделитель
    st.markdown("<hr style='margin: 1em 0;'>", unsafe_allow_html=True)

    # --- ПОЛУЧЕНИЕ ДАННЫХ ---
    active_filters = {'address': f_addr, 'executor': f_exec, 'service_type': f_service, 'status': f_status}
    data = fetch_main_data(active_filters)

    if data.empty:
        st.warning("Заявки не найдены")
        st.link_button("➕ Создать", "https://mirsudhelp.ru", use_container_width=True)
    else:
        def to_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            return output.getvalue()

        # --- КНОПКИ (Excel, ID, Открыть, Создать) ---
        st.markdown('<div class="button-row">', unsafe_allow_html=True)
        # Используем параметр vertical_alignment для точного выравнивания по нижней линии
        col_excel, col5, col6, col7, spacer = st.columns([1, 2, 1, 1.2, 9], gap="small", vertical_alignment="bottom")

        with col_excel:
            st.download_button(
                label="📥 Excel",
                data=to_excel(data),
                file_name=f'report_{datetime.now().strftime("%d_%m")}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        with col5:
            quick_id = st.text_input("ID", placeholder="Введите ID", label_visibility="collapsed")

        with col6:
            if st.button("Открыть", use_container_width=True) and quick_id:
                if quick_id.isdigit():
                    st.query_params["id"] = quick_id
                    st.rerun()

        with col7:
            st.link_button("➕ Создать", "https://mirsudhelp.ru", use_container_width=True)

        with spacer:
            st.empty()
        st.markdown('</div>', unsafe_allow_html=True)
        

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
            "Вид работ": st.column_config.SelectboxColumn(options=["Удаленно", "Выезд", "Дубль"], width="small"),
            "Тип": st.column_config.SelectboxColumn(options=list(types_map.keys()), width="medium"),
            "Описание": st.column_config.TextColumn(width="large"),
            "Адрес": st.column_config.TextColumn(width="medium"),
            "Район": st.column_config.TextColumn(disabled=True),
            "Уч.": st.column_config.NumberColumn(width=40),
            "Закрыта": st.column_config.TextColumn(width="small"),
        }
    )