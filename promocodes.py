import json
import os
import logging

# Имя файла для хранения промокодов
PROMO_FILE = "active_promocodes.json"

# Стандартные промокоды
ACTIVE_PROMOCODES = {
    "ОБНОВЛЕНИЯ!": {"amount": 150_000_000, "max_uses": 100},
}


class PromocodeSystem:
    # Кэширование загруженных промокодов
    _loaded_promocodes = None
    _logger = logging.getLogger('PromocodeSystem')

    @classmethod
    def load_promocodes(cls):
        """Загружает промокоды из файла или возвращает дефолтные"""
        # Возвращаем кэшированный результат если он существует
        if cls._loaded_promocodes is not None:
            return cls._loaded_promocodes

        # Создаем файл с дефолтными промокодами если не существует
        if not os.path.exists(PROMO_FILE):
            cls._loaded_promocodes = ACTIVE_PROMOCODES.copy()
            cls.save_promocodes(cls._loaded_promocodes)
            return cls._loaded_promocodes

        # Загружаем промокоды из файла
        try:
            with open(PROMO_FILE, 'r') as f:
                cls._loaded_promocodes = json.load(f)
                return cls._loaded_promocodes
        except Exception as e:
            cls._logger.error(f"Ошибка загрузки промокодов: {e}")
            cls._loaded_promocodes = ACTIVE_PROMOCODES.copy()
            return cls._loaded_promocodes

    @classmethod
    def save_promocodes(cls, data):
        """Сохраняет промокоды в файл"""
        try:
            with open(PROMO_FILE, 'w') as f:
                json.dump(data, f)
            # Обновляем кэш
            cls._loaded_promocodes = data
        except Exception as e:
            cls._logger.error(f"Ошибка сохранения промокодов: {e}")