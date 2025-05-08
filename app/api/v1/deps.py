# app/api/v1/deps.py
from fastapi import Depends, HTTPException, status, Header, Request # Добавили Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple, Dict, Any # Добавили Tuple, Dict, Any
import json

from app.core.security import _parse_and_validate_init_data
from app.core.config import settings
from app.db.database import get_async_db # Наша зависимость для получения сессии БД
from app.db.models.user import User as UserModel
from app.db.models.chat import Chat as ChatModel
from app import crud # Импортируем все CRUD операции

# Определение структуры для возвращаемого контекста
class AuthContext:
    def __init__(self, user: UserModel, chat_id: Optional[int] = None, chat_type: Optional[str] = None, chat_instance: Optional[str] = None):
        self.user = user
        self.chat_id = chat_id
        self.chat_type = chat_type
        self.chat_instance = chat_instance # Может быть полезен

    @property
    def is_group_context(self) -> bool:
        return self.chat_type in ["group", "supergroup"]

    @property
    def owner_user_id(self) -> Optional[int]:
        # Всегда возвращаем ID пользователя, независимо от контекста
        return self.user.id

    @property
    def owner_chat_id(self) -> Optional[int]:
        # Возвращаем chat_id только для группового чата
        return self.chat_id if self.is_group_context else None


async def get_auth_context(
    # request: Request, # Можно получить весь объект запроса
    init_data_header: Optional[str] = Header(None, alias="X-Telegram-Init-Data"), # Получаем заголовок
    db: AsyncSession = Depends(get_async_db) # Получаем сессию БД
) -> AuthContext:
    """
    Зависимость FastAPI для проверки initData и предоставления контекста аутентификации.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}, # Условно, т.к. это не Bearer, но стандартный заголовок
    )

    if init_data_header is None:
        print("Auth failed: Missing X-Telegram-Init-Data header")
        raise credentials_exception

    # Валидируем initData
    validated_data = _parse_and_validate_init_data(
        init_data=init_data_header,
        bot_token=settings.TELEGRAM_BOT_TOKEN_HMAC # Используем токен из настроек
    )

    if not validated_data or not validated_data.get("_valid"):
        print(f"Auth failed: Invalid initData")
        raise credentials_exception

    # Извлекаем данные пользователя
    user_data = validated_data.get("user")
    if not user_data or not isinstance(user_data, dict) or "id" not in user_data:
        print("Auth failed: Invalid user data in initData")
        raise credentials_exception # Не можем работать без ID пользователя

    # Получаем или создаем пользователя в нашей БД
    try:
        current_user: UserModel = await crud.crud_user.get_or_create_or_update_user_from_telegram(
            db=db,
            user_id=int(user_data["id"]),
            first_name=user_data.get("first_name", "N/A"), # Предоставляем значение по умолчанию
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            language_code=user_data.get("language_code"),
            is_premium=user_data.get("is_premium", False),
            photo_url=user_data.get("photo_url")
        )
    except Exception as e:
        print(f"Auth failed: Error processing user in DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error processing user")

    if not current_user: # Дополнительная проверка
        print("Auth failed: User could not be fetched or created.")
        raise credentials_exception


    # Определяем контекст чата
    chat_id: Optional[int] = None
    chat_type: Optional[str] = None
    chat_title: Optional[str] = None
    chat_instance: Optional[str] = validated_data.get("chat_instance") # ID инстанса чата (уникален для пары юзер-чат)

    # Определяем тип контекста на основе chat_type или chat_instance
    if validated_data.get("chat_type") == "group" or (chat_instance and validated_data.get("chat_type") == "group"):
        chat_type = "group"
    
    # Если есть явные данные о чате, используем их
    chat_data = validated_data.get("chat")
    if chat_data and isinstance(chat_data, dict) and "id" in chat_data and chat_data.get("type") in ["group", "supergroup"]:
        # Это групповой чат
        chat_id = int(chat_data["id"])
        chat_type = chat_data.get("type")
        chat_title = chat_data.get("title")
        
        # Убеждаемся, что запись о чате есть в БД (название могло обновиться)
        try:
            await crud.crud_chat.get_or_create_or_update_chat_from_telegram(
                db=db,
                chat_id=chat_id,
                chat_type=chat_type,
                chat_title=chat_title,
                update_if_exists=True # Обновляем название, если изменилось
            )
        except Exception as e:
             print(f"Auth warning: Error processing group chat in DB: {e}")
             # Не фатально для аутентификации, но нужно залогировать
             pass
    else:
        # Если есть chat_instance и chat_type="group", но нет явных данных о чате,
        # значит мы в групповом чате, но нужно получить его ID
        if chat_instance and validated_data.get("chat_type") == "group":
            # Для групповых чатов используем chat_instance в качестве идентификатора
            # Можно также сделать запрос к БД, чтобы найти чат по chat_instance, если это поле сохраняется
            chat_type = "group"
            
            # Для первой версии можно использовать хеш от chat_instance как chat_id
            # В будущем лучше добавить поле chat_instance в модель чата и искать по нему
            import hashlib
            hash_object = hashlib.md5(chat_instance.encode())
            chat_id = int(hash_object.hexdigest(), 16) % (10 ** 10)  # Берем остаток от деления на 10^10 для получения 10-значного числа
            
            try:
                await crud.crud_chat.get_or_create_or_update_chat_from_telegram(
                    db=db,
                    chat_id=chat_id,
                    chat_type="group",
                    chat_title=f"Group Chat {chat_id}",  # Временное название
                    update_if_exists=False  # Не обновляем существующие записи
                )
            except Exception as e:
                print(f"Auth warning: Error processing inferred group chat in DB: {e}")
                pass
        else:
            # Предполагаем личный контекст (чат с ботом или нет информации о чате)
            chat_type = validated_data.get("chat_type") or "private"

    # Возвращаем объект контекста
    return AuthContext(
        user=current_user,
        chat_id=chat_id,
        chat_type=chat_type,
        chat_instance=chat_instance
    )

# --- Опционально: Зависимости для получения только пользователя или ID чата ---

async def get_current_user(context: AuthContext = Depends(get_auth_context)) -> UserModel:
    return context.user

async def get_current_chat_id(context: AuthContext = Depends(get_auth_context)) -> Optional[int]:
    """Возвращает ID группового чата, если контекст групповой, иначе None."""
    return context.owner_chat_id

async def get_current_owner_ids(context: AuthContext = Depends(get_auth_context)) -> Tuple[Optional[int], Optional[int]]:
    """Возвращает кортеж (owner_user_id, owner_chat_id)."""
    return context.owner_user_id, context.owner_chat_id