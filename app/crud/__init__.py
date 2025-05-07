# app/crud/__init__.py
from . import crud_user
from . import crud_chat # Добавим, когда создадим crud_chat.py
from . import crud_budget # Добавим, когда создадим crud_budget.py
from . import crud_category # Добавим, когда создадим crud_category.py
from . import crud_transaction # Добавим, когда создадим crud_transaction.py

# Или можно экспортировать конкретные функции/объекты, если удобнее
# from .crud_user import get_user, create_user, ...