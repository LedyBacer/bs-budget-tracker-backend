# app/db/base_class.py
from typing import Any
from sqlalchemy.orm import declarative_base # Используйте declarative_base из sqlalchemy.orm
# from sqlalchemy.ext.declarative import as_declarative, declared_attr # Это более старый способ

# @as_declarative() # Можно использовать это или declarative_base()
# class Base:
#     id: Any
#     __name__: str
#
#     @declared_attr
#     def __tablename__(cls) -> str:
#         # ... ваша логика именования ...
#         # Для простоты, давайте вернемся к явному указанию __tablename__ в каждой модели
#         # и сделаем Base максимально простым
#         pass

Base = declarative_base() # Это более современный и простой способ