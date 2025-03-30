import time
import logging
from telebot import types
import math
logger = logging.getLogger('BusinessSystem')

class BusinessSystem:
    BUSINESS_TYPES = {
        'СЕРВЕР_MINECRAFT': {'price': 150_000, 'income': 15_000, 'emoji': '🌳'},
        'ЗАБЕГАЛОВКА': {'price': 1_000_000, 'income': 40_000, 'emoji': '🍔'},
        'АПТЕКА': {'price': 5_000_000, 'income': 80_000, 'emoji': '💊'},
        'ХАЙПОВЫЙ_ПАБЛИК': {'price': 20_000_000, 'income': 110_000, 'emoji': '🐬'},
        'РЫНОК_С_ОДЕЖДОЙ': {'price': 50_000_000, 'income': 160_000, 'emoji': '👕'},
        'САУНА': {'price': 100_000_000, 'income': 165_000, 'emoji': '🔥'},
        'КАЛЬЯННАЯ': {'price': 250_000_000, 'income': 375_000, 'emoji': '💨'},
        'ЗАВОД_В_ГАРАЖЕ': {'price': 500_000_000, 'income': 600_000, 'emoji': '🔨'},
        'САЙТ_С_КЕЙСАМИ': {'price': 1_000_000_000, 'income': 2_000_000, 'emoji': '🎰'},
        'АНИМАЦИОННАЯ_СТУДИЯ': {'price': 5_000_000_000, 'income': 5_000_000, 'emoji': '💡'},
        'СТРАХОВАЯ_КОМПАНИЯ': {'price': 15_000_000_000, 'income': 10_000_000, 'emoji': '📝'},
        'TESLA': {'price': 100_000_000_000, 'income': 60_000_000, 'emoji': '🚀'}
    }

    BUSINESS_NAMES = {
        'СЕРВЕР_MINECRAFT': 'Сервер Minecraft',
        'ЗАБЕГАЛОВКА': 'Забегаловка',
        'АПТЕКА': 'Аптека',
        'ХАЙПОВЫЙ_ПАБЛИК': 'Хайповый паблик',
        'РЫНОК_С_ОДЕЖДОЙ': 'Рынок с одеждой',
        'САУНА': 'Сауна',
        'КАЛЬЯННАЯ': 'Кальянная',
        'ЗАВОД_В_ГАРАЖЕ': 'Завод в гараже',
        'САЙТ_С_КЕЙСАМИ': 'Сайт с кейсами',
        'АНИМАЦИОННАЯ_СТУДИЯ': 'Анимационная студия',
        'СТРАХОВАЯ_КОМПАНИЯ': 'Страховая компания',
        'TESLA': 'Tesla'
    }

    MINUTE_IN_SECONDS = 60
    HOUR_IN_SECONDS = 3600
    MAX_BUSINESSES_PER_TYPE = 1  # Только 1 бизнес вообще

    def __init__(self, casino):
        self.user_businesses = {}
        self.casino = casino

    def format_full_balance(self, price):
        """Форматирует баланс с разделителями тысяч (без префиксов: млн, млрд)"""
        return f"{int(price):,}".replace(",", ".")
    def get_hourly_income(self, user_id):
        """Возвращает почасовой доход с учетом 30% VIP-бонуса"""
        if not self.user_businesses.get(user_id):
            return 0

        # Сначала считаем базовый доход (без VIP)
        total_income = sum(
            self.BUSINESS_TYPES[business['type']]['income']
            for business in self.user_businesses[user_id]
        )

        # Затем применяем VIP-бонус, если активен
        if self.casino.is_vip_active(user_id):
            total_income *= 1.3  # Увеличиваем на 30%

        return total_income

    def get_minute_income(self, user_id):
        """Возвращает доход в минуту с учетом 30% VIP-бонуса"""
        hourly_income = self.get_hourly_income(user_id)
        return hourly_income / 60

    def collect_income(self, user_id):
        """Собирает доход от всех бизнесов пользователя"""
        if user_id not in self.user_businesses or not self.user_businesses[user_id]:
            return 0, 0

        total_income = 0
        current_time = time.time()
        is_vip = self.casino.is_vip_active(user_id)

        for business in self.user_businesses[user_id]:
            time_diff = current_time - business.get('last_collect', current_time)
            minutes_passed = time_diff // self.MINUTE_IN_SECONDS

            if minutes_passed >= 1:
                # Базовый доход в минуту (без VIP)
                minute_income = self.BUSINESS_TYPES[business['type']]['income'] / 60

                # Применяем VIP-бонус
                if is_vip:
                    minute_income *= 1.3  # 30% бонус

                income_earned = int(minutes_passed * minute_income)

                if 'balance' not in business:
                    business['balance'] = 0
                business['balance'] += income_earned

                business['last_collect'] = current_time
                total_income += income_earned

        total_balance = sum(business.get('balance', 0) for business in self.user_businesses[user_id])
        return total_income, total_balance

    def withdraw_business_funds(self, user_id, business_type=None):
        """Снимает средства с баланса бизнеса с проверкой изменений"""
        if user_id not in self.user_businesses or not self.user_businesses[user_id]:
            return 0

        # Сохраняем исходный баланс
        original_balance = self.casino.get_balance(user_id)

        # Сбор прибыли
        self.collect_income(user_id)

        total_balance = sum(
            business.get('balance', 0)
            for business in self.user_businesses[user_id]
            if not business_type or business['type'] == business_type
        )

        # Проверка изменений
        if total_balance > 0:
            max_deposit = self.casino.MAX_BALANCE - original_balance
            if total_balance > max_deposit:
                total_balance = max_deposit

            self.casino.deposit(user_id, total_balance)

            # Обнуляем только после успешного депозита
            for business in self.user_businesses[user_id]:
                if not business_type or business['type'] == business_type:
                    business['balance'] = 0

            return total_balance

        return 0

    def format_price_with_prefix(self, price):
        """Форматирует цену с префиксом (млн, млрд и т.д.) с одним знаком после запятой, если нужно"""
        if price >= 1_000_000_000_000:  # триллион
            formatted = price / 1_000_000_000_000
            if formatted == int(formatted):  # если целое число
                return f"{int(formatted)} трлн"
            else:
                return f"{formatted:.1f} трлн"
        elif price >= 1_000_000_000:  # миллиард
            formatted = price / 1_000_000_000
            if formatted == int(formatted):  # если целое число
                return f"{int(formatted)} млрд"
            else:
                return f"{formatted:.1f} млрд"
        elif price >= 1_000_000:  # миллион
            formatted = price / 1_000_000
            if formatted == int(formatted):  # если целое число
                return f"{int(formatted)} млн"
            else:
                return f"{formatted:.1f} млн"
        elif price >= 1_000:  # тысяча
            formatted = price / 1_000
            if formatted == int(formatted):  # если целое число
                return f"{int(formatted)} тыс"
            else:
                return f"{formatted:.1f} тыс"
        else:
            return f"{int(price)}"

    def buy_business(self, user_id, business_type):
        """Покупает бизнес указанного типа"""
        try:
            business_type = business_type.upper().replace(' ', '_')
            if business_type not in self.BUSINESS_TYPES:
                raise ValueError(f"❌ Бизнес {business_type} не найден")
            user_businesses = self.user_businesses.get(user_id, [])
            # Проверка на количество бизнесов - теперь только один вообще
            if len(user_businesses) > 0:
                current_business = user_businesses[0]['type']
                business_name = self.BUSINESS_NAMES.get(current_business, current_business)
                emoji = self.BUSINESS_TYPES[current_business]['emoji']
                return False, (
                    f"❌ {user_id}, у вас уже имеется бизнес «{business_name}» {emoji}\n\n"
                    f"🛍 Если хотите приобрести другой бизнес, продайте текущий командой: продать бизнес"
                )
            business_price = self.BUSINESS_TYPES[business_type]['price']
            # Проверка через функцию format_number
            format_number = lambda n: f"{n:,}".replace(",", ".")
            if self.casino.get_balance(user_id) < business_price:
                return False, (
                    f"❌ Недостаточно средств!\n"
                    f"Нужно: {format_number(business_price)} ₽\n"
                    f"Ваш баланс: {format_number(self.casino.get_balance(user_id))} ₽"
                )
            new_business = {'type': business_type, 'last_collect': time.time(), 'balance': 0}
            if user_id not in self.user_businesses:
                self.user_businesses[user_id] = []
            self.user_businesses[user_id] = [new_business]  # Заменяем список на новый бизнес
            self.casino.withdraw(user_id, business_price)
            updated_balance = self.casino.get_balance(user_id)
            business_name = self.BUSINESS_NAMES.get(business_type, business_type)
            hour_income = self.BUSINESS_TYPES[business_type]['income']
            minute_income = hour_income / 60
            emoji = self.BUSINESS_TYPES[business_type]['emoji']
            return True, (
                f"✅ Куплен бизнес {emoji} {business_name} за {format_number(business_price)} ₽\n"
                f"💰 Доход: {format_number(minute_income)} ₽/мин ({format_number(hour_income)} ₽/час)\n"
                f"💰 Текущий баланс: {format_number(updated_balance)} ₽"
            )
        except Exception as e:
            logger.error(f"Ошибка при покупке бизнеса: {e}")
            return False, str(e)

    def sell_business(self, user_id, business_type=None):
        """Продает бизнес указанного типа с возвратом 75% стоимости"""
        try:
            # Автоматическое определение бизнеса, если тип не указан
            if not business_type:
                if not self.user_businesses.get(user_id):
                    raise ValueError("❌ У вас нет бизнесов для продажи")
                business_type = self.user_businesses[user_id][0]['type']
            else:
                business_type = business_type.upper().replace(' ', '_')

            if business_type not in self.BUSINESS_TYPES:
                available = "\n".join([f"- {name}" for name in self.BUSINESS_NAMES.values()])
                raise ValueError(f"❌ Бизнес не найден. Доступные:\n{available}")

            user_businesses = self.user_businesses.get(user_id, [])
            business_obj = next((b for b in user_businesses if b['type'] == business_type), None)
            if not business_obj:
                raise ValueError(f"❌ У вас нет бизнеса {self.BUSINESS_NAMES.get(business_type, business_type)}")

            self.collect_income(user_id)
            business_balance = business_obj.get('balance', 0)
            original_price = self.BUSINESS_TYPES[business_type]['price']
            refund = int(original_price * 0.75) + business_balance
            self.user_businesses[user_id] = [b for b in user_businesses if b['type'] != business_type]
            self.casino.deposit(user_id, refund)

            business_name = self.BUSINESS_NAMES.get(business_type, business_type)
            format_number = lambda n: f"{n:,}".replace(",", ".")
            return True, (
                f"✅ Продан бизнес {business_name}.\n"
                f"💵 Получено: {format_number(refund)} ₽\n"
                f"💰 Текущий баланс: {format_number(self.casino.get_balance(user_id))} ₽"
            )
        except Exception as e:
            logger.error(f"Ошибка при продаже бизнеса: {e}")
            return False, str(e)

    def get_business_counts(self, user_id):
        """Возвращает количество бизнесов каждого типа"""
        if user_id not in self.user_businesses:
            return {}

        counts = {}
        for business in self.user_businesses[user_id]:
            business_type = business['type']
            counts[business_type] = counts.get(business_type, 0) + 1

        return counts

    def has_business(self, user_id):
        """Проверяет, есть ли у пользователя бизнес"""
        return user_id in self.user_businesses and len(self.user_businesses[user_id]) > 0

    # В файле Business.py в методе get_business_info

    def get_business_info(self, user_id, business_type=None):
        """Возвращает информацию о бизнесе с проверкой наличия emoji"""
        try:
            if not self.has_business(user_id):
                return None

            # Получаем первый бизнес пользователя
            business = self.user_businesses[user_id][0]
            actual_type = business['type']

            # Проверяем наличие всех необходимых ключей
            business_data = self.BUSINESS_TYPES.get(actual_type, {})
            if not business_data:
                return None

            # Используем get() с значением по умолчанию для emoji
            return {
                'type': actual_type,
                'name': self.BUSINESS_NAMES.get(actual_type, actual_type),
                'price': business_data.get('price', 0),
                'income_hour': business_data.get('income', 0),
                'income_minute': business_data.get('income', 0) / 60,
                'emoji': business_data.get('emoji', '🏢'),  # Дефолтный emoji
                'balance': business.get('balance', 0),
                'sell_price': int(business_data.get('price', 0) * 0.75)
            }

        except Exception as e:
            logger.error(f"Ошибка в get_business_info: {str(e)}")
            return None
    def _get_first_business_info(self, user_id):
        """Возвращает информацию о первом бизнесе пользователя"""
        try:
            business = self.user_businesses[user_id][0]
            business_type = business['type']
            return {
                'type': business_type,
                'name': self.BUSINESS_NAMES.get(business_type, business_type),
                # ... остальные поля
            }
        except:
            return None

    def get_business_details(self, user_id, business_type=None):
        """Возвращает подробную информацию о бизнесе пользователя и клавиатуру"""
        if not self.has_business(user_id):
            return "У вас нет бизнеса.", None

        # Обновляем доходы перед выдачей информации
        self.collect_income(user_id)

        business_info = self.get_business_info(user_id, business_type)
        if not business_info:
            return "У вас нет бизнеса.", None

        # Проверяем VIP-статус
        is_vip = self.casino.is_vip_active(user_id)
        vip_bonus = 1.3 if is_vip else 1.0
        vip_text = " (+30% VIP)" if is_vip else ""

        # Применяем VIP-бонус к доходам
        base_hour_income = business_info['income_hour']
        base_minute_income = business_info['income_minute']
        adjusted_hour_income = base_hour_income * vip_bonus
        adjusted_minute_income = base_minute_income * vip_bonus

        # Форматируем данные
        price = self.format_price_with_prefix(business_info['price'])
        hour_income = self.format_price_with_prefix(int(adjusted_hour_income))
        minute_income = math.ceil(adjusted_minute_income / 10) * 10  # Округляем до десятков

        formatted_minute = f"{minute_income:,}".replace(",", ".")

        # Создаем текст сообщения
        text = (
            f"*Ваш бизнес:* {business_info['emoji']} {business_info['name']}\n\n"
            f"💰 Цена: {price} ₽\n"
            f"📈 Доход в минуту: {formatted_minute} ₽{vip_text}\n"
            f"🕒 Доход в час: {hour_income} ₽{vip_text}\n"
            f"💸 Накоплено: {self.format_price_with_prefix(business_info['balance'])} ₽"
        )

        # Создаем клавиатуру
        markup = self.create_business_keyboard(user_id)
        return text, markup
    def create_business_keyboard(self, user_id):
        """Создает клавиатуру для меню бизнеса"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        if self.has_business(user_id):
            business_info = self.get_business_info(user_id)
            balance = self.format_price_with_prefix(business_info['balance'])

            # Кнопка "Собрать прибыль" (только сумма)
            collect_button = types.InlineKeyboardButton(
                text=f"💰 Снять {balance} ₽",
                callback_data=f"business_collect_{business_info['type']}"
            )
            sell_button = types.InlineKeyboardButton(
                text="🔄 Продать бизнес",
                callback_data=f"confirm_sell_{business_info['type']}"
            )
            markup.add(collect_button, sell_button)
        else:
            buy_button = types.InlineKeyboardButton(
                text="🛒 Купить бизнес",
                callback_data="business_buy_menu"
            )
            markup.add(buy_button)
        return markup
    def create_business_purchase_keyboard(self):
        """Создает клавиатуру для выбора бизнеса при покупке"""
        # Создаем правильную клавиатуру
        markup = types.InlineKeyboardMarkup(row_width=1)

        # Сортируем бизнесы по цене
        sorted_businesses = sorted(
            self.BUSINESS_TYPES.items(),
            key=lambda x: x[1]['price']
        )

        # Создаем кнопки для каждого типа бизнеса
        for business_type, business_info in sorted_businesses:
            emoji = business_info['emoji']
            name = self.BUSINESS_NAMES.get(business_type, business_type)
            price = self.format_price_with_prefix(business_info['price'])

            button = types.InlineKeyboardButton(
                text=f"{emoji} {name} - {price} ₽",
                callback_data=f"business_buy_{business_type}"
            )
            markup.add(button)

        # Кнопка "Назад"
        back_button = types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="business_menu"
        )
        markup.add(back_button)

        return markup

    def format_business_list(self):
        """Форматирует список бизнесов для покупки"""
        # Сортируем бизнесы по цене
        sorted_businesses = sorted(
            self.BUSINESS_TYPES.items(),
            key=lambda x: x[1]['price']
        )

        text = "*📋 Список доступных бизнесов:*\n\n"

        for i, (business_type, business_info) in enumerate(sorted_businesses, 1):
            name = self.BUSINESS_NAMES.get(business_type, business_type)
            price = self.format_price_with_prefix(business_info['price'])
            income = self.format_price_with_prefix(business_info['income'])
            emoji = business_info['emoji']

            text += f"{i}. {emoji} *{name}*\n" \
                    f"   💰 Цена: {price} ₽\n" \
                    f"   💵 Доход: {income} ₽/час\n\n"

        text += "\n_Для покупки бизнеса введите:_ `/бизнес [номер]`\n" \
                "_Например:_ `/бизнес 1`"

        return text

    def format_business_info(self, user_id):
        """Форматирует информацию о бизнесе для отображения в профиле"""
        if not self.has_business(user_id):
            return "💼 Бизнес: Отсутствует"

        # Обновляем баланс бизнеса
        self.collect_income(user_id)
        business_info = self.get_business_info(user_id)

        if not business_info:
            return "💼 Бизнес: Отсутствует"

        business_name = self.BUSINESS_NAMES.get(business_info['type'], business_info['type'])
        emoji = self.BUSINESS_TYPES[business_info['type']]['emoji']
        hour_income = business_info['income_hour']
        minute_income = business_info['income_minute']

        # Применяем бонус VIP если активен
        vip_bonus = ""
        if self.casino.is_vip_active(user_id):
            hour_income *= 1.3
            minute_income *= 1.3
            vip_bonus = " (+30% VIP)"

        # Округляем доход в минуту вверх до ближайшего десятка
        rounded_minute_income = math.ceil(minute_income / 10) * 10  # Исправлено!

        # Форматируем числа
        format_number = lambda n: f"{n:,}".replace(",", ".")

        return (
            f"💼 Бизнес: {emoji} {business_name}\n"
            f"📈 Доход: {format_number(rounded_minute_income)} ₽/мин{vip_bonus}\n"
            f"💰 Накоплено: {format_number(business_info['balance'])} ₽"
        )