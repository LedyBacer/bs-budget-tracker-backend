# app/api/v1/api.py
from fastapi import APIRouter

from app.api.v1.endpoints import budgets # Импортируем модуль с роутером бюджетов
from app.api.v1.endpoints import categories
from app.api.v1.endpoints import transactions # <--- ИМПОРТИРОВАНО

api_router = APIRouter()

# Подключаем роутер для бюджетов с префиксом /budgets
api_router.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
# Подключаем роутер для категорий.
# Заметьте, что префикс здесь не указываем, т.к. пути уже определены в самом роутере категорий
# (например, /budgets/{budget_id}/categories/ и /categories/{category_id})
api_router.include_router(categories.router, tags=["Categories"]) # <--- ДОБАВЛЕНО
api_router.include_router(transactions.router, tags=["Transactions"]) # <--- ДОБАВЛЕНО (Без префикса здесь, т.к. пути уже полные)