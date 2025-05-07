# app/db/models/user.py
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, func
from app.db.base_class import Base
from sqlalchemy.orm import relationship # Если понадобится связь от User к Budget (личные бюджеты)

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True, index=True)
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    photo_url = Column(String, nullable=True)
    
    # Если у пользователя могут быть личные бюджеты, добавляем связь
    personal_budgets = relationship(
        "Budget",
        foreign_keys="[Budget.owner_user_id]", # Указываем внешний ключ
        back_populates="owner_user",
        cascade="all, delete-orphan"
    )

    transactions_authored = relationship("Transaction", back_populates="author_user", cascade="all, delete-orphan")

    # created_at для User не так критичен, но для единообразия можно добавить
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())