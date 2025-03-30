import time
import random
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from utils import format_number

logger = logging.getLogger('MiningSystem')

class MiningSystem:
    FARM_TYPES = {
        'AORUS': {'price': 20_000_000, 'income': 1.0},
        'PALIT': {'price': 60_000_000, 'income': 3.0},
        'ASUS': {'price': 100_000_000, 'income': 5.0}
    }

    MIN_BTC_RATE = 50_000
    HOUR_IN_SECONDS = 3600
    MAX_FARMS_PER_TYPE = 1_000_000  # 1кк

    def __init__(self, casino):
        self.btc_rate = 80_000
        self.last_btc_update = time.time()
        self.next_btc_update = self.last_btc_update + self.HOUR_IN_SECONDS
        self.user_farms = {}
        self.casino = casino

    def get_hourly_income(self, user_id):
        """Возвращает почасовой доход с учетом 30% VIP-бонуса"""
        if not self.user_farms.get(user_id):
            return 0.0

        total_income = sum(
            self.FARM_TYPES[farm['type']]['income']
            for farm in self.user_farms[user_id]
        )

        return total_income * 1.3 if self.casino.is_vip_active(user_id) else total_income

    def update_btc_rate(self):
        """Обновляет курс BTC при достижении времени следующего обновления"""
        current_time = time.time()
        try:
            if current_time >= self.next_btc_update:
                # Рассчитываем новый курс
                change_percent = random.uniform(-0.05, 0.05)
                new_rate = int(self.btc_rate * (1 + change_percent))
                self.btc_rate = max(new_rate, self.MIN_BTC_RATE)
                # Обновляем временные метки
                self.last_btc_update = current_time
                self.next_btc_update = current_time + self.HOUR_IN_SECONDS
                # Логируем обновление
                moscow_time = datetime.now(ZoneInfo('Europe/Moscow')).strftime("%H:%M")
                logger.info(f"[Курс BTC] Обновлен: {self.btc_rate} ₽ ({moscow_time} МСК)")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления курса BTC: {str(e)}")
            return False

    def get_btc_info(self):
        """Возвращает информацию о текущем курсе BTC и времени следующего обновления"""
        current_time = time.time()

        # Форматирование времени последнего и следующего обновления в московском времени
        moscow_tz = ZoneInfo('Europe/Moscow')

        last_update_time = datetime.fromtimestamp(self.last_btc_update, moscow_tz)
        next_update_time = datetime.fromtimestamp(self.next_btc_update, moscow_tz)

        last_update_str = last_update_time.strftime("%H:%M")
        next_update_str = next_update_time.strftime("%H:%M")

        # Время до следующего обновления в минутах
        minutes_until_update = max(0, int((self.next_btc_update - current_time) / 60))

        return {
            'rate': self.btc_rate,
            'last_update': last_update_str,
            'next_update': next_update_str,
            'minutes_until_update': minutes_until_update
        }
    @property
    def farms(self):
        """Возвращает типы ферм"""
        return self.FARM_TYPES

    def auto_collect_btc(self):
        """Автоматический сбор BTC (заглушка)"""
        pass

    def collect_btc(self, user_id):
        """Собирает BTC для пользователя с учетом VIP-статуса"""
        # Проверка наличия ферм
        if user_id not in self.user_farms or not self.user_farms[user_id]:
            return 0

        total_btc = 0
        current_time = time.time()
        is_vip = self.casino.is_vip_active(user_id)  # Check VIP status

        for farm in self.user_farms[user_id]:
            # Устанавливаем метку сбора, если не существует
            if 'last_collect' not in farm:
                farm['last_collect'] = current_time
                continue

            # Расчет заработанного BTC
            time_diff = current_time - farm['last_collect']
            hours_passed = int(time_diff // self.HOUR_IN_SECONDS)

            if hours_passed >= 1:
                farm_income = self.FARM_TYPES[farm['type']]['income']

                # Apply VIP bonus if active
                if is_vip:
                    farm_income *= 1.3  # Apply 30% bonus

                btc_earned = hours_passed * farm_income
                total_btc += btc_earned
                farm['last_collect'] += hours_passed * self.HOUR_IN_SECONDS

        return int(total_btc)  # Возвращаем целое число

    def buy_farm(self, user_id, farm_type, quantity):
        """Покупает фермы указанного типа"""
        try:
            quantity = int(quantity)
            farm_type = farm_type.upper()

            if farm_type not in self.FARM_TYPES:
                raise ValueError("❌ Неизвестная ферма")

            # Проверка лимита ферм одного типа
            current_farms = sum(1 for farm in self.user_farms.get(user_id, []) if farm['type'] == farm_type)
            if current_farms + quantity > self.MAX_FARMS_PER_TYPE:
                raise ValueError(f"❌ Превышен лимит ферм одного типа ({format_number(self.MAX_FARMS_PER_TYPE)} шт.)")

            farm_price = self.FARM_TYPES[farm_type]['price']
            total_price = farm_price * quantity

            # Получаем текущий баланс
            current_balance = self.casino.get_balance(user_id)

            # Дополнительная проверка на отрицательный баланс
            if current_balance < total_price:
                return False, (
                    f"❌ Недостаточно средств!\n"
                    f"Нужно: {format_number(total_price)} ₽\n"
                    f"Ваш баланс: {format_number(current_balance)} ₽"
                )

            # Создаем фермы
            new_farms = [{'type': farm_type, 'last_collect': time.time()} for _ in range(quantity)]
            if user_id not in self.user_farms:
                self.user_farms[user_id] = []
            self.user_farms[user_id].extend(new_farms)

            # Списание средств
            self.casino.withdraw(user_id, total_price)

            # Получаем обновленный баланс
            updated_balance = self.casino.get_balance(user_id)

            return True, (
                f"✅ Куплено {quantity} ферм {farm_type} за {format_number(total_price)} ₽\n"
                f"💰 Текущий баланс: {format_number(updated_balance)} ₽"
            )
        except Exception as e:
            return False, str(e)

    def sell_farm(self, user_id, farm_type, quantity):
        """Продает фермы указанного типа с возвратом 75% стоимости"""
        try:
            quantity = int(quantity)
            farm_type = farm_type.upper()

            if farm_type not in self.FARM_TYPES:
                raise ValueError("❌ Неизвестная ферма")

            user_farms = self.user_farms.get(user_id, [])
            if not user_farms:
                raise ValueError("❌ У вас нет ферм для продажи")

            # Получаем все фермы нужного типа
            target_farms = [f for f in user_farms if f['type'] == farm_type]
            if len(target_farms) < quantity:
                raise ValueError(f"❌ Недостаточно ферм {farm_type} для продажи")

            # Оставляем фермы, которые не продаются
            farms_to_keep = [f for f in user_farms if f['type'] != farm_type]
            # Добавляем оставшиеся фермы продаваемого типа (после продажи)
            farms_to_keep += target_farms[quantity:]  # Все, кроме проданных quantity

            # Обновляем список ферм пользователя
            self.user_farms[user_id] = farms_to_keep

            original_price = self.FARM_TYPES[farm_type]['price']
            refund = int(original_price * quantity * 0.75)
            self.casino.deposit(user_id, refund)

            return True, (
                f"✅ Продано {quantity} ферм {farm_type}.\n"
                f"💵 Получено: {format_number(refund)} ₽\n"
                f"💰 Текущий баланс: {format_number(self.casino.get_balance(user_id))} ₽"
            )

        except Exception as e:
            return False, str(e)



    def get_farm_counts(self, user_id):
        """Возвращает количество ферм каждого типа"""
        counts = {'AORUS': 0, 'PALIT': 0, 'ASUS': 0}

        if user_id in self.user_farms:
            for farm in self.user_farms[user_id]:
                counts[farm['type']] += 1

        return counts