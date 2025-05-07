# app/crud/crud_budget.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, subqueryload
from sqlalchemy import func, case
from typing import Optional, List, Union
import uuid

from app.db.models.budget import Budget as BudgetModel
from app.db.models.transaction import Transaction as TransactionModel, TransactionType
from app.schemas.budget import BudgetCreate, BudgetUpdate, Budget as BudgetSchema # Импортируем схему ответа Budget

# --- Read Operations ---

async def get_budget(db: AsyncSession, budget_id: uuid.UUID) -> Optional[BudgetModel]:
    """
    Получить бюджет по его ID.
    Загружает связанные транзакции для вычисления сумм.
    """
    # stmt = select(BudgetModel).options(selectinload(BudgetModel.transactions)).filter(BudgetModel.id == budget_id)
    # result = await db.execute(stmt)
    # budget = result.scalar_one_or_none()
    
    # Более эффективный способ получить сам бюджет и суммы транзакций одним запросом
    stmt = (
        select(
            BudgetModel,
            func.coalesce(func.sum(
                case(
                    (TransactionModel.type == TransactionType.expense, TransactionModel.amount),
                    else_=0
                )
            ), 0.0).label("calculated_total_expense"), # Используем coalesce для обработки NULL
            func.coalesce(func.sum(
                case(
                    (TransactionModel.type == TransactionType.income, TransactionModel.amount),
                    else_=0
                )
            ), 0.0).label("calculated_total_income")
        )
        .outerjoin(TransactionModel, BudgetModel.id == TransactionModel.budget_id)
        .filter(BudgetModel.id == budget_id)
        .group_by(BudgetModel.id) # Убедимся, что группировка корректна для всех полей BudgetModel
                                   # или только по BudgetModel.id, если остальные поля функционально зависимы.
                                   # Для PostgreSQL, если BudgetModel.id - PK, то группировки по нему достаточно.
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if row:
        budget, total_expense, total_income = row
        # Присваиваем атрибуты с именами, как в схеме Pydantic Budget
        budget.total_expense = float(total_expense) # Явное приведение к float, т.к. sum может вернуть Decimal
        budget.total_income = float(total_income)
        budget.balance = float(budget.total_amount) - budget.total_expense + budget.total_income # total_amount уже float в модели
        return budget
    return None


async def get_budgets_by_owner(
    db: AsyncSession,
    *,
    owner_user_id: Optional[int] = None,
    owner_chat_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[BudgetModel]:
    """
    Получить список бюджетов для указанного владельца (пользователя или чата).
    Вычисляет суммы для каждого бюджета.
    """
    if not owner_user_id and not owner_chat_id:
        # Должен быть указан хотя бы один владелец
        return []

    # Базовый запрос для агрегации транзакций
    transaction_sums_subquery = (
        select(
            TransactionModel.budget_id,
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.expense, TransactionModel.amount), else_=0)
            ), 0.0).label("total_expense"), # Используем coalesce
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.income, TransactionModel.amount), else_=0)
            ), 0.0).label("total_income") # Используем coalesce
        )
        .group_by(TransactionModel.budget_id)
        .subquery()
    )

    # Основной запрос к бюджетам
    stmt = (
        select(BudgetModel, transaction_sums_subquery.c.total_expense, transaction_sums_subquery.c.total_income)
        .outerjoin(transaction_sums_subquery, BudgetModel.id == transaction_sums_subquery.c.budget_id)
    )

    if owner_user_id:
        stmt = stmt.filter(BudgetModel.owner_user_id == owner_user_id)
    elif owner_chat_id:
        stmt = stmt.filter(BudgetModel.owner_chat_id == owner_chat_id)
    stmt = stmt.order_by(BudgetModel.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    raw_budgets = result.all()

    budgets_with_sums: List[BudgetModel] = []
    for row in raw_budgets:
        budget, total_expense, total_income = row
        # Присваиваем атрибуты с именами, как в схеме Pydantic Budget
        budget.total_expense = float(total_expense if total_expense is not None else 0.0)
        budget.total_income = float(total_income if total_income is not None else 0.0)
        budget.balance = float(budget.total_amount) - budget.total_expense + budget.total_income
        budgets_with_sums.append(budget)
        
    return budgets_with_sums


# --- Create Operation ---

async def create_budget_with_owner(
    db: AsyncSession,
    *,
    obj_in: BudgetCreate,
    owner_user_id: Optional[int] = None,
    owner_chat_id: Optional[int] = None
) -> BudgetModel:
    if not (owner_user_id is None) ^ (owner_chat_id is None):
         raise ValueError("Either owner_user_id or owner_chat_id must be provided, but not both, and one must be not None.")

    db_obj = BudgetModel(
        name=obj_in.name,
        total_amount=obj_in.total_amount,
        owner_user_id=owner_user_id,
        owner_chat_id=owner_chat_id
    )
    db.add(db_obj)

    try:
        await db.flush()
        await db.refresh(db_obj)
    except Exception as e:
         print(f"Error during flush/refresh after adding budget: {e}")
         raise

    # Проверка полей после refresh
    if db_obj.id is None or db_obj.created_at is None or db_obj.updated_at is None:
        print("Warning: Budget object missing id/created_at/updated_at after refresh.")
        await db.refresh(db_obj)
        if db_obj.id is None or db_obj.created_at is None or db_obj.updated_at is None:
             raise ValueError("Failed to load generated fields for the new budget.")

    # Устанавливаем/вычисляем поля для Pydantic схемы ПОСЛЕ refresh
    # total_expense и total_income должны быть 0 по умолчанию из БД
    db_obj.total_expense = float(db_obj.current_total_expense)
    db_obj.total_income = float(db_obj.current_total_income)
    # Вычисляем баланс на основе total_amount и текущих (нулевых) сумм
    db_obj.balance = float(db_obj.total_amount) - db_obj.total_expense + db_obj.total_income

    return db_obj

# --- Update Operation ---

async def update_budget(
    db: AsyncSession,
    *,
    db_obj: BudgetModel, # Существующий объект BudgetModel из БД
    obj_in: Union[BudgetUpdate, dict] # Pydantic схема или словарь с данными для обновления
) -> BudgetModel:
    """
    Обновить существующий бюджет.
    """
    if isinstance(obj_in, dict):
        update_data = obj_in
    else:
        update_data = obj_in.model_dump(exclude_unset=True) # Только поля, которые были переданы

    for field, value in update_data.items():
        if hasattr(db_obj, field):
            setattr(db_obj, field, value)
    
    db.add(db_obj)
    # Коммит и refresh будут в get_async_db
    # После обновления нужно будет пересчитать баланс, если total_amount изменился
    # Но если изменились транзакции, то баланс тоже изменится.
    # Пересчет баланса лучше делать при запросе get_budget или get_budgets_by_owner,
    # так как он зависит от транзакций.
    # Однако, если total_amount изменился, а транзакций нет, то balance_val должен отразить это.
    # Для простоты, мы будем полагаться на пересчет в get_budget/get_budgets_by_owner.
    # Или можно добавить логику пересчета сюда, если это критично для возвращаемого объекта сразу после update.
    # Пока оставим так, что `updated_at` обновится автоматически.
    return db_obj

# --- Delete Operation ---

async def remove_budget(db: AsyncSession, *, budget_id: uuid.UUID) -> Optional[BudgetModel]:
    """
    Удалить бюджет по ID.
    """
    # Сначала получаем бюджет, чтобы вернуть его (и для проверки существования)
    # Каскадное удаление категорий и транзакций настроено в моделях
    db_obj = await get_budget(db, budget_id=budget_id) # get_budget уже вычисляет суммы, но это не страшно
    if db_obj:
        await db.delete(db_obj)
        # Коммит будет в get_async_db
        return db_obj
    return None