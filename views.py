import streamlit as st
import re
from datetime import datetime
from db_utils import * # Убедитесь, что все нужные функции есть в db_utils.py
from email_monitor import send_email
from not_bot import *
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

        if "id" in st.query_params:
            del st.query_params["id"]

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
        tab_internal, tab_reply = st.tabs(["🔒 Внутренняя заметка", "✉️ Ответ заявителю"])

        # --- ВКЛАДКА: ВНУТРЕННЯЯ ЗАМЕТКА (только в БД) ---
        with tab_internal:
            with st.form("internal_note_form", clear_on_submit=True):
                st.write("📌 **Заметка для внутреннего пользования**")
                internal_text = st.text_area("Комментарий:", height=120, key="ta_internal")
                
                # Добавляем загрузку файла для внутреннего пользования
                internal_file = st.file_uploader("Прикрепить внутренний документ/фото:", 
                                                type=['png', 'jpg', 'jpeg', 'pdf', 'zip'], 
                                                key="internal_file_upload")
                
                note_btn = st.form_submit_button("💾 Сохранить заметку")

            if note_btn and (internal_text or internal_file):
                file_save_path = None
                
                # Если файл прикреплен, сохраняем его локально
                if internal_file:
                    os.makedirs("attachments", exist_ok=True)
                    file_save_path = os.path.join("attachments", f"internal_{int(time.time())}_{internal_file.name}")
                    with open(file_save_path, "wb") as f:
                        f.write(internal_file.getbuffer())

                # Вызываем вашу функцию из db_utils
                # ВАЖНО: здесь НЕТ функции send_email, файл остается только у нас
                if add_request_message(conn, request_id, 'Internal', internal_text, current_user, file_save_path):
                    st.toast("Внутренняя заметка с файлом сохранена", icon="📌")
                    time.sleep(1)
                    st.rerun()
                    
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

    # =================================================
    # ПРАВАЯ КОЛОНКА: ИНФОРМАЦИЯ И РЕДАКТИРОВАНИЕ
    # =================================================
    with right_col:
        st.subheader("⚙️ Управление заявкой")

        # 1. Подготовка данных
        service_opts = ["Удаленно", "Выезд", "Дубль"]
        status_opts = ["🔴 Новая", "⚙️ В работе", "✅ Выполнена"]
        executors_map = get_lookup_options("executor", "Executor_ID", "Full_Name")
        exec_list = [""] + list(executors_map.keys())
        types_map = get_lookup_options("request_type", "Type_ID", "Type_Name")
        types_list = list(types_map.keys())

        def get_idx(lst, val):
            return lst.index(val) if val in lst else 0

        # 2. Отрисовка
        col1, col2 = st.columns([1, 1])

        with col1:
            # Статус и Исполнитель
            status = st.selectbox("Статус:", status_opts, index=get_idx(status_opts, data.get('Status')), key="st_status", disabled=is_disabled)
            executor = st.selectbox("Исполнитель:", exec_list, index=get_idx(exec_list, data.get('Executor_Name')), key="st_exec", disabled=is_disabled)
            
           

        with col2:
            # Информация о заявителе
            st.markdown(f"""
                **Заявитель:** {data.get('User_Name', 'Не указан')}<br>
                **Район:** {data.get('District_Name', 'Не указан')}, {data.get('Section_Number', 'Не указан')}<br>
                **Раб.тел.:** {data.get('Landline_Phone', 'Не указан')}<br>
                **Закрыта:** {data.get('Closed_At', 'Не указан')}
                """, unsafe_allow_html=True)
        col1, col2 = st.columns([1, 1])
        with col1:
            req_type = st.selectbox("Тип:", types_list, index=get_idx(types_list, data.get('Type_Name')), key="st_type", disabled=is_disabled)

        with col2:
            service_type = st.selectbox("Вид работ:", service_opts, index=get_idx(service_opts, data.get('Service_Type')), key="st_service", disabled=is_disabled)
            
        # 1. Инициализация состояния, чтобы поля были пустыми при открытии, 
        # но сохраняли данные, пока вы их вводите
        if 'new_res' not in st.session_state: st.session_state.new_res = ""
        if 'new_time' not in st.session_state: st.session_state.new_time = 0
        if 'new_mile' not in st.session_state: st.session_state.new_mile = 0.0

        # 2. Неизменяемые поля (Итоги)
        st.markdown("### Итог")
        st.text_area("Общий результат:", value=data.get('Result', '') or '', disabled=True, height=218)
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            st.number_input("Общее время:", value=int(data.get('Time_Spent', 0) or 0), disabled=True)
        with col_i2:
            st.number_input("Общий пробег:", value=float(data.get('Mileage', 0.0) or 0.0), disabled=True)

        st.write("---")

        # 3. Поля ввода (БЕЗ ФОРМЫ - никакой надписи не будет!)
        st.markdown("### Добавить информацию")
        st.session_state.new_res = st.text_area("Результат:", value=st.session_state.new_res)
        col_n1, col_n2 = st.columns([5,5])
        with col_n1:
            st.session_state.new_time = st.number_input("Затрачено минут:", value=st.session_state.new_time, step=5)
             # 4. Кнопка сохранения
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                # Берем значения из session_state, так как они теперь привязаны к ключам
                new_status = st.session_state.st_status
                new_executor = st.session_state.st_exec
                new_type = st.session_state.st_type
                new_service = st.session_state.st_service

                # 1. СТАТУС
                if str(new_status) != str(data.get('Status', '')):
                    update_db_field(request_id, "Status", new_status)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Статус изменен на '{new_status}'")
                    update_closed_date(request_id, new_status == '✅ Выполнена')
                    
                    # Уведомление директору
                    if new_status == '⚙️ В работе':
                        director_tg_id = get_director_tg_id()
                        if director_tg_id:
                            msg = format_request_message(data, f"🛠 Заявка #{request_id} взята в работу!")
                            msg += f"\n\n👤 <b>Исполнитель:</b> {new_executor}"
                            bot.send_message(director_tg_id, msg, parse_mode="HTML")

                # 2. ИСПОЛНИТЕЛЬ
                if str(new_executor) != str(data.get('Executor_Name', '')):
                    update_db_field(request_id, "Assigned_Executor_ID", executors_map.get(new_executor))
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Исполнитель изменен на '{new_executor}'")
                    
                    # Уведомление исполнителю
                    msg = format_request_message(data, "🔔 Вам назначена новая заявка!")
                    send_tg_notification(new_executor, msg)
                                
                # 3. ТИП
                if str(new_type) != str(data.get('Type_Name', '')):
                    update_db_field(request_id, "Request_Type_ID", types_map.get(new_type))
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Тип изменен на '{new_type}'")

                # 4. ВИД РАБОТ
                if str(new_service) != str(data.get('Service_Type', '')):
                    update_db_field(request_id, "Service_Type", new_service)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Вид работ изменен на '{new_service}'")

                st.success("Изменения сохранены!")
                st.rerun() # Обновляем страницу, чтобы данные обновились из БД

                # 2. ЛОГИКА ДОБАВЛЕНИЯ РЕЗУЛЬТАТОВ (Авто-счетчик)
                if st.session_state.new_res.strip() or st.session_state.new_time > 0 or st.session_state.new_mile > 0:
                    
                    old_result = data.get('Result') or ''
                    
                    # Считаем, сколько раз встречается "[Результат", чтобы понять номер следующего
                    # count будет равен 1, если ничего не найдено, или номеру последнего + 1
                    count = old_result.count("[Результат") + 1
                    
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%d.%m %H:%M")
                    
                    # Форматируем добавление компактно
                    addition = (f"\n\n--- [Результат {count} | {timestamp}] ---\n"
                                f"📝 {st.session_state.new_res.strip()}\n"
                                f"⏱ Время: {st.session_state.new_time} мин. | 🛣 Пробег: {st.session_state.new_mile} км.")
                    
                    full_result = (old_result + addition).strip()

                    # Агрегация сумм
                    total_time = int(data.get('Time_Spent') or 0) + st.session_state.new_time
                    total_mileage = float(data.get('Mileage') or 0.0) + st.session_state.new_mile
                    
                    # Обновление БД
                    update_db_field(request_id, "Result", full_result)
                    update_db_field(request_id, "Time_Spent", total_time)
                    update_fuel_record(request_id, "Mileage", total_mileage)
                    
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Добавлен результат #{count}")
                    
                    # Сброс временных полей
                    st.session_state.new_res = ""
                    st.session_state.new_time = 0
                    st.session_state.new_mile = 0.0
                    
                    st.toast(f"✅ Результат {count} добавлен!")
                    time.sleep(0.5)
                    st.rerun()

        with col_n2:
            st.session_state.new_mile = st.number_input("Пробег (км):", value=st.session_state.new_mile, step=1.0)
            if st.button("👥 Создать дубликат", use_container_width=True):
                new_request_id = duplicate_request(request_id)
                if new_request_id:
                    # Логируем действие
                    log_action(current_user, "DUPLICATE", f"Создан дубликат #{new_request_id} на основе #{request_id}")
                    
                    st.toast(f"✅ Создана новая заявка №{new_request_id}")
                    
                    # Переключаем интерфейс на новую заявку
                    st.session_state.selected_request_id = new_request_id
                    st.query_params["id"] = str(new_request_id)
                    
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Не удалось создать дубликат. Проверьте логи сервера.")  


