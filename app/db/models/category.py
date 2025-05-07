# app/db/models/category.py
import uuid
from sqlalchemy import Column, String, Numeric, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    limit_amount = Column(Numeric(12, 2), nullable=False) # Лимит на категорию
    # spent, income, balance - также лучше вычислять или обновлять при транзакциях.

    budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Хранимые поля для сумм
    current_spent = Column("spent", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0')
    current_income = Column("income", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0')
    current_balance = Column("balance", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0') # Рассчитывается как limit_amount - spent + income

    # Связи
    budget = relationship("Budget", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category", cascade="all, delete-orphan") # Или SET NULL, если транзакции не должны удаляться с категорией