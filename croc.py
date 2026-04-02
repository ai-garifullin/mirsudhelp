import streamlit as st
import pandas as pd
import re

def croc():
    st.set_page_config(page_title="Генератор VBS", page_icon="⚖️")
    st.title("Генератор VBS")

    uploaded_file = st.file_uploader("Загрузите CSV-файл (пароли_новый_сервер_cleaned.csv)", type=['csv'])

    if uploaded_file:
        try:
            # Читаем CSV (utf-8-sig для корректной кириллицы)
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
            
            # Словарь для хранения: { "Полное название": "ID участка (16MS...)" }
            mapping = {}
            id_pattern = re.compile(r'16MS\d{4}')

            # Проходим по строкам и ищем соответствие "Судебный участок №..." и "16MS..."
            for _, row in df.iterrows():
                row_str = " ".join(row.astype(str))
                
                # Ищем длинное название (регулярка ищет строку от "Судебный участок" до конца названия района)
                name_match = re.search(r'(Судебный участок №\s*\d+\s*по\s*[^,]+)', row_str)
                # Ищем технический ID (16MSxxxx)
                id_match = id_pattern.search(row_str)
                
                if name_match and id_match:
                    full_name = name_match.group(1).strip()
                    tech_id = id_match.group(0)
                    mapping[full_name] = tech_id

            if not mapping:
                st.warning("В файле не найдены строки формата 'Судебный участок №...'")
                return

            # --- ИНТЕРФЕЙС ---
            
            # 1. Выбор участка по полному названию
            sorted_names = sorted(mapping.keys())
            selected_full_name = st.selectbox("Выберите судебный участок", sorted_names, index=None, placeholder="Выбрать из списка")
            
            if not selected_full_name:
                st.stop()
            # Получаем внутренний ID (например, 16MS0001)
            target_id = mapping[selected_full_name]
            st.info(f"Технический идентификатор: **{target_id}**")

            # 2. Выбор должности
            user_types = {
                "Помощник (pomms)": "pomms",
                "Мировой судья (ms)": "ms",
                "Секретарь (secms)": "secms",
                "Заведующий канцелярией (zavkan)": "zavkan"
            }
            selected_user_label = st.selectbox("Выберите должность", list(user_types.keys()))
            user_prefix = user_types[selected_user_label]

            if st.button("Сгенерировать и скачать", type="primary"):
                # Ищем IP и пароль
                all_text = " ".join(df.astype(str).values.flatten())
                
                # Поиск IP
                url_match = re.search(r'http://([0-9\.]+)/' + re.escape(target_id), all_text)
                
                # Поиск пароля
                password = None
                search_login = f"mirsud\\{user_prefix}-{target_id}".lower()
                
                for _, row in df.iterrows():
                    # Приводим все ячейки строки к нижнему регистру и убираем пробелы для поиска
                    row_list = [str(x).replace(" ", "").lower() for x in row.values]
                    if any(search_login in item for item in row_list):
                        # Пароль обычно в ячейке справа от логина
                        for i, cell in enumerate(row_list):
                            if search_login in cell:
                                if i + 1 < len(row.values):
                                    password = str(row.iloc[i+1]).strip()
                                    break
                
                if url_match and password:
                    ip = url_match.group(1)
                    login = f"mirsud\\{user_prefix}-{target_id}"
                    
                    vbs_code = f"""Dim oShell
Set oShell = WScript.CreateObject ("WScript.Shell")
oShell.run "cmdkey.exe /add:{ip} /user:{login} /pass:{password}"
Set objIE = CreateObject("InternetExplorer.Application")
objIE.Navigate "http://{ip}/{target_id}"
objIE.Visible = 1
WScript.Quit"""

                    # Кнопка скачивания
                    st.success("Скрипт готов!")
                    st.download_button(
                        label=f"💾 Скачать {user_prefix}-{target_id}.vbs",
                        data=vbs_code,
                        file_name=f"{user_prefix}-{target_id}.vbs",
                        mime="text/plain"
                    )
                else:
                    st.error("Не удалось найти IP или Пароль для этого участка. Проверьте содержимое CSV.")

        except Exception as e:
            st.error(f"Ошибка: {e}")

if __name__ == "__main__":
    main()