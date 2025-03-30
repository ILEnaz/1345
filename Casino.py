from utils import format_number
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import logging


class CasinoSystem:
    # Константы класса
    START_BALANCE = 50_000_000
    MIN_BET = 100
    WIN_CHANCE = 0.35
    VIP_PRICE_PER_DAY = 100_000_000  # 100 млн ₽ за 1 день
    MAX_BALANCE = 100_000_000_000_000  # Максимальный баланс (100 триллионов)
    vip_users = {}
    VIP_WIN_BOOST = 0.15

    def __init__(self):
        self.balances = {}
        self.used_promocodes = {}
        self.vip_users = {}
        self.registration_dates = {}
        self.last_bonus_claim = {}

    def get_top_players(self, limit=15):
        """
        Returns a list of top players sorted by balance.
        Only includes players with balances greater than 0.
        """
        # Filter players with balances greater than 0
        players_with_balances = [(user_id, self.get_balance(user_id))
                                 for user_id in self.balances
                                 if self.get_balance(user_id) > 0]

        # Sort by balance (descending)
        sorted_players = sorted(players_with_balances, key=lambda x: x[1], reverse=True)

        # Get top players
        top_players = sorted_players[:limit]

        # Add VIP status
        result = []
        for user_id, balance in top_players:
            is_vip = self.is_vip_active(user_id)
            result.append((user_id, {'balance': balance, 'is_vip': is_vip}))

        return result

    def get_balance(self, user_id):
        """Получает баланс пользователя"""
        return self.balances.get(user_id, self.START_BALANCE)

    def deposit(self, user_id, amount):
        """Пополняет баланс пользователя с учетом лимита"""
        if not isinstance(amount, (int, float)) or amount <= 0:
            return False

        self.ensure_user_exists(user_id)

        # Проверяем, не превысит ли баланс максимальный лимит
        current_balance = self.get_balance(user_id)
        new_balance = current_balance + amount

        if new_balance > self.MAX_BALANCE:
            # Если превышает лимит, устанавливаем максимальное значение
            self.balances[user_id] = self.MAX_BALANCE
            return True

        self.balances[user_id] += amount
        return True

    def withdraw(self, user_id, amount):
        """Снимает средства с баланса пользователя (без ухода в минус)"""
        current_balance = self.get_balance(user_id)
        if current_balance < amount:
            raise ValueError("❌ Недостаточно средств для списания")
        self.balances[user_id] = current_balance - amount

    def ensure_user_exists(self, user_id):
        """Создает пользователя, если он не существует"""
        if user_id not in self.balances:
            self.balances[user_id] = self.START_BALANCE
            self.registration_dates[user_id] = time.time()  # Фиксируем время регистрации

    def play_50_50(self, user_id, amount):
        base_chance = self.WIN_CHANCE
        if self.is_vip_active(user_id):
            base_chance += self.VIP_WIN_BOOST  # Убедитесь, что VIP_WIN_BOOST объявлен в классе

        is_win = random.random() < base_chance

        if is_win:
            self.deposit(user_id, amount)
            return f"🏆 Победа! +{format_number(amount)} ₽", True
        else:
            self.withdraw(user_id, amount)
            return f"💸 Проигрыш! -{format_number(amount)} ₽", False

    def buy_vip(self, user_id, days):
        """
        Покупает или продлевает VIP статус на указанное количество дней
        Максимальный срок: 30 дней
        """
        if days > 30:
            raise ValueError("❌ Максимальный срок VIP: 30 дней")

        now = datetime.now(ZoneInfo('Europe/Moscow')).timestamp()
        total_cost = days * self.VIP_PRICE_PER_DAY

        # Проверяем, может ли пользователь заплатить
        if self.get_balance(user_id) < total_cost:
            raise ValueError(f"Недостаточно средств! Требуется: {format_number(total_cost)} ₽")

        # Снимаем деньги
        self.withdraw(user_id, total_cost)

        # Если уже есть VIP, продлеваем его
        if user_id in self.vip_users:
            current_expires = self.vip_users[user_id]
            # Если срок действия истек, начинаем с текущего момента
            if current_expires < now:
                new_expires = now + (days * 24 * 3600)
            else:
                # Иначе добавляем дни к текущему сроку
                new_expires = current_expires + (days * 24 * 3600)
        else:
            # Устанавливаем новый срок
            new_expires = now + (days * 24 * 3600)

        # Обновляем данные VIP
        self.vip_users[user_id] = new_expires

        return new_expires

    def is_vip_active(self, user_id):
        """Оптимизированная проверка VIP-статуса"""
        try:
            expires = self.vip_users.get(user_id)
            if not expires:
                return False

            is_active = float(expires) > time.time()
            if not is_active:
                del self.vip_users[user_id]

            return is_active
        except:
            return False

    def get_vip_expires(self, user_id):
        """Возвращает время окончания VIP или None"""
        vip_data = self.vip_users.get(user_id)
        if vip_data is None:
            return None

        # Handle both formats (direct timestamp or dict with 'expires' key)
        if isinstance(vip_data, dict):
            return vip_data.get("expires")
        else:
            # Assuming it's a float timestamp
            return vip_data
    def can_claim_bonus(self, user_id: int) -> tuple[bool, str]:
        """Проверяет, может ли пользователь получить бонус"""
        now = time.time()
        last_claim = self.last_bonus_claim.get(user_id, 0)
        cooldown = 6 * 3600  # 6 часов в секундах

        if now - last_claim < cooldown:
            remaining = cooldown - (now - last_claim)
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return False, f"⏳ Следующий бонус через: {hours}ч {minutes}мин"
        return True, "🎁 Бонус доступен!"

    def claim_vip_bonus(self, user_id: int) -> str:
        """Выдает VIP-бонус"""
        can_claim, msg = self.can_claim_bonus(user_id)
        if not can_claim:
            return msg

        bonus = 10_000_000  # 10 млн ₽
        self.deposit(user_id, bonus)
        self.last_bonus_claim[user_id] = time.time()
        return f"🎉 Получено +{format_number(bonus)} ₽ (VIP-бонус)"

    # Добавьте это в методы сохранения/загрузки
    def get_vip_users(self):
        return self.vip_users

    def set_vip_users(self, vip_users):
        self.vip_users = vip_users

    def get_vip_expires(self, user_id):
        """Возвращает время окончания VIP или None"""
        vip_data = self.vip_users.get(user_id)
        if vip_data is None:
            return None

        # Handle both formats (direct timestamp or dict with 'expires' key)
        if isinstance(vip_data, dict):
            return vip_data.get("expires")
        else:
            # Assuming it's a float timestamp
            return vip_data

    def is_vip_active(self, user_id):
        """Проверяет, активен ли VIP-статус у пользователя"""
        if user_id not in self.vip_users:
            return False

        # Получаем время окончания VIP-статуса
        vip_expires = self.vip_users.get(user_id)

        # Handle both formats
        if isinstance(vip_expires, dict):
            vip_expires = vip_expires.get('expires', 0)

        # Проверяем, не истек ли срок действия
        current_time = datetime.now(ZoneInfo('Europe/Moscow')).timestamp()
        return vip_expires > current_time

