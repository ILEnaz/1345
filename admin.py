import os
import logging
import time
import pickle
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from utils import format_number, resolve_user_id


class AdminPanel:
    # Обновленная константа с текстом команд
    ADMIN_COMMANDS = (
        "🛠 *Админ-команды:*\n"
        "📋 `/админ` - Справка\n"
        "📊 `/логи [N]` - Последние N логов\n"
        "💸 `/выдать [ID] [Сумма]` - Выдача средств\n"
        "🎟 `/сд-промо [код] [сумма] [использований]` - Создать промокод\n"
        "👤 `/инфо [ID]` - Информация о пользователе\n\n"
        "💎 `/сет-вип [ID] [дни]` - Выдать VIP-статус\n"
        "💎 `/убр-вип [ID]` - Убрать VIP-статус\n"
        "💰 `/сет-курс [курс]` - Установить курс BTC\n"
        "📊 `/стат` - Статистика бота\n"
        "📢 `/сообщения [сообщение]` - Рассылка всем\n"
        "📢 `/соб-лич [ID] [сообщение]` - Сообщение пользователю\n"
        "💾 `/backup` - Создать резервную копию\n"
        "💾 `/restore [backup_id]` - Восстановить из копии"
    )

    # Кэшированный список админов
    _admin_ids = None

    @classmethod
    def _get_admins(cls):
        """Получает список ID администраторов из переменной окружения"""
        # Используем кэш если он заполнен
        if cls._admin_ids is not None:
            return cls._admin_ids

        admins = os.getenv("ADMINS", "")
        try:
            # Преобразуем строку с ID в список целых чисел
            cls._admin_ids = [int(a.strip()) for a in admins.split(",") if a.strip()]
            return cls._admin_ids
        except Exception as e:
            logging.error(f"Ошибка чтения списка админов: {e}")
            cls._admin_ids = []
            return []

    @staticmethod
    def admin_give_money(casino_system, bot, admin_id, to_user_reference, amount):
        """
        Функция для админов, позволяющая выдать деньги пользователю
        """
        # Используем resolve_user_id из utils
        # Check if the user is an admin
        if not AdminPanel.is_admin(admin_id):
            return False, "❌ У вас нет прав для выполнения этой команды.", None

        # Resolve the recipient ID
        success, result = resolve_user_id(bot, to_user_reference)
        if not success:
            return False, result, None  # This is the error message from resolve_user_id

        to_user_id = result

        try:
            # Ensure user exists
            casino_system.ensure_user_exists(to_user_id)

            # Give money with limit check
            if hasattr(casino_system, 'MAX_BALANCE') and amount > casino_system.MAX_BALANCE:
                return False, f"❌ Превышен лимит выдачи ({format_number(casino_system.MAX_BALANCE)} ₽)", None
            casino_system.deposit(to_user_id, amount)

            # Get recipient's info for the message
            try:
                user = bot.get_chat(to_user_id)
                username = f"@{user.username}" if user.username else f"{user.first_name}"
            except:
                username = f"ID: {to_user_id}"

            return True, f"✅ Выдано {format_number(amount)} ₽ пользователю {username}", to_user_id

        except Exception as e:
            return False, f"❌ Ошибка при выдаче средств: {str(e)}", None

    @staticmethod
    def is_admin(user_id):
        """Проверяет, является ли пользователь администратором"""
        return user_id in AdminPanel._get_admins()

    @staticmethod
    def get_logs(lines=10):
        """Получает последние N строк из лог-файла"""
        try:
            # Ограничиваем количество строк разумным значением
            lines = max(1, min(lines, 100))

            # Проверяем, существует ли файл логов
            if not os.path.exists('bot.log'):
                return "Файл логов не найден."

            # Проверяем, не пустой ли файл
            if os.path.getsize('bot.log') == 0:
                return "Файл логов пуст."

            with open('bot.log', 'r', encoding='utf-8') as f:
                # Читаем все строки и берем последние N
                log_lines = f.readlines()

                if not log_lines:
                    return "Файл логов пуст."

                # Берем только последние lines строк
                logs = log_lines[-lines:]

                # Объединяем строки в одну
                result = "".join(logs)

                # Если строки пустые, сообщаем об этом
                if not result.strip():
                    return "Файл логов содержит только пустые строки."

                return result
        except Exception as e:
            logging.error(f"Ошибка чтения логов: {e}")
            return f"Ошибка чтения логов: {str(e)}"

    @staticmethod
    def get_system_stats(casino_system, mining_system, business_system=None):
        """Получает общую статистику о системе"""
        try:
            # Базовая статистика
            total_users = len(casino_system.balances)

            # Исправление: преобразуем строки в числа при сравнении
            active_users = 0
            for uid, balance in casino_system.balances.items():
                # Преобразуем баланс в число, если он строка
                if isinstance(balance, str):
                    try:
                        balance_num = float(balance)
                    except (ValueError, TypeError):
                        balance_num = 0
                else:
                    balance_num = balance

                if balance_num > 0:
                    active_users += 1

            vip_users = sum(1 for uid in casino_system.vip_users if casino_system.is_vip_active(uid))

            # Экономика - обеспечиваем преобразование всех значений в числа
            total_balance = 0
            for balance in casino_system.balances.values():
                if isinstance(balance, str):
                    try:
                        balance_num = float(balance)
                    except (ValueError, TypeError):
                        balance_num = 0
                else:
                    balance_num = balance

                total_balance += balance_num

            avg_balance = total_balance / active_users if active_users > 0 else 0

            # Майнинг
            total_farms = sum(len(farms) for farms in mining_system.user_farms.values())

            # Бизнесы (если система бизнесов передана)
            total_businesses = 0
            if business_system is not None:
                total_businesses = sum(len(businesses) for businesses in business_system.user_businesses.values())
                businesses_info = f"\n💼 Всего бизнесов: `{total_businesses}`"
            else:
                businesses_info = ""

            # Форматирование результата
            stats = (
                "📊 *Общая статистика:*\n"
                f"👥 Всего пользователей: `{total_users}`\n"
                f"👤 Активных пользователей: `{active_users}`\n"
                f"💎 VIP-пользователей: `{vip_users}`\n\n"
                f"💰 Общий баланс: `{format_number(total_balance)} ₽`\n"
                f"💵 Средний баланс: `{format_number(avg_balance)} ₽`\n\n"
                f"⛏ Всего ферм: `{total_farms}`{businesses_info}\n"
                f"💲 Текущий курс BTC: `{format_number(mining_system.btc_rate)} ₽`"
            )
            return stats
        except Exception as e:
            logging.error(f"Ошибка получения статистики: {e}")
            return f"❌ Ошибка получения статистики: {str(e)}"

    @staticmethod
    def create_backup(casino_system, mining_system, business_system=None):
        """Создает резервную копию данных вручную"""
        try:
            from saving import SaveManager

            # Текущая дата и время для имени файла
            timestamp = datetime.now(ZoneInfo('Europe/Moscow')).strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(SaveManager.BACKUP_DIR, f"admin_backup_{timestamp}.pkl")

            # Создаем данные для сохранения
            data = {
                'version': 2,
                'balances': casino_system.balances,
                'vip_users': casino_system.vip_users,
                'used_promocodes': casino_system.used_promocodes,
                'registration_dates': casino_system.registration_dates,
                'user_farms': mining_system.user_farms,
                'btc_rate': mining_system.btc_rate,
                'last_btc_update': mining_system.last_btc_update,
                'next_btc_update': mining_system.next_btc_update,
                'timestamp': time.time()
            }

            # Добавляем данные о бизнесах если они есть
            if business_system is not None:
                data['user_businesses'] = business_system.user_businesses

            # Создаем директорию если не существует
            os.makedirs(SaveManager.BACKUP_DIR, exist_ok=True)

            # Сохраняем резервную копию
            with open(backup_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

            return True, f"✅ Резервная копия создана: admin_backup_{timestamp}.pkl"
        except Exception as e:
            logging.error(f"Ошибка создания резервной копии: {e}")
            return False, f"❌ Ошибка создания резервной копии: {str(e)}"

    @staticmethod
    def restore_backup(backup_id, casino_system, mining_system, business_system=None):
        """Восстанавливает данные из указанной резервной копии"""
        try:
            from saving import SaveManager

            # Проверяем существование файла
            backup_path = os.path.join(SaveManager.BACKUP_DIR, backup_id)
            if not os.path.exists(backup_path):
                return False, "❌ Указанная резервная копия не найдена"

            # Загружаем данные
            with open(backup_path, 'rb') as f:
                data = pickle.load(f)

            # Проверяем валидность данных
            required_keys = [
                'version', 'balances', 'vip_users', 'used_promocodes',
                'registration_dates', 'user_farms', 'btc_rate'
            ]
            if not all(key in data for key in required_keys):
                return False, "❌ Резервная копия повреждена или имеет неверный формат"

            # Восстанавливаем данные
            casino_system.balances = data.get('balances', {})
            casino_system.vip_users = data.get('vip_users', {})
            casino_system.used_promocodes = data.get('used_promocodes', {})
            casino_system.registration_dates = data.get('registration_dates', {})

            mining_system.user_farms = data.get('user_farms', {})
            mining_system.btc_rate = data.get('btc_rate', 80000)

            # Восстанавливаем данные о бизнесах если система передана
            if business_system is not None and 'user_businesses' in data:
                business_system.user_businesses = data.get('user_businesses', {})

            # Текущие timestamps для обновления BTC
            mining_system.last_btc_update = time.time()
            mining_system.next_btc_update = mining_system.last_btc_update + mining_system.HOUR_IN_SECONDS

            # Сохраняем обновленные данные
            if business_system is not None:
                SaveManager.save_data(casino_system, mining_system, business_system)
            else:
                SaveManager.save_data(casino_system, mining_system)

            return True, f"✅ Данные успешно восстановлены из {backup_id}"
        except Exception as e:
            logging.error(f"Ошибка восстановления: {e}")
            return False, f"❌ Ошибка восстановления: {str(e)}"

    @staticmethod
    def list_backups():
        """Возвращает список доступных резервных копий"""
        try:
            from saving import SaveManager

            if not os.path.exists(SaveManager.BACKUP_DIR):
                return []

            # Получаем все файлы .pkl в директории бэкапов
            backups = [f for f in os.listdir(SaveManager.BACKUP_DIR) if f.endswith('.pkl')]
            return sorted(backups, reverse=True)  # Сортируем по времени (новые сверху)
        except Exception as e:
            logging.error(f"Ошибка получения списка резервных копий: {e}")
            return []