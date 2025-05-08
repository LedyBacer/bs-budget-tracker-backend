# app/crud/crud_transaction.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import update as sqlalchemy_update, delete as sqlalchemy_delete
from sqlalchemy import func, case, desc, and_ # Добавили and_
from typing import Optional, List, Union, Dict, Any, Tuple # Добавили Tuple
from datetime import datetime, date # Добавили date
import uuid
from decimal import Decimal # Используем Decimal для точности

from app.db.models.transaction import Transaction as TransactionModel, TransactionType
from app.db.models.budget import Budget as BudgetModel
from app.db.models.category import Category as CategoryModel
from app.db.models.user import User as UserModel # Для информации об авторе
from app.schemas.transaction import TransactionCreate, TransactionUpdate, Transaction as TransactionSchema

# Вспомогательная функция для обновления сумм бюджета и категории
async def _update_budget_category_sums(
    db: AsyncSession,
    budget_id: uuid.UUID,
    category_id: uuid.UUID
):
    """
    Пересчитывает и обновляет хранимые суммы (expense, income, balance)
    для указанного бюджета и категории на основе всех их транзакций.
    """
    # 1. Пересчет для категории
    cat_sums_stmt = (
        select(
            func.coalesce(func.sum(case((TransactionModel.type == TransactionType.expense, TransactionModel.amount), else_=Decimal(0))), Decimal(0)).label("total_spent"),
            func.coalesce(func.sum(case((TransactionModel.type == TransactionType.income, TransactionModel.amount), else_=Decimal(0))), Decimal(0)).label("total_income")
        )
        .filter(TransactionModel.category_id == category_id)
    )
    cat_sums_res = await db.execute(cat_sums_stmt)
    cat_sums = cat_sums_res.one()
    
    # Получаем лимит категории
    category_limit_res = await db.execute(select(CategoryModel.limit_amount).filter(CategoryModel.id == category_id))
    category_limit = category_limit_res.scalar_one_or_none() or Decimal(0) # Если категория вдруг удалена, считаем лимит 0
    
    new_cat_balance = category_limit - cat_sums.total_spent + cat_sums.total_income

    await db.execute(
        sqlalchemy_update(CategoryModel)
        .where(CategoryModel.id == category_id)
        .values(
            current_spent=cat_sums.total_spent,
            current_income=cat_sums.total_income,
            current_balance=new_cat_balance
        )
        .execution_options(synchronize_session="fetch") # Важно для обновления сессии
    )

    # 2. Пересчет для бюджета
    budget_sums_stmt = (
         select(
            func.coalesce(func.sum(case((TransactionModel.type == TransactionType.expense, TransactionModel.amount), else_=Decimal(0))), Decimal(0)).label("total_expense"),
            func.coalesce(func.sum(case((TransactionModel.type == TransactionType.income, TransactionModel.amount), else_=Decimal(0))), Decimal(0)).label("total_income")
        )
        .filter(TransactionModel.budget_id == budget_id)
    )
    budget_sums_res = await db.execute(budget_sums_stmt)
    budget_sums = budget_sums_res.one()

    # Получаем общую сумму бюджета
    budget_total_res = await db.execute(select(BudgetModel.total_amount).filter(BudgetModel.id == budget_id))
    budget_total = budget_total_res.scalar_one_or_none() or Decimal(0) # Если бюджет вдруг удален

    new_budget_balance = budget_total - budget_sums.total_expense + budget_sums.total_income

    await db.execute(
        sqlalchemy_update(BudgetModel)
        .where(BudgetModel.id == budget_id)
        .values(
            current_total_expense=budget_sums.total_expense,
            current_total_income=budget_sums.total_income,
            current_balance=new_budget_balance
        )
        .execution_options(synchronize_session="fetch")
    )
    # Коммит будет сделан в get_async_db

# --- Read Operations ---

async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> Optional[TransactionModel]:
    """
    Получить транзакцию по ее ID.
    Загружает связанного автора и категорию для информации.
    """
    result = await db.execute(
        select(TransactionModel)
        .options(
            joinedload(TransactionModel.author_user), # Загружаем автора сразу
            joinedload(TransactionModel.category)    # Загружаем категорию сразу
         )
        .filter(TransactionModel.id == transaction_id)
    )
    return result.scalar_one_or_none()

