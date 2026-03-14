import streamlit as st
import time
from datetime import datetime
from db_utils import * 
import io
import pandas as pd

def render_main_view():
   
    st.markdown("""
        <style>
        /* 1. Общие стили (БЕЗ использования широких селекторов) */
        .block-container { padding-top: 2rem !important; }
        h1 { padding-top: 0px !important; margin-top: 0px !important; margin-bottom: 0.5rem !important; }
        
        /* Применяем gap только к вертикальным блокам, чтобы не ломать структуру */
        div.block-container [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
        
        /* Кнопки */
        .stButton > button, .stDownloadButton > button, .stLinkButton > a {
            height: 38px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
        }

        /* 2. МОБИЛЬНАЯ ВЕРСТКА (Только внутри наших классов) */
        @media (max-width: 640px) {
            /* Фильтры: активируются ТОЛЬКО внутри .mobile-flex */
            .mobile-flex [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: repeat(4, 1fr) !important;
                gap: 5px !important;
            }
            .mobile-flex [data-testid="column"]:nth-child(1),
            .mobile-flex [data-testid="column"]:nth-child(2) { grid-column: span 4 !important; }
            .mobile-flex [data-testid="column"]:nth-child(3),
            .mobile-flex [data-testid="column"]:nth-child(4) { grid-column: span 2 !important; }

            /* Кнопки: активируются ТОЛЬКО внутри .button-row */
            .button-row [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: 1fr 2fr 1fr 1fr !important;
                gap: 5px !important;
            }
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
    def update_filters():
        # Сохраняем значения в параметры URL
        st.query_params["addr"] = st.session_state.f_addr
        st.query_params["exec"] = st.session_state.f_exec
        st.query_params["service"] = st.session_state.f_service
        st.query_params["status"] = st.session_state.f_status
        st.markdown('<div class="mobile-flex">', unsafe_allow_html=True)

    params = st.query_params

    st.markdown('<div class="mobile-flex">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([2.5, 1.5, 1.5, 1.5])

    with col1:
        f_addr = st.multiselect("📍 Адрес:", options=all_addresses, 
                                default=params.get_all("addr"), 
                                key="f_addr", on_change=update_filters)
    with col2:
        f_exec = st.multiselect("👤 Исполнитель:", options=list(executors_map.keys()), 
                                default=params.get_all("exec"), 
                                key="f_exec", on_change=update_filters)
    with col3:
        f_service = st.multiselect("🛠 Вид работ:", options=["Удаленно", "Выезд", "Дубль"], 
                                default=params.get_all("service"), 
                                key="f_service", on_change=update_filters)
    with col4:
        f_status = st.multiselect("Статус:", options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], 
                                default=params.get_all("status"), 
                                key="f_status", on_change=update_filters)
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
    #data['ID_LINK'] = "/?id=" + data['ID'].astype(str)

    # Выводим таблицу
    event = st.dataframe(
        data,
        height=600,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_order=("ID", "Статус", "Дата", "Исполнитель", "Адрес", "Район", "Уч.", "Вид работ", "Тип", "Описание", "Закрыта"),
        column_config={
            "ID": st.column_config.NumberColumn(label="ID", width=60),
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
    selected_rows = event.selection.rows
    if event.selection.rows:
        selected_index = event.selection.rows[0]
        selected_id = data.iloc[selected_index]['ID']
    
        # Устанавливаем параметр
        if st.query_params.get("id") != str(selected_id):
            st.query_params["id"] = selected_id
            # ПРИНУДИТЕЛЬНЫЙ ПЕРЕЗАПУСК
            st.rerun()