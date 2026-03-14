import streamlit as st
import pandas as pd

def calculate_salary(df, hourly_rate, fuel_cost):
    # 1. Фильтрация: только выполненные заявки
    df = df[df['Статус'] == '✅ Выполнена'].copy()
    
    # Конвертируем дату закрытия (предполагаем формат ДД.ММ.ГГГГ ЧЧ:ММ)
    df['Закрыта'] = pd.to_datetime(df['Закрыта'], format='%d.%m.%Y %H:%M', errors='coerce')
    
    # 2. Логика расчета
    def compute_row(row):
        # Переводим минуты в часы
        hours = row['Минут'] / 60
        base_pay = hours * hourly_rate
        
        # Проверка локации (ищем частичное совпадение в адресе)
        is_major_city = any(city in row['Адрес'] for city in ['Казань', 'Набережные Челны', 'Нижнекамск'])
        
        if row['Вид работ'] == 'Удаленно':
            return base_pay
        elif is_major_city:
            return base_pay + 400
        else:
            # Офлайн вне крупных городов: ГСМ = (Пробег/100) * расход * цена
            fuel_pay = (row['Пробег'] / 100) * row['Расход'] * fuel_cost
            return base_pay + fuel_pay

    df['Зарплата'] = df.apply(compute_row, axis=1)
    return df

st.title("Калькулятор зарплаты")

uploaded_file = st.file_uploader("Загрузите CSV/Excel файл", type=['csv', 'xlsx'])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    
    # Настройки
    col1, col2 = st.columns(2)
    hourly_rate = col1.number_input("Ставка в час (руб)", value=300)
    fuel_cost = col2.number_input("Стоимость бензина за литр (руб)", value=55.0)
    
    date_range = st.date_input("Выберите период закрытия заявок", [])
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        processed_df = calculate_salary(df, hourly_rate, fuel_cost)
        
                # Фильтр по дате
                # Преобразуем input-даты в Timestamp для корректного сравнения
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)

        # Сравниваем напрямую с колонкой datetime64
        mask = (processed_df['Закрыта'] >= start_ts) & (processed_df['Закрыта'] <= end_ts)
        result = processed_df.loc[mask]
        
        st.write("Итоговая таблица:", result[['ID', 'Исполнитель', 'Закрыта', 'Зарплата']])
        st.success(f"Общая сумма к выплате: {result['Зарплата'].sum():.2f} руб.")