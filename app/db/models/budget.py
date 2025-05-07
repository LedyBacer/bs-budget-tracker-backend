# app/db/models/budget.py
import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, func, BigInteger, CheckConstraint
from sqlalchemy.orm import relationship # Убедитесь, что relationship импортирован
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, index=True, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    owner_chat_id = Column(BigInteger, ForeignKey("chats.id"), nullable=True, index=True)

    # Хранимые поля для сумм
    current_total_expense = Column("total_expense", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0')
    current_total_income = Column("total_income", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0')
    current_balance = Column("balance", Numeric(12, 2), nullable=False, default=0.0, server_default='0.0') # Рассчитывается как total_amount - expense + income

    # Связи
    owner_user = relationship(
        "User", # Название класса связанной модели
        foreign_keys=[owner_user_id],    # Явно указываем, какой внешний ключ используется для этой связи
        back_populates="personal_budgets" # Атрибут в модели User, который ссылается на список бюджетов этого пользователя
    )
    owner_chat = relationship(
        "Chat",
        foreign_keys=[owner_chat_id],
        back_populates="shared_budgets"
    )

    categories = relationship("Category", back_populates="budget", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            '(owner_user_id IS NOT NULL AND owner_chat_id IS NULL) OR (owner_user_id IS NULL AND owner_chat_id IS NOT NULL)',
            name='ck_budget_owner_exclusive'
        ),
    )