async def get_transactions_by_budget(
    db: AsyncSession,
    *,
    budget_id: uuid.UUID,
    skip: int = 0,
    limit: int = 10,
    filters: Dict[str, Any] # Словарь с фильтрами
) -> Tuple[List[TransactionModel], int]:
    """
    Получить список транзакций для бюджета с фильтрацией и пагинацией.
    Возвращает кортеж: (список транзакций, общее количество по фильтрам).
    """
    # Базовый запрос с загрузкой связанных данных
    query = (
        select(TransactionModel)
        .options(
            joinedload(TransactionModel.author_user), # Загружаем автора
            joinedload(TransactionModel.category)     # Загружаем категорию (для category_name)
        )
        .filter(TransactionModel.budget_id == budget_id)
    )

    # Применяем фильтры
    conditions = []
    if filters.get("category_id"):
        conditions.append(TransactionModel.category_id == filters["category_id"])
    if filters.get("author_user_id"): # Если фильтруем по автору
        conditions.append(TransactionModel.author_user_id == filters["author_user_id"])
    if filters.get("type") and filters["type"] != 'all':
        conditions.append(TransactionModel.type == TransactionType(filters["type"])) # Преобразуем строку в Enum

    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    if start_date and end_date:
        try:
            # Преобразуем строки в объекты date и затем в datetime с началом/концом дня
            start_dt = datetime.combine(date.fromisoformat(start_date), datetime.min.time())
            end_dt = datetime.combine(date.fromisoformat(end_date), datetime.max.time())
            conditions.append(TransactionModel.transaction_date >= start_dt)
            conditions.append(TransactionModel.transaction_date <= end_dt)
        except ValueError:
            pass # Игнорируем некорректные даты

    if conditions:
        query = query.filter(and_(*conditions)) # Применяем все условия через AND

    # Создаем отдельный запрос для подсчета количества транзакций
    # Используем DISTINCT для предотвращения дублирования из-за джойнов
    count_query = select(func.count(func.distinct(TransactionModel.id))).where(
        TransactionModel.budget_id == budget_id
    )
    
    # Применяем те же фильтры к запросу подсчета
    if conditions:
        count_query = count_query.where(and_(*conditions))
    
    total_count_res = await db.execute(count_query)
    total_count = total_count_res.scalar_one()

    # Затем применяем сортировку, пагинацию и получаем сами транзакции
    query = query.order_by(desc(TransactionModel.transaction_date)).offset(skip).limit(limit)
    result = await db.execute(query)
    transactions = result.scalars().all()

    return transactions, total_count


# --- Create Operation ---

async def create_transaction(
    db: AsyncSession,
    *,
    obj_in: TransactionCreate, # Схема Pydantic
    author_user_id: int,
    budget_id: uuid.UUID
) -> TransactionModel:
    """
    Создать новую транзакцию.
    Обновляет связанные суммы в бюджете и категории.
    """
    db_obj = TransactionModel(
        type=obj_in.type,
        amount=obj_in.amount,
        name=obj_in.name,
        comment=obj_in.comment,
        transaction_date=obj_in.transaction_date, # Используем дату из запроса
        budget_id=budget_id,
        category_id=obj_in.category_id,
        author_user_id=author_user_id
    )
    db.add(db_obj)
    await db.flush() # Получаем ID и другие сгенерированные значения перед пересчетом сумм

    # Обновляем суммы в бюджете и категории
    await _update_budget_category_sums(db, budget_id=budget_id, category_id=obj_in.category_id)

    # Загружаем автора и категорию, чтобы вернуть полный объект
    await db.refresh(db_obj, attribute_names=['author_user', 'category'])

    return db_obj

# --- Update Operation ---

