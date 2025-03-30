from PIL import Image, ImageDraw, ImageFont
import os
from zoneinfo import ZoneInfo

class RouletteRenderer:
    # Константы и кэшированные значения
    COLORS = {
        0: (0, 128, 0),  # Зеленый для 0
        "red": (255, 0, 0),  # Красный
        "black": (0, 0, 0)  # Черный
    }

    # Кэшируем числа красного цвета
    RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

    # Размеры и координаты
    CELL_WIDTH = 60
    CELL_HEIGHT = 60
    START_X = 50
    START_Y = 50

    # Матрица чисел (неизменна)
    NUMBERS = [
        [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36],  # Красная 3 осталась
        [0, 2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35],  # Черной 3 нет
        [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]  # 12 элементов
    ]

    # Секции для ставок
    BET_SECTIONS = [
        ("1-12", 50, 230, 290, 290),
        ("13-24", 290, 230, 530, 290),
        ("25-36", 530, 230, 770, 290),
        ("чет", 50, 290, 230, 350),
        ("красное", 230, 290, 410, 350),
        ("черное", 410, 290, 590, 350),
        ("нечет", 590, 290, 770, 350)
    ]

    @staticmethod
    def create_wheel(result=None):
        # Размер изображения
        img_width = 800
        img_height = 600
        img = Image.new('RGB', (img_width, img_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Загрузка шрифта один раз
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 24)
        except IOError:
            font = ImageFont.load_default()

        # Рисуем числа
        for row_idx, row in enumerate(RouletteRenderer.NUMBERS):
            for col_idx, number in enumerate(row):
                x = RouletteRenderer.START_X + col_idx * RouletteRenderer.CELL_WIDTH
                y = RouletteRenderer.START_Y + row_idx * RouletteRenderer.CELL_HEIGHT

                # Определяем цвет числа эффективнее
                if number == 0:
                    color = RouletteRenderer.COLORS[0]
                elif number in RouletteRenderer.RED_NUMBERS:
                    color = RouletteRenderer.COLORS["red"]
                else:
                    color = RouletteRenderer.COLORS["black"]

                # Рисуем прямоугольник с цветом
                cell_coords = [x, y, x + RouletteRenderer.CELL_WIDTH, y + RouletteRenderer.CELL_HEIGHT]
                draw.rectangle(cell_coords, fill=color)

                # Рисуем текст (число)
                text = str(number)
                bbox = draw.textbbox((x, y), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                text_x = x + (RouletteRenderer.CELL_WIDTH - text_width) // 2
                text_y = y + (RouletteRenderer.CELL_HEIGHT - text_height) // 2
                draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)

                # Выделение выпавшего числа
                if number == result:
                    draw.rectangle(cell_coords, outline=(255, 215, 0), width=3)

        # Секции для ставок
        for text, x1, y1, x2, y2 in RouletteRenderer.BET_SECTIONS:
            draw.rectangle([x1, y1, x2, y2], outline=(0, 0, 0), width=2)
            bbox = draw.textbbox((x1, y1), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = x1 + (x2 - x1 - text_width) // 2
            text_y = y1 + (y2 - y1 - 24) // 2
            draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

        # Сохраняем изображение
        output_path = os.path.join(os.getcwd(), "roulette_temp.png")
        img.save(output_path)
        return img