# app/crud/crud_category.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, case
from typing import Optional, List, Union
import uuid

from app.db.models.category import Category as CategoryModel
from app.db.models.transaction import Transaction as TransactionModel, TransactionType
from app.schemas.category import CategoryCreate, CategoryUpdate # CategorySchema для ответа не импортируем, будем возвращать модель

# --- Read Operations ---

async def get_category(db: AsyncSession, category_id: uuid.UUID) -> Optional[CategoryModel]:
    """
    Получить категорию по ее ID.
    Вычисляет spent, income, balance, progress, transaction_count.
    """
    stmt = (
        select(
            CategoryModel,
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.expense, TransactionModel.amount), else_=0.0)
            ), 0.0).label("calculated_spent"),
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.income, TransactionModel.amount), else_=0.0)
            ), 0.0).label("calculated_income"),
            func.coalesce(func.count(TransactionModel.id), 0).label("calculated_transaction_count")
        )
        .outerjoin(TransactionModel, CategoryModel.id == TransactionModel.category_id)
        .filter(CategoryModel.id == category_id)
        .group_by(CategoryModel.id) # Группировка по PK категории достаточна
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if row:
        category, spent, income, transaction_count = row
        category.spent = float(spent)
        category.income = float(income)
        category.balance = float(category.limit_amount) - category.spent + category.income
        category.transaction_count = int(transaction_count)
        if float(category.limit_amount) > 0:
            # Прогресс считаем как (лимит - баланс) / лимит, т.е. сколько потрачено от лимита.
            # Или (потрачено_реально / лимит), если баланс может быть положительным из-за доходов.
            # Для простоты, если баланс < 0, это 100% прогресс (или больше, если разрешено превышение).
            # Если spent > limit, то прогресс > 100%. Ограничим 100% или оставим как есть?
            # Ваша mockData считала: progress = category.limit > 0 ? Math.min(100, Math.max(0, (category.balance / category.limit) * 100)) : 0;
            # Это было (остаток / лимит). Если хотим (потрачено / лимит):
            category.progress = min(100.0, max(0.0, (category.spent / float(category.limit_amount)) * 100)) if category.spent >0 else 0.0
        else:
            category.progress = 0.0 # Если лимит 0, прогресс 0
        return category
    return None

async def get_categories_by_budget_id(
    db: AsyncSession,
    *,
    budget_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100 # Может быть, для категорий пагинация не так важна, но оставим
) -> List[CategoryModel]:
    """
    Получить список категорий для указанного бюджета.
    Вычисляет суммы и счетчики для каждой категории.
    """
    # Подзапрос для агрегации данных транзакций по категориям
    transaction_agg_subquery = (
        select(
            TransactionModel.category_id,
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.expense, TransactionModel.amount), else_=0.0)
            ), 0.0).label("total_spent"),
            func.coalesce(func.sum(
                case((TransactionModel.type == TransactionType.income, TransactionModel.amount), else_=0.0)
            ), 0.0).label("total_income"),
            func.coalesce(func.count(TransactionModel.id), 0).label("transaction_count_val")
        )
        .group_by(TransactionModel.category_id)
        .subquery()
    )

    # Основной запрос к категориям
    stmt = (
        select(
            CategoryModel,
            transaction_agg_subquery.c.total_spent,
            transaction_agg_subquery.c.total_income,
            transaction_agg_subquery.c.transaction_count_val
        )
        .outerjoin(transaction_agg_subquery, CategoryModel.id == transaction_agg_subquery.c.category_id)
        .filter(CategoryModel.budget_id == budget_id)
        .order_by(CategoryModel.name) # Сортируем по имени для предсказуемого порядка
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    raw_categories = result.all()

    categories_with_details: List[CategoryModel] = []
    for row in raw_categories:
        category, spent, income, transaction_count = row
        category.spent = float(spent if spent is not None else 0.0)
        category.income = float(income if income is not None else 0.0)
        category.balance = float(category.limit_amount) - category.spent + category.income
        category.transaction_count = int(transaction_count if transaction_count is not None else 0)

        if float(category.limit_amount) > 0:
            category.progress = min(100.0, max(0.0, (category.spent / float(category.limit_amount)) * 100)) if category.spent > 0 else 0.0
        else:
            category.progress = 0.0
        
        categories_with_details.append(category)
        
    return categories_with_details

# --- Create Operation ---

async def create_category(
    db: AsyncSession,
    *,
    obj_in: CategoryCreate, # Схема Pydantic
    budget_id: uuid.UUID
) -> CategoryModel:
    """
    Создать новую категорию для указанного бюджета.
    """
    db_obj = CategoryModel(
        name=obj_in.name,
        limit_amount=obj_in.limit_amount,
        budget_id=budget_id
    )
    db.add(db_obj)
    await db.flush()  # Генерируем ID и временные метки
    # Устанавливаем начальные значения для полей, ожидаемых схемой Category
    db_obj.spent = 0.0
    db_obj.income = 0.0
    db_obj.balance = float(db_obj.limit_amount) # Начальный баланс равен лимиту
    db_obj.progress = 0.0
    db_obj.transaction_count = 0
    return db_obj

# --- Update Operation ---

async def update_category(
    db: AsyncSession,
    *,
    db_obj: CategoryModel, # Существующий объект CategoryModel из БД
    obj_in: Union[CategoryUpdate, dict] # Pydantic схема или словарь
) -> CategoryModel:
    """
    Обновить существующую категорию.
    """
    if isinstance(obj_in, dict):
        update_data = obj_in
    else:
        update_data = obj_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(db_obj, field):
            setattr(db_obj, field, value)
    
    db.add(db_obj)
    # Коммит и refresh будут в get_async_db.
    # Вычисляемые поля (spent, income, balance, progress, transaction_count)
    # будут обновлены при следующем чтении через get_category или get_categories_by_budget_id.
    # Если нужно вернуть их обновленными сразу после update, то логику вычисления нужно добавить сюда,
    # что усложнит функцию update. Пока оставим пересчет при чтении.
    return db_obj

# --- Delete Operation ---

async def remove_category(db: AsyncSession, *, category_id: uuid.UUID) -> Optional[CategoryModel]:
    """
    Удалить категорию по ID.
    Транзакции, связанные с этой категорией, также будут удалены из-за cascade в модели.
    """
    # Перед удалением проверим, нет ли у категории транзакций (как в вашем mockApi)
    # Хотя cascade в модели должен справиться, бизнес-логика может требовать такой проверки.
    # Для упрощения пока полагаемся на cascade. Если нужна проверка - нужно добавить запрос к TransactionModel.
    # Например, как в mockApi:
    # count_result = await db.execute(select(func.count(TransactionModel.id)).filter(TransactionModel.category_id == category_id))
    # transaction_count_for_category = count_result.scalar_one_or_none()
    # if transaction_count_for_category and transaction_count_for_category > 0:
    #     raise ValueError("Нельзя удалить категорию, по ней есть транзакции.")
        # Или можно возвращать специальный код/сообщение, чтобы API обработал это

    db_obj = await get_category(db, category_id=category_id) # get_category уже вычисляет суммы, это ок
    if db_obj:
        await db.delete(db_obj)
        # Коммит будет в get_async_db
        return db_obj
    return None