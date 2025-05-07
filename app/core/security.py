# app/core/security.py
import hmac
import hashlib
from urllib.parse import parse_qsl, unquote
from datetime import datetime, timedelta, timezone # Добавляем timezone
from typing import Optional, Dict, Any

from app.core.config import settings

def _parse_and_validate_init_data(
    init_data: str,
    bot_token: str,
    c_str: str = "WebAppData",
    expiration_hours: int = 24 # Время жизни initData в часах
) -> Optional[Dict[str, Any]]:
    """
    Парсит и валидирует строку initData от Telegram Web App.

    Args:
        init_data: Строка initData, полученная из window.Telegram.WebApp.initData.
        bot_token: Токен вашего Telegram бота.
        c_str: Константная строка для HMAC ключа (обычно "WebAppData").
        expiration_hours: Максимальное время жизни initData в часах.

    Returns:
        Словарь с распарсенными данными, если валидация прошла успешно, иначе None.
        Включает поле '_valid' (bool) и оригинальные поля.
    """
    try:
        # 1. Парсим строку запроса
        # parse_qsl сохраняет порядок, unquote декодирует URL-кодированные символы
        parsed_data = dict(parse_qsl(init_data))
    except Exception:
        # Не удалось распарсить строку
        return None

    if "hash" not in parsed_data:
        # Отсутствует обязательный хэш
        return None

    received_hash = parsed_data.pop("hash")

    # 2. Проверка времени жизни (auth_date)
    try:
        auth_date_unix = int(parsed_data.get("auth_date", 0))
        auth_date = datetime.fromtimestamp(auth_date_unix, tz=timezone.utc) # Указываем UTC
        if datetime.now(tz=timezone.utc) - auth_date > timedelta(hours=expiration_hours): # Сравниваем с UTC now
             # Данные устарели
             print(f"initData validation failed: auth_date expired. Auth: {auth_date}, Now: {datetime.now(tz=timezone.utc)}")
             return None
    except (ValueError, TypeError):
        # Некорректный формат auth_date
        return None

    # 3. Формируем строку для проверки хэша
    # Все поля ключ=значение, кроме 'hash', отсортированные по ключу, разделенные \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )

    # 4. Вычисляем HMAC подпись
    # Первый ключ - HMAC-SHA256 от токена бота с константой "WebAppData"
    secret_key_part1 = hmac.new(c_str.encode(), bot_token.encode(), hashlib.sha256).digest()
    # Финальный хэш - HMAC-SHA256 от data_check_string с использованием ключа из шага 1
    calculated_hash = hmac.new(secret_key_part1, data_check_string.encode(), hashlib.sha256).hexdigest()

    # 5. Сравниваем хэши
    if calculated_hash == received_hash:
        # Валидация прошла успешно
        # Декодируем поля user и chat, если они есть (они в формате JSON)
        import json
        try:
            if 'user' in parsed_data:
                 # Декодируем URL-кодированный JSON
                user_json_str = unquote(parsed_data['user'])
                parsed_data['user'] = json.loads(user_json_str)
            if 'chat' in parsed_data:
                chat_json_str = unquote(parsed_data['chat'])
                parsed_data['chat'] = json.loads(chat_json_str)
            if 'receiver' in parsed_data:
                 receiver_json_str = unquote(parsed_data['receiver'])
                 parsed_data['receiver'] = json.loads(receiver_json_str)
        except json.JSONDecodeError:
             print(f"initData validation warning: Could not decode user/chat/receiver JSON.")
             # Можно вернуть None или продолжить без user/chat объектов
             pass # Продолжим без них, если декодирование не удалось
        
        parsed_data['_valid'] = True
        return parsed_data
    else:
        # Неверный хэш
        print(f"initData validation failed: Hash mismatch. Calculated: {calculated_hash}, Received: {received_hash}")
        return None

# Добавляем другие функции безопасности, если нужны (например, хеширование паролей, JWT)
# ... (пока не нужны)