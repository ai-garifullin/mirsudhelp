import streamlit as st
import pandas as pd
from io import BytesIO

def calculate_salary(df, hourly_rate, city_bonus):
    # 1. Фильтруем: только выполненные и не "Дубль"
    df = df[df['Статус'] == '✅ Выполнена'].copy()
    df = df[df['Вид работ'].astype(str).str.strip() != 'Дубль']
    
    # Парсинг даты
    def parse_date(date_val):
        if pd.isna(date_val): return None
        if isinstance(date_val, str):
            try:
                return pd.to_datetime(date_val + ".2026", format='%d.%m %H:%M.%Y')
            except:
                return None
        return pd.to_datetime(date_val)

    df['Закрыта'] = df['Закрыта'].apply(parse_date)
    df = df.dropna(subset=['Закрыта'])
    
    # Расчет по строкам
    def compute_details(row):
        # Оплата за время (Работа)
        hours = row.get('Минут', 0) / 60
        work_pay = hours * hourly_rate
        
        address_str = str(row.get('Адрес', ''))
        is_major_city = any(city in address_str for city in ['Казань', 'Набережные Челны', 'Нижнекамск'])
        work_type = str(row.get('Вид работ', ''))
        
        # Данные из отчета
        mileage = row.get('Пробег', 0)
        consumption = row.get('Расход', 0)
        # БЕРЕМ ЦЕНУ ИЗ СТОЛБЦА "Цена"
        row_fuel_price = row.get('Цена', 0)
        
        # Обработка NaN (пустых ячеек)
        mileage = 0 if pd.isna(mileage) else mileage
        consumption = 0 if pd.isna(consumption) else consumption
        row_fuel_price = 0 if pd.isna(row_fuel_price) else row_fuel_price
        
        extra_bonus = 0
        fuel_pay = 0
        
        if work_type == 'Удаленно':
            pass 
        elif is_major_city:
            if mileage > 0:
                # Если есть пробег — считаем ГСМ по цене из файла
                fuel_pay = (mileage / 100) * consumption * row_fuel_price
                extra_bonus = 0
            else:
                # Если пробега нет — фиксированный бонус
                extra_bonus = city_bonus
                fuel_pay = 0
        else:
            # Для прочих городов всегда ГСМ по цене из файла
            fuel_pay = (mileage / 100) * consumption * row_fuel_price
            extra_bonus = 0

        total = work_pay + fuel_pay + extra_bonus
        
        return pd.Series([hours, work_pay, fuel_pay, extra_bonus, total, row_fuel_price])

    # Применяем расчет
    res_cols = ['Часы', 'Работа', 'ГСМ', 'Доп_выплаты', 'Итого', 'Цена_бензина_файл']
    df[res_cols] = df.apply(compute_details, axis=1)
    return df

st.set_page_config(page_title="Калькулятор выплат", layout="wide")
st.title("Калькулятор зарплаты")

# --- Интерфейс управления ставками ---
st.sidebar.header("Параметры расчета")
hourly_rate = st.sidebar.number_input("Ставка в час (руб)", value=500, step=50)
city_bonus = st.sidebar.number_input("Фикс", value=400, step=50)

uploaded_file = st.file_uploader("Загрузите файл Excel (должен содержать столбец 'Цена')", type=['xlsx'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        
        # Проверка наличия столбца "Цена"
        if 'Цена' not in df.columns:
            st.error("В загруженном файле отсутствует столбец 'Цена'. Пожалуйста, добавьте его для расчета ГСМ.")
        else:
            processed_df = calculate_salary(df, hourly_rate, city_bonus)

            executors = sorted(processed_df['Исполнитель'].dropna().unique().tolist())
            selected_executor = st.selectbox("👤 Выберите исполнителя", executors)

            date_range = st.date_input("📅 Выберите период закрытия заявок", [])
            
            if len(date_range) == 2:
                executor_df = processed_df[processed_df['Исполнитель'] == selected_executor]
                mask = (executor_df['Закрыта'].dt.date >= date_range[0]) & \
                       (executor_df['Закрыта'].dt.date <= date_range[1])
                result = executor_df[mask].copy()

                result['Ставка_час'] = hourly_rate
                result['Дата_строка'] = result['Закрыта'].dt.strftime('%d.%m.%Y %H:%M')

                # Формируем итоговую структуру
                report_display = result[[
                    'ID', 'Дата_строка', 'Результат', 'Часы', 'Ставка_час', 
                    'Пробег', 'Расход', 'Цена_бензина_файл', 
                    'Доп_выплаты', 'Работа', 'ГСМ', 'Итого'
                ]].copy()

                report_display.columns = [
                    'ID заявки', 'Дата закрытия', 'Результат по заявке', 
                    'Затрачено часов', 'Ставка (руб/ч)', 'Пробег (км)', 
                    'Расход (л/100км)', 'Цена бензина (из файла)', 
                    'Доп. выплаты', 'Работа', 'ГСМ', 'Сумма к выплате'
                ]

                st.subheader(f"📊 Отчет: {selected_executor}")
                st.dataframe(report_display, use_container_width=True)
                
                # Итоговые метрики
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Всего заявок", len(report_display))
                c2.metric("За работу", f"{report_display['Работа'].sum():.2f} ₽")
                c3.metric("ГСМ + Доп", f"{(report_display['ГСМ'].sum() + report_display['Доп. выплаты'].sum()):.2f} ₽")
                c4.metric("ИТОГО К ВЫПЛАТЕ", f"{report_display['Сумма к выплате'].sum():.2f} ₽")

                # Генерация Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    report_display.to_excel(writer, index=False, sheet_name='Отчет')
                    
                    workbook  = writer.book
                    worksheet = writer.sheets['Отчет']
                    
                    header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                    for col_num, value in enumerate(report_display.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                    
                    for i, col in enumerate(report_display.columns):
                        column_len = max(report_display[col].astype(str).str.len().max(), len(col)) + 3
                        worksheet.set_column(i, i, column_len)
                
                processed_data = output.getvalue()

                st.download_button(
                    label="📥 Скачать отчет в Excel (.xlsx)",
                    data=processed_data,
                    file_name=f"report_{selected_executor}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
    except Exception as e:
        st.error(f"Ошибка: {e}")