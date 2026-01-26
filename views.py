import streamlit as st
import re
from datetime import datetime
from db_utils import * # Убедитесь, что все нужные функции есть в db_utils.py
from email_monitor import send_email
import time

def render_detail_view(request_id):
    """Рисует страницу-карточку с чатом слева и данными справа."""
    
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

    # --- 2. ДЕЛИМ ЭКРАН НА ДВЕ КОЛОНКИ ---
    left_col, right_col = st.columns([2, 1])

    # =================================================
    # ЛЕВАЯ КОЛОНКА: ЧАТ И ОТПРАВКА СООБЩЕНИЙ
    # =================================================
    with left_col:
        st.subheader("✉️ Переписка с заявителем")
        
        # Стили для чата
        st.markdown("""
            <style>
                .chat-message { padding: 10px; border-radius: 8px; margin-bottom: 10px; max-width: 95%; word-wrap: break-word; color: #000000; }
                .user-message { background-color: #f1f0f0; align-self: flex-start; }
                .support-message { background-color: #e7f3ff; align-self: flex-end; }
                .message-header { font-size: 0.8em; color: #555; margin-bottom: 5px; color: #555555; }
            </style>
        """, unsafe_allow_html=True)
        
        # Контейнер для чата с прокруткой
        with st.container(height=500):
            messages = re.split(r'--- \[(ОТВЕТ .*?)\] ---', data.get('Description', ''))
            initial_description = messages.pop(0).strip()
            message_pairs = [messages[i:i+2] for i in range(0, len(messages), 2)]
            
            # Оригинальное сообщение
            # 1. Подготавливаем текст ЗАРАНЕЕ
            safe_description = initial_description.replace('\n', '<br>')

            # 2. Вставляем уже готовую переменную
            st.markdown(f"""
                <div class="chat-message user-message">
                    <div class="message-header">ОРИГИНАЛЬНАЯ ЗАЯВКА</div>
                    {safe_description}
                </div>
            """, unsafe_allow_html=True)
            
            # Ответы
            for header, text in reversed(message_pairs):
                text_html = text.strip().replace('\n', '<br>')
                
                css_class = "support-message" if "ТЕХПОДДЕРЖКИ" in header else "user-message"
                st.markdown(f'<div style="display: flex; flex-direction: column;"><div class="chat-message {css_class}"><div class="message-header">{header}</div>{text_html}</div></div>', unsafe_allow_html=True)
        
        st.divider()
        
        # Форма отправки
        recipient_email = data.get('Email')
        if not recipient_email:
            st.warning("Email участка не указан.")
        else:
            with st.form("email_form", clear_on_submit=True):
                st.info(f"Сообщение будет отправлено на: **{recipient_email}**")
                email_body = st.text_area("Текст нового сообщения:", height=100)
                send_button = st.form_submit_button("📨 Отправить email", disabled = is_disabled)

            if send_button and email_body:
                subject = f"Service Desk: Ответ по заявке №{request_id}"
                status_message = send_email(recipient_email, subject, email_body) # send_email должна быть в db_utils
                if "✅" in status_message:
                    st.success(status_message)
                    # 1. Получаем старое описание
                    old_description = data['Description']

                    # 2. Формируем заголовок для нового сообщения
                    ts = datetime.now().strftime('%d.%m.%Y %H:%M')
                    header = f"--- [ОТВЕТ ТЕХПОДДЕРЖКИ {ts}] ---"

                    # 3. "Склеиваем" все части с помощью переносов строк \n
                    new_description = "\n\n".join([old_description, header, email_body])

                    update_db_field(request_id, "Description", new_description)
                    st.rerun()
                else:
                    st.error(status_message)

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
                # Получаем логин текущего пользователя для лога
                current_user = st.session_state.get("user_login", "Unknown")
                
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
                print('усппппех')
                st.rerun()


