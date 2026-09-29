import os
import telebot
import requests
import time
import logging
from statistics import mean, median
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", 180))
# Цены, отличающиеся от медианы больше чем на этот процент, отбрасываются
MAX_DEVIATION_PERCENT = float(os.getenv("MAX_DEVIATION_PERCENT", 3))
REQUEST_TIMEOUT = 10

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

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (gram_bot)", "Accept": "application/json"})


def get_json(url):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


# --- Курс GRAM/USDT на биржах ---
# TON переименован в GRAM: пары TONUSDT на биржах удалены или заморожены (Binance TONUSDT в статусе BREAK)

def binance():
    return get_json("https://api.binance.com/api/v3/ticker/price?symbol=GRAMUSDT")["price"]

def bybit():
    return get_json("https://api.bybit.com/v5/market/tickers?category=spot&symbol=GRAMUSDT")["result"]["list"][0]["lastPrice"]

def okx():
    return get_json("https://www.okx.com/api/v5/market/ticker?instId=GRAM-USDT")["data"][0]["last"]

def kucoin():
    return get_json("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=GRAM-USDT")["data"]["price"]

def gate():
    return get_json("https://api.gateio.ws/api/v4/spot/tickers?currency_pair=GRAM_USDT")[0]["last"]

def mexc():
    return get_json("https://api.mexc.com/api/v3/ticker/price?symbol=GRAMUSDT")["price"]

def htx():
    return get_json("https://api.huobi.pro/market/detail/merged?symbol=gramusdt")["tick"]["close"]

def bitget():
    return get_json("https://api.bitget.com/api/v2/spot/market/tickers?symbol=GRAMUSDT")["data"][0]["lastPr"]

EXCHANGES = {
    "Binance": binance,
    "Bybit": bybit,
    "OKX": okx,
    "KuCoin": kucoin,
    "Gate": gate,
    "MEXC": mexc,
    "HTX": htx,
    "Bitget": bitget,
}


# --- Курс USDT/RUB ---

def usdt_rub_rapira():
    for item in get_json("https://api.rapira.net/open/market/rates")["data"]:
        if item["symbol"] == "USDT/RUB":
            return item["close"]
    raise ValueError("пара USDT/RUB не найдена")

def usd_rub_cbr():
    return get_json("https://www.cbr-xml-daily.ru/daily_json.js")["Valute"]["USD"]["Value"]

# Порядок = приоритет: рыночный курс USDT/RUB, если недоступен — официальный курс ЦБ
USDT_RUB_SOURCES = {
    "Rapira": usdt_rub_rapira,
    "ЦБ РФ": usd_rub_cbr,
}


def fetch_price(name, fetcher):
    try:
        price = float(fetcher())
        if price <= 0:
            raise ValueError(f"некорректная цена {price}")
        return price
    except Exception as e:
        logger.warning(f"{name}: не удалось получить курс: {e}")
        return None


def get_gram_usdt_price():
    with ThreadPoolExecutor(max_workers=len(EXCHANGES)) as pool:
        futures = {name: pool.submit(fetch_price, name, fetcher) for name, fetcher in EXCHANGES.items()}
        prices = {name: f.result() for name, f in futures.items() if f.result() is not None}

    if not prices:
        logger.error("Ни одна биржа не вернула курс GRAM/USDT")
        return None

    # Отбрасываем выбросы (замороженные пары, сбои API) относительно медианы
    med = median(prices.values())
    valid = {n: p for n, p in prices.items() if abs(p - med) / med * 100 <= MAX_DEVIATION_PERCENT}
    for name in prices.keys() - valid.keys():
        logger.warning(f"{name}: курс {prices[name]} отброшен (медиана {med})")

    avg = mean(valid.values())
    logger.info(f"GRAM/USDT = {avg:.4f} (среднее по {len(valid)} биржам: {valid})")
    return avg


def get_usdt_rub_rate():
    for name, fetcher in USDT_RUB_SOURCES.items():
        rate = fetch_price(name, fetcher)
        if rate is not None:
            logger.info(f"USDT/RUB ({name}) = {rate}")
            return rate
    logger.error("Не удалось получить курс USDT/RUB")
    return None


def get_gram_rub_price():
    usdt_price = get_gram_usdt_price()
    if usdt_price is None:
        return None
    rub_rate = get_usdt_rub_rate()
    if rub_rate is None:
        return None
    rub_price = usdt_price * rub_rate
    logger.info(f"GRAM/RUB = {rub_price:.2f}")
    return rub_price


def format_price(value):
    return f"{value:.2f}₽"

def post_price():
    price = get_gram_rub_price()
    if price is None:
        logger.error("Курс не получен — пост пропущен")
        return
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
