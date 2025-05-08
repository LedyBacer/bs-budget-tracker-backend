#!/bin/sh

# Ждем, пока база данных будет готова
echo "Ожидание готовности базы данных..."
# Получим хост и порт из переменной DATABASE_URL
DB_HOST=$(echo $DATABASE_URL | sed -E 's/.*@([^:]+):.*/\1/')
DB_PORT=$(echo $DATABASE_URL | sed -E 's/.*:([0-9]+)\/.*/\1/')

# Если не удалось получить хост и порт, используем значения по умолчанию из переменных окружения или хардкод
DB_HOST=${DB_HOST:-${POSTGRES_HOST:-db}}
DB_PORT=${DB_PORT:-${POSTGRES_PORT:-5432}}

echo "Проверка соединения с базой данных $DB_HOST:$DB_PORT..."

# Проверяем наличие netcat
if ! command -v nc >/dev/null 2>&1; then
    echo "Установка netcat..."
    apk add --no-cache netcat-openbsd
fi

# Ждем, пока порт базы данных станет доступен
until nc -z $DB_HOST $DB_PORT; do
    echo "База данных еще не доступна - ожидание..."
    sleep 1
done

echo "База данных готова!"

# Применяем миграции Alembic
echo "Запуск миграций базы данных..."
poetry run alembic upgrade head

# Запускаем приложение
echo "Запуск приложения..."
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 $@ 