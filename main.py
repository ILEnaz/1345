import os
from dotenv import load_dotenv
import telebot
from telebot import types, formatting
from HI import Greetings
from Casino import RouletteSystem
from Mining import MiningSystem
from functools import partial
from saving import SaveManager
from admin import AdminPanel
import time
from utils import format_number, transfer_money
from promocodes import PromocodeSystem
from Casino import CasinoSystem
import atexit
import converter
from Business import BusinessSystem
from monitoring import BotMonitor, patch_save_manager
from zoneinfo import ZoneInfo
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import warnings
import random
from telebot import types
from RouletteImage import RouletteRenderer
from utils import format_number
from converter import parse_amount

warnings.filterwarnings("ignore", category=Warning, message=".*zone attribute is specific to pytz.*")
# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Создаем логгер для main
logger = logging.getLogger('main')
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
bot = telebot.TeleBot(TG_TOKEN)
ui = Greetings()
def get_timezone(zone_name):
    """Получает объект временной зоны по имени"""
    try:
        return ZoneInfo(zone_name)
    except Exception as e:
        logging.error(f"Ошибка создания временной зоны {zone_name}: {e}")
        return ZoneInfo('UTC')
def start_btc_scheduler(mining: MiningSystem):
    """Запускает планировщик обновления курса BTC"""
    # Используем ZoneInfo вместо pytz
    scheduler = BackgroundScheduler(timezone=get_timezone('Europe/Moscow'))
    def update_and_save():
        if mining.update_btc_rate():
            try:
                SaveManager.save_data(casino, mining)
                logger.info("Данные сохранены после обновления курса BTC")
            except Exception as e:
                logger.error(f"Ошибка сохранения после обновления курса: {str(e)}")
    scheduler.add_job(
        func=update_and_save,
        trigger='interval',
        minutes=60,
        max_instances=1,
        id='btc_update_job'
    )
    try:
        scheduler.start()
        logger.info("Планировщик курса BTC активирован")
    except Exception as e:
        logger.error(f"Ошибка при запуске планировщика BTC: {str(e)}")
# Измените функцию setup_autosave
def setup_autosave(casino, mining, business=None, interval_minutes=120):
    """Настраивает автоматическое сохранение."""
    # Используем ZoneInfo вместо pytz
    scheduler = BackgroundScheduler(timezone=get_timezone('Europe/Moscow'))
    def save_wrapper():
        try:
            SaveManager.save_data(casino, mining, business)
            logger.info("Автосохранение выполнено")
        except Exception as e:
            logger.error(f"Ошибка автосохранения: {str(e)}")
    scheduler.add_job(
        func=save_wrapper,
        trigger='interval',
        minutes=interval_minutes,
        id='autosave_job'
    )
    try:
        scheduler.start()
        logger.info(f"Автосохранение настроено (интервал: {interval_minutes} мин)")
        atexit.register(save_wrapper)
    except Exception as e:
        logger.error(f"Ошибка запуска автосохранения: {str(e)}")
# Функция для проверки рабочего времени остается почти такой же:
def is_working_time():
    """Проверяет, рабочее ли сейчас время (НЕ с 00:00 до 05:00 МСК)"""
    # Используем ZoneInfo вместо pytz
    moscow_time = datetime.now(ZoneInfo('Europe/Moscow'))
    # Бот НЕ работает с 00:00 до 5:00
    return not (0 <= moscow_time.hour < 5)


# Загрузка данных
data, is_new = SaveManager.load_data()

# Инициализация систем
casino = CasinoSystem()
mining = MiningSystem(casino)
mining.casino = casino  # Связываем системы
business = BusinessSystem(casino)
# Заполнение данных (игнорируем сохраненные last_btc_update и next_btc_update)
casino.balances = data.get('balances', {})
casino.vip_users = data.get('vip_users', {})
casino.used_promocodes = data.get('used_promocodes', {})
casino.registration_dates = data.get('registration_dates', {})
business.user_businesses = data.get('user_businesses', {})
mining.user_farms = data.get('user_farms', {})
mining.btc_rate = data.get('btc_rate', 80000)  # Сохраняем курс, но не время обновления
# Устанавливаем текущее время при запуске
mining.last_btc_update = time.time()
mining.next_btc_update = mining.last_btc_update + mining.HOUR_IN_SECONDS  # +1 час


# Функция для объединения данных пользователей без люкс-вип и USDT
def merge_user_data():
    import time
    from logging import getLogger

    # Создаем логгер
    logger = getLogger(__name__)

    logger.info("Запуск процесса поиска и объединения дубликатов...")
    logger.info(f"Текущее количество пользователей: {len(casino.balances)}")

    # Создаем список уникальных ID
    unique_ids = []
    # Создаем отдельный словарь для обработанных данных
    processed_balances = {}
    processed_farms = {}
    processed_businesses = {}
    processed_vip = {}

    # Счетчики для отчета
    total_users = len(casino.balances)
    duplicate_count = 0

    # Первый проход - проверяем наличие дубликатов и собираем максимальные значения
    for user_id, balance in list(casino.balances.items()):
        # Если пользователь уже обработан, считаем его дубликатом
        if user_id in unique_ids:
            duplicate_count += 1
            # Обновляем баланс, если текущий больше
            if balance > processed_balances.get(user_id, 0):
                processed_balances[user_id] = balance
                logger.info(f"Найден дубликат ID {user_id}, обновлен баланс до {balance}")
        else:
            # Первое появление ID
            unique_ids.append(user_id)
            processed_balances[user_id] = balance

            # Копируем фермы, если есть
            if hasattr(mining, 'user_farms') and user_id in mining.user_farms:
                processed_farms[user_id] = mining.user_farms[user_id]

            # Копируем бизнесы, если есть
            if hasattr(business, 'user_businesses') and user_id in business.user_businesses:
                processed_businesses[user_id] = business.user_businesses[user_id]

            # Копируем VIP статус, если есть
            if hasattr(casino, 'vip_users') and user_id in casino.vip_users:
                processed_vip[user_id] = casino.vip_users[user_id]

    if duplicate_count == 0:
        logger.info("Дубликаты не найдены, слияние не требуется")
        return

    logger.info(f"Найдено {duplicate_count} дубликатов среди {total_users} пользователей")

    # Применяем обработанные данные
    logger.info("Применение обработанных данных...")

    # Обновляем балансы
    casino.balances = processed_balances
    logger.info(f"Обновлены балансы, теперь {len(casino.balances)} пользователей")

    # Обновляем фермы, если они есть
    if hasattr(mining, 'user_farms'):
        mining.user_farms = processed_farms
        logger.info(f"Обновлены фермы, теперь {len(mining.user_farms)} записей")

    # Обновляем бизнесы, если они есть
    if hasattr(business, 'user_businesses'):
        business.user_businesses = processed_businesses
        logger.info(f"Обновлены бизнесы, теперь {len(business.user_businesses)} записей")

    # Обновляем VIP статусы
    if hasattr(casino, 'vip_users'):
        casino.vip_users = processed_vip
        logger.info(f"Обновлены VIP статусы, теперь {len(casino.vip_users)} записей")

    # Сохраняем объединенные данные
    SaveManager.save_data(casino, mining, business)
    logger.info("Слияние данных пользователей завершено успешно")
    logger.info(f"Итого: обработано {total_users} пользователей, удалено {duplicate_count} дубликатов")
merge_user_data()


# Функция для исправления одинаковых ID в разных форматах
def fix_duplicate_id_formats():
    from logging import getLogger
    logger = getLogger(__name__)

    logger.info("Запуск проверки и исправления форматов ID...")

    # Преобразуем все ID в числовой формат
    numeric_balances = {}
    numeric_vip_users = {}
    numeric_farms = {}
    numeric_businesses = {}

    # Подсчет дубликатов
    string_count = 0
    numeric_count = 0

    # Анализируем и отображаем все виды ключей
    logger.info("Анализ типов ключей в балансах:")
    for user_id in casino.balances:
        if isinstance(user_id, str):
            string_count += 1
            try:
                numeric_id = int(user_id)
                logger.info(f"Строковый ID: {user_id}, преобразован в числовой: {numeric_id}")
            except:
                logger.info(f"Строковый ID (не числовой): {user_id}")
        else:
            numeric_count += 1
            logger.info(f"Числовой ID: {user_id}")

    logger.info(f"Найдено строковых ID: {string_count}, числовых ID: {numeric_count}")

    # Преобразуем все ID в балансах в числовой формат
    for user_id, balance in list(casino.balances.items()):
        try:
            # Преобразуем строковый ID в числовой, если это возможно
            numeric_id = int(user_id) if isinstance(user_id, str) else user_id

            # Обновляем значение или используем максимальное
            if numeric_id in numeric_balances:
                numeric_balances[numeric_id] = max(numeric_balances[numeric_id], balance)
                logger.info(f"Объединение балансов для ID {numeric_id}: новый баланс {numeric_balances[numeric_id]}")
            else:
                numeric_balances[numeric_id] = balance
        except:
            # Если ID не преобразуется в число, оставляем как есть
            numeric_balances[user_id] = balance

    # Преобразуем все ID в VIP пользователях в числовой формат
    if hasattr(casino, 'vip_users'):
        for user_id, expires in list(casino.vip_users.items()):
            try:
                numeric_id = int(user_id) if isinstance(user_id, str) else user_id

                # Обновляем значение или используем более позднюю дату
                if numeric_id in numeric_vip_users:
                    numeric_vip_users[numeric_id] = max(numeric_vip_users[numeric_id], expires)
                    logger.info(f"Объединение VIP статусов для ID {numeric_id}")
                else:
                    numeric_vip_users[numeric_id] = expires
            except:
                numeric_vip_users[user_id] = expires

    # Преобразуем все ID в фермах в числовой формат
    if hasattr(mining, 'user_farms'):
        for user_id, farms in list(mining.user_farms.items()):
            try:
                numeric_id = int(user_id) if isinstance(user_id, str) else user_id

                # Если у пользователя уже есть фермы, объединяем их
                if numeric_id in numeric_farms:
                    if isinstance(farms, list) and isinstance(numeric_farms[numeric_id], list):
                        # Список ферм - просто объединяем
                        numeric_farms[numeric_id].extend(farms)
                        logger.info(f"Объединение ферм (список) для ID {numeric_id}")
                    elif isinstance(farms, dict) and isinstance(numeric_farms[numeric_id], dict):
                        # Словарь ферм - обновляем с новыми значениями
                        numeric_farms[numeric_id].update(farms)
                        logger.info(f"Объединение ферм (словарь) для ID {numeric_id}")
                    else:
                        logger.info(f"Неизвестный формат данных ферм для ID {numeric_id}")
                else:
                    numeric_farms[numeric_id] = farms
            except:
                numeric_farms[user_id] = farms

    # Преобразуем все ID в бизнесах в числовой формат
    if hasattr(business, 'user_businesses'):
        for user_id, businesses_data in list(business.user_businesses.items()):
            try:
                numeric_id = int(user_id) if isinstance(user_id, str) else user_id

                # Если у пользователя уже есть бизнесы, объединяем их
                if numeric_id in numeric_businesses:
                    if isinstance(businesses_data, list) and isinstance(numeric_businesses[numeric_id], list):
                        # Список бизнесов - просто объединяем
                        numeric_businesses[numeric_id].extend(businesses_data)
                        logger.info(f"Объединение бизнесов (список) для ID {numeric_id}")
                    elif isinstance(businesses_data, dict) and isinstance(numeric_businesses[numeric_id], dict):
                        # Словарь бизнесов - обновляем с новыми значениями
                        numeric_businesses[numeric_id].update(businesses_data)
                        logger.info(f"Объединение бизнесов (словарь) для ID {numeric_id}")
                    else:
                        logger.info(f"Неизвестный формат данных бизнесов для ID {numeric_id}")
                else:
                    numeric_businesses[numeric_id] = businesses_data
            except:
                numeric_businesses[user_id] = businesses_data

    # Обновляем данные с новыми числовыми ключами
    casino.balances = numeric_balances
    logger.info(f"Обновлены балансы, новое количество: {len(casino.balances)}")

    if hasattr(casino, 'vip_users'):
        casino.vip_users = numeric_vip_users
        logger.info(f"Обновлены VIP статусы, новое количество: {len(casino.vip_users)}")

    if hasattr(mining, 'user_farms'):
        mining.user_farms = numeric_farms
        logger.info(f"Обновлены фермы, новое количество: {len(mining.user_farms)}")

    if hasattr(business, 'user_businesses'):
        business.user_businesses = numeric_businesses
        logger.info(f"Обновлены бизнесы, новое количество: {len(business.user_businesses)}")

    # Сохраняем изменения
    SaveManager.save_data(casino, mining, business)
    logger.info("Исправление форматов ID и объединение дубликатов завершено.")