async def update_transaction(
    db: AsyncSession,
    *,
    db_obj: TransactionModel, # Существующий объект TransactionModel из БД
    obj_in: Union[TransactionUpdate, Dict[str, Any]] # Pydantic схема или словарь
) -> Optional[TransactionModel]:
    """
    Обновить существующую транзакцию.
    Пересчитывает суммы для старой и новой (если изменились) категории/бюджета.
    """
    if isinstance(obj_in, dict):
        update_data = obj_in
    else:
        update_data = obj_in.model_dump(exclude_unset=True)

    # Сохраняем старые значения для пересчета, если категория или сумма/тип изменятся
    old_category_id = db_obj.category_id
    old_budget_id = db_obj.budget_id # Бюджет вряд ли изменится, но на всякий случай
    # old_amount = db_obj.amount
    # old_type = db_obj.type
    needs_sum_update = False

    for field, value in update_data.items():
        if hasattr(db_obj, field):
            current_value = getattr(db_obj, field)
            if current_value != value:
                setattr(db_obj, field, value)
                if field in ['amount', 'type', 'category_id', 'budget_id']:
                    needs_sum_update = True

    if not needs_sum_update:
        # Если не менялись ключевые поля, просто обновляем updated_at (автоматически) и возвращаем
        db.add(db_obj)
        await db.flush()
        # Явно получаем обновленное значение updated_at
        updated_at_result = await db.execute(
            select(TransactionModel.updated_at).filter(TransactionModel.id == db_obj.id)
        )
        db_obj.updated_at = updated_at_result.scalar_one()
        await db.refresh(db_obj, attribute_names=['author_user', 'category'])
        return db_obj

    db.add(db_obj)
    await db.flush() # Сохраняем изменения транзакции в БД перед пересчетом
    
    # Явно получаем обновленное значение updated_at
    updated_at_result = await db.execute(
        select(TransactionModel.updated_at).filter(TransactionModel.id == db_obj.id)
    )
    db_obj.updated_at = updated_at_result.scalar_one()

    # Пересчитываем суммы
    # Нужно пересчитать для старой категории И для новой, если она изменилась
    categories_to_update = {old_category_id}
    if 'category_id' in update_data and update_data['category_id'] != old_category_id:
        categories_to_update.add(update_data['category_id'])
    
    budgets_to_update = {old_budget_id}
    # Если бы бюджет мог меняться, добавили бы новый budget_id сюда
    # if 'budget_id' in update_data and update_data['budget_id'] != old_budget_id:
    #     budgets_to_update.add(update_data['budget_id'])

    # Выполняем пересчет для всех затронутых бюджетов/категорий
    for budget_id_to_update in budgets_to_update:
        for category_id_to_update in categories_to_update:
            # Проверяем, принадлежит ли категория этому бюджету (на всякий случай)
            # Это усложнение, возможно, излишнее. Пока просто пересчитываем.
             await _update_budget_category_sums(db, budget_id=budget_id_to_update, category_id=category_id_to_update)


    # Перезагружаем объект транзакции с обновленными связями
    await db.refresh(db_obj, attribute_names=['author_user', 'category'])

    return db_obj

# --- Delete Operation ---

async def remove_transaction(db: AsyncSession, *, transaction_id: uuid.UUID) -> Optional[TransactionModel]:
    """
    Удалить транзакцию по ID.
    Пересчитывает суммы для связанных бюджета и категории.
    """
    # Сначала получаем транзакцию, чтобы знать budget_id и category_id для пересчета
    db_obj = await get_transaction(db, transaction_id=transaction_id)
    if not db_obj:
        return None

    budget_id_to_update = db_obj.budget_id
    category_id_to_update = db_obj.category_id

    # Удаляем транзакцию
    await db.delete(db_obj)
    await db.flush() # Применяем удаление перед пересчетом

    # Пересчитываем суммы
    await _update_budget_category_sums(db, budget_id=budget_id_to_update, category_id=category_id_to_update)

    return db_obj # Возвращаем удаленный объект (уже без связей после коммита)

# --- Aggregation Operations ---

async def get_transaction_date_summaries(
    db: AsyncSession,
    *,
    budget_id: uuid.UUID,
    start_date: date,
    end_date: date = None,  # Сделаем end_date опциональным
    transaction_type: Optional[str] = None
) -> Dict[str, float]:
    """
    Получает суммы транзакций по датам для указанного бюджета и даты.
    Использует SQL агрегацию для оптимизации производительности.
    
    Args:
        db: Асинхронная сессия БД
        budget_id: ID бюджета
        start_date: Дата для фильтрации
        end_date: Конечная дата, если нужен диапазон (по умолчанию равна start_date)
        transaction_type: Тип транзакций для фильтрации ('expense', 'income', или None для всех)
        
    Returns:
        Словарь, где ключи - даты в формате YYYY-MM-DD, значения - суммы транзакций
    """
    # Если end_date не указан, используем start_date
    if end_date is None:
        end_date = start_date
    
    # Преобразуем даты в datetime с временем начала и конца дня
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    try:
        # Исправляем SQL-запрос, используя формат даты как самостоятельное выражение
        date_format = func.to_char(TransactionModel.transaction_date, 'YYYY-MM-DD').label('date_key')
        
        query = (
            select(
                date_format,
                func.sum(TransactionModel.amount).label('total_amount')
            )
            .filter(
                TransactionModel.budget_id == budget_id,
                TransactionModel.transaction_date >= start_dt,
                TransactionModel.transaction_date <= end_dt
            )
            .group_by(date_format)  # Используем готовый label
        )
        
        # Добавляем фильтр по типу транзакции, если он указан
        if transaction_type and transaction_type != 'all':
            try:
                query = query.filter(TransactionModel.type == TransactionType(transaction_type))
            except ValueError:
                # В случае недопустимого значения типа, игнорируем фильтр
                pass
        
        # Выполняем запрос
        result = await db.execute(query)
        rows = result.all()
        
        # Преобразуем результат в словарь
        date_summaries: Dict[str, float] = {
            row.date_key: float(row.total_amount) 
            for row in rows
        }
        
        return date_summaries
    except Exception as e:
        # Добавляем логирование для отладки
        print(f"SQL Error in get_transaction_date_summaries: {e}")
        raise