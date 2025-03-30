# Оптимизированные множители для быстрого доступа
MULTIPLIERS = {
    'к': 1_000,
    'кк': 1_000_000,
    'ккк': 1_000_000_000,
    'кккк': 1_000_000_000_000
}

# Кэшированный список суффиксов, отсортированный по длине (обратный порядок)
SORTED_SUFFIXES = sorted(MULTIPLIERS.keys(), key=len, reverse=True)


def parse_amount(text):
    """Преобразует текстовый ввод суммы в числовое значение"""
    # Предварительная обработка текста
    text = text.lower().replace(' ', '').replace(',', '.')

    # Проверка на суффикс (к, кк, ...)
    for suffix in SORTED_SUFFIXES:
        if text.endswith(suffix):
            number_part = text[:-len(suffix)]
            try:
                number = float(number_part)
                # Проверка на целое число
                if not number.is_integer():
                    raise ValueError("❌ Дробное количество с множителем недопустимо")
                return int(number * MULTIPLIERS[suffix])
            except ValueError:
                raise ValueError(f"Некорректное число: {number_part}")

    # Если нет суффикса, пробуем преобразовать напрямую
    try:
        number = float(text)
        if not number.is_integer():
            raise ValueError("❌ Дробное количество не поддерживается")
        return int(number)
    except ValueError:
        raise ValueError("Некорректный формат суммы")