import streamlit as st
from datetime import datetime
from db_utils import *
from email_monitor import send_email
from not_bot import *
import time
import requests
from urllib.parse import urlencode
import hashlib
import dotenv
import os

dotenv.load_dotenv()

def get_yandex_disk_resources(public_key, path=""):
    """Рекурсивно собирает ВСЕ файлы из всех папок по ссылке"""
    base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources'
    # Увеличиваем limit до 1000, чтобы точно увидеть все файлы
    params = {'public_key': public_key, 'limit': 1000}
    if path:
        params['path'] = path
        
    final_url = base_url + '?' + urlencode(params)
    response = requests.get(final_url)
    
    files_dict = {}
    
    if response.status_code == 200:
        data = response.json()
        items = data.get('_embedded', {}).get('items', [])
        
        for item in items:
            if item['type'] == 'file':
                # Сохраняем путь + имя, чтобы не запутаться в одинаковых именах
                full_name = f"{path}/{item['name']}" if path else item['name']
                files_dict[full_name] = item['file']
            elif item['type'] == 'dir':
                # Если это папка — идем внутрь!
                inner_path = item['path'] # Это внутренний путь Яндекса
                # Рекурсивно вызываем эту же функцию
                files_dict.update(get_yandex_disk_resources(public_key, inner_path))
    
    return files_dict

cloud_link = os.getenv('CLOUD_LINK')
all_cloud_resources = get_yandex_disk_resources(cloud_link)

