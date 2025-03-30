from telebot import formatting


def safe_markdown(text: str) -> str:
    """Экранирует все спецсимволы Markdown в тексте."""
    if not text:
        return ""

    # Экранируем специальные символы Markdown
    chars_to_escape = ['_', '*', '`', '[']
    for char in chars_to_escape:
        text = text.replace(char, f"\\{char}")

    return text
def format_number(value):
    """Форматирует число с разделителями тысяч

    Использует точки в качестве разделителей тысяч.
    Например: 1.000.000
    """
    try:
        # Оптимизация: сразу преобразуем в int и делаем round только для float
        if isinstance(value, float):
            value = int(round(value))
        elif not isinstance(value, int):
            value = int(float(value))
        # Форматирование с разделителями
        formatted = f"{value:,}".replace(",", ".")
        return formatted
    except (ValueError, TypeError):
        return "0"


def safe_markdown(text: str) -> str:
    """Экранирует все спецсимволы Markdown."""
    return formatting.escape_markdown(text)


def resolve_user_id(bot, user_reference):
    """
    Resolves various user references to a user ID

    Parameters:
    - bot: TeleBot instance
    - user_reference: Can be numerical ID, username (with or without @), or a mention/reply

    Returns:
    - tuple (success, user_id or error_message)
    """
    # Log the input for debugging
    print(f"Trying to resolve: {user_reference} (type: {type(user_reference)})")

    # If it's already a numerical ID
    if isinstance(user_reference, int) or (isinstance(user_reference, str) and user_reference.isdigit()):
        return True, int(user_reference)

    # If it's a username (with or without @)
    if isinstance(user_reference, str):
        # Clean up username if it has @ prefix
        username = user_reference.lstrip('@')
        print(f"Looking up username: {username}")

        try:
            # Try to get user info by username
            chat = bot.get_chat(username)
            user_id = chat.id
            print(f"Resolved to user ID: {user_id}")
            return True, user_id
        except Exception as e:
            print(f"Error resolving username: {str(e)}")

    # If we couldn't resolve the user ID
    return False, "❌ Невозможно найти пользователя. Используйте ID или корректное имя пользователя."


def transfer_money(casino_system, bot, from_user_id, to_user_reference, amount):
    """Переводит деньги от одного пользователя другому"""
    # Use the resolver function defined above
    success, result = resolve_user_id(bot, to_user_reference)

    if not success:
        raise ValueError(result)  # This is the error message from resolve_user_id

    to_user_id = result

    # Проверка идентичности отправителя и получателя перед другими проверками
    if from_user_id == to_user_id:
        raise ValueError("❌ Нельзя перевести самому себе")

    if amount < 100:
        raise ValueError("❌ Минимальная сумма перевода: 100 ₽")

    # Убедимся что пользователи существуют
    casino_system.ensure_user_exists(from_user_id)
    casino_system.ensure_user_exists(to_user_id)

    # Проверка баланса
    sender_balance = casino_system.get_balance(from_user_id)
    if sender_balance < amount:
        raise ValueError(f"❌ Недостаточно средств. Баланс: {format_number(sender_balance)} ₽")

    # Выполнение транзакции
    casino_system.withdraw(from_user_id, amount)
    casino_system.deposit(to_user_id, amount)

    return to_user_id  # Return the resolved user ID for confirmation messages