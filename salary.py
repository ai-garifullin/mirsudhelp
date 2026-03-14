import streamlit as st
import pandas as pd

def calculate_salary(df, hourly_rate, fuel_cost, city_bonus):
    # Фильтруем только выполненные
    df = df[df['Статус'] == '✅ Выполнена'].copy()
    
    # Парсинг даты
    def parse_date(date_val):
        if pd.isna(date_val): return None
        if isinstance(date_val, str):
            try:
                # Добавляем год для парсинга, если его нет
                return pd.to_datetime(date_val + ".2026", format='%d.%m %H:%M.%Y')
            except:
                return None
        return pd.to_datetime(date_val)

    df['Закрыта'] = df['Закрыта'].apply(parse_date)
    df = df.dropna(subset=['Закрыта'])
    
    # Расчет зарплаты
    def compute_row(row):
        hours = row['Минут'] / 60
        base_pay = hours * hourly_rate
        
        is_major_city = any(city in str(row['Адрес']) for city in ['Казань', 'Набережные Челны', 'Нижнекамск'])
        
        if row['Вид работ'] == 'Удаленно':
            return base_pay
        elif is_major_city:
            return base_pay + city_bonus
        else:
            return base_pay + (row['Пробег'] / 100) * row['Расход'] * fuel_cost

    df['Зарплата'] = df.apply(compute_row, axis=1)
    return df

st.title("Калькулятор зарплаты")

# --- Настройки в боковой панели ---
st.sidebar.header("Параметры расчета")
hourly_rate = st.sidebar.number_input("Ставка в час (руб)", value=500)
fuel_cost = st.sidebar.number_input("Стоимость бензина (руб/л)", value=65.0)
city_bonus = st.sidebar.number_input("Бонус за работу в крупных городах (руб)", value=400)

uploaded_file = st.file_uploader("Загрузите файл Excel", type=['xlsx'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        processed_df = calculate_salary(df, hourly_rate, fuel_cost, city_bonus)

        # Выбор исполнителя
        executors = sorted(processed_df['Исполнитель'].dropna().unique().tolist())
        selected_executor = st.selectbox("Выберите исполнителя", executors)

        # Фильтр по дате
        date_range = st.date_input("Выберите период закрытия заявок", [])
        
        if len(date_range) == 2:
            # Фильтруем данные
            executor_df = processed_df[processed_df['Исполнитель'] == selected_executor]
            mask = (executor_df['Закрыта'].dt.date >= date_range[0]) & \
                   (executor_df['Закрыта'].dt.date <= date_range[1])
            result = executor_df[mask]

            # Вывод таблицы
            st.subheader(f"Отчет для: {selected_executor}")
            
            # Показываем нужные колонки
            cols = ['ID', 'Дата', 'Адрес', 'Вид работ', 'Результат', 'Закрыта', 'Зарплата']
            display_df = result[[c for c in cols if c in result.columns]]
            
            st.dataframe(display_df, use_container_width=True)
            
            st.metric(label="Итого к выплате", value=f"{result['Зарплата'].sum():.2f} руб.")

            # Скачивание
            csv = result.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button("Скачать отчет в CSV", data=csv, file_name=f"report_{selected_executor}.csv")
            
    except Exception as e:
        st.error(f"Ошибка: {e}")