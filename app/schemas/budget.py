# app/schemas/budget.py
from pydantic import BaseModel, Field
from typing import Optional, List # List пока не используется, но может понадобиться
from datetime import datetime
import uuid

# Чтобы избежать циклических импортов для связанных сущностей при расширении схем,
# можно использовать ForwardRef. Пока оставим так, но будем иметь в виду.
# from .category import Category # Закомментировано, т.к. пока не используется напрямую в этой схеме
# from .transaction import Transaction # Закомментировано

class BudgetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100) # Увеличил max_length для имени бюджета
    total_amount: float = Field(..., ge=0) # Разрешил 0, если бюджет может быть с нулевой суммой изначально

class BudgetCreate(BudgetBase):
    # owner_user_id или owner_chat_id будут определяться на бэкенде
    # на основе контекста (initData) при вызове эндпоинта.
    # Фронтенд не должен передавать их явно при создании.
    pass

class BudgetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    total_amount: Optional[float] = Field(None, ge=0)

class BudgetInDBBase(BudgetBase):
    id: uuid.UUID
    owner_user_id: Optional[int] = None
    owner_chat_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Budget(BudgetInDBBase):
    # Эти поля будут вычисляться на бэкенде и добавляться к ответу
    total_expense: float = Field(default=0.0)
    total_income: float = Field(default=0.0)
    balance: float = Field(default=0.0)

# Схема для ответа, включающая детали (пока не используем, но как задел на будущее)
# class BudgetWithDetails(Budget):
#     categories: List['Category'] = [] # Используем строковую аннотацию для ForwardRef
#     transactions: List['Transaction'] = []