class RouletteSystem:
    # Константы класса - оптимизировано обращение к данным
    BET_TYPES = {
        "0": {"numbers": {0}, "payout": 35},
        "красный": {"numbers": {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}, "payout": 1.95},
        "черный": {"numbers": {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}, "payout": 1.95},
        "1-12": {"numbers": set(range(1, 13)), "payout": 2.8},
        "13-24": {"numbers": set(range(13, 25)), "payout": 2.8},
        "25-36": {"numbers": set(range(25, 37)), "payout": 2.8}
    }
    LOSS_PROBABILITY = 0.12
    VIP_LOSS_REDUCTION = 0.05

    @staticmethod
    def spin():
        """Генерирует случайное число для рулетки"""
        return random.randint(0, 36)

    @staticmethod
    def check_win(bet_type, result, is_vip=False):
        loss_prob = RouletteSystem.LOSS_PROBABILITY
        if is_vip:
            loss_prob -= RouletteSystem.VIP_LOSS_REDUCTION
        return (
                result in RouletteSystem.BET_TYPES[bet_type]["numbers"] and
                random.random() > loss_prob
        )


class Casino:
    def withdraw(self, user_id, amount):
        if user_id not in self.users:
            raise ValueError("Пользователь не найден")
        if self.users[user_id]['balance'] < amount:
            raise ValueError("Недостаточно средств")
        self.users[user_id]['balance'] -= amount