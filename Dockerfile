# 1. Базовый образ
FROM python:3.9-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Копируем файл с зависимостями
COPY requirements.txt .

RUN apt-get update && apt-get install -y tzdata \
    && rm -rf /var/lib/apt/lists/*

# 4. Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем все файлы проекта в контейнер
COPY . .

# 6. Открываем порт, на котором будет работать Streamlit
EXPOSE 8501

# 7. Команда, которая запустится при старте контейнера
CMD ["sh", "-c", "python service_desk_bot.py & streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0"]

