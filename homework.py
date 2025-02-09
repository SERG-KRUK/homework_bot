import os
import time
import logging
import requests
import telegram
from dotenv import load_dotenv
from http import HTTPStatus

# Загрузка переменных окружения
load_dotenv()

# Конфигурация логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Константы
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_TIME = 600  # 10 минут
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

# Вердикты для статусов домашней работы
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for key, value in tokens.items():
        if not value:
            logger.critical(f'Отсутствует переменная окружения: {key}')
            return False
    return True


def get_api_answer(current_timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    params = {'from_date': current_timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            logger.error(f'Ошибка при запросе к API: {response.status_code}')
            raise Exception(f'Ошибка API: {response.status_code}')
        return response.json()
    except Exception as error:
        logger.error(f'Сбой при запросе к API: {error}')
        raise Exception(f'Сбой при запросе к API: {error}')


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        logger.error('Ответ API не является словарем')
        raise TypeError('Ответ API не является словарем')

    if 'homeworks' not in response or 'current_date' not in response:
        logger.error('Отсутствуют ожидаемые ключи в ответе API')
        raise KeyError('Отсутствуют ожидаемые ключи в ответе API')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        logger.error('Домашние работы в ответе API не являются списком')
        raise TypeError('Домашние работы в ответе API не являются списком')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework or 'status' not in homework:
        logger.error(
            'Отсутствуют ожидаемые ключи в информации о домашней работе')
        raise KeyError(
            'Отсутствуют ожидаемые ключи в информации о домашней работе')

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        logger.error(f'Неожиданный статус домашней работы: {homework_status}')
        raise ValueError(
            f'Неожиданный статус домашней работы: {homework_status}')

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено в Telegram')
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {error}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise SystemExit('Отсутствуют необходимые переменные окружения')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Нет новых статусов домашней работы')

            current_timestamp = response.get('current_date', current_timestamp)
        except Exception as error:
            logger.error(f'Сбой в работе программы: {error}')
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
