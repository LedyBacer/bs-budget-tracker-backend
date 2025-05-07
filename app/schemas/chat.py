# app/schemas/chat.py
from pydantic import BaseModel
from typing import Optional

class ChatBase(BaseModel):
    # ID не здесь, т.к. он будет либо путем для GET, либо частью initData
    type: str
    title: Optional[str] = None

class ChatCreate(ChatBase):
    id: int # Telegram Chat ID

class ChatUpdate(BaseModel): # Если понадобится обновлять информацию о чате
    type: Optional[str] = None
    title: Optional[str] = None

class ChatInDBBase(ChatBase):
    id: int

    class Config:
        from_attributes = True

class Chat(ChatInDBBase):
    pass

class ChatInDB(ChatInDBBase):
    pass