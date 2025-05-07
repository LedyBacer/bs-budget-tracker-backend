# app/db/models/transaction.py
import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, func, Enum as SQLAlchemyEnum, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base
import enum

class TransactionType(str, enum.Enum): # Наследуем от str для лучшей интеграции с Pydantic/FastAPI
    expense = "expense"
    income = "income"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(SQLAlchemyEnum(TransactionType, name="transaction_type_enum", create_constraint=True), nullable=False) # Добавил name и create_constraint для Enum
    amount = Column(Numeric(12, 2), nullable=False)
    name = Column(String, nullable=True)
    comment = Column(String, nullable=True)
    
    # Дата создания записи в БД
    created_at_db = Column("created_at", DateTime(timezone=True), server_default=func.now()) # Переименовал, чтобы не путать с датой транзакции
    # Фактическая дата транзакции, указанная пользователем (из вашего TS типа `createdAt`)
    transaction_date = Column(DateTime(timezone=True), nullable=False, default=func.now())
    # Время последнего обновления записи
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


    budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    author_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)


    budget = relationship("Budget", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    author_user = relationship("User", back_populates="transactions_authored") 