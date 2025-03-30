# leaderboard.py
from Casino import CasinoSystem
from Mining import MiningSystem
from utils import format_number
import logging
from telebot import formatting

# Создаем логгер для модуля
logger = logging.getLogger(__name__)


# В файле leaderboard.py исправьте функцию get_top_players так:

def get_top_players(casino: CasinoSystem, mining: MiningSystem, top_n=5):
    """Получает список игроков с наибольшим балансом"""
    try:
        # Проверка на пустые балансы
        if not casino.balances:
            logger.warning("Список балансов пуст!")
            return []

        # Приведение всех балансов к числовому формату перед сортировкой
        users_with_balance = []
        for uid, bal in casino.balances.items():
            # Преобразуем строки в числа при необходимости
            if isinstance(bal, str):
                try:
                    numeric_balance = float(bal)
                except (ValueError, TypeError):
                    numeric_balance = 0
            else:
                numeric_balance = bal

            if numeric_balance > 0:
                users_with_balance.append((uid, numeric_balance))

        # Сортируем по убыванию
        users_with_balance.sort(key=lambda x: x[1], reverse=True)

        # Возвращаем только top_n записей
        return users_with_balance[:top_n]
    except Exception as e:
        logger.error(f"Ошибка в get_top_players: {str(e)}", exc_info=True)
        return []


я