fix_duplicate_id_formats()
# Настройка автосохранения
setup_autosave(casino, mining, business, interval_minutes=120)
# Устанавливаем текущее время при запуске
# Запуск планировщика BTC
start_btc_scheduler(mining)


# Общие утилиты
def get_user_id(message):
    return message.from_user.id


def check_balance(user_id, amount):
    return casino.get_balance(user_id) >= amount


def handle_common_error(chat_id, error_msg):
    bot.send_message(
        chat_id,
        f"{error_msg}",
        reply_markup=create_main_keyboard()  # Добавьте эту строку
    )


def create_main_keyboard():
    return ui.create_keyboard()


SUPPORT_USERNAME = "@Kykodor"  # Имя аккаунта поддержки
MIN_TRANSFER = 10_000_000  # Минимальная сумма перевода
MIN_VIP_DAYS = 1  # Минимальное количество дней для покупки VIP
MAX_VIP_DAYS = 30  # Максимальное количество дней для покупки VIP

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)


def check_working_time(func):
    """Декоратор для проверки рабочего времени"""

    def wrapper(message):
        if is_working_time():
            return func(message)
        else:
            moscow_time = datetime.now(ZoneInfo('Europe/Moscow'))
            bot.send_message(
                message.chat.id,
                f"⏰ Бот работает не 0:00 до 5:00 по МСК времени.\n"
                f"Текущее время: {moscow_time.strftime('%H:%M')} МСК"
            )

    return wrapper
