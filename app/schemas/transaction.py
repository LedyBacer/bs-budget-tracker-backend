# app/schemas/transaction.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
import uuid
from app.db.models.transaction import TransactionType

class TransactionAuthorInfo(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

    class Config:
        from_attributes = True

class TransactionBase(BaseModel):
    type: TransactionType
    amount: float = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=200)
    comment: Optional[str] = Field(None, max_length=1000)
    transaction_date: datetime = Field(default_factory=datetime.now)

class TransactionCreate(TransactionBase):
    category_id: uuid.UUID # Фронтенд присылает ID категории
    pass

class TransactionUpdate(BaseModel):
    type: Optional[TransactionType] = None
    amount: Optional[float] = Field(None, gt=0)
    name: Optional[str] = Field(None, max_length=200)
    comment: Optional[str] = Field(None, max_length=1000)
    category_id: Optional[uuid.UUID] = None # Можно изменить категорию
    transaction_date: Optional[datetime] = None

class TransactionInDBBase(TransactionBase):
    id: uuid.UUID
    budget_id: uuid.UUID
    category_id: uuid.UUID # ID категории всегда будет здесь из БД
    author_user_id: int
    created_at_db: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Transaction(TransactionInDBBase):
    author: Optional[TransactionAuthorInfo] = None
    category_name: Optional[str] = None # <--- РАСКОММЕНТИРОВАНО и добавлено

class TransactionListResponse(BaseModel):
    transactions: List[Transaction] # Список транзакций по схеме Transaction
    total_count: int              # Общее количество транзакций, соответствующее фильтрам

class DateTransactionSummary(BaseModel):
    """Схема для ответа с суммами транзакций по датам"""
    summaries: Dict[str, float]  # Ключи - даты в формате YYYY-MM-DD, значения - суммы