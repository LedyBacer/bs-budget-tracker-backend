# app/main.py
from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.api import api_router as api_router_v1 # Мы создадим это позже
# from app.db.database import Base, engine # Для создания таблиц при старте (если не используем Alembic сразу)

# Если не используем Alembic для создания таблиц при первом запуске (не рекомендуется для продакшена)
# def create_tables():
#    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" # URL для OpenAPI схемы
)

# create_tables() # Раскомментировать, если таблицы нужно создать при запуске (без Alembic)

app.include_router(api_router_v1, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}

# TODO: Добавить обработку CORS, если фронтенд будет на другом домене/порту во время разработки
# from fastapi.middleware.cors import CORSMiddleware
# origins = [
#     "http://localhost",
#     "http://localhost:5173", # Пример порта Vite
#     # "your_production_domain.com",
# ]
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )