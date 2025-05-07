# app/crud/crud_user.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # Для жадной загрузки связанных данных, если понадобится
from typing import Optional, List, Any

from app.db.models.user import User as UserModel # Модель SQLAlchemy
from app.schemas.user import UserCreate, UserUpdate # Схемы Pydantic

# --- Read Operations ---

async def get_user(db: AsyncSession, user_id: int) -> Optional[UserModel]:
    """
    Получить пользователя по его ID.
    """
    result = await db.execute(select(UserModel).filter(UserModel.id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[UserModel]:
    """
    Получить пользователя по его username (если он есть и уникален).
    Это может быть полезно, но username в Telegram не всегда уникален глобально.
    """
    if not username: # Проверка, что username не пустой
        return None
    result = await db.execute(select(UserModel).filter(UserModel.username == username))
    return result.scalar_one_or_none()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[UserModel]:
    """
    Получить список пользователей с пагинацией.
    (Для нашего приложения это может быть не так часто нужно, но для полноты CRUD)
    """
    result = await db.execute(select(UserModel).offset(skip).limit(limit))
    return result.scalars().all()

# --- Create Operation ---

async def create_user(db: AsyncSession, *, user_in: UserCreate) -> UserModel:
    """
    Создать нового пользователя.
    user_in должен быть схемой Pydantic UserCreate.
    """
    # Преобразуем Pydantic схему в словарь, который можно передать в модель SQLAlchemy
    # Мы не используем user_in.model_dump() напрямую в конструкторе UserModel,
    # чтобы избежать передачи полей, которых нет в UserModel, если бы они были в UserCreate.
    # Но в нашем случае UserCreate точно соответствует полям User (кроме связей).
    
    db_user = UserModel(
        id=user_in.id,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        username=user_in.username,
        language_code=user_in.language_code,
        is_premium=user_in.is_premium,
        photo_url=str(user_in.photo_url) if user_in.photo_url else None # Pydantic HttpUrl нужно конвертировать в str
    )
    db.add(db_user)
    # Коммит будет сделан в зависимости get_async_db после успешного завершения запроса
    # await db.commit() # Не здесь
    # await db.refresh(db_user) # Не здесь, если коммит в get_async_db
    return db_user

# --- Update Operation ---

async def update_user(db: AsyncSession, *, db_obj: UserModel, obj_in: UserUpdate) -> UserModel:
    """
    Обновить существующего пользователя.
    db_obj - это существующий объект UserModel из базы данных.
    obj_in - это Pydantic схема UserUpdate с полями для обновления.
    """
    # Получаем данные из Pydantic схемы как словарь, исключая неустановленные значения (те, что None)
    update_data = obj_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(db_obj, field): # Проверяем, есть ли такое поле в модели SQLAlchemy
            # Особая обработка для photo_url, если он HttpUrl
            if field == "photo_url" and value is not None:
                setattr(db_obj, field, str(value))
            else:
                setattr(db_obj, field, value)
    
    db.add(db_obj) # Помечаем объект как измененный (хотя SQLAlchemy обычно отслеживает изменения)
    # await db.commit() # Не здесь
    # await db.refresh(db_obj) # Не здесь
    return db_obj

# --- Delete Operation ---

async def remove_user(db: AsyncSession, *, user_id: int) -> Optional[UserModel]:
    """
    Удалить пользователя по ID.
    Возвращает удаленного пользователя или None, если не найден.
    """
    db_obj = await get_user(db, user_id=user_id)
    if db_obj:
        await db.delete(db_obj)
        # await db.commit() # Не здесь
        return db_obj
    return None


# --- Специальная функция для создания или обновления пользователя на основе данных из initData ---
async def get_or_create_or_update_user_from_telegram(
    db: AsyncSession,
    *,
    user_id: int,
    first_name: str,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    language_code: Optional[str] = None,
    is_premium: Optional[bool] = False,
    photo_url: Optional[str] = None # Принимаем как строку, т.к. из initData может прийти строка
) -> UserModel:
    """
    Получает пользователя из БД по user_id.
    Если пользователь не найден, создает нового.
    Если пользователь найден, обновляет его данные, если они изменились.
    """
    db_user = await get_user(db, user_id=user_id)

    user_data_from_telegram = {
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "language_code": language_code,
        "is_premium": is_premium,
        "photo_url": photo_url,
    }

    if db_user:
        # Пользователь существует, проверяем, нужно ли обновление
        needs_update = False
        update_payload_dict = {}
        for key, value_from_telegram in user_data_from_telegram.items():
            current_db_value = getattr(db_user, key, None)
            if current_db_value != value_from_telegram:
                needs_update = True
                update_payload_dict[key] = value_from_telegram
        
        if needs_update:
            # Создаем Pydantic схему для обновления только измененных полей
            # Это гарантирует, что UserUpdate применит валидацию Pydantic, если она есть
            # print(f"Updating user {user_id} with data: {update_payload_dict}")
            update_schema = UserUpdate(**update_payload_dict)
            db_user = await update_user(db=db, db_obj=db_user, obj_in=update_schema)
    else:
        # Пользователя нет, создаем нового
        # print(f"Creating new user {user_id}")
        create_schema = UserCreate(
            id=user_id,
            **user_data_from_telegram # Передаем остальные поля
        )
        db_user = await create_user(db=db, user_in=create_schema)
    
    # Коммит и рефреш будут сделаны в get_async_db
    # Важно! Мы не делаем здесь db.commit() или db.refresh(db_user)
    # Эти операции должны происходить на уровне обработчика запроса (или зависимости get_async_db)
    # чтобы обеспечить атомарность операции в рамках одного HTTP-запроса.
    # Здесь мы только добавляем объект в сессию или изменяем его.
    
    return db_user