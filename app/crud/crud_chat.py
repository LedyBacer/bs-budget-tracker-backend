# app/crud/crud_chat.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List

from app.db.models.chat import Chat as ChatModel # Модель SQLAlchemy
from app.schemas.chat import ChatCreate, ChatUpdate # Схемы Pydantic

# --- Read Operations ---

async def get_chat(db: AsyncSession, chat_id: int) -> Optional[ChatModel]:
    """
    Получить чат по его ID.
    """
    result = await db.execute(select(ChatModel).filter(ChatModel.id == chat_id))
    return result.scalar_one_or_none()

async def get_chats(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[ChatModel]:
    """
    Получить список чатов с пагинацией.
    (Может быть полезно для административных целей, но не для основного API)
    """
    result = await db.execute(select(ChatModel).offset(skip).limit(limit))
    return result.scalars().all()

# --- Create Operation (внутренняя, будет вызываться из get_or_create) ---

async def _create_chat(db: AsyncSession, *, chat_in: ChatCreate) -> ChatModel:
    """
    Создать новый чат. Приватная функция, используется в get_or_create_chat.
    """
    db_chat = ChatModel(
        id=chat_in.id,
        type=chat_in.type,
        title=chat_in.title
    )
    db.add(db_chat)
    # Коммит и refresh будут сделаны в get_async_db
    return db_chat

# --- Update Operation (внутренняя, будет вызываться из get_or_create_or_update) ---
async def _update_chat(db: AsyncSession, *, db_obj: ChatModel, obj_in: ChatUpdate) -> ChatModel:
    """
    Обновить существующий чат. Приватная функция.
    """
    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_obj, field):
            setattr(db_obj, field, value)
    db.add(db_obj)
    return db_obj


# --- Специальная функция для получения или создания (и опционального обновления) чата ---

async def get_or_create_or_update_chat_from_telegram(
    db: AsyncSession,
    *,
    chat_id: int,
    chat_type: str,
    chat_title: Optional[str] = None,
    update_if_exists: bool = True # Флаг, указывающий, нужно ли обновлять title, если чат уже существует
) -> ChatModel:
    """
    Получает чат из БД по chat_id.
    Если чат не найден, создает новый.
    Если чат найден и update_if_exists=True, обновляет его данные (например, title).
    """
    db_chat = await get_chat(db, chat_id=chat_id)

    if db_chat:
        if update_if_exists:
            # Чат существует, проверяем, нужно ли обновление (например, изменился title)
            # В нашем случае, в основном может меняться title
            current_chat_data = {
                "type": chat_type, # Тип чата вряд ли изменится, но для полноты
                "title": chat_title
            }
            update_payload_dict = {}
            needs_update = False

            if db_chat.type != chat_type: # Маловероятно, но проверим
                update_payload_dict["type"] = chat_type
                needs_update = True
            if db_chat.title != chat_title:
                update_payload_dict["title"] = chat_title
                needs_update = True
            
            if needs_update:
                # print(f"Updating chat {chat_id} with data: {update_payload_dict}")
                update_schema = ChatUpdate(**update_payload_dict)
                db_chat = await _update_chat(db=db, db_obj=db_chat, obj_in=update_schema)
    else:
        # Чата нет, создаем новый
        # print(f"Creating new chat {chat_id}")
        create_schema = ChatCreate(
            id=chat_id,
            type=chat_type,
            title=chat_title
        )
        db_chat = await _create_chat(db=db, chat_in=create_schema)
    
    # Коммит и refresh будут сделаны в get_async_db
    return db_chat