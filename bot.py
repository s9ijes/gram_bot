import os
import telebot
import requests
import time
import logging
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", 180))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан! Установите переменную окружения.")
if not CHANNEL_ID:
    raise ValueError("❌ CHANNEL_ID не задан! Установите переменную окружения.")

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)

def get_gram_rub_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=rub"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        rub_price = data.get('the-open-network', {}).get('rub')
        if rub_price is None:
            logger.error("Не удалось получить rub из ответа CoinGecko")
            return None

        logger.info(f"GRAM/RUB (CoinGecko) = {rub_price}")
        return float(rub_price)

    except Exception as e:
        logger.error(f"Ошибка получения курса CoinGecko: {e}")
        return None

def format_price(value):
    if value is None:
        return "0.00₽"
    return f"{value:.2f}₽"

def post_price():
    price = get_gram_rub_price()
    formatted = format_price(price)
    try:
        bot.send_message(CHANNEL_ID, formatted)
        logger.info(f"Пост отправлен: {formatted}")
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")

def main():
    logger.info(f"Бот запущен. Постинг каждые {INTERVAL_SECONDS} секунд.")
    post_price()
    while True:
        time.sleep(INTERVAL_SECONDS)
        post_price()

if __name__ == "__main__":
    main()