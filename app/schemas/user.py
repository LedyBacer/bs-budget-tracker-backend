# app/schemas/user.py
from pydantic import BaseModel, HttpUrl
from typing import Optional
# import uuid # Хотя ID пользователя BigInteger, UUID может понадобиться для других ID

class UserBase(BaseModel):
    # Поля, которые мы получаем из Telegram initData и хотим хранить
    # ID не здесь, т.к. он будет либо путем для GET, либо частью initData
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = False
    photo_url: Optional[HttpUrl] = None

class UserCreate(UserBase):
    id: int # Telegram User ID

class UserUpdate(BaseModel): # Для обновления пользователя, если понадобится
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None
    photo_url: Optional[HttpUrl] = None

class UserInDBBase(UserBase):
    id: int # Telegram User ID

    class Config:
        from_attributes = True # Позволяет Pydantic работать с ORM объектами (например, SQLAlchemy)

# Схема для отображения пользователя (может включать связанные данные в будущем)
class User(UserInDBBase):
    pass

# Схема для внутреннего использования, если нужно хранить пользователя в БД
class UserInDB(UserInDBBase):
    pass