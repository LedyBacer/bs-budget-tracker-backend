# app/db/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
from typing import AsyncGenerator

# Асинхронный движок для FastAPI
async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=True, # Логирование SQL запросов (полезно для отладки)
    future=True # Включает стиль SQLAlchemy 2.0
)

# Асинхронная сессия
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False, # Важно для асинхронных операций
    autocommit=False,
    autoflush=False,
)

# Базовый класс для декларативных моделей SQLAlchemy
Base = declarative_base()

# Зависимость для получения асинхронной сессии в эндпоинтах
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit() # Коммит в конце, если все успешно
        except Exception:
            await session.rollback() # Откат при ошибке
            raise
        finally:
            await session.close()


# Синхронный движок и сессия для Alembic (миграций)
# Alembic не работает с asyncio напрямую в конфигурации env.py
from sqlalchemy import create_engine
SYNC_DATABASE_URL = settings.SYNC_DATABASE_URL # Получаем из настроек
sync_engine = create_engine(SYNC_DATABASE_URL, echo=True)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)