bot_monitor = BotMonitor(casino, mining, business)
patch_save_manager(SaveManager, bot_monitor)
# Обработчики команд
@bot.message_handler(commands=['start'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/start', 'start'])
@check_working_time
def start(message):
    username = message.from_user.first_name or message.from_user.username or "Игрок"
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {username}!\n\n{Greetings.HELP_MESSAGE}",
        reply_markup=create_main_keyboard(),
        parse_mode="Markdown"
    )


@bot.message_handler(commands=['баланс'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/баланс', 'баланс'])
@check_working_time
def handle_balance_command(message):
    user_id = get_user_id(message)
    casino.ensure_user_exists(user_id)

    balance = casino.get_balance(user_id)
    balance_display = business.format_full_balance(balance)  # Новый метод

    # Проверяем VIP-статус и доход от бизнесов (остается без изменений)
    vip_status = "✅" if casino.is_vip_active(user_id) else "❌"
    vip_expires = ""
    if casino.is_vip_active(user_id):
        expires_timestamp = casino.vip_users.get(user_id, 0)
    hourly_income = business.get_hourly_income(user_id)
    income_text = ""
    # Отправка сообщения с полным балансом
    bot.send_message(
        message.chat.id,
        f"💰 *Ваш баланс*: {balance_display} ₽\n"
        f"💎 VIP-статус: {vip_status}{vip_expires}{income_text}",
        parse_mode="Markdown"
    )
@bot.message_handler(commands=['айди'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/айди', 'айди'])
@check_working_time
def handle_id_command(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"🆔 Ваш ID: `{user_id}`", parse_mode="Markdown")


@bot.message_handler(commands=['промокод'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/промокод', 'промокод')))
@check_working_time
def handle_promocode(message):
    try:
        user_id = message.from_user.id
        args = message.text.split()

        if len(args) < 2:
            raise ValueError("Введите промокод после команды\nПример: /промокод ПРОМОКОД")

        promo_code = args[1].upper()
        promocodes = PromocodeSystem.load_promocodes()

        if promo_code not in promocodes:
            raise ValueError("❌ Недействительный промокод")

        if user_id in casino.used_promocodes and promo_code in casino.used_promocodes[user_id]:
            raise ValueError("⚠️ Вы уже активировали этот промокод")

        amount = int(promocodes[promo_code]['amount'])

        # Начисление бонуса
        casino.deposit(user_id, amount)

        # Обновление использованных промокодов
        if user_id not in casino.used_promocodes:
            casino.used_promocodes[user_id] = []
        casino.used_promocodes[user_id].append(promo_code)

        # Обновление счетчика использований
        promocodes[promo_code]['max_uses'] -= 1
        if promocodes[promo_code]['max_uses'] <= 0:
            del promocodes[promo_code]
        PromocodeSystem.save_promocodes(promocodes)

        bot.send_message(
            message.chat.id,
            f"🎉 Промокод активирован! Получено +{format_number(amount)} ₽",
            parse_mode="Markdown"
        )

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


@bot.message_handler(func=lambda m: m.text in ["🆘Помощь", "🆘 Помощь"])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/помощь', 'помощь')))
@check_working_time
def info_commands(message):
    bot.send_message(message.chat.id, Greetings.HELP_MESSAGE, parse_mode="Markdown")


# Обновленный обработчик команды топ
@bot.message_handler(commands=['топ'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/топ', 'топ'])
@check_working_time
def show_top_players(message):
    try:
        top_players = casino.get_top_players()
        if not top_players:
            bot.send_message(message.chat.id, "🏆 Пока никто не в топе!")
            return

        formatted_top = []
        for idx, (user_id, data) in enumerate(top_players, 1):
            try:
                user = bot.get_chat(user_id)
                username = user.username or user.first_name

                # Проверяем, является ли пользователь администратором
                is_admin = AdminPanel.is_admin(user_id)
                is_vip = data['is_vip']

                # Добавляем соответствующие метки
                admin_tag = "👑 " if is_admin else ""
                vip_tag = "💎 " if is_vip else ""
                combined_tag = admin_tag + vip_tag

                # Кликабельное упоминание с @
                line = (
                    f"{idx}. {combined_tag}[@{formatting.escape_markdown(username)}](tg://user?id={user_id})\n"
                    f"      └ 🆔 ID: `{user_id}`\n"  # Added ID line
                    f"      └ 💰 Баланс: `{format_number(data['balance'])} ₽`"
                )
                formatted_top.append(line)

            except Exception as e:
                logging.error(f"Ошибка пользователя {user_id}: {str(e)}")
                continue

        bot.send_message(
            message.chat.id,
            "🏆 *Топ игроков:*\n\n" + "\n\n".join(formatted_top),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        handle_common_error(message.chat.id, f"Ошибка топа: {str(e)}")


def format_top_players(top_players, casino):
    formatted = []
    for idx, (user_id, balance) in enumerate(top_players, 1):
        try:
            user = bot.get_chat(user_id)
            username = user.username or user.first_name
            vip_tag = " (VIP)" if casino.is_vip_active(user_id) else ""
            line = f"{idx}. {username}{vip_tag} — {format_number(balance)} ₽"
            formatted.append(line)
        except:
            continue
    return "\n".join(formatted)

# Обработчик для снятия прибыли с бизнеса
@bot.message_handler(func=lambda m: m.text and m.text in ["💼Бизнес", "💼 Бизнес"])
@check_working_time
def business_menu(message):
    """Обработчик для кнопки 'Бизнес' в главном меню"""
    user_id = get_user_id(message)
    casino.ensure_user_exists(user_id)
    # Проверяем наличие бизнесов у пользователя
    user_businesses = business.user_businesses.get(user_id, [])
    if user_businesses:
        # Если есть бизнесы, сразу показываем первый бизнес пользователя
        first_business = user_businesses[0]
        business_type = first_business['type']
        text, markup = business.get_business_details(user_id, business_type)
        bot.send_message(
            message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        # Если нет бизнесов, показываем список доступных для покупки
        business_list = business.format_business_list()
        bot.send_message(
            message.chat.id,
            business_list,
            parse_mode="Markdown"
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('business_collect_'))
def handle_collect_income(call):
    user_id = call.from_user.id
    business_type = call.data.split('_')[2]

    try:
        # Сохраняем исходное состояние
        original_text, original_markup = business.get_business_details(user_id, business_type)

        # Собираем прибыль
        withdrawn = business.withdraw_business_funds(user_id, business_type)

        if withdrawn > 0:
            # Получаем обновленные данные
            new_text, new_markup = business.get_business_details(user_id, business_type)

            # Проверяем изменения
            if new_text != original_text or str(new_markup) != str(original_markup):
                bot.edit_message_text(
                    new_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=new_markup
                )
                bot.answer_callback_query(call.id, f"✅ Собрано {business.format_price_with_prefix(withdrawn)} ₽")
            else:
                bot.answer_callback_query(call.id, "⚠️ Нет изменений для обновления")

        else:
            bot.answer_callback_query(call.id, "❌ Нет накопленной прибыли", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка при сборе прибыли: {str(e)}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка, попробуйте позже")
@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_business_'))
def withdraw_business_callback(call):
    user_id = call.from_user.id
    business_type = call.data.split('_')[2]
    # Снимаем прибыль с конкретного бизнеса
    withdrawn = business.withdraw_business_funds(user_id, business_type)
    if withdrawn > 0:
        bot.answer_callback_query(
            call.id,
            f"✅ Вы сняли {format_number(withdrawn)} ₽ с бизнеса",
            show_alert=True
        )
    else:
        bot.answer_callback_query(
            call.id,
            "❌ Нет доступной прибыли для снятия",
            show_alert=True
        )
    # Обновляем информацию о бизнесе
    text, markup = business.get_business_details(user_id, business_type)
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


# Обработчик для подтверждения продажи бизнеса
@bot.message_handler(commands=['продать_бизнес'])
def handle_sell_business_command(message):
    user_id = message.from_user.id
    if not business.has_business(user_id):
        bot.reply_to(message, "❌ У вас нет бизнеса.")
        return

    success, result = business.sell_business(user_id)
    if success:
        bot.reply_to(message, result)
    else:
        bot.reply_to(message, f"❌ Ошибка: {result}")
# Обновленный обработчик подтверждения продажи
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_sell_'))
def confirm_sell_business_callback(call):
    try:
        user_id = call.from_user.id
        business_type = call.data.replace('confirm_sell_', '')  # Извлекаем полный ключ

        if business_type not in business.BUSINESS_TYPES:
            available = "\n".join([f"- {name}" for name in business.BUSINESS_NAMES.values()])
            bot.answer_callback_query(
                call.id,
                f"❌ Бизнес не найден. Доступные:\n{available}",
                show_alert=True
            )
            return

        business_info = business.get_business_info(user_id, business_type)
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Да, продать", callback_data=f"sell_confirm_{business_type}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data=f"view_business_{business_type}")
        )
        bot.edit_message_text(
            f"⚠️ *Подтверждение продажи*\n\nВы точно хотите продать {business_info['name']}?",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка в confirm_sell: {str(e)}")
# Обновленный обработчик продажи
@bot.callback_query_handler(func=lambda call: call.data.startswith('sell_confirm_'))
def sell_business_callback(call):
    try:
        user_id = call.from_user.id
        business_type = call.data.split('_confirm_')[1]
        success, result = business.sell_business(user_id, business_type)
        if success:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, result, reply_markup=create_main_keyboard())
        else:
            bot.answer_callback_query(call.id, result, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в sell_confirm: {str(e)}")


# Обработчик для покупки бизнеса
@bot.callback_query_handler(func=lambda call: call.data.startswith("business_buy_"))
def buy_business_callback(call):
    user_id = call.from_user.id
    business_type = call.data.replace("business_buy_", "")
    if business_type == "menu":
        # Показываем список бизнесов
        markup = business.create_business_purchase_keyboard()
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=business.format_business_list(),
            parse_mode="Markdown",
            reply_markup=markup
        )
        return
    # Проверяем, есть ли у пользователя уже бизнес такого типа
    user_businesses = business.user_businesses.get(user_id, [])
    # Если у пользователя уже есть какой-то бизнес (ограничение в 1 бизнес)
    if user_businesses:
        existing_business = user_businesses[0]  # Берем первый бизнес в списке
        existing_type = existing_business['type']
        existing_name = business.BUSINESS_NAMES.get(existing_type)

        # Получаем информацию о существующем бизнесе
        info = business.get_business_info(user_id, existing_type)
        income = info.get('hourly_income', 0)
        income_display = business.format_price_with_prefix(income)
        funds = info.get('funds', 0)
        funds_display = business.format_price_with_prefix(funds)

        # Создаем сообщение с подробной информацией
        error_message = (
            f"❌ У вас уже есть бизнес: {existing_name}\n\n"
            f"💰 Накоплено: {funds_display} ₽\n"
            f"💸 Доход: {income_display} ₽/час\n\n"
            f"ℹ️ Вы не можете владеть более чем одним бизнесом.\n"
            f"Сначала продайте текущий бизнес, чтобы купить новый."
        )

        bot.answer_callback_query(
            call.id,
            "У вас уже есть бизнес. Сначала продайте его.",
            show_alert=True
        )

        # Показываем информацию о текущем бизнесе и клавиатуру для управления
        text, markup = business.get_business_details(user_id, existing_type)

        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        return
    # Проверяем, хватает ли денег
    user_balance = casino.get_balance(user_id)
    business_price = business.BUSINESS_TYPES[business_type]['price']
    if user_balance < business_price:
        bot.answer_callback_query(
            call.id,
            f"❌ Недостаточно средств для покупки бизнеса",
            show_alert=True
        )
        bot.edit_message_text(
            f"❌ *Недостаточно средств*\n\n"
            f"Для покупки {business.BUSINESS_NAMES.get(business_type)} требуется {format_number(business_price)} ₽\n"
            f"Цена бизнеса: {format_number(business_price)} ₽\n"
            f"Ваш баланс: {format_number(user_balance)} ₽",
            parse_mode="Markdown",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return
    # Покупаем бизнес
    success, result_text = business.buy_business(user_id, business_type)
    if success:
        bot.answer_callback_query(call.id, "✅ Бизнес успешно куплен")
        # Сразу показываем информацию о бизнесе
        text, markup = business.get_business_details(user_id, business_type)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка при покупке бизнеса", show_alert=True)
        bot.send_message(call.message.chat.id, result_text, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_sell_'))
def confirm_sell_business_callback(call):
    try:
        user_id = call.from_user.id
        business_type = call.data.split('confirm_sell_')[1]  # Получаем полное название

        # Проверка существования бизнеса
        if business_type not in business.BUSINESS_TYPES:
            bot.answer_callback_query(call.id, "❌ Ошибка: бизнес не найден", show_alert=True)
            return

        business_info = business.get_business_info(user_id, business_type)
        if not business_info:
            raise ValueError("Бизнес не найден")

        sell_price = business_info['sell_price']
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Да, продать", callback_data=f"sell_confirm_{business_type}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data=f"view_business_{business_type}")
        )

        bot.edit_message_text(
            f"⚠️ *Подтверждение продажи*\n\n"
            f"Вы точно хотите продать {business_info['name']}?\n"
            f"Вы получите {business.format_price_with_prefix(sell_price)} ₽ (75% от стоимости).",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        handle_common_error(call.message.chat.id, str(e))


@bot.callback_query_handler(func=lambda call: call.data.startswith('sell_confirm_'))
def sell_business_callback(call):
    try:
        user_id = call.from_user.id
        business_type = call.data.split('sell_confirm_')[1]  # Полное название

        success, result_text = business.sell_business(user_id, business_type)
        if success:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                result_text,
                parse_mode="Markdown",
                reply_markup=create_main_keyboard()
            )
        else:
            bot.answer_callback_query(call.id, result_text, show_alert=True)
    except Exception as e:
        handle_common_error(call.message.chat.id, str(e))
@bot.callback_query_handler(func=lambda call: call.data.startswith('view_business_'))
def view_business_callback(call):
    user_id = call.from_user.id
    business_type = call.data.split('_')[2]
    # Получаем информацию о бизнесе и клавиатуру
    text, markup = business.get_business_details(user_id, business_type)
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


# Обработчик для списка бизнесов
@bot.callback_query_handler(func=lambda call: call.data == 'list_businesses')
def list_businesses_callback(call):
    business_list = business.format_business_list()
    markup = business.create_business_purchase_keyboard()
    bot.edit_message_text(
        business_list,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.message_handler(commands=['бизнес'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/бизнес', 'бизнес'])
@check_working_time
def handle_business_command(message):
    """Обработчик для команды 'бизнес'"""
    user_id = get_user_id(message)
    casino.ensure_user_exists(user_id)
    user_businesses = business.user_businesses.get(user_id, [])
    if user_businesses:
        # Если есть бизнесы, сразу показываем первый бизнес пользователя
        first_business = user_businesses[0]
        business_type = first_business['type']
        text, markup = business.get_business_details(user_id, business_type)
        bot.send_message(
            message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        # Если нет бизнесов, показываем список доступных для покупки
        handle_businesses_list(message)


@bot.message_handler(commands=['бизнесы'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/бизнесы', 'бизнесы'])
@check_working_time
def handle_businesses_list(message):
    """Показывает список всех доступных бизнесов"""
    business_list = business.format_business_list()
    bot.send_message(message.chat.id, business_list, parse_mode="Markdown")


# Обработчик команды для покупки бизнеса по номеру
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith('бизнес '))
@check_working_time
def buy_business_by_number(message):
    user_id = get_user_id(message)
    try:
        args = message.text.split()
        if len(args) < 2:
            raise ValueError("❌ Укажите номер или название бизнеса.")
        # Пытаемся определить бизнес по номеру или названию
        query = args[1].upper()
        # Проверяем, можно ли преобразовать в число
        try:
            business_idx = int(query) - 1
            business_types = list(business.BUSINESS_TYPES.keys())
            if business_idx < 0 or business_idx >= len(business_types):
                raise ValueError(f"❌ Номер бизнеса должен быть от 1 до {len(business_types)}.")
            business_type = business_types[business_idx]
        except ValueError:
            # Если не число, ищем по названию
            business_type = None
            for key, name in business.BUSINESS_NAMES.items():
                if query in name.upper() or query in key:
                    business_type = key
                    break
            if not business_type:
                raise ValueError("❌ Бизнес с таким номером или названием не найден.")
        # Проверяем, есть ли у пользователя уже бизнес (ограничение в 1 бизнес)
        user_businesses = business.user_businesses.get(user_id, [])
        if user_businesses:
            existing_business = user_businesses[0]  # Берем первый бизнес
            existing_type = existing_business['type']
            existing_name = business.BUSINESS_NAMES.get(existing_type)

            # Получаем информацию о существующем бизнесе
            info = business.get_business_info(user_id, existing_type)
            income = info.get('hourly_income', 0)
            income_display = business.format_price_with_prefix(income)
            funds = info.get('funds', 0)
            funds_display = business.format_price_with_prefix(funds)

            # Создаем сообщение с подробной информацией
            error_message = (
                f"❌ У вас уже есть бизнес: {existing_name}\n\n"
                f"💰 Накоплено: {funds_display} ₽\n"
                f"💸 Доход: {income_display} ₽/час\n\n"
                f"ℹ️ Вы не можете владеть более чем одним бизнесом.\n"
                f"Сначала продайте текущий бизнес, чтобы купить новый."
            )

            bot.send_message(
                message.chat.id,
                error_message,
                parse_mode="Markdown"
            )
            return
        # Проверяем хватает ли денег
        user_balance = casino.get_balance(user_id)
        business_price = business.BUSINESS_TYPES[business_type]['price']
        if user_balance < business_price:
            business_name = business.BUSINESS_NAMES.get(business_type)
            bot.send_message(
                message.chat.id,
                f"❌ *Недостаточно средств*\n\n"
                f"Для покупки {business_name} требуется {format_number(business_price)} ₽\n"
                f"Цена бизнеса: {format_number(business_price)} ₽\n"
                f"Ваш баланс: {format_number(user_balance)} ₽",
                parse_mode="Markdown"
            )
            return
        # Покупаем бизнес
        success, result_text = business.buy_business(user_id, business_type)
        if success:
            bot.send_message(
                message.chat.id,
                result_text,
                parse_mode="Markdown"
            )
            # Сразу показываем информацию о бизнесе
            text, markup = business.get_business_details(user_id, business_type)
            bot.send_message(
                message.chat.id,
                text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(
                message.chat.id,
                result_text,
                parse_mode="Markdown"
            )
    except ValueError as e:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {str(e)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ Произошла ошибка: {str(e)}",
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['перевод'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/перевод', 'перевод')))
def transfer_handler(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Command format: /перевод [user] [amount]
    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        bot.send_message(chat_id, "❌ Используйте: /перевод айди сумма")
        return

    recipient_reference = args[1]
    try:
        amount = converter.parse_amount(args[2])
    except ValueError as e:
        bot.send_message(chat_id, str(e))
        return

    try:
        # Using our modified transfer_money function
        recipient_id = transfer_money(casino, bot, user_id, recipient_reference, amount)

        # Get recipient's info for the message
        try:
            recipient = bot.get_chat(recipient_id)
            recipient_name = f"@{recipient.username}" if recipient.username else f"{recipient.first_name}"
        except:
            recipient_name = f"ID: {recipient_id}"

        bot.send_message(
            chat_id,
            f"✅ Перевод выполнен!\n"
            f"💸 Сумма: {format_number(amount)} ₽\n"
            f"👤 Получатель: {recipient_name}\n"
            f"💰 Ваш баланс: {format_number(casino.get_balance(user_id))} ₽"
        )
    except Exception as e:
        bot.send_message(chat_id, str(e))


# ===== VIP-МЕНЮ =====
@bot.message_handler(commands=['випбонус'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/випбонус', 'випбонус'])
@check_working_time
def handle_vip_bonus(message):
    user_id = get_user_id(message)
    if not casino.is_vip_active(user_id):
        bot.send_message(message.chat.id, "❌ Только ВИП-игроки могут получать бонус!")
        return

    result = casino.claim_vip_bonus(user_id)
    bot.send_message(message.chat.id, result, reply_markup=create_main_keyboard())




@bot.message_handler(func=lambda message: message.text == "💎Вип")
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/Вип', 'Вип')))
def vip_menu(message):
    try:
        user_id = get_user_id(message)
        is_vip = casino.is_vip_active(user_id)

        # Формируем сообщение о VIP
        if is_vip:
            # Используем московское время для вывода
            expires_timestamp = casino.get_vip_expires(user_id)
            expires_date = datetime.fromtimestamp(expires_timestamp, ZoneInfo('Europe/Moscow'))
            expires_str = expires_date.strftime("%d.%m.%Y %H:%M")

            msg = (
                "💎 *У вас активирован VIP-статус*\n\n"
                f"⏱ Действует до: {expires_str} МСК\n\n"
                "📋 *Ваши привилегии:*\n"
                "- +15% к шансу выигрыша в казино\n"
                "- -5% вероятность проигрыша в рулетке\n"
                "- +30% доход с майнинг-ферм\n"
                "- +30% доход с бизнесов\n"
                "- Доступ к VIP-бонусу каждые 6 часов\n\n"
                "🎁 Введите /випбонус чтобы получить бонус"
            )
        else:
            msg = (
                "💎 *VIP-статус*\n\n"
                "Приобретите VIP-статус, чтобы получить следующие привилегии:\n\n"
                "- +15% к шансу выигрыша в казино\n"
                "- -5% вероятность проигрыша в рулетке\n"
                "- +30% доход с майнинг-ферм\n"
                "- Доступ к VIP-бонусу (10 млн ₽) каждые 6 часов\n\n"
                f"💰 Стоимость: {format_number(casino.VIP_PRICE_PER_DAY)} ₽ за 1 день\n\n"
                f"Введите цифрами количество дней (от {MIN_VIP_DAYS} до {MAX_VIP_DAYS}), "
                f"на которое хотите приобрести VIP:"
            )

        bot.send_message(
            message.chat.id,
            msg,
            parse_mode='Markdown'
        )

        # Регистрируем обработчик для ввода количества дней (и для продления, и для новой покупки)
        bot.register_next_step_handler(message, process_vip_days)

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


def process_vip_days(message):
    try:
        user_id = get_user_id(message)
        text = message.text.strip()

        # Проверяем, не нажал ли пользователь кнопку из основного меню
        if text in ["🎰Казино", "🎡Рулетка", "⛏Майнинг", "🆔Профиль", "💎Вип", "🔄Обновления", "🆘Помощь"]:
            # Просто перенаправляем на соответствующий обработчик
            bot.process_new_messages([message])
            return

        # Если пользователь передумал или ввел некорректные данные
        if not text.isdigit():
            bot.send_message(
                message.chat.id,
                "❌ Операция отменена. Нажмите 💎 Вип для повторной попытки."
            )
            return

        days = int(text)

        # Проверка ограничений
        if days < MIN_VIP_DAYS or days > MAX_VIP_DAYS:
            bot.send_message(
                message.chat.id,
                f"❌ Количество дней должно быть от {MIN_VIP_DAYS} до {MAX_VIP_DAYS}."
            )
            return

        # Рассчитываем стоимость
        total_price = casino.VIP_PRICE_PER_DAY * days

        # Проверяем баланс
        if not check_balance(user_id, total_price):
            bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств!\n"
                f"Стоимость: {format_number(total_price)} ₽\n"
                f"Ваш баланс: {format_number(casino.get_balance(user_id))} ₽"
            )
            return

        # Покупаем VIP
        try:
            expires_timestamp = casino.buy_vip(user_id, days)
            # Используем московское время для вывода
            expires_date = datetime.fromtimestamp(expires_timestamp, ZoneInfo('Europe/Moscow'))
            expires_str = expires_date.strftime("%d.%m.%Y %H:%M")

            bot.send_message(
                message.chat.id,
                f"✅ Вип-статус успешно {'продлен' if casino.is_vip_active(user_id) else 'приобретен'}!\n\n"
                f"⏱ Действует до: {expires_str} МСК\n"
                f"💰 Списано: {format_number(total_price)} ₽\n"
                f"💰 Баланс: {format_number(casino.get_balance(user_id))} ₽\n\n"
                f"🎁 Введите /випбонус чтобы получить бонус"
            )
        except ValueError as e:
            bot.send_message(message.chat.id, str(e))

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


@bot.message_handler(func=lambda m: m.text and m.text in ["👤Профиль", "👤 Профиль", "профиль"])
@check_working_time
def profile_menu(message):
    """Показывает профиль пользователя со всей информацией"""
    user_id = get_user_id(message)
    casino.ensure_user_exists(user_id)
    # Информация о пользователе
    user_name = message.from_user.first_name
    user_username = message.from_user.username or "нет"
    # Дата регистрации
    registration_date = casino.registration_dates.get(user_id, time.time())
    registration_date_formatted = datetime.fromtimestamp(registration_date).strftime("%d.%m.%Y")
    # Баланс
    balance = casino.get_balance(user_id)
    max_balance = casino.MAX_BALANCE
    balance_percent = (balance / max_balance) * 100 if max_balance > 0 else 0
    balance_display = business.format_price_with_prefix(balance)
    # VIP статус
    is_vip = casino.is_vip_active(user_id)
    vip_status = "✅" if is_vip else "❌"
    # Информация о сроке действия VIP
    vip_expires_text = ""
    if is_vip:
        expires_timestamp = casino.vip_users.get(user_id, 0)
        if expires_timestamp > 0:
            expires_date = datetime.fromtimestamp(expires_timestamp).strftime("%d.%m.%Y %H:%M")
            vip_expires_text = f"до {expires_date}"
    # Бизнесы
    user_businesses = business.user_businesses.get(user_id, [])
    business_count = len(user_businesses)
    business_income = business.get_hourly_income(user_id)
    business_income_display = business.format_price_with_prefix(business_income)
    # Добавляем описание бизнеса если он есть
    business_info = business.format_business_info(user_id)
    # Майнинг фермы
    farm_counts = mining.get_farm_counts(user_id)
    total_farms = sum(farm_counts.values())
    mining_income = mining.get_hourly_income(user_id)
    btc_rate = mining.btc_rate
    mining_income_rub = mining_income * btc_rate
    # Форматируем BTC доход с 1 знаком после запятой
    mining_btc_display = f"{mining_income:.1f}"
    mining_income_display = f"{mining_btc_display} BTC/час ({business.format_price_with_prefix(mining_income_rub)} ₽)"
    # Общая сумма заработка в час
    total_hourly_income = business_income + mining_income_rub
    total_income_display = business.format_price_with_prefix(total_hourly_income)
    # Создаем сообщение профиля
    profile_text = (
        f"👤 *ПРОФИЛЬ @{user_username}*\n\n"
        f"Ник: @{user_username}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📅 Дата регистрации: {registration_date_formatted}\n\n"
        f"💰 *Баланс*: {balance_display} ₽ ({balance_percent:.1f}% от макс.)\n\n"
        f"💎 *VIP-статус*: {vip_status} {vip_expires_text}\n\n"
        f"💼 *Бизнес*: {business_info}\n"
        f"⛏ *Майнинг-фермы*: {total_farms} шт.\n"
        f"├ AORUS: {farm_counts.get('AORUS', 0)} шт.\n"
        f"├ PALIT: {farm_counts.get('PALIT', 0)} шт.\n"
        f"├ ASUS: {farm_counts.get('ASUS', 0)} шт.\n"
        f"└ Доход: {mining_income_display}\n\n"
        f"📈 *Общий доход*: {total_income_display} ₽/час"
    )
    # Отправляем сообщение
    bot.send_message(
        message.chat.id,
        profile_text,
        parse_mode="Markdown"
    )
def process_bet(message, game_type, bet_handler):
    user_id = get_user_id(message)
    try:
        # Обработка команды "все"
        if message.text.strip().lower() == "все":
            amount = casino.get_balance(user_id)
            if amount < casino.MIN_BET:  # Используем константу из CasinoSystem
                return handle_common_error(message.chat.id, f"❗ Минимум {casino.MIN_BET} ₽")
        else:
            amount = parse_amount(message.text)

        # Проверка минимальной ставки
        if amount < casino.MIN_BET:
            return handle_common_error(message.chat.id, f"❗ Минимум {casino.MIN_BET} ₽")

        # Проверка баланса
        if not check_balance(user_id, amount):
            return handle_common_error(message.chat.id,
                                       f"❌ Недостаточно средств. Баланс: {format_number(casino.get_balance(user_id))} ₽")

        return bet_handler(user_id, amount)

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


user_states = {}


# Функция для проверки состояния пользователя
def user_id_in_game_state(user_id):
    return user_id in user_states and user_states[user_id] is not None


# Обработчик единого игрового меню
@bot.message_handler(func=lambda message: message.text.lower() in ["🎮игры", "игры", "/игры", "games", "/games"])
def games_menu(message):
    """Единое игровое меню с выбором между Казино и Рулеткой"""
    user_id = message.from_user.id

    # Сбрасываем состояние пользователя, чтобы предыдущие обработчики не сработали
    user_states[user_id] = None

    # Создаем инлайн-клавиатуру с вариантами игр
    markup = types.InlineKeyboardMarkup(row_width=2)
    casino_button = types.InlineKeyboardButton("🎰 Казино", callback_data="game_casino")
    roulette_button = types.InlineKeyboardButton("🎡 Рулетка", callback_data="game_roulette")
    back_button = types.InlineKeyboardButton("↩️ Назад", callback_data="game_back")

    markup.add(casino_button, roulette_button)
    markup.add(back_button)

    # Отправляем фото игрового зала с описанием
    img_path = os.path.join(os.getcwd(), "игровойзал-min.jpg")

    with open(img_path, 'rb') as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="*✨ Добро пожаловать в Игровой Зал ✨*\n\n"
                    "🌟 Здесь вы можете испытать свою удачу и сорвать настоящий джекпот!\n\n"
                    "👑 Выберите одну из эксклюзивных игр нашего казино:",
            reply_markup=markup,
            parse_mode="Markdown"
        )


# Обработчик выбора казино
@bot.callback_query_handler(func=lambda call: call.data == "game_casino")
def casino_callback(call):
    # Убираем уведомление
    bot.answer_callback_query(call.id)

    # Получаем информацию о пользователе
    user_id = call.from_user.id
    balance = casino.get_balance(user_id)
    is_vip = casino.is_vip_active(user_id)

    # Устанавливаем состояние пользователя - он в режиме ввода ставки для казино
    user_states[user_id] = "casino_bet"

    # Показываем информацию о казино с улучшенным текстом
    vip_info = "\n• VIP-бонус: +15% к шансу выигрыша" if is_vip else ""
    chance_info = "50%" if is_vip else "35%"

    msg = bot.edit_message_caption(
        caption=f"*🎰 Казино 🎰*\n\n"
                f"💼 *Информация:*\n"
                f"• Коэффициент выплат: x2\n"
                f"• Шанс выигрыша: {chance_info}{vip_info}\n"
                f"• Минимальная ставка: 100 ₽\n\n"
                f"💰 Ваш баланс: {format_number(balance)} ₽\n\n"
                f"🎲 *Введите сумму ставки* или напишите \"*все*\" для максимальной ставки:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("↩️ Вернуться в холл казино", callback_data="game_menu")
        ),
        parse_mode="Markdown"
    )


# Обработчик выбора рулетки
@bot.callback_query_handler(func=lambda call: call.data == "game_roulette")
def roulette_callback(call):
    # Убираем уведомление
    bot.answer_callback_query(call.id)

    # Получаем информацию о пользователе
    user_id = call.from_user.id
    balance = casino.get_balance(user_id)
    is_vip = casino.is_vip_active(user_id)

    # Сбрасываем состояние пользователя
    user_states[user_id] = None

    # Формируем сообщение с правильной информацией о VIP
    vip_info = "\n• VIP-привилегия: -5% к шансу проигрыша" if is_vip else ""

    # Создаем клавиатуру для выбора типа ставки
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Добавляем кнопки типов ставок с эмодзи
    bet_options = [
        ("0️⃣ Зеро", "0"),
        ("🔴 Красное", "красный"),
        ("⚫ Черное", "черный"),
        ("🔢 1-12", "1-12"),
        ("🔢 13-24", "13-24"),
        ("🔢 25-36", "25-36")
    ]

    bet_buttons = [types.InlineKeyboardButton(name, callback_data=f"roul_type_{data}")
                   for name, data in bet_options]
    markup.add(*bet_buttons)

    # Добавляем кнопку "назад"
    back_button = types.InlineKeyboardButton("↩️ Вернуться в холл казино", callback_data="game_menu")
    markup.add(back_button)

    # Создаем изображение рулетки
    img = RouletteRenderer.create_wheel()
    img_path = os.path.join(os.getcwd(), "roulette_temp.png")

    # Удаляем предыдущее сообщение
    bot.delete_message(call.message.chat.id, call.message.message_id)

    # Отправляем изображение рулетки с клавиатурой и улучшенным текстом
    with open(img_path, 'rb') as photo:
        bot.send_photo(
            call.message.chat.id,
            photo,
            caption=f"*🎡 Рулетка 🎡*\n\n"
                    f"✨ *Правила игры:*\n"
                    f"• Делайте ставки на числа, цвета или группы\n"
                    f"• Выигрыш зависит от типа ставки\n"
                    f"• Минимальная ставка: 100 ₽{vip_info}\n\n"
                    f"💰 Ваш баланс: {format_number(balance)} ₽\n\n"
                    f"🎯 *Выберите тип ставки:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )


# Обработчик выбора типа ставки в рулетке
@bot.callback_query_handler(func=lambda call: call.data.startswith("roul_type_"))
def roulette_type_handler(call):
    # Получаем тип ставки из колбэка
    bet_type = call.data.split("_")[2]

    # Получаем баланс пользователя и проверяем VIP-статус
    user_id = call.from_user.id
    balance = casino.get_balance(user_id)
    is_vip = casino.is_vip_active(user_id)

    # Устанавливаем состояние пользователя - он в режиме ввода ставки для рулетки
    user_states[user_id] = f"roulette_bet_{bet_type}"

    # Получаем коэффициент для выбранного типа ставки
    if bet_type in RouletteSystem.BET_TYPES:
        payout = RouletteSystem.BET_TYPES[bet_type]["payout"]
    else:
        # Используем коэффициент по умолчанию, если тип ставки не найден
        payout = 35

    # Определяем название типа ставки для отображения
    bet_names = {
        "0": "Зеро (0)",
        "красный": "Красное",
        "черный": "Черное",
        "1-12": "Числа 1-12",
        "13-24": "Числа 13-24",
        "25-36": "Числа 25-36"
    }
    bet_name = bet_names.get(bet_type, bet_type)

    # Формируем сообщение с правильной информацией о VIP
    vip_info = "\n• VIP-привилегия: -5% к шансу проигрыша" if is_vip else ""

    # Создаем сообщение
    message_text = (
        f"*🎡 Рулетка 🎡*\n\n"
        f"✅ Выбранная ставка: *{bet_name}*\n"
        f"✅ Коэффициент выплат: x{payout}\n\n"
        f"💼 *Информация:*\n"
        f"• Минимальная ставка: 100 ₽{vip_info}\n\n"
        f"💰 Ваш баланс: {format_number(balance)} ₽\n\n"
        f"💵 *Введите сумму ставки* или напишите \"*все*\" для максимальной ставки:"
    )

    # Добавляем кнопку "Назад"
    markup = types.InlineKeyboardMarkup()
    back_button = types.InlineKeyboardButton("↩️ Назад к выбору ставки", callback_data="game_roulette")
    markup.add(back_button)

    # Обновляем сообщение с учетом типа
    if hasattr(call.message, 'photo') and call.message.photo:
        bot.edit_message_caption(
            caption=message_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            text=message_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )


# Обработчик возврата в игровое меню
@bot.callback_query_handler(func=lambda call: call.data == "game_menu")
def back_to_games_menu(call):
    # Убираем уведомление
    bot.answer_callback_query(call.id)

    # Сбрасываем состояние пользователя
    user_id = call.from_user.id
    user_states[user_id] = None

    # Создаем инлайн-клавиатуру с вариантами игр
    markup = types.InlineKeyboardMarkup(row_width=2)
    casino_button = types.InlineKeyboardButton("🎰 Казино", callback_data="game_casino")
    roulette_button = types.InlineKeyboardButton("🎡 Рулетка", callback_data="game_roulette")
    back_button = types.InlineKeyboardButton("↩️ Вернуться в основное меню", callback_data="game_back")

    markup.add(casino_button, roulette_button)
    markup.add(back_button)

    # Отправляем фото игрового зала
    img_path = os.path.join(os.getcwd(), "игровойзал-min.jpg")

    # Если сообщение содержит фото (рулетка), удаляем его и отправляем новое
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)

        with open(img_path, 'rb') as photo:
            bot.send_photo(
                call.message.chat.id,
                photo,
                caption="*✨ Игровой Зал ✨*\n\n"
                        "🌟 Здесь вы можете испытать свою удачу и сорвать настоящий джекпот!\n\n"
                        "👑 Выберите одну из эксклюзивных игр нашего казино:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        # Если не получилось, отправляем новое
        logging.error(f"Ошибка при возврате в игровое меню: {e}")

        with open(img_path, 'rb') as photo:
            bot.send_photo(
                call.message.chat.id,
                photo,
                caption="*✨ Игровой Зал ✨*\n\n"
                        "🌟 Здесь вы можете испытать свою удачу и сорвать настоящий джекпот!\n\n"
                        "👑 Выберите одну из эксклюзивных игр нашего казино:",
                reply_markup=markup,
                parse_mode="Markdown"
            )


# Возврат в главное меню
@bot.callback_query_handler(func=lambda call: call.data == "game_back")
def back_to_main_menu(call):
    # Убираем уведомление
    bot.answer_callback_query(call.id)

    # Сбрасываем состояние пользователя
    user_id = call.from_user.id
    user_states[user_id] = None

    # Удаляем сообщение с инлайн-клавиатурой
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения: {e}")

    # Отправляем сообщение с основной клавиатурой
    bot.send_message(
        call.message.chat.id,
        "✅ Вы вернулись в главное меню бота.",
        reply_markup=ui.create_keyboard()
    )


# Специальный обработчик для игровых сообщений, с более узким условием
@bot.message_handler(func=lambda message: user_id_in_game_state(message.from_user.id), content_types=['text'])
def handle_game_messages(message):
    user_id = message.from_user.id

    # Проверяем состояние пользователя
    if user_id in user_states:
        state = user_states[user_id]

        # Обработка ставки для казино
        if state == "casino_bet":
            process_casino_bet(message)
        # Обработка ставки для рулетки
        elif state.startswith("roulette_bet_"):
            bet_type = state.split("_")[2]
            process_roulette_bet(message, bet_type)
        else:
            # Неизвестное состояние, сбрасываем
            user_states[user_id] = None


# Обработчик ставок в казино
def process_casino_bet(message):
    user_id = message.from_user.id

    try:
        # Получаем баланс пользователя
        balance = casino.get_balance(user_id)
        is_vip = casino.is_vip_active(user_id)

        # Проверяем, если пользователь хочет поставить все деньги
        if message.text.lower() in ["все", "всё", "all"]:
            bet_amount = balance
        else:
            # Пытаемся преобразовать введенную строку в число
            bet_amount = parse_amount(message.text)

        # Проверяем минимальную ставку
        if bet_amount < 100:
            bot.send_message(
                message.chat.id,
                "❌ *Минимальная ставка: 100 ₽*\nПопробуйте сделать более высокую ставку.",
                parse_mode="Markdown",
                reply_markup=ui.create_keyboard()
            )
            # Сбрасываем состояние
            user_states[user_id] = None
            return

        # Проверяем, хватает ли денег
        if balance < bet_amount:
            bot.send_message(
                message.chat.id,
                f"❌ *У вас недостаточно средств!*\nВаш баланс: {format_number(balance)} ₽",
                parse_mode="Markdown",
                reply_markup=ui.create_keyboard()
            )
            # Сбрасываем состояние
            user_states[user_id] = None
            return

        # Играем в казино
        result_message, win = casino.play_50_50(user_id, bet_amount)

        # Получаем обновленный баланс
        new_balance = casino.get_balance(user_id)

        # Отправляем сообщение с результатом и продолжаем игру
        status_emoji = "💰" if win else "💔"
        status_header = "ВЫИГРЫШ!" if win else "ПРОИГРЫШ..."

        # Формируем сообщение с правильной информацией о VIP
        vip_info = "\n• VIP-бонус: +15% к шансу выигрыша" if is_vip else ""
        chance_info = "50%" if is_vip else "35%"

        # Добавляем кнопку назад
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("↩️ Вернуться в холл казино", callback_data="game_menu")
        markup.add(back_button)

        bot.send_message(
            message.chat.id,
            f"*🎰 Казино 🎰*\n\n"
            f"*{status_header}*\n"
            f"{status_emoji} {result_message}\n\n"
            f"💼 *Информация:*\n"
            f"• Коэффициент выплат: x2\n"
            f"• Шанс выигрыша: {chance_info}{vip_info}\n"
            f"• Минимальная ставка: 100 ₽\n\n"
            f"💰 Ваш баланс: {format_number(new_balance)} ₽\n\n"
            f"🎲 *Введите сумму следующей ставки* или напишите \"*все*\" для максимальной ставки:",
            parse_mode="Markdown",
            reply_markup=markup
        )

        # Сохраняем состояние - пользователь продолжает играть в казино
        user_states[user_id] = "casino_bet"

    except Exception as e:
        # В случае ошибки
        logging.error(f"Ошибка в процессе обработки ставки казино: {str(e)}")
        bot.send_message(
            message.chat.id,
            "❌ *Ошибка!* Пожалуйста, введите корректное число или слово \"*все*\".",
            parse_mode="Markdown",
            reply_markup=ui.create_keyboard()
        )
        # Сбрасываем состояние
        user_states[user_id] = None


# Обработчик ставок в рулетке
def process_roulette_bet(message, bet_type):
    user_id = message.from_user.id

    try:
        # Получаем баланс пользователя
        balance = casino.get_balance(user_id)
        is_vip = casino.is_vip_active(user_id)

        # Проверяем, если пользователь хочет поставить все деньги
        if message.text.lower() in ["все", "всё", "all"]:
            bet_amount = balance
        else:
            # Пытаемся преобразовать введенную строку в число
            bet_amount = parse_amount(message.text)

        # Проверяем минимальную ставку
        if bet_amount < 100:
            bot.send_message(
                message.chat.id,
                "❌ *Минимальная ставка: 100 ₽*\nПопробуйте сделать более высокую ставку.",
                parse_mode="Markdown",
                reply_markup=ui.create_keyboard()
            )
            # Сбрасываем состояние
            user_states[user_id] = None
            return

        # Проверяем, хватает ли денег
        if balance < bet_amount:
            bot.send_message(
                message.chat.id,
                f"❌ *У вас недостаточно средств!*\nВаш баланс: {format_number(balance)} ₽",
                parse_mode="Markdown",
                reply_markup=ui.create_keyboard()
            )
            # Сбрасываем состояние
            user_states[user_id] = None
            return

        # Снимаем ставку с баланса
        casino.withdraw(user_id, bet_amount)

        # Генерируем случайное число для рулетки (используем RouletteSystem)
        number = RouletteSystem.spin()

        # Проверяем выигрыш
        win = RouletteSystem.check_win(bet_type, number, is_vip)

        # Получаем коэффициент для выбранного типа ставки
        if bet_type in RouletteSystem.BET_TYPES:
            payout = RouletteSystem.BET_TYPES[bet_type]["payout"]
        else:
            # Используем коэффициент по умолчанию, если тип ставки не найден
            payout = 35

        # Определяем название типа ставки для отображения
        bet_names = {
            "0": "Зеро (0)",
            "красный": "Красное",
            "черный": "Черное",
            "1-12": "Числа 1-12",
            "13-24": "Числа 13-24",
            "25-36": "Числа 25-36"
        }
        bet_name = bet_names.get(bet_type, bet_type)

        # Рассчитываем выигрыш
        if win:
            win_amount = int(bet_amount * payout)
            casino.deposit(user_id, win_amount)
            result_message = f"🎯 Выигрыш: +{format_number(win_amount - bet_amount)} ₽"
            header = "ПОБЕДА! 🏆"
        else:
            result_message = f"💸 Проигрыш: -{format_number(bet_amount)} ₽"
            header = "ПРОИГРЫШ... 💔"

        # Получаем обновленный баланс
        new_balance = casino.get_balance(user_id)

        # Создаем изображение рулетки с выпавшим числом
        img = RouletteRenderer.create_wheel(number)
        img_path = os.path.join(os.getcwd(), "roulette_temp.png")

        # Определяем цвет выпавшего числа
        if number == 0:
            color_text = "зеленое"
            color_emoji = "💚"
        elif number in RouletteSystem.BET_TYPES["красный"]["numbers"]:
            color_text = "красное"
            color_emoji = "❤️"
        else:
            color_text = "черное"
            color_emoji = "🖤"

        # Создаем клавиатуру для выбора типа ставки
        markup = types.InlineKeyboardMarkup(row_width=2)

        # Добавляем кнопки типов ставок с эмодзи
        bet_options = [
            ("0️⃣ Зеро", "0"),
            ("🔴 Красное", "красный"),
            ("⚫ Черное", "черный"),
            ("🔢 1-12", "1-12"),
            ("🔢 13-24", "13-24"),
            ("🔢 25-36", "25-36")
        ]

        bet_buttons = [types.InlineKeyboardButton(name, callback_data=f"roul_type_{data}")
                       for name, data in bet_options]
        markup.add(*bet_buttons)

        # Добавляем кнопку "назад"
        back_button = types.InlineKeyboardButton("↩️ Вернуться в холл казино", callback_data="game_menu")
        markup.add(back_button)

        # Сбрасываем состояние пользователя
        user_states[user_id] = None

        # Отправляем результат с изображением
        with open(img_path, 'rb') as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption=f"*🎡 Рулетка 🎡*\n\n"
                        f"*{header}*\n\n"
                        f"Ваша ставка: *{bet_name}*\n"
                        f"Выпало {color_emoji} {color_text} число: *{number}*\n"
                        f"{result_message}\n\n"
                        f"💰 Ваш баланс: {format_number(new_balance)} ₽\n\n"
                        f"🎮 *Выберите следующую ставку:*",
                reply_markup=markup,
                parse_mode="Markdown"
            )

    except Exception as e:
        # В случае ошибки
        logging.error(f"Ошибка в процессе обработки ставки рулетки: {str(e)}")
        bot.send_message(
            message.chat.id,
            "❌ *Ошибка!* Пожалуйста, введите корректное число или слово \"*все*\".",
            parse_mode="Markdown",
            reply_markup=ui.create_keyboard()
        )
        # Сбрасываем состояние
        user_states[user_id] = None
@bot.message_handler(func=lambda message: message.text == "⛏Майнинг")
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/майнинг', 'майнинг')))
@check_working_time
def mining_info_handler(message):
    try:
        user_id = get_user_id(message)
        hourly_income_btc = mining.get_hourly_income(user_id)
        hourly_income_rub = hourly_income_btc * mining.btc_rate

        response = (
            f"💰 *Почасовой доход:*\n"
            f"▫️ {hourly_income_btc:.2f} BTC\n"
            f"▫️ {format_number(int(hourly_income_rub))} ₽\n"
            f"{'💎 Вип-бонус: +30%' if casino.is_vip_active(user_id) else ''}"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton("🛒 Купить фермы", callback_data="mining_farms"),
            types.InlineKeyboardButton("💰 Продать фермы", callback_data="mining_sell"),
            types.InlineKeyboardButton("📊 Курс BTC", callback_data="mining_rate")
        ]
        markup.add(*buttons)

        # Отправка изображения "видиха.jpg" с подписью
        try:
            with open("Видокарта.jpg", "rb") as photo:
                bot.send_photo(
                    message.chat.id,
                    photo,
                    caption=response,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
        except FileNotFoundError:
            bot.send_message(
                message.chat.id,
                response,
                reply_markup=markup,
                parse_mode="Markdown"
            )

    except Exception as e:
        handle_common_error(message.chat.id, f"Ошибка: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data == "refresh_rate")
@check_working_time
def refresh_btc_rate(call):
    try:
        mining.update_btc_rate()
        handle_btc_rate(call)  # Перезагружаем сообщение с курсом
    except Exception as e:
        handle_common_error(call.message.chat.id, f"Ошибка обновления: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data == "mining_sell")
@check_working_time
def handle_sell_farms(call):
    try:
        user_id = call.from_user.id
        farm_counts = mining.get_farm_counts(user_id)

        markup = types.InlineKeyboardMarkup()
        for farm_type, count in farm_counts.items():
            if count > 0:
                btn = types.InlineKeyboardButton(
                    f"Продать {farm_type} (до {count})",
                    callback_data=f"sell_{farm_type}"
                )
                markup.add(btn)

        bot.send_message(
            call.message.chat.id,
            "🔻 Выберите тип ферм для продажи (возврат 75% стоимости):",
            reply_markup=markup
        )
    except Exception as e:
        handle_common_error(call.message.chat.id, str(e))


@bot.callback_query_handler(func=lambda call: call.data.startswith("sell_"))
@check_working_time
def handle_sell_type(call):
    farm_type = call.data.split("_")[1]
    msg = bot.send_message(
        call.message.chat.id,
        f"⛏ Введите количество ферм {farm_type} для продажи:",
        reply_markup=types.ForceReply()
    )
    bot.register_next_step_handler(msg, process_sell_quantity, farm_type)


def process_sell_quantity(message, farm_type):
    try:
        user_id = message.from_user.id
        quantity = parse_amount(message.text)

        success, response = mining.sell_farm(user_id, farm_type, quantity)
        if success:
            try:
                bot.delete_message(message.chat.id, message.message_id - 1)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass

            bot.send_message(
                message.chat.id,
                response,
                reply_markup=create_main_keyboard()
            )

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


@bot.callback_query_handler(func=lambda call: call.data == "mining_farms")
@check_working_time
def handle_farms_info(call):
    try:
        user_id = call.from_user.id
        farms = mining.user_farms.get(user_id, [])

        # Считаем количество ферм каждого типа
        farm_counts = {
            'AORUS': 0,
            'PALIT': 0,
            'ASUS': 0
        }
        for farm in farms:
            farm_counts[farm['type']] += 1

        farms_info = "\n".join(
            [f"{farm_type}: {count} шт."
             for farm_type, count in farm_counts.items() if count > 0]
        ) or "У вас нет ферм"

        text = (
            "🛒 Доступные фермы:\n\n"
            f"{Greetings.create_price_list(mining.farms)}\n\n"
            "📊 Ваши фермы:\n"
            f"{farms_info}\n\n"
            "Пример команды:\n/ферма 1 2\n"
            "Где:\n1 - номер фермы\n2 - количество"
        )
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        handle_common_error(call.message.chat.id, "❌ Ошибка загрузки списка ферм")


# Обработчик кнопки "📊 Курс BTC"
@bot.callback_query_handler(func=lambda call: call.data == "mining_rate")
@check_working_time
def handle_btc_rate(call):
    try:
        btc_info = mining.get_btc_info()
        response = (
            f"🏦 *Текущий курс BTC:* {format_number(mining.btc_rate)} ₽\n"
            f"🕒 Последнее обновление: {btc_info['last_update']} МСК\n"
            f"⏳ Следующее обновление: {btc_info['next_update']} МСК"
        )

        # Отправка изображения "курс-min.jpg"
        with open("курс-min .jpg", "rb") as photo:
            bot.send_photo(
                call.message.chat.id,
                photo,
                caption=response,
                parse_mode="Markdown"
            )

    except FileNotFoundError:
        handle_common_error(call.message.chat.id, "❌ Изображение курса не найдено")
    except Exception as e:
        handle_common_error(call.message.chat.id, f"Ошибка: {str(e)}")


@check_working_time
def handle_farms_info(message):
    try:
        text = (
            "🛒 Доступные фермы:\n\n"
            f"{Greetings.create_price_list(mining.farms)}\n\n"
            "Пример команды:\n/ферма 1 2\n"
            "Где:\n1 - номер фермы\n2 - количество\n"
            "Или 'все' вместо числа для максимальной покупки"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        handle_common_error(message.chat.id, "❌ Ошибка загрузки списка ферм")
        print(f"[Ошибка ферм]: {str(e)}")


@bot.message_handler(commands=['ферма'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/ферма', 'ферма')))
@check_working_time
def handle_farm_purchase(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            return bot.send_message(message.chat.id,
                                    "❌ Неправильный формат!\n"
                                    "Используйте: /ферма [номер] [количество]\n"
                                    "Пример: /ферма 1 3\n"
                                    f"{Greetings.create_price_list(mining.farms)}")

        farm_id, quantity_str = parts[1], ' '.join(parts[2:])
        farm_types = {"1": "AORUS", "2": "PALIT", "3": "ASUS"}

        if farm_id not in farm_types:
            raise ValueError("❌ Неверный номер фермы. Доступно: 1-3")

        user_id = get_user_id(message)
        farm_type = farm_types[farm_id]
        farm_price = mining.farms[farm_type]['price']

        # Обработка количества
        if quantity_str.strip().lower() == "все":
            max_amount = int(casino.get_balance(user_id)) // farm_price
            if max_amount < 1:
                raise ValueError("❌ Недостаточно средств для покупки")
            quantity = max_amount
        else:
            quantity = parse_amount(quantity_str)
            if quantity < 1:
                raise ValueError("❌ Минимальное количество: 1")
        # Убедимся, что quantity целое число
        quantity = int(quantity)

        total_price = farm_price * quantity

        if not check_balance(user_id, total_price):
            raise ValueError(f"❌ Нужно {format_number(total_price)} ₽")

        success, response = mining.buy_farm(user_id, farm_type, quantity)
        bot.send_message(message.chat.id, response)

    except Exception as e:
        handle_common_error(message.chat.id, str(e))


def _get_time_until_next_collect(user_id):
    if user_id not in mining.user_farms or not mining.user_farms[user_id]:
        return "—"
    earliest_time = min(farm['last_collect'] for farm in mining.user_farms[user_id])
    remaining = earliest_time + 3600 - time.time()
    if remaining <= 0:
        return "`0 мин`"  # Фикс: только минуты и моноширинный шрифт
    mins = int(remaining // 60)
    return f"`{mins} мин`"  # Оборачиваем в ` для запрета копирования


@bot.message_handler(commands=['биткоин'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/биткоин', 'биткоин')))
@check_working_time
def collect_btc(message):
    user_id = get_user_id(message)
    try:
        # Проверка наличия ферм перед сбором
        if user_id not in mining.user_farms or not mining.user_farms[user_id]:
            bot.send_message(
                message.chat.id,
                "❌ У вас нет ферм! Купите их через /ферма",
                parse_mode="Markdown"
            )
            return

        btc_amount = mining.collect_btc(user_id)
        if btc_amount > 0:
            rub_amount = int(btc_amount * mining.btc_rate)
            casino.deposit(user_id, rub_amount)
            response = (
                f"⛏️ Собрано: {int(btc_amount)} ₿\n"
                f"💰 Конвертировано: {format_number(rub_amount)} ₽"
            )
        else:
            next_collect = _get_time_until_next_collect(user_id)
            response = (
                "⏳ Ваши фермы ещё добывают BTC.\n"
                f"До следующего сбора: {next_collect}"
            )
        bot.send_message(message.chat.id, response, parse_mode="Markdown")
    except Exception as e:
        handle_common_error(message.chat.id, str(e))


# Общие обработчики
@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
@check_working_time
def back_to_menu(message):
    bot.send_message(message.chat.id, "Возврат в главное меню:", reply_markup=create_main_keyboard())


@bot.message_handler(func=lambda m: m.text == "🔄Обновления")
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/обновления', 'обновления')))
@check_working_time
def show_updates(message):
    bot.send_message(message.chat.id, Greetings.UPDATE_MESSAGE, parse_mode="Markdown")


# Админ-панель
@bot.message_handler(commands=['админ'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/админ', 'админ')))
def admin_help(message):
    try:
        if AdminPanel.is_admin(message.from_user.id):
            bot.send_message(message.chat.id, AdminPanel.ADMIN_COMMANDS, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Недостаточно прав!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в /помощь-ад: {str(e)}")


@bot.message_handler(commands=['логи'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/логи', 'логи')))
def handle_logs(message):
    if AdminPanel.is_admin(message.from_user.id):
        try:
            lines = 10
            args = message.text.split()
            if len(args) > 1:
                lines = int(args[1])

            # Проверка существования файла логов
            if not os.path.exists('bot.log'):
                raise FileNotFoundError("Файл логов не найден")

            logs = AdminPanel.get_logs(lines)
            bot.send_message(
                message.chat.id,
                f"📜 Последние {lines} логов:\n```\n{logs}\n```",
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    else:
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")


@bot.message_handler(commands=['выдать'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith(('/выдать', 'выдать')))
def admin_give_money_handler(message):
    chat_id = message.chat.id
    admin_id = message.from_user.id

    # Command format: /give_money [user] [amount]
    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        bot.send_message(chat_id, "❌ Используйте: /выдать айди сумма")
        return

    recipient_reference = args[1]
    try:
        amount = converter.parse_amount(args[2])
    except ValueError as e:
        bot.send_message(chat_id, str(e))
        return

    # Using admin_give_money function
    success, result_message, _ = AdminPanel.admin_give_money(
        casino,
        bot,
        admin_id,
        recipient_reference,
        amount
    )
    bot.send_message(chat_id, result_message)


@bot.message_handler(commands=['инфо'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/инфо', "инфо"])
def handle_user_info(message):
    if AdminPanel.is_admin(message.from_user.id):
        try:
            args = message.text.split()
            if len(args) < 2:
                raise ValueError("Используйте: /инфо [ID]")

            target_id = int(args[1])
            balance = casino.get_balance(target_id)
            farms = mining.get_farm_counts(target_id)

            response = (
                f"👤 Информация о пользователе {target_id}:\n"
                f"💰 Баланс: {format_number(balance)} ₽\n"
                f"⛏ Ферм: {farms} шт."
            )
            bot.send_message(message.chat.id, response)

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    else:
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")


@bot.message_handler(commands=['сд-промо'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/сд-промо', 'сд-промо'])
def handle_add_promo(message):
    if AdminPanel.is_admin(message.from_user.id):
        try:
            args = message.text.split()
            if len(args) < 4:
                raise ValueError("Формат: /сд-промо [код] [сумма] [использований]")

            promocodes = PromocodeSystem.load_promocodes()
            promocodes[args[1].upper()] = {
                "amount": int(parse_amount(args[2])),
                "max_uses": int(args[3])
            }
            PromocodeSystem.save_promocodes(promocodes)

            bot.send_message(message.chat.id, f"✅ Промокод {args[1]} создан")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(commands=['сет-вип'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/сет-вип', 'сет-вип'])
def handle_set_vip(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split()
        if len(args) < 3:
            bot.send_message(message.chat.id, "❌ Используйте: /сет-вип [ID] [дни]")
            return

        user_id = int(args[1])
        days = int(args[2])

        if days <= 0:
            bot.send_message(message.chat.id, "❌ Количество дней должно быть больше нуля!")
            return

        casino.ensure_user_exists(user_id)

        # Получаем текущее время окончания VIP, если есть
        current_expires = casino.get_vip_expires(user_id)

        # Добавляем дни к VIP
        casino.vip_users[user_id] = time.time() + (days * 24 * 60 * 60)

        try:
            user = bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else f"{user.first_name}"
        except:
            username = f"ID: {user_id}"

        bot.send_message(
            message.chat.id,
            f"✅ VIP-статус выдан пользователю {username} на {days} дней"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в set_vip: {str(e)}")


@bot.message_handler(commands=['убр-вип'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/убр-вип', 'убр-вип'])
def handle_remove_vip(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "❌ Используйте: /убр-вип [ID]")
            return

        user_id = int(args[1])

        if user_id in casino.vip_users:
            del casino.vip_users[user_id]

            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else f"{user.first_name}"
            except:
                username = f"ID: {user_id}"

            bot.send_message(
                message.chat.id,
                f"✅ VIP-статус удален у пользователя {username}"
            )
        else:
            bot.send_message(message.chat.id, "❌ У пользователя нет VIP-статуса!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в remove_vip: {str(e)}")


@bot.message_handler(commands=['сет-курс'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/сет-курс', "сет-курс"])
def handle_set_btc_rate(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "❌ Используйте: /сет-курс [курс]")
            return

        rate = int(args[1])

        if rate < mining.MIN_BTC_RATE:
            bot.send_message(
                message.chat.id,
                f"❌ Минимальный курс BTC: {format_number(mining.MIN_BTC_RATE)} ₽"
            )
            return

        old_rate = mining.btc_rate
        mining.btc_rate = rate

        # Обновляем время последнего обновления
        mining.last_btc_update = time.time()
        mining.next_btc_update = mining.last_btc_update + mining.HOUR_IN_SECONDS

        bot.send_message(
            message.chat.id,
            f"✅ Курс BTC изменен:\n" +
            f"📉 Старый: {format_number(old_rate)} ₽\n" +
            f"📈 Новый: {format_number(rate)} ₽"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в сет-курс: {str(e)}")


@bot.message_handler(commands=['стат'])
def handle_stats(message):
    """Обработчик команды /стат для администраторов - показывает статистику с мониторингом"""
    if not AdminPanel.is_admin(message.from_user.id):
        return

    try:
        # Получаем базовую статистику через AdminPanel
        stats = AdminPanel.get_system_stats(casino, mining, business)

        # Добавляем информацию мониторинга к существующей статистике
        monitoring_stats = bot_monitor.get_monitoring_report()
        combined_stats = f"{stats}\n{monitoring_stats}"

        bot.send_message(message.chat.id, combined_stats, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка получения статистики: {e}")

@bot.message_handler(commands=['сообщения'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/сообщения', 'сообщения'])
def handle_broadcast(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.send_message(message.chat.id, "❌ Используйте: /сообщения [сообщение]")
            return

        broadcast_message = args[1]

        # Получаем всех пользователей
        users = set(casino.balances.keys())
        sent_count = 0
        failed_count = 0

        # Отправляем сообщение всем пользователям
        for user_id in users:
            try:
                bot.send_message(
                    user_id,
                    f"📢 *Объявление:*\n\n{broadcast_message}",
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                failed_count += 1
                logging.error(f"Ошибка отправки сообщения пользователю {user_id}: {str(e)}")

        bot.send_message(
            message.chat.id,
            f"✅ Сообщение отправлено {sent_count} пользователям\n" +
            f"❌ Не удалось отправить {failed_count} пользователям"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в сообщения: {str(e)}")


@bot.message_handler(commands=['соб-лич'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/соб-лич', 'соб-лич'])
def handle_notify(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.send_message(message.chat.id, "❌ Используйте: /соб-лич [ID] [сообщение]")
            return

        user_id = int(args[1])
        notify_message = args[2]

        try:
            bot.send_message(
                user_id,
                f"📢 *Сообщение от администрации:*\n\n{notify_message}",
                parse_mode="Markdown"
            )

            user = bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else f"{user.first_name}"

            bot.send_message(
                message.chat.id,
                f"✅ Сообщение отправлено пользователю {username}"
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"❌ Не удалось отправить сообщение пользователю {user_id}: {str(e)}"
            )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в соб-лич: {str(e)}")


@bot.message_handler(commands=['backup'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/backup', 'backup'])
def handle_backup(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        success, result = AdminPanel.create_backup(casino, mining)
        bot.send_message(message.chat.id, result)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в backup: {str(e)}")


@bot.message_handler(commands=['restore'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['/restore', 'restore'])
def handle_restore(message):
    if not AdminPanel.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Доступ запрещен!")
        return

    try:
        args = message.text.split()
        if len(args) > 1:
            # Если указан ID резервной копии, восстанавливаем ее
            backup_id = args[1]
            success, result = AdminPanel.restore_backup(backup_id, casino, mining)
            bot.send_message(message.chat.id, result)
        else:
            # Если ID не указан, показываем список доступных копий
            backups = AdminPanel.list_backups()

            if not backups:
                bot.send_message(message.chat.id, "❌ Резервные копии не найдены!")
                return

            markup = types.InlineKeyboardMarkup(row_width=1)
            for backup in backups[:10]:  # Показываем только 10 последних копий
                markup.add(types.InlineKeyboardButton(
                    backup,
                    callback_data=f"restore_{backup}"
                ))

            bot.send_message(
                message.chat.id,
                "📋 Выберите резервную копию для восстановления:",
                reply_markup=markup
            )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в restore: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('restore_'))
def handle_restore_callback(call):
    if not AdminPanel.is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
        return

    try:
        backup_id = call.data[8:]  # Отрезаем 'restore_'

        bot.edit_message_text(
            f"⏳ Восстановление из {backup_id}...",
            call.message.chat.id,
            call.message.message_id
        )

        success, result = AdminPanel.restore_backup(backup_id, casino, mining)

        bot.edit_message_text(
            result,
            call.message.chat.id,
            call.message.message_id
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в restore_callback: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_business_'))
def withdraw_business_callback(call):
    user_id = call.from_user.id
    business_type = call.data.split('_')[2]

    # Проверяем, не достиг ли максимального баланса
    if casino.get_balance(user_id) >= casino.MAX_BALANCE:
        bot.answer_callback_query(
            call.id,
            "⚠️ Ваш баланс уже достиг максимального значения (100 трлн ₽)!",
            show_alert=True
        )
        # Обновляем информацию о бизнесе
        text, markup = business.get_business_details(user_id, business_type)
        bot.edit_message_text(
            text=text + "\n\n⚠️ *Внимание!* Ваш баланс достиг максимального значения (100 трлн ₽).",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    # Снимаем прибыль с конкретного бизнеса
    withdrawn = business.withdraw_business_funds(user_id, business_type)

    if withdrawn > 0:
        withdrawn_display = business.format_price_with_prefix(withdrawn)
        bot.answer_callback_query(
            call.id,
            f"✅ Вы сняли {withdrawn_display} ₽ с бизнеса",
            show_alert=True
        )
    else:
        bot.answer_callback_query(
            call.id,
            "❌ Нечего снимать! Подождите, пока накопится прибыль.",
            show_alert=True
        )

    # Обновляем информацию о бизнесе
    text, markup = business.get_business_details(user_id, business_type)

    # Проверяем снова, не достиг ли максимального баланса после снятия
    if casino.get_balance(user_id) >= casino.MAX_BALANCE:
        text += "\n\n⚠️ *Внимание!* Ваш баланс достиг максимального значения (100 трлн ₽)."

    bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: True)
@check_working_time
def handle_unknown(message):
    bot.send_message(
        message.chat.id,
        "❌ Неизвестная команда. Введите Помощь чтоб узнать список команд.",
        reply_markup=create_main_keyboard()
    )


def setup_autosave(bot, casino, mining):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: SaveManager.save_data(casino, mining),
        trigger='interval',
        hours=1
    )
    scheduler.start()

    # Сохранение при выключении
    atexit.register(lambda: SaveManager.save_data(casino, mining))


# 3. Вызов функции настройки автосохранения
setup_autosave(bot, casino, mining)

# 4. Запуск бота
# В конце файла main.py после всех обработчиков
if __name__ == "__main__":
    try:
        logger.info("Бот запущен.")
        # Используем только параметры, поддерживаемые вашей версией pyTelegramBotAPI
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.error(f"Критическая ошибка при работе бота: {e}")
    finally:
        # Сохраняем данные при завершении
        try:
            SaveManager.save_data(casino, mining, business)
            logger.info("Данные сохранены при завершении работы.")
        except Exception as save_error:
            logger.error(f"Ошибка при сохранении данных: {save_error}")