def render_detail_view(request_id):
    
    st.markdown("""
        <style>
            #root > div:nth-child(1) > div > div > div > div > section > div {
                padding-top: 0rem !important;
                padding-bottom: 0rem !important;
            }
            .stAppHeader {
                display: none !important;
            }
            h1 {
                margin-top: 5px !important;
                padding-top: 0 !important;
            }
        </style>
    """, unsafe_allow_html=True) 

    # --- 1. ЗАГРУЗКА ДАННЫХ И КНОПКА "НАЗАД" ---
    # 1. ЗАГРУЗКА ДАННЫХ ЧЕРЕЗ UTILS
    data = fetch_single_request(request_id)
    if not data:
        st.error("Заявка не найдена.")
        return

    st.title(f"📝 Заявка №{request_id}, **Адрес:** {data.get('Address_Name', 'Не указан')}")
    
    if st.button("⬅️ Назад к списку"):
        st.session_state.selected_request_id = None
        if "id" in st.query_params: del st.query_params["id"]
        st.rerun()

    # --- ЛОГИКА БЛОКИРОВКИ ---
    is_admin = st.session_state.get("user_role") == 'admin'
    is_finished = data['Status'] in ['✅ Выполнена', 'Дубль']
    is_disabled = is_finished or not is_admin
    
    current_service_type = st.session_state.get('st_service', data.get('Service_Type'))
    fuel_disabled = is_disabled or (current_service_type == "Удаленно") or (current_service_type == "Дубль") or "г.Казань" in data.get('Address_Name', 'Не указан')
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
            
            # Генерируем уникальный хэш для текущего пути к файлу + времени/состояния
            # Если нужно, чтобы ключ был СОВСЕМ уникальным при каждом рендере, 
            # можно добавить time.time()
            unique_id = hashlib.md5(file_path.encode()).hexdigest()[:8]
            
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
                            key=f"dl_{unique_id}_{file_name}" # Уникальный ключ
                        )
    with left_col:
        st.subheader("✉️ Переписка с заявителем")
        
        # --- CSS СТИЛИ ДЛЯ ЧАТА ---
        st.markdown("""
            <style>
                /* Общий контейнер для всех сообщений */
                .chat-container {
                    display: flex;
                    flex-direction: column;
                    width: 100%;
                    gap: 10px;
                }

                /* Базовый стиль сообщения */
                .message-box {
                    padding: 15px;
                    border-radius: 12px;
                    max-width: 80%;
                    width: fit-content; /* Чтобы блок не растягивался на весь экран */
                    word-wrap: break-word;
                    font-size: 15px;
                    margin-bottom: 10px;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
                }

                /* Исходная заявка (по центру) */
                .initial-msg {
                    align-self: center;
                    background-color: #fff3cd;
                    color: #856404;
                    width: 95%; /* Она может быть широкой */
                    border: 1px solid #ffeeba;
                }

                /* Заявитель (Слева) */
                .client-msg {
                    align-self: flex-start;
                    background-color: #f2f3f5;
                    color: #1f1f1f;
                    border-bottom-left-radius: 2px;
                    border: 1px solid #e0e0e0;
                }

                /* Исполнитель (Справа) */
                .support-msg {
                    align-self: flex-end;
                    background-color: #e3f2fd;
                    color: #0d47a1;
                    border-bottom-right-radius: 2px;
                    border: 1px solid #bbdefb;
                    margin-left: auto; /* Дополнительная страховка для прижатия вправо */
                }

                /* Внутренняя заметка (Справа) */
                .internal-msg {
                    align-self: flex-end;
                    background-color: #d4edda;
                    color: #155724;
                    border-bottom-right-radius: 2px;
                    border: 1px solid #c3e6cb;
                    margin-left: auto;
                }

                .meta-info {
                    display: flex;
                    justify-content: space-between;
                    font-size: 12px;
                    font-weight: bold;
                    margin-bottom: 8px;
                    gap: 20px;
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
            messages = fetch_request_messages(request_id)
            
            # 3. ЦИКЛ ОТРИСОВКИ СООБЩЕНИЙ
            messages = fetch_request_messages(request_id)
            for msg in messages:
                # 1. Определяем стили и имя
                if msg['Sender_Type'] == 'Client':
                    css, name = "client-msg", f"👤 {data.get('User_Name')}"
                elif msg['Sender_Type'] == 'Internal':
                    css, name = "internal-msg", f"📌 {msg['Author']}"
                else:
                    css, name = "support-msg", f"🛠 {msg['Author']}"
                
                # 2. ГОТОВИМ ТЕКСТ ЗАРАНЕЕ (решаем проблему с \n)
                raw_text = msg.get('Message_Text', '')
                clean_text = raw_text.replace('\n', '<br>')
                formatted_date = msg['Created_At'].strftime('%d.%m %H:%M')

                # 3. Выводим чистую f-строку без лишней логики внутри скобок
                st.markdown(f"""
                    <div class='message-box {css}'>
                        <div class='meta-info'>
                            <span>{name}</span>
                            <span>{formatted_date}</span>
                        </div>
                        {clean_text}
                    </div>
                """, unsafe_allow_html=True)
                
                # 4. Вложения
                if msg.get('Attachment_Path'):
                    display_attachment(msg['Attachment_Path'])

            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        # --- ФОРМА ОТПРАВКИ (ОТВЕТ И ЗАМЕТКИ) ---
        recipient_email = data.get('Email')

        # Создаем две вкладки
        tab_internal, tab_reply, tab_telegram = st.tabs(["🔒 Внутренняя", "✉️ Почта", "📱 Telegram"])

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
                if add_request_message(request_id, 'Internal', internal_text, current_user, file_save_path):
                    st.toast("Внутренняя заметка с файлом сохранена", icon="📌")
                    time.sleep(1)
                    st.rerun()
                    
        # --- ВКЛАДКА: ОТВЕТ ЗАЯВИТЕЛЮ (уходит на почту) ---
        with tab_reply:
            with st.form("reply_form", clear_on_submit=True):
                st.write("📤 **Написать ответ заявителю**")
                reply_text = st.text_area("Текст сообщения:", height=120, disabled=is_disabled, key="ta_reply")
                
                # Добавляем выбор из облака
                selected_cloud_file_reply = st.selectbox(
                    "📁 Выбрать файл из облака (Я.Диск):", 
                    options=["Не выбрано"] + list(all_cloud_resources.keys()),
                    key="cloud_file_picker_reply", disabled=is_disabled
                )
                
                uploaded_file = st.file_uploader("ИЛИ прикрепить файл с ПК:", 
                                                type=None, # Разрешаем все типы
                                                disabled=is_disabled, key="file_reply")
                
                send_btn = st.form_submit_button("📨 Отправить почту", disabled=is_disabled)

            if send_btn and (reply_text or uploaded_file or selected_cloud_file_reply != "Не выбрано"):
                if not recipient_email:
                    st.error("❌ У этого участка не указан Email!")
                else:
                    file_save_path = None
                    os.makedirs("attachments", exist_ok=True)
                    
                    # Приоритет: локальный файл -> облачный файл
                    if uploaded_file:
                        file_save_path = os.path.join("attachments", f"{int(time.time())}_{uploaded_file.name}")
                        with open(file_save_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                    
                    elif selected_cloud_file_reply != "Не выбрано":
                        # Логика скачивания с облака
                        download_url = all_cloud_resources[selected_cloud_file_reply]
                        file_name_clean = selected_cloud_file_reply.split('/')[-1]
                        file_save_path = os.path.join("attachments", f"{int(time.time())}_{file_name_clean}")
                        
                        with st.spinner("Скачиваю файл из облака..."):
                            r = requests.get(download_url)
                            if r.status_code == 200:
                                with open(file_save_path, "wb") as f:
                                    f.write(r.content)
                            else:
                                st.error("Не удалось скачать файл из облака")
                                file_save_path = None

                    # Отправка, если файл успешно подготовлен или есть текст
                    if file_save_path or reply_text:
                        subject = f"Re: Заявка №{request_id}"
                        status_msg = send_email(recipient_email, subject, reply_text, attachment=file_save_path)
                        
                        if "✅" in status_msg:
                            if add_request_message(request_id, 'Support', reply_text, current_user, file_save_path):
                                st.toast("Письмо успешно отправлено!", icon="✅")
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error(f"Ошибка: {status_msg}")
        
        # --- ВКЛАДКА: TELEGRAM (Отправка сообщения и файлов) ---
        with tab_telegram:
            with st.form("telegram_form", clear_on_submit=True):
                st.write("📱 **Отправить сообщение в Telegram**")
                tg_text = st.text_area("Текст сообщения:", height=100, key="tg_reply_text_v2", disabled=is_disabled)
                
                # Выпадающий список теперь содержит ВСЕ файлы (docx, rar, zip и т.д.)
                selected_resource = st.selectbox(
                    "📁 Выбрать из облака (любой формат):", 
                    options=["Не выбрано"] + list(all_cloud_resources.keys()), disabled=is_disabled,
                    help="Здесь отображаются все документы, архивы и подпапки"
                )
                
                # Убрали ограничение по type, чтобы разрешить docx/rar при ручной загрузке
                tg_file = st.file_uploader("ИЛИ загрузить файл с ПК:", 
                                        type=None, 
                                        key="tg_file_upload_v2", disabled=is_disabled)
                
                send_tg_btn = st.form_submit_button("🚀 Отправить", disabled=is_disabled)

            if send_tg_btn:
                file_save_path = None
                
                # 1. Проверка: не выбрана ли папка
                if selected_resource.startswith("📁"):
                    st.error("Вы выбрали папку. Пожалуйста, выберите конкретный файл внутри неё.")
                
                # 2. Логика сохранения файла
                elif tg_file:
                    os.makedirs("attachments", exist_ok=True)
                    file_save_path = os.path.join("attachments", f"tg_{int(time.time())}_{tg_file.name}")
                    with open(file_save_path, "wb") as f:
                        f.write(tg_file.getbuffer())
                
                elif selected_resource != "Не выбрано":
                    with st.spinner("Скачиваю файл из облака..."):
                        download_url = all_cloud_resources[selected_resource]
                        os.makedirs("attachments", exist_ok=True)
                        file_save_path = os.path.join("attachments", selected_resource)
                        
                        # Скачиваем любой файл (docx, rar и т.д.) как байты
                        r = requests.get(download_url)
                        if r.status_code == 200:
                            with open(file_save_path, "wb") as f:
                                f.write(r.content)
                        else:
                            st.error("Не удалось скачать файл из облака")
                            file_save_path = None

                # 3. Отправка в БД / Бот
                if file_save_path or tg_text:
                    if add_request_message(request_id, 'Support', tg_text, current_user, file_save_path):
                        st.toast("Сообщение готово к отправке!", icon="✅")
                        time.sleep(1)
                        st.rerun()

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
        st.text_area("Общий результат:", value=data.get('Result', '') or '', disabled=True, height=208)
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            st.number_input("Общее время:", value=int(data.get('Time_Spent', 0) or 0), disabled=True)
            fuel_cons = st.number_input("Расход (л/100км):", value=float(data.get('Fuel_Consumption', 0.0) or 0.0), step=0.1, disabled=fuel_disabled)
        with col_i2:
            st.number_input("Общий пробег:", value=float(data.get('Mileage', 0.0) or 0.0), disabled=True)
            fuel_price = st.number_input("Цена бензина (руб):", value=float(data.get('Fuel_Price', 0.0) or 0.0), step=0.1, disabled=fuel_disabled)

        st.write("---")

        # 3. Поля ввода (БЕЗ ФОРМЫ - никакой надписи не будет!)
        st.markdown("### Добавить информацию")
        st.session_state.new_res = st.text_area("Результат:", value=st.session_state.new_res)
        col_r1, col_r2 = st.columns([5,5])
        with col_r1:
            st.session_state.new_time = st.number_input("Затрачено минут:", value=st.session_state.new_time, step=5)
        with col_r2:
            st.session_state.new_mile = st.number_input("Пробег (км):", value=st.session_state.new_mile, step=1.0, disabled = fuel_disabled)

        # Сохранение и дубликат    
        col_n1, col_n2 = st.columns([5,5])
        with col_n1:
            
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
                
                old_fuel = float(data.get('Fuel_Consumption') or 0.0)
                if float(fuel_cons) != old_fuel:
                    update_fuel_record(request_id, "Fuel_Consumption", fuel_cons)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Расход изменен на '{fuel_cons}'")
                    # Расход меняется редко, можно не спамить в лог, или логировать по желанию

                old_price = float(data.get('Fuel_Price') or 0.0)
                if float(fuel_price) != old_price:
                    update_fuel_record(request_id, "Fuel_Price", fuel_price)
                    log_action(current_user, "UPDATE", f"Заявка #{request_id}: Цена бензина изменена на '{fuel_price}'")
                
                if new_status == '✅ Выполнена':
                    st.success("✅ Заявка закрыта. Возврат к списку...")
                    time.sleep(3) # Короткая пауза для уведомления
                    
                    # Сбрасываем состояние, чтобы вернуться на главную
                    st.session_state.selected_request_id = None
                    
                    # Чистим адресную строку браузера
                    if "id" in st.query_params:
                        del st.query_params["id"]
                    
                    st.rerun()

                # 2. ЛОГИКА ДОБАВЛЕНИЯ РЕЗУЛЬТАТОВ (Авто-счетчик)
                if st.session_state.new_res.strip() or st.session_state.new_time > 0 or st.session_state.new_mile > 0:
                    
                    old_result = data.get('Result') or ''
                    
                    # Считаем, сколько раз встречается "[Результат", чтобы понять номер следующего
                    # count будет равен 1, если ничего не найдено, или номеру последнего + 1
                    count = old_result.count("[Результат") + 1
                    
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%d.%m %H:%M")
                    
                    # Форматируем добавление компактно
                    if current_service_type == "Удаленно" or "г.Казань" in data.get('Address_Name', 'Не указан'):
                        addition = (f"\n\n--- [Результат {count} | {timestamp}] ---\n"
                                f"📝 {st.session_state.new_res.strip()}\n"
                                f"⏱ Время: {st.session_state.new_time} мин.")
                    else: 
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


