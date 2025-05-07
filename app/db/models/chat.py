# app/db/models/chat.py
from sqlalchemy import Column, BigInteger, String, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Chat(Base):
    __tablename__ = "chats"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=False) # Telegram Chat ID группы
    type = Column(String, nullable=False) # e.g., "group", "supergroup"
    title = Column(String, nullable=True)

    # Связь с бюджетами, принадлежащими этому чату
    shared_budgets = relationship(
        "Budget",
        foreign_keys="[Budget.owner_chat_id]", # Указываем внешний ключ
        back_populates="owner_chat",
        cascade="all, delete-orphan"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())