import os
import time
import logging
from datetime import datetime

# Настройка отдельного логгера для мониторинга
monitor_logger = logging.getLogger('monitoring')
monitor_logger.setLevel(logging.WARNING)  # Понижаем до WARNING для снижения нагрузки

# Формат логирования
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    "%Y-%m-%d %H:%M:%S"
)

# Файловый обработчик (с ограниченным размером)
log_dir = os.path.expanduser("~/bot_logs")
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(
    os.path.join(log_dir, "monitor.log"),
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
monitor_logger.addHandler(file_handler)


class BotMonitor:
    """Легкая система мониторинга состояния бота"""

    def __init__(self, casino, mining, business):
        self.casino = casino
        self.mining = mining
        self.business = business
        self.start_time = time.time()
        self.last_save_time = None
        self.last_save_result = None

        # Вызываем первичную проверку
        self.check_systems()
        monitor_logger.info("Система мониторинга инициализирована")

    def record_save_event(self, success, save_time=None):
        """Записывает информацию о последнем сохранении"""
        self.last_save_time = save_time or time.time()
        self.last_save_result = success
        monitor_logger.info(f"Сохранение: {'успешно' if success else 'ошибка'}")

    def check_systems(self):
        """Проверяет состояние всех систем бота по запросу"""
        results = {
            'casino': True,
            'mining': True,
            'business': True,
            'saving': True,
        }

        # Проверка Casino
        try:
            assert hasattr(self.casino, 'balances')
            assert isinstance(self.casino.balances, dict)
        except Exception:
            results['casino'] = False

        # Проверка Mining
        try:
            assert hasattr(self.mining, 'btc_rate')
            assert isinstance(self.mining.btc_rate, (int, float))
        except Exception:
            results['mining'] = False

        # Проверка Business
        try:
            assert hasattr(self.business, 'user_businesses')
            assert isinstance(self.business.user_businesses, dict)
        except Exception:
            results['business'] = False

        # Проверка системы сохранений
        try:
            save_dir_exists = os.path.exists(os.path.expanduser("~/bot_data"))
            save_file_exists = os.path.exists(os.path.expanduser("~/bot_data/user_data.zlib"))
            results['saving'] = save_dir_exists and save_file_exists
        except Exception:
            results['saving'] = False

        return results

    def get_save_info(self):
        """Возвращает информацию о последнем сохранении и файлах данных"""
        info = {}

        # Информация о директории сохранений
        save_dir = os.path.expanduser("~/bot_data")
        save_file = os.path.join(save_dir, "user_data.zlib")
        backup_dir = os.path.join(save_dir, "backups")

        # Проверяем существование директорий
        info['save_dir_exists'] = os.path.exists(save_dir)
        info['backup_dir_exists'] = os.path.exists(backup_dir)

        # Информация о файле сохранения
        if info['save_dir_exists'] and os.path.exists(save_file):
            info['save_file_size'] = os.path.getsize(save_file) / 1024  # KB
            info['save_file_time'] = datetime.fromtimestamp(
                os.path.getmtime(save_file)
            ).strftime('%Y-%m-%d %H:%M:%S')
        else:
            info['save_file_size'] = 0
            info['save_file_time'] = "Файл не найден"

        # Информация о резервных копиях
        if info['backup_dir_exists']:
            backup_files = [f for f in os.listdir(backup_dir)
                            if f.startswith("backup_") and f.endswith(".zlib")]
            info['backup_count'] = len(backup_files)

            if backup_files:
                # Сортируем резервные копии по времени создания (от новых к старым)
                backup_files.sort(reverse=True)
                latest_backup = os.path.join(backup_dir, backup_files[0])
                info['latest_backup_time'] = datetime.fromtimestamp(
                    os.path.getmtime(latest_backup)
                ).strftime('%Y-%m-%d %H:%M:%S')
                info['latest_backup_size'] = os.path.getsize(latest_backup) / 1024  # KB
            else:
                info['latest_backup_time'] = "Нет резервных копий"
                info['latest_backup_size'] = 0
        else:
            info['backup_count'] = 0
            info['latest_backup_time'] = "Директория не найдена"
            info['latest_backup_size'] = 0

        # Информация о последнем сохранении из автосохранения
        if self.last_save_time:
            info['last_save_time'] = datetime.fromtimestamp(
                self.last_save_time
            ).strftime('%Y-%m-%d %H:%M:%S')
            info['last_save_result'] = "Успешно" if self.last_save_result else "Ошибка"
        else:
            info['last_save_time'] = "Неизвестно"
            info['last_save_result'] = "Неизвестно"

        return info

    def get_monitoring_report(self):
        """Формирует отчет о мониторинге для добавления к существующей статистике"""
        # Время работы
        uptime = time.time() - self.start_time
        uptime_hours = int(uptime // 3600)
        uptime_minutes = int((uptime % 3600) // 60)

        # Проверяем системы
        system_status = self.check_systems()
        status_icons = {True: "✅", False: "❌"}

        # Получаем информацию о сохранениях
        save_info = self.get_save_info()

        # Формируем блок отчета
        report_lines = [
            f"\n*🛠 Мониторинг бота:*",
            f"⏱ Время работы: {uptime_hours} ч {uptime_minutes} мин",
            f"",
            f"*Состояние систем:*",
            f"💰 Казино: {status_icons[system_status['casino']]}",
            f"⛏ Майнинг: {status_icons[system_status['mining']]}",
            f"💼 Бизнес: {status_icons[system_status['business']]}",
            f"💾 Сохранение: {status_icons[system_status['saving']]}",
            f"",
            f"*Данные сохранения:*",
            f"📄 Файл данных: {save_info['save_file_size']:.1f} KB (изменен {save_info['save_file_time']})",
            f"📑 Резервных копий: {save_info['backup_count']}",
        ]

        # Добавляем информацию о последней резервной копии, если она есть
        if save_info['backup_count'] > 0:
            report_lines.append(
                f"📎 Последняя копия: {save_info['latest_backup_size']:.1f} KB (создана {save_info['latest_backup_time']})")

        # Добавляем информацию о последнем сохранении
        report_lines.append(f"🔄 Последнее сохранение: {save_info['last_save_time']} ({save_info['last_save_result']})")

        return "\n".join(report_lines)


# Патч для SaveManager для логирования сохранений
def patch_save_manager(save_manager_class, monitor):
    """Добавляет логирование сохранений в SaveManager"""
    original_save_data = save_manager_class.save_data

    @classmethod
    def save_data_with_monitoring(cls, casino, mining, business=None):
        start_time = time.time()
        result = original_save_data(casino, mining, business)
        monitor.record_save_event(result, start_time)
        return result

    save_manager_class.save_data = save_data_with_monitoring