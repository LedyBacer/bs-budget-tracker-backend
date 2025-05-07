# app/api/v1/endpoints/transactions.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Path # Добавили Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Any
import uuid
from datetime import date # Для фильтрации по дате

from app import schemas # Это работает, т.к. есть app/schemas/__init__.py
from app import crud    # Это работает, т.к. есть app/crud/__init__.py
from app.db import models # Импортируем подмодуль models из app.db
from app.api.v1 import deps
from app.db.models.transaction import TransactionType

router = APIRouter()

# --- Вспомогательная зависимость для проверки доступа к бюджету для транзакций ---
# (Аналогична той, что в categories.py, можно было бы вынести в deps.py)
async def get_budget_for_transaction_operations(
    budget_id: uuid.UUID = Path(..., description="ID бюджета для транзакций"),
    db: AsyncSession = Depends(deps.get_async_db),
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
) -> models.Budget:
    budget = await crud.crud_budget.get_budget(db=db, budget_id=budget_id)
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget not found")
    if not (
        (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
        (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the budget")
    return budget

# --- Эндпоинты ---

@router.post(
    "/budgets/{budget_id}/transactions/", # Путь для создания транзакции в бюджете
    response_model=schemas.Transaction,
    status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    *,
    budget: models.Budget = Depends(get_budget_for_transaction_operations), # Проверяем доступ к бюджету
    transaction_in: schemas.TransactionCreate, # Данные из тела запроса
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user) # Получаем текущего пользователя как автора
):
    """
    Создать новую транзакцию для указанного бюджета.
    Автор транзакции - текущий аутентифицированный пользователь.
    Суммы в бюджете и категории будут обновлены.
    """
    # Дополнительная проверка: существует ли указанная категория и принадлежит ли она этому бюджету
    category = await crud.crud_category.get_category(db=db, category_id=transaction_in.category_id)
    if not category or category.budget_id != budget.id:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Или 400 Bad Request
            detail="Category not found or does not belong to this budget"
        )

    try:
        transaction = await crud.crud_transaction.create_transaction(
            db=db,
            obj_in=transaction_in,
            author_user_id=current_user.id, # ID автора
            budget_id=budget.id # ID бюджета
        )
        # get_transaction внутри CRUD должен был загрузить author и category
        # Если нет, нужно будет загрузить их здесь перед возвратом
        # Но create_transaction уже делает refresh
        
        # Добавим category_name для ответа
        if transaction.category:
             transaction.category_name = transaction.category.name
        else: # На всякий случай, если категория не загрузилась
             cat_temp = await crud.crud_category.get_category(db=db, category_id=transaction.category_id)
             transaction.category_name = cat_temp.name if cat_temp else "N/A"

        # Author уже должен быть загружен через refresh в CRUD
        if not hasattr(transaction, 'author') or not transaction.author:
             usr_temp = await crud.crud_user.get_user(db=db, user_id=transaction.author_user_id)
             setattr(transaction, 'author', usr_temp) # Устанавливаем атрибут для схемы

        return transaction # FastAPI сериализует по schemas.Transaction
    except Exception as e:
        print(f"Error creating transaction for budget {budget.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create transaction")


@router.get(
    "/budgets/{budget_id}/transactions/", # Путь для получения списка транзакций
    response_model=schemas.TransactionListResponse # Новая схема для ответа со списком и total_count
)
async def read_transactions(
    *,
    budget: models.Budget = Depends(get_budget_for_transaction_operations), # Проверяем доступ к бюджету
    db: AsyncSession = Depends(deps.get_async_db),
    skip: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(10, gt=0, le=200, description="Лимит записей на страницу"),
    # Фильтры (как query параметры)
    category_id: Optional[uuid.UUID] = Query(None, description="Фильтр по ID категории"),
    author_user_id: Optional[int] = Query(None, description="Фильтр по ID автора (Telegram User ID)"),
    type: Optional[TransactionType] = Query(None, description="Фильтр по типу (expense или income)"), # Используем импортированный Enum FastAPI сам проверит Enum
    start_date: Optional[date] = Query(None, description="Начальная дата для фильтра (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Конечная дата для фильтра (YYYY-MM-DD)"),
):
    """
    Получить список транзакций для бюджета с фильтрацией и пагинацией.
    """
    filters = {
        "category_id": category_id,
        "author_user_id": author_user_id,
        "type": type.value if type else None, # Передаем значение Enum или None
        "start_date": str(start_date) if start_date else None, # Передаем строку
        "end_date": str(end_date) if end_date else None,
    }
    # Убираем None значения из фильтров
    active_filters = {k: v for k, v in filters.items() if v is not None}

    try:
        transactions_list, total_count = await crud.crud_transaction.get_transactions_by_budget(
            db=db,
            budget_id=budget.id,
            skip=skip,
            limit=limit,
            filters=active_filters
        )
        
        # Подготавливаем транзакции для ответа (добавляем category_name)
        transactions_for_response: List[schemas.Transaction] = []
        for trans in transactions_list:
            # Создаем Pydantic объект Transaction из объекта SQLAlchemy
            # category_name и author должны были быть загружены через joinedload в CRUD
            author_info = None
            if trans.author_user:
                 author_info = schemas.TransactionAuthorInfo.model_validate(trans.author_user) # Используем model_validate

            trans_schema = schemas.Transaction.model_validate(trans) # Валидация и создание схемы из модели
            trans_schema.author = author_info
            trans_schema.category_name = trans.category.name if trans.category else "N/A"
            transactions_for_response.append(trans_schema)

        return schemas.TransactionListResponse(
            transactions=transactions_for_response,
            total_count=total_count
        )
    except Exception as e:
        print(f"Error reading transactions for budget {budget.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve transactions")

# --- Эндпоинты для работы с конкретной транзакцией ---

@router.get(
    "/transactions/{transaction_id}", # Путь к конкретной транзакции
    response_model=schemas.Transaction
)
async def read_transaction(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    transaction_id: uuid.UUID,
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Получить транзакцию по её ID.
    Проверяет доступ к родительскому бюджету.
    """
    try:
        transaction = await crud.crud_transaction.get_transaction(db=db, transaction_id=transaction_id)
    except Exception as e:
        print(f"Error reading transaction {transaction_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve transaction")

    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Проверяем доступ через родительский бюджет
    budget = await crud.crud_budget.get_budget(db=db, budget_id=transaction.budget_id)
    if not budget:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for transaction not found")
    if not (
        (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
        (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the transaction's budget")

    # Добавляем category_name и author для ответа
    author_info = None
    if transaction.author_user:
            author_info = schemas.TransactionAuthorInfo.model_validate(transaction.author_user)
    
    trans_schema = schemas.Transaction.model_validate(transaction)
    trans_schema.author = author_info
    trans_schema.category_name = transaction.category.name if transaction.category else "N/A"

    return trans_schema


@router.put(
    "/transactions/{transaction_id}", # Путь для обновления транзакции
    response_model=schemas.Transaction
)
async def update_transaction(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    transaction_id: uuid.UUID,
    transaction_in: schemas.TransactionUpdate, # Данные для обновления
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Обновить транзакцию по ID.
    Проверяет права доступа через родительский бюджет.
    Пересчитывает суммы в связанных бюджетах/категориях.
    """
    try:
        # Получаем транзакцию и проверяем доступ к бюджету
        db_transaction = await crud.crud_transaction.get_transaction(db=db, transaction_id=transaction_id)
        if not db_transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

        budget = await crud.crud_budget.get_budget(db=db, budget_id=db_transaction.budget_id)
        if not budget:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for transaction not found")
        if not (
            (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the transaction's budget")
            
        # Проверяем новую категорию, если она меняется
        if transaction_in.category_id and transaction_in.category_id != db_transaction.category_id:
             new_category = await crud.crud_category.get_category(db=db, category_id=transaction_in.category_id)
             if not new_category or new_category.budget_id != budget.id:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail="New category not found or does not belong to this budget"
                  )

        # Выполняем обновление
        updated_transaction = await crud.crud_transaction.update_transaction(
            db=db, db_obj=db_transaction, obj_in=transaction_in
        )
        if not updated_transaction: # На случай, если CRUD вернет None (хотя он не должен при успехе)
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update transaction")

        # Добавляем category_name и author для ответа
        author_info = None
        if updated_transaction.author_user:
             author_info = schemas.TransactionAuthorInfo.model_validate(updated_transaction.author_user)
        
        trans_schema = schemas.Transaction.model_validate(updated_transaction)
        trans_schema.author = author_info
        trans_schema.category_name = updated_transaction.category.name if updated_transaction.category else "N/A"
        
        return trans_schema

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error updating transaction {transaction_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update transaction")


@router.delete(
    "/transactions/{transaction_id}", # Путь для удаления транзакции
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_transaction(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    transaction_id: uuid.UUID,
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Удалить транзакцию по ID.
    Проверяет права доступа через родительский бюджет.
    Пересчитывает суммы в связанных бюджете/категории.
    """
    try:
        # Получаем транзакцию для проверки доступа и для получения ID для пересчета сумм
        db_transaction = await crud.crud_transaction.get_transaction(db=db, transaction_id=transaction_id)
        if not db_transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

        # Проверяем доступ к бюджету
        budget = await crud.crud_budget.get_budget(db=db, budget_id=db_transaction.budget_id)
        if not budget:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for transaction not found")
        if not (
            (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the transaction's budget")

        # Выполняем удаление
        deleted_transaction = await crud.crud_transaction.remove_transaction(db=db, transaction_id=transaction_id)
        if not deleted_transaction:
            # Эта проверка может быть избыточной, если get_transaction выше отработал
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found during deletion attempt")
        
        return None # Ответ 204 No Content

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error deleting transaction {transaction_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete transaction")