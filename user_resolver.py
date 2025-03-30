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