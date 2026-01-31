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
        # Поле для ввода ID. label=" " делает его почти невидимым, но надпись будет слева
        search_id = st.number_input("ID заявки:", min_value=1, step=1, value=None)
    with col5:
  
        # Мы добавляем невидимый отступ сверху, равный высоте подписи к полю (label)
        st.markdown("""
            <style>
                div[data-testid="stVerticalBlock"] div[data-testid="stButton"] {
                    margin-top: 12px;
                }
            </style>
        """, unsafe_allow_html=True)

        if st.button("▶️ Открыть"):
            if search_id:
                st.session_state.selected_request_id = search_id
                st.rerun()
            else:
                st.warning("Введите ID.")

    with col6:
        st.write("") 
        st.write("")
        show_completed_only = st.checkbox("Архив", value=False)

    st.divider() # Разделитель под фильтрами
    # --- КОНЕЦ НОВОЙ ПАНЕЛИ ---

    active_filters = {'address': f_addr, 'executor': f_exec, 'service_type': f_service, 'status': show_completed_only}
    
    data = fetch_main_data(active_filters)
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        return output.getvalue()

    excel_data = to_excel(data)

    st.download_button(
        label="📥 Скачать отчет в Excel",
        data=excel_data,
        file_name='report.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    
    # Определяем, заблокирована ли таблица
    is_table_disabled = show_completed_only
    is_admin = st.session_state["user_role"] == 'admin'
    if not is_admin:
        is_table_disabled = True
    # ТАБЛИЦА
    with st.form("main_form"):
        edited_df = st.data_editor(
            data, key="editor",
            height=600,
            use_container_width=True,
            hide_index=True,
            disabled=is_table_disabled,
            column_order=("ID", "Статус", "Дата", "Исполнитель", "Адрес", "Район", "Уч.", "Вид работ", "Тип", "Описание", "Закрыта"),
            column_config={
                "ID": st.column_config.NumberColumn(width=50, disabled=True),
                "Статус": st.column_config.SelectboxColumn(options=["🔴 Новая", "⚙️ В работе", "✅ Выполнена"], required=True, width=110),
                "Дата": st.column_config.TextColumn(width="small", disabled=True),
                "Исполнитель": st.column_config.SelectboxColumn(options=list(executors_map.keys()), width=120),
                "Вид работ": st.column_config.SelectboxColumn(options=["Удаленно", "Выезд"], required=True, width="small"),
                "Тип": st.column_config.SelectboxColumn(options=list(types_map.keys()), width="medium"),
                "Описание": st.column_config.TextColumn(width="large"),
                "Адрес": st.column_config.TextColumn(width="medium", disabled=True),
                "Район": st.column_config.TextColumn(disabled=True),
                "Уч.": st.column_config.NumberColumn(width=40, disabled=True),
                "Закрыта":st.column_config.TextColumn(width="small", disabled=True),
            }
        )
        submit_button = st.form_submit_button("💾 Сохранить изменения в таблице", type="primary", disabled=is_table_disabled)

    # СОХРАНЕНИЕ
        # СОХРАНЕНИЕ
    if submit_button:
        has_changes = False
        current_user = st.session_state.get("user_login", "Unknown") # Получаем логин
        
        for i in range(len(edited_df)):
            new_row = edited_df.iloc[i]
            req_id = new_row['ID']
            # Находим эту же заявку в исходных данных
            old_row = data[data['ID'] == req_id].iloc[0]
            
            # --- 1. СТАТУС ---
            if new_row['Статус'] != old_row['Статус']:
                has_changes = True
                val = new_row['Статус']
                update_db_field(req_id, "Status", val)
                log_action(current_user, "UPDATE", f"Заявка #{req_id}: Статус изменен на '{val}'")
                
                if val == "✅ Выполнена": update_closed_date(req_id, True)
                else: update_closed_date(req_id, False)

            # --- 2. ИСПОЛНИТЕЛЬ ---
            if new_row['Исполнитель'] != old_row['Исполнитель']:
                has_changes = True
                new_exec = new_row['Исполнитель']
                update_db_field(req_id, "Assigned_Executor_ID", executors_map.get(new_exec))
                log_action(current_user, "UPDATE", f"Заявка #{req_id}: Исполнитель изменен на '{new_exec or 'Никто'}'")

            # --- 3. ВИД РАБОТ ---
            if new_row['Вид работ'] != old_row['Вид работ']:
                has_changes = True
                update_db_field(req_id, "Service_Type", new_row['Вид работ'])
                # Вид работ меняется часто, можно не логировать или логировать по желанию

            # --- 4. ТИП ---
            if new_row['Тип'] != old_row['Тип']:
                has_changes = True
                update_db_field(req_id, "Request_Type_ID", types_map.get(new_row['Тип']))
                log_action(current_user, "UPDATE", f"Заявка #{req_id}: Тип изменен на '{new_row['Тип']}'")

            # --- 5. ОПИСАНИЕ (Осторожно, может быть много текста) ---
            if new_row['Описание'] != old_row['Описание']:
                has_changes = True
                update_db_field(req_id, "Description", new_row['Описание'])
                log_action(current_user, "UPDATE", f"Заявка #{req_id}: Отредактировано описание")

            # --- 6. РЕЗУЛЬТАТ ---
            if 'Результат' in new_row and new_row['Результат'] != old_row.get('Результат'):
                has_changes = True
                update_db_field(req_id, "Result", new_row['Результат'])
                log_action(current_user, "UPDATE", f"Заявка #{req_id}: Обновлен результат")

            # --- 7. ГСМ И ВРЕМЯ ---
            # Здесь можно не логировать каждое изменение цифры, чтобы не засорять лог, 
            # или логировать только факт изменения "Затрат"
            
            # (Код сохранения ГСМ без изменений)
            if new_row.get('Минут') != old_row.get('Минут'):
                has_changes = True
                update_db_field(req_id, "Time_Spent", new_row['Минут'])
            
            if new_row.get('Пробег') != old_row.get('Пробег'):
                has_changes = True
                update_fuel_record(req_id, "Mileage", new_row['Пробег'])
            
            if new_row.get('Расход') != old_row.get('Расход'):
                has_changes = True
                update_fuel_record(req_id, "Fuel_Consumption", new_row['Расход'])
                
            if new_row.get('Цена') != old_row.get('Цена'):
                has_changes = True
                update_fuel_record(req_id, "Fuel_Price", new_row['Цена'])

        if has_changes:
            st.toast("✅ Успешно сохранено!")
            time.sleep(1)
            st.rerun()
        else:
            st.info("Вы ничего не изменили.")
