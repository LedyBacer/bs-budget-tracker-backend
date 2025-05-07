# app/schemas/category.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100) # Увеличил max_length
    limit_amount: float = Field(..., ge=0) # Лимит может быть 0 (безлимитная) или больше

class CategoryCreate(CategoryBase):
    # budget_id будет браться из URL-параметра эндпоинта (например, /budgets/{budget_id}/categories)
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    limit_amount: Optional[float] = Field(None, ge=0)

class CategoryInDBBase(CategoryBase):
    id: uuid.UUID
    budget_id: uuid.UUID # Это поле будет в объекте из БД
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Category(CategoryInDBBase):
    # Поля для отображения, вычисляемые на бэкенде
    spent: float = Field(default=0.0)
    income: float = Field(default=0.0)
    balance: float = Field(default=0.0) # limit_amount - spent + income (или как вы считали)
    progress: float = Field(default=0.0)
    transaction_count: int = Field(default=0)