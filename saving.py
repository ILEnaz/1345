import json
import os
import logging
import time
import atexit
import shutil
import zlib
import base64
from apscheduler.schedulers.background import BackgroundScheduler

# Настройка логирования с меньшим уровнем для экономии ресурсов
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('SaveManager')


def compress_number(num):
    """Возвращает число в экспоненциальном формате, если оно достаточно велико."""
    if isinstance(num, (int, float)) and num >= 1e6:
        return f"{num:.2e}"
    return num


class SaveManager:
    """Менеджер сохранений с сжатием данных и надежным резервным копированием."""

    # Пути для PythonAnywhere
    BASE_DIR = os.path.expanduser("~")
    DATA_DIR = os.path.join(BASE_DIR, "bot_data")
    SAVE_FILE = os.path.join(DATA_DIR, "user_data.zlib")
    BACKUP_DIR = os.path.join(DATA_DIR, "backups")
    LOCK_FILE = os.path.join(DATA_DIR, "save.lock")

    # Настройки для сохранений
    COMPRESSION_LEVEL = 9
    MAX_BACKUPS = 1  # Уменьшено для экономии места
    MAX_BACKUP_AGE_HOURS = 24  # Увеличено для снижения нагрузки

    @classmethod
    def _ensure_dir_exists(cls):
        """Создаёт директории для сохранения, если они не существуют."""
        try:
            os.makedirs(cls.DATA_DIR, exist_ok=True)
            os.makedirs(cls.BACKUP_DIR, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Ошибка создания директории: {str(e)}")
            return False

    @classmethod
    def _create_lock(cls):
        """Создаёт lock-файл для предотвращения одновременных записей."""
        try:
            with open(cls.LOCK_FILE, 'w') as f:
                f.write(str(time.time()))
            return True
        except Exception as e:
            logger.error(f"Не удалось создать lock-файл: {str(e)}")
            return False

    @classmethod
    def _remove_lock(cls):
        """Удаляет lock-файл после завершения операции."""
        try:
            if os.path.exists(cls.LOCK_FILE):
                os.remove(cls.LOCK_FILE)
            return True
        except Exception as e:
            logger.error(f"Не удалось удалить lock-файл: {str(e)}")
            return False

    @classmethod
    def _is_locked(cls):
        """Проверяет, заблокирован ли файл сохранения другим процессом."""
        if not os.path.exists(cls.LOCK_FILE):
            return False

        try:
            # Если lock-файл старше 15 секунд, считаем его устаревшим (увеличено с 10 до 15 сек)
            mtime = os.path.getmtime(cls.LOCK_FILE)
            if time.time() - mtime > 15:
                cls._remove_lock()
                return False
            return True
        except Exception:
            return False

    @classmethod
    def _compress_data(cls, data_dict):
        """Сжимает данные для уменьшения размера файла."""
        try:
            json_str = json.dumps(data_dict, ensure_ascii=False, separators=(',', ':'))
            compressed = zlib.compress(json_str.encode('utf-8'), cls.COMPRESSION_LEVEL)
            encoded = base64.b64encode(compressed)
            return encoded
        except Exception as e:
            logger.error(f"Ошибка сжатия данных: {str(e)}")
            return None

    @classmethod
    def _decompress_data(cls, compressed_data):
        """Распаковывает сжатые данные с поддержкой разных форматов."""
        try:
            # Пробуем новый формат (base64 + zlib)
            try:
                decoded = base64.b64decode(compressed_data)
                decompressed = zlib.decompress(decoded)
                data_dict = json.loads(decompressed.decode('utf-8'))
                return data_dict
            except Exception as e1:
                logger.warning(f"Не удалось расшифровать в новом формате, пробуем старый: {e1}")

                # Пробуем старый формат (просто zlib)
                try:
                    decompressed = zlib.decompress(compressed_data)
                    data_dict = json.loads(decompressed.decode('utf-8'))
                    return data_dict
                except Exception as e2:
                    logger.warning(f"Не удалось расшифровать в старом формате: {e2}")

                    # Пробуем как обычный JSON
                    try:
                        data_dict = json.loads(compressed_data.decode('utf-8'))
                        return data_dict
                    except Exception as e3:
                        logger.error(f"Все методы декодирования не удались: {e3}")
                        return None
        except Exception as e:
            logger.error(f"Ошибка распаковки данных: {str(e)}")
            return None

    @classmethod
    def _create_backup(cls, timestamp=None):
        """Создает резервную копию текущего файла данных."""
        if not os.path.exists(cls.SAVE_FILE):
            return False

        timestamp = timestamp or int(time.time())
        backup_file = os.path.join(cls.BACKUP_DIR, f"backup_{timestamp}.zlib")

        try:
            shutil.copy2(cls.SAVE_FILE, backup_file)
            cls._clean_old_backups()
            return True
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {str(e)}")
            return False

    @classmethod
    def save_data(cls, casino, mining, business=None):
        """Сохраняет данные с защитой от одновременной записи."""
        if cls._is_locked():
            logger.warning("Файл заблокирован. Пропускаем сохранение.")
            return False

        cls._ensure_dir_exists()
        cls._create_lock()

        try:
            # Собираем данные
            data = {
                'balances': casino.balances,
                'vip_users': casino.vip_users,
                'used_promocodes': casino.used_promocodes,
                'registration_dates': casino.registration_dates,
                'user_farms': mining.user_farms,
                'btc_rate': mining.btc_rate
            }

            # Добавляем бизнесы, если переданы
            if business is not None:
                data['user_businesses'] = business.user_businesses

            # Сжимаем и сохраняем
            compressed = cls._compress_data(data)
            if not compressed:
                return False

            with open(cls.SAVE_FILE, 'wb') as f:
                f.write(compressed)

            # Создаем резервную копию только если их нет
            if not os.path.exists(cls.BACKUP_DIR) or len(os.listdir(cls.BACKUP_DIR)) < 1:
                cls._create_backup()

            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {str(e)}")
            return False
        finally:
            cls._remove_lock()

    @classmethod
    def load_data(cls):
        """Загружает данные с восстановлением из резервных копий при ошибке."""
        cls._ensure_dir_exists()

        # Функция для загрузки данных из файла
        def load_from_file(file_path, is_compressed=True):
            try:
                with open(file_path, 'rb') as f:
                    file_data = f.read()

                    if is_compressed:
                        data_dict = cls._decompress_data(file_data)
                    else:
                        data_dict = json.loads(file_data.decode('utf-8'))

                    if data_dict is None:
                        return None

                    # Проверка и преобразование строковых балансов в числа
                    if 'balances' in data_dict:
                        for user_id, balance in data_dict['balances'].items():
                            if isinstance(balance, str):
                                try:
                                    data_dict['balances'][user_id] = float(balance)
                                except (ValueError, TypeError):
                                    # Если не удалось преобразовать, используем значение по умолчанию
                                    logger.warning(f"Не удалось преобразовать баланс {balance} для {user_id}")
                                    data_dict['balances'][user_id] = 10000  # Значение по умолчанию

                    return data_dict
            except Exception as e:
                logger.error(f"Ошибка загрузки из {file_path}: {str(e)}")
                return None

        # Пробуем загрузить основной файл
        if os.path.exists(cls.SAVE_FILE):
            data = load_from_file(cls.SAVE_FILE)
            if data:
                return data, False
        # Пробуем загрузить из резервных копий (от новых к старым)
        backup_files = []
        if os.path.exists(cls.BACKUP_DIR):
            for f in os.listdir(cls.BACKUP_DIR):
                if f.startswith("backup_") and f.endswith(".zlib"):
                    backup_files.append(os.path.join(cls.BACKUP_DIR, f))
            # Сортируем по времени модификации (от новых к старым)
            backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for backup in backup_files:
                data = load_from_file(backup)
                if data:
                    # Восстанавливаем из резервной копии
                    logger.warning(f"Восстановление из резервной копии: {backup}")
                    return data, False
        # Если не удалось загрузить, создаем новые данные
        logger.warning("Создание новых данных")
        return cls._create_new_data(), True

    @classmethod
    def _create_new_data(cls):
        """Создаёт новую структуру данных по умолчанию."""
        return {
            'balances': {},
            'vip_users': {},
            'used_promocodes': {},
            'registration_dates': {},
            'user_farms': {},
            'btc_rate': 80000,
            'user_businesses': {}
        }


def setup_autosave(casino, mining, business=None, interval_minutes=120):
    """Настраивает автоматическое сохранение."""
    scheduler = BackgroundScheduler()

    def save_wrapper():
        try:
            SaveManager.save_data(casino, mining, business)
            logger.info("Автосохранение выполнено")
        except Exception as e:
            logger.error(f"Ошибка автосохранения: {str(e)}")

    # Запускаем задачу с увеличенным интервалом
    scheduler.add_job(
        func=save_wrapper,
        trigger='interval',
        minutes=interval_minutes,
        id='autosave_job'
    )

    try:
        scheduler.start()
        logger.info(f"Автосохранение настроено (интервал: {interval_minutes} мин)")

        # Регистрируем функцию сохранения при выходе
        atexit.register(save_wrapper)
    except Exception as e:
        logger.error(f"Ошибка запуска автосохранения: {str(e)}")