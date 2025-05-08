# Используем официальный образ Python
FROM python:3.13-alpine

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Устанавливаем Poetry
RUN pip install poetry==2.1.3 # Укажите версию poetry, которая у вас установлена локально или желаемую

# Копируем файлы проекта (только необходимые для установки зависимостей)
COPY pyproject.toml /app/

# Устанавливаем зависимости проекта без dev-зависимостей и создаем .venv в /app
# --no-root нужен, чтобы не устанавливать сам проект как пакет, а только его зависимости
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-interaction --no-ansi --no-root

# Копируем остальной код приложения
COPY ./app /app/app
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini

# Создаем скрипт entrypoint.sh
COPY ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Команда для запуска приложения через entrypoint скрипт
EXPOSE 8000

# Запускаем entrypoint скрипт вместо прямого запуска uvicorn
ENTRYPOINT ["/app/entrypoint.sh"]