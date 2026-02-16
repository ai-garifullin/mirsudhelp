import streamlit as st
import re
from datetime import datetime
from db_utils import * # Убедитесь, что все нужные функции есть в db_utils.py
from email_monitor import send_email
import time



def render_detail_view(request_id):
    """Рисует страницу-карточку с чатом слева и данными справа."""
    conn = get_db_connection()

    # --- 1. ЗАГРУЗКА ДАННЫХ И КНОПКА "НАЗАД" ---
    data = fetch_single_request(request_id)
    if not data:
        st.error("Заявка не найдена.")
        return
    st.title(f"📝 Заявка №{request_id}, **Адрес:** {data.get('Address_Name', 'Не указан')}")
    
    if st.button("⬅️ Назад к списку"):
        st.session_state.selected_request_id = None
        st.rerun()

    if data['Status'] == '✅ Выполнена':
        is_disabled = True  # Блокируем поля
    else:
        is_disabled = False # Разрешаем редактирование

        # Блокировка полей неадминам
    is_admin = st.session_state["user_role"] == 'admin'
    if not is_admin:
        is_disabled = True

    # Получаем логин текущего пользователя для лога
    current_user = st.session_state.get("user_login", "Unknown")

    # --- 2. ДЕЛИМ ЭКРАН НА ДВЕ КОЛОНКИ ---
    left_col, right_col = st.columns([2, 1])

    # =================================================
    # ЛЕВАЯ КОЛОНКА: ЧАТ И ОТПРАВКА СООБЩЕНИЙ
    # =================================================
    def display_attachment(file_path):
        """Отображает файл в зависимости от типа под спойлером"""
        if file_path and os.path.exists(file_path):
            file_ext = os.path.splitext(file_path)[1].lower()
            file_name = os.path.basename(file_path)
            
            with st.expander("📎 Вложение: " + file_name):
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    st.image(file_path, use_container_width=True)
                else:
                    # Для документов даем ссылку на скачивание
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"Скачать {file_name}",
                            data=f,
                            file_name=file_name,
                            key=file_path # уникальный ключ
                        )
    with left_col:
        st.subheader("✉️ Переписка с заявителем")
        
        # --- CSS СТИЛИ ДЛЯ ЧАТА ---
        st.markdown("""
            <style>
                .chat-container {
                    display: flex;
                    flex-direction: column;
                    gap: 30px;
                    padding: 10px;
                }
                .message-box {
                    padding: 15px;
                    border-radius: 12px;
                    max-width: 90%;
                    word-wrap: break-word;
                    font-size: 15px;
                    line-height: 1.5;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
                    margin-bottom: 20px; /* Отступ СНИЗУ от каждого сообщения */
                }
                /* Стиль для заявителя (Слева, серый) */
                .client-msg {
                    background-color: #f2f3f5;
                    color: #1f1f1f;
                    align-self: flex-start;
                    border-bottom-left-radius: 2px;
                    border: 1px solid #e0e0e0;
                }
                /* Стиль для техподдержки (Справа, зеленый/синий) */
                .support-msg {
                    background-color: #e3f2fd; /* Светло-синий */
                    color: #0d47a1;
                    align-self: flex-end;
                    border-bottom-right-radius: 2px;
                    border: 1px solid #bbdefb;
                }
                /* Стиль для самой первой заявки (Выделяем особо) */
                .initial-msg {
                    background-color: #fff3cd; /* Желтоватый фон */
                    color: #856404;
                    align-self: center;
                    width: 100%;
                    border: 1px solid #ffeeba;
                }
                /* Стиль для внутренних заметок (сотрудники видят, заявитель — нет) */
                .internal-msg {
                    background-color: #b6d7a8; /* Светло-зеленый, как стикер */
                    color: #1f1f1f;
                    align-self: flex-start;
                    border-bottom-left-radius: 2px;
                    border: 1px solid #6aa84f;
                }
                .meta-info {
                    font-size: 12px;
                    color: #6c757d;
                    margin-bottom: 5px;
                    font-weight: bold;
                    display: flex;
                    justify-content: space-between;
                }
            </style>
        """, unsafe_allow_html=True)

        # --- КОНТЕЙНЕР СООБЩЕНИЙ ---
        with st.container(height=600, border=True):
            st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
            
            # 1. ОТРИСОВКА ИСХОДНОЙ ЗАЯВКИ (Из таблицы Request)
            initial_desc = data.get('Description', '').replace('\n', '<br>')
            initial_date = data.get('Date_Received') # Убедитесь, что это поле datetime
            date_str = initial_date.strftime('%d.%m.%Y %H:%M') if initial_date else "Неизвестно"
            
            st.markdown(f"""
                <div class='message-box initial-msg'>
                    <div class='meta-info'>
                        <span>🚀 ИСХОДНАЯ ЗАЯВКА</span>
                        <span>{date_str}</span>
                    </div>
                    {initial_desc}
                </div>
            """, unsafe_allow_html=True)

            # 2. ПОЛУЧЕНИЕ ПЕРЕПИСКИ (Из таблицы request_message)
            # conn должен быть определен выше в вашем коде
            cursor = conn.cursor()
            sql_chat = """
                SELECT Sender_Type, Message_Text, Created_At, Attachment_Path, Author
                FROM request_message 
                WHERE Request_ID = %s 
                ORDER BY Created_At ASC
            """
            cursor.execute(sql_chat, (request_id,))
            messages = cursor.fetchall()
            
            # 3. ЦИКЛ ОТРИСОВКИ СООБЩЕНИЙ
            for sender, text, created_at, attachment_path, author in messages:
                # Определяем стиль и заголовок
                if sender == 'Client':
                    css_class = "client-msg"
                    sender_name = f"👤 {data.get('User_Name', 'Не указан')}"
                elif sender == 'Internal':
                    css_class = "internal-msg"
                    sender_name = f"📌{author}"
                else:
                    css_class = "support-msg"
                    sender_name = f'🛠 {author}'
                
                time_formatted = created_at.strftime('%d.%m.%Y %H:%M')
                text_formatted = text.replace('\n', '<br>')
                
                st.markdown(f"""
                    <div class='message-box {css_class}'>
                        <div class='meta-info'>
                            <span>{sender_name}</span>
                            <span>{time_formatted}</span>
                        </div>
                        {text_formatted}
                    </div>
                """, unsafe_allow_html=True)
                if attachment_path:
                    display_attachment(attachment_path)
                
            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        # --- ФОРМА ОТПРАВКИ (ОТВЕТ И ЗАМЕТКИ) ---
        recipient_email = data.get('Email')

        # Создаем две вкладки
        tab_reply, tab_internal = st.tabs(["✉️ Ответ заявителю", "🔒 Внутренняя заметка"])

        # --- ВКЛАДКА: ОТВЕТ ЗАЯВИТЕЛЮ (уходит на почту) ---
        with tab_reply:
            with st.form("reply_form", clear_on_submit=True):
                st.write("📤 **Написать ответ заявителю**")
                reply_text = st.text_area("Текст сообщения:", height=120, disabled=is_disabled, key="ta_reply")
                uploaded_file = st.file_uploader("Прикрепить медиафайл:", 
                                                type=['png', 'jpg', 'jpeg', 'pdf', 'zip'],
                                                disabled=is_disabled, key="file_reply")
                send_btn = st.form_submit_button("📨 Отправить почту", disabled=is_disabled)

            if send_btn and (reply_text or uploaded_file):
                if not recipient_email:
                    st.error("❌ У этого участка не указан Email!")
                else:
                    file_save_path = None
                    if uploaded_file:
                        os.makedirs("attachments", exist_ok=True)
                        file_save_path = os.path.join("attachments", f"{int(time.time())}_{uploaded_file.name}")
                        with open(file_save_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                    subject = f"Re: Заявка №{request_id}"
                    status_msg = send_email(recipient_email, subject, reply_text, attachment=file_save_path)
                    
                    if "✅" in status_msg:
                        # Используем новую функцию из db_utils
                        if add_request_message(conn, request_id, 'Support', reply_text, current_user, file_save_path):
                            st.toast("Письмо успешно отправлено!", icon="✅")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error(f"Ошибка: {status_msg}")

        # --- ВКЛАДКА: ВНУТРЕННЯЯ ЗАМЕТКА (только в БД) ---
        with tab_internal:
            with st.form("internal_form", clear_on_submit=True):
                st.write("📌 **Заметка для внутреннего пользования**")
                internal_text = st.text_area("Комментарий (не виден заявителю):", height=120, disabled=is_disabled, key="ta_internal")
                note_btn = st.form_submit_button("💾 Сохранить заметку", disabled=is_disabled)

            if note_btn and internal_text:
                # Для заметок просто вызываем функцию БД с типом 'Internal'
                if add_request_message(conn, request_id, 'Internal', internal_text, current_user):
                    st.toast("Заметка сохранена!", icon="📌")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Ошибка при сохранении заметки в базу данных")

    # =================================================
    # ПРАВАЯ КОЛОНКА: ИНФОРМАЦИЯ И РЕДАКТИРОВАНИЕ
    # =================================================
    with right_col:
        st.subheader("⚙️ Управление заявкой")
        
        with st.form("detail_form"):
            # Редактируемые поля
            service_opts = ["Удаленно", "Выезд"]
            current_service = data.get('Service_Type', 'Удаленно')
    
            executors_map = get_lookup_options("executor", "Executor_ID", "Full_Name")
            exec_list = [""] + list(executors_map.keys())
            types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
            types_list = list(types_map.keys())

            status_opts = ["🔴 Новая", "⚙️ В работе", "✅ Выполнена"]
            current_status_val = data.get('Status', '🔴 Новая')
            if "Новая" in str(current_status_val): current_status_val = '🔴 Новая'
            elif "В работе" in str(current_status_val): current_status_val = '⚙️ В работе'
            elif "Выполнена" in str(current_status_val): current_status_val = '✅ Выполнена'
            current_status_idx = status_opts.index(current_status_val) if current_status_val in status_opts else 0
            
            current_executor_idx = exec_list.index(data['Executor_Name']) if data.get('Executor_Name') in exec_list else 0
            current_type_idx = types_list.index(data['Type_Name']) if data.get('Type_Name') in types_list else 0
            service_idx = service_opts.index(current_service) if current_service in service_opts else 0
            
            col1, col2 = st.columns([1,1])
            with col1:
                status = st.selectbox("Статус:", status_opts, index=current_status_idx, disabled=is_disabled)
                executor = st.selectbox("Исполнитель:", exec_list, index=current_executor_idx, disabled=is_disabled)
            with col2:
                st.markdown(f"""
                **Заявитель:** {data.get('User_Name', 'Не указан')}<br>
                **Район:** {data.get('District_Name', 'Не указан')}, {data.get('Section_Number', 'Не указан')}<br>
                **Раб.тел.:** {data.get('Landline_Phone', 'Не указан')}<br>
                **Закрыта:** {data.get('Closed_At', 'Не указан')}
                """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([2,1])
            with col1:
                req_type = st.selectbox("Тип:", types_list, index=current_type_idx, disabled=is_disabled)
            with col2:
                service_type = st.selectbox("Вид работ:", service_opts, index=service_idx, disabled=is_disabled)
            result = st.text_area("Результат выполнения:", value=data.get('Result', ''), height=100, disabled=is_disabled)
            
            st.write("---")
            st.markdown("**Служебная информация**")
            
            time_spent = st.number_input("Затрачено минут:", value=int(data.get('Time_Spent', 0) or 0), step=5, disabled=is_disabled)
            mileage = st.number_input("Пробег (км):", value=float(data.get('Mileage', 0.0) or 0.0), step=1.0, disabled=is_disabled)
            fuel_cons = st.number_input("Расход (л/100км):", value=float(data.get('Fuel_Consumption', 0.0) or 0.0), step=0.1, disabled=is_disabled)
            fuel_price = st.number_input("Цена бензина (руб):", value=float(data.get('Fuel_Price', 0.0) or 0.0), step=0.1, disabled=is_disabled)
            
            submit_button_card = st.form_submit_button("💾 Сохранить", type="primary", disabled=is_disabled)

            if submit_button_card:
                
                
                # 1. СТАТУС
                # Сравниваем новое значение (status) со старым из базы (data['Status'])
                # Используем "мягкое" сравнение (str), чтобы избежать ошибок типов
                if str(status) != str(data.get('Status', '')):
                    update_db_field(request_id, "Status", status)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Статус изменен на '{status}'")
                    
                    # Логика даты закрытия
                    if status == '✅ Выполнена': 
                        update_closed_date(request_id, True)
                    else: 
                        update_closed_date(request_id, False)

                # 2. ИСПОЛНИТЕЛЬ
                if str(executor) != str(data.get('Executor_Name', '')):
                    new_id = executors_map.get(executor)
                    update_db_field(request_id, "Assigned_Executor_ID", new_id)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Исполнитель изменен на '{executor}'")

                # 3. ТИП ЗАЯВКИ
                if str(req_type) != str(data.get('Type_Name', '')):
                    new_type_id = types_map.get(req_type)
                    update_db_field(request_id, "Request_Type_ID", new_type_id)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Тип изменен на '{req_type}'")
                # 3.1 ВИД РАБОТ
                if str(service_type) != str(data.get('Service_Type', '')):
            
                    update_db_field(request_id, "Service_Type", service_type)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Вид работ изменен на '{service_type}'")

                # 4. РЕЗУЛЬТАТ
                if str(result) != str(data.get('Result', '')):
                    update_db_field(request_id, "Result", result)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Обновлен результат работы")

                # 5. ВРЕМЯ
                # Приводим к int для корректного сравнения (0 вместо None)
                old_time = int(data.get('Time_Spent') or 0)
                if int(time_spent) != old_time:
                    update_db_field(request_id, "Time_Spent", time_spent)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Время изменено с {old_time} на {time_spent} мин.")

                # 6. ГСМ (Пробег, Расход, Цена)
                old_mileage = float(data.get('Mileage') or 0.0)
                if float(mileage) != old_mileage:
                    update_fuel_record(request_id, "Mileage", mileage)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Пробег изменен на {mileage} км")

                old_fuel = float(data.get('Fuel_Consumption') or 0.0)
                if float(fuel_cons) != old_fuel:
                    update_fuel_record(request_id, "Fuel_Consumption", fuel_cons)
                    # Расход меняется редко, можно не спамить в лог, или логировать по желанию

                old_price = float(data.get('Fuel_Price') or 0.0)
                if float(fuel_price) != old_price:
                    update_fuel_record(request_id, "Fuel_Price", fuel_price)

                st.toast("✅ Заявка обновлена!")
                time.sleep(1)
                st.rerun()


