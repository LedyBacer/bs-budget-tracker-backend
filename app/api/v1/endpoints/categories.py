# app/api/v1/endpoints/categories.py
from fastapi import APIRouter, Depends, HTTPException, status, Path # Добавили Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid

from app import schemas # Это работает, т.к. есть app/schemas/__init__.py
from app import crud    # Это работает, т.к. есть app/crud/__init__.py
from app.db import models # Импортируем подмодуль models из app.db
from app.api.v1 import deps

# Создаем отдельный роутер для категорий.
# Префикс и теги лучше задавать при подключении в api.py, но можно и здесь для ясности.
router = APIRouter()

# --- Вспомогательная зависимость для проверки доступа к бюджету ---
async def get_budget_for_category_operations(
    budget_id: uuid.UUID = Path(..., description="ID бюджета, к которому относится категория"), # Получаем из пути
    db: AsyncSession = Depends(deps.get_async_db),
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
) -> models.Budget:
    """
    Проверяет существование бюджета и права доступа к нему
    для операций с категориями этого бюджета.
    Возвращает объект бюджета, если все в порядке.
    """
    budget = await crud.crud_budget.get_budget(db=db, budget_id=budget_id)
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget not found")

    # Проверка авторизации: принадлежит ли бюджет текущему пользователю или чату
    if not (
        (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
        (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the parent budget")
    
    return budget

# --- Эндпоинты ---

@router.post(
    "/budgets/{budget_id}/categories/", # Обратите внимание на путь
    response_model=schemas.Category,
    status_code=status.HTTP_201_CREATED
)
async def create_category(
    *,
    # budget_id берется из пути и проверяется зависимостью get_budget_for_category_operations
    budget: models.Budget = Depends(get_budget_for_category_operations), # Получаем проверенный бюджет
    category_in: schemas.CategoryCreate, # Данные для создания категории
    db: AsyncSession = Depends(deps.get_async_db),
    # auth_context здесь не нужен явно, т.к. проверка уже в get_budget_for_category_operations
):
    """
    Создать новую категорию для указанного бюджета.
    Права доступа к бюджету проверяются автоматически.
    """
    try:
        # Бюджет уже проверен на доступ зависимостью
        category = await crud.crud_category.create_category(
            db=db,
            obj_in=category_in,
            budget_id=budget.id # Передаем ID проверенного бюджета
        )
        # Коммит в get_async_db
        return category
    except Exception as e:
        # TODO: Логирование ошибки e
        print(f"Error creating category for budget {budget.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create category")


@router.get(
    "/budgets/{budget_id}/categories/", # Путь для получения списка категорий бюджета
    response_model=List[schemas.Category]
)
async def read_categories(
    *,
    # budget_id берется из пути и проверяется зависимостью
    budget: models.Budget = Depends(get_budget_for_category_operations), # Проверяем доступ к бюджету
    db: AsyncSession = Depends(deps.get_async_db),
    skip: int = 0,
    limit: int = 100 # Или убрать пагинацию для категорий, если их обычно немного
):
    """
    Получить список категорий для указанного бюджета.
    Права доступа к бюджету проверяются автоматически.
    """
    try:
        categories = await crud.crud_category.get_categories_by_budget_id(
            db=db,
            budget_id=budget.id,
            skip=skip,
            limit=limit
        )
        # Объекты CategoryModel уже содержат вычисленные поля
        return categories
    except Exception as e:
        # TODO: Логирование ошибки e
        print(f"Error reading categories for budget {budget.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve categories")

# Эндпоинты для работы с конкретной категорией (PUT, DELETE, GET)
# Здесь нам нужен ID самой категории

@router.get(
    "/categories/{category_id}", # Путь для получения конкретной категории
    response_model=schemas.Category
)
async def read_category(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    category_id: uuid.UUID,
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Получить категорию по её ID.
    Проверяет, имеет ли пользователь/чат доступ к родительскому бюджету этой категории.
    """
    try:
        category = await crud.crud_category.get_category(db=db, category_id=category_id)
    except Exception as e:
        print(f"Error reading category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve category")

    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Проверяем доступ через родительский бюджет
    # Нужно загрузить бюджет или проверить budget_id категории
    # Проще проверить budget_id напрямую
    budget_check = await crud.crud_budget.get_budget(db=db, budget_id=category.budget_id)
    if not budget_check:
         # Странная ситуация: категория есть, а бюджета нет. Возможно, ошибка данных.
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for category not found")

    # Проверка авторизации на бюджет
    if not (
        (auth_context.owner_user_id and budget_check.owner_user_id == auth_context.owner_user_id) or
        (auth_context.owner_chat_id and budget_check.owner_chat_id == auth_context.owner_chat_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the category's budget")

    # category уже содержит вычисленные поля
    return category


@router.put(
    "/categories/{category_id}", # Путь для обновления категории
    response_model=schemas.Category
)
async def update_category(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    category_id: uuid.UUID,
    category_in: schemas.CategoryUpdate, # Данные для обновления
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Обновить категорию по ID.
    Проверяет права доступа через родительский бюджет.
    """
    try:
        # Сначала получаем категорию и проверяем доступ к ее бюджету
        db_category = await crud.crud_category.get_category(db=db, category_id=category_id)
        if not db_category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

        # Проверяем доступ к бюджету
        budget_check = await crud.crud_budget.get_budget(db=db, budget_id=db_category.budget_id)
        if not budget_check:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for category not found")
        if not (
            (auth_context.owner_user_id and budget_check.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and budget_check.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the category's budget")

        # Выполняем обновление
        updated_category = await crud.crud_category.update_category(db=db, db_obj=db_category, obj_in=category_in)
        
        # Перезагружаем категорию с обновленными суммами для ответа
        refreshed_category = await crud.crud_category.get_category(db=db, category_id=updated_category.id)
        if not refreshed_category:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve updated category")
             
        return refreshed_category

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error updating category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update category")

@router.delete(
    "/categories/{category_id}", # Путь для удаления категории
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_category(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    category_id: uuid.UUID,
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Удалить категорию по ID.
    Проверяет права доступа через родительский бюджет.
    Каскадно удалит связанные транзакции (если настроено в модели).
    """
    try:
        # Получаем категорию для проверки доступа к бюджету
        db_category = await crud.crud_category.get_category(db=db, category_id=category_id)
        if not db_category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

        # Проверяем доступ к бюджету
        budget_check = await crud.crud_budget.get_budget(db=db, budget_id=db_category.budget_id)
        if not budget_check:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent budget for category not found")
        if not (
            (auth_context.owner_user_id and budget_check.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and budget_check.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for the category's budget")

        # Выполняем удаление
        # Учитываем возможную проверку на транзакции внутри crud.remove_category
        try:
            deleted_category = await crud.crud_category.remove_category(db=db, category_id=category_id)
        except ValueError as ve: # Ловим ошибку, если CRUD запретил удаление (например, из-за транзакций)
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))

        if not deleted_category: # Если CRUD вернул None (хотя проверка выше должна была это отловить)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found during deletion attempt")
            
        return None # Ответ 204 No Content

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error deleting category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete category")