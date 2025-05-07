# app/api/v1/endpoints/budgets.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid # Для budget_id

from app import schemas # Это работает, т.к. есть app/schemas/__init__.py
from app import crud    # Это работает, т.к. есть app/crud/__init__.py
from app.db import models # Импортируем подмодуль models из app.db
from app.api.v1 import deps # Импортируем наши зависимости (сессия БД и аутентификация)

router = APIRouter()

@router.post(
    "/",
    response_model=schemas.Budget, # Схема для ответа
    status_code=status.HTTP_201_CREATED # Статус код для успешного создания
)
async def create_budget(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    budget_in: schemas.BudgetCreate, # Данные для создания из тела запроса (валидируются FastAPI)
    auth_context: deps.AuthContext = Depends(deps.get_auth_context) # Получаем пользователя и контекст чата
):
    """
    Создать новый бюджет.
    Бюджет будет привязан либо к текущему пользователю (если личный контекст),
    либо к текущему чату (если групповой контекст).
    """
    # Вызываем CRUD функцию для создания бюджета, передавая владельца из контекста
    try:
        budget = await crud.crud_budget.create_budget_with_owner(
            db=db,
            obj_in=budget_in,
            owner_user_id=auth_context.owner_user_id,
            owner_chat_id=auth_context.owner_chat_id
        )
        # Коммит произойдет в get_async_db
        return budget # FastAPI автоматически преобразует в JSON по схеме schemas.Budget
    except ValueError as e: # Ловим ошибку из create_budget_with_owner, если владелец не определен
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e: # Ловим другие возможные ошибки БД
        # TODO: Логирование ошибки e
        print(f"Error creating budget: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create budget")


@router.get(
    "/",
    response_model=List[schemas.Budget] # Возвращаем список бюджетов
)
async def read_budgets(
    db: AsyncSession = Depends(deps.get_async_db),
    auth_context: deps.AuthContext = Depends(deps.get_auth_context),
    skip: int = 0, # Параметр для пагинации
    limit: int = 100 # Параметр для пагинации
):
    """
    Получить список бюджетов, доступных текущему пользователю в текущем контексте
    (либо личные бюджеты, либо бюджеты текущего группового чата).
    """
    try:
        budgets = await crud.crud_budget.get_budgets_by_owner(
            db=db,
            owner_user_id=auth_context.owner_user_id,
            owner_chat_id=auth_context.owner_chat_id,
            skip=skip,
            limit=limit
        )
        # Объекты BudgetModel уже содержат вычисленные поля total_expense, total_income, balance
        return budgets # FastAPI преобразует список по схеме schemas.Budget
    except Exception as e:
        # TODO: Логирование ошибки e
        print(f"Error reading budgets: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve budgets")

@router.get(
    "/{budget_id}",
    response_model=schemas.Budget # Возвращаем один бюджет
)
async def read_budget(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    budget_id: uuid.UUID, # Получаем ID из пути URL
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Получить конкретный бюджет по его ID.
    Проверяет, имеет ли текущий пользователь/чат доступ к этому бюджету.
    """
    try:
        budget = await crud.crud_budget.get_budget(db=db, budget_id=budget_id)
    except Exception as e:
         # TODO: Логирование ошибки e
        print(f"Error reading budget {budget_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve budget details")

    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

    # Проверка авторизации: принадлежит ли найденный бюджет текущему пользователю или чату
    if not (
        (auth_context.owner_user_id and budget.owner_user_id == auth_context.owner_user_id) or
        (auth_context.owner_chat_id and budget.owner_chat_id == auth_context.owner_chat_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    # budget уже содержит вычисленные поля total_expense, total_income, balance
    return budget

@router.put(
    "/{budget_id}",
    response_model=schemas.Budget # Возвращаем обновленный бюджет
)
async def update_budget(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    budget_id: uuid.UUID,
    budget_in: schemas.BudgetUpdate, # Данные для обновления (валидируются)
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Обновить бюджет по ID.
    Проверяет права доступа перед обновлением.
    """
    try:
        # Сначала получаем бюджет, чтобы проверить права доступа
        db_budget = await crud.crud_budget.get_budget(db=db, budget_id=budget_id)
        if not db_budget:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

        # Проверка авторизации
        if not (
            (auth_context.owner_user_id and db_budget.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and db_budget.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

        # Выполняем обновление
        updated_budget = await crud.crud_budget.update_budget(db=db, db_obj=db_budget, obj_in=budget_in)
        
        # Перезагружаем бюджет с обновленными суммами для корректного ответа
        # Это немного избыточно, т.к. update_budget сам возвращает объект,
        # но get_budget гарантирует пересчет баланса, если total_amount изменился.
        # Альтернатива: передать обновленные поля в get_budget или сделать пересчет в update_budget.
        # Пока оставим так для надежности.
        refreshed_budget = await crud.crud_budget.get_budget(db=db, budget_id=updated_budget.id)
        if not refreshed_budget: # На всякий случай
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve updated budget")
             
        return refreshed_budget

    except HTTPException as e:
        raise e # Пробрасываем HTTP исключения дальше
    except Exception as e:
        # TODO: Логирование ошибки e
        print(f"Error updating budget {budget_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update budget")


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT # Стандартный статус для успешного DELETE без тела ответа
)
async def delete_budget(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    budget_id: uuid.UUID,
    auth_context: deps.AuthContext = Depends(deps.get_auth_context)
):
    """
    Удалить бюджет по ID.
    Проверяет права доступа перед удалением.
    Каскадно удалит связанные категории и транзакции.
    """
    try:
         # Сначала получаем бюджет, чтобы проверить права доступа
        db_budget = await crud.crud_budget.get_budget(db=db, budget_id=budget_id)
        if not db_budget:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

        # Проверка авторизации
        if not (
            (auth_context.owner_user_id and db_budget.owner_user_id == auth_context.owner_user_id) or
            (auth_context.owner_chat_id and db_budget.owner_chat_id == auth_context.owner_chat_id)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

        # Выполняем удаление
        deleted_budget = await crud.crud_budget.remove_budget(db=db, budget_id=budget_id)
        if not deleted_budget: # Дополнительная проверка, хотя get_budget выше уже проверил
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found during deletion attempt")
        
        # Ответ без тела со статусом 204
        return None # FastAPI вернет 204 No Content

    except HTTPException as e:
        raise e
    except Exception as e:
        # TODO: Логирование ошибки e
        print(f"Error deleting budget {budget_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete budget")