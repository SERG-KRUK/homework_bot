import logging
import os
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv
from requests.exceptions import RequestException

# Загрузка переменных окружения
load_dotenv()

# Конфигурация логирования
home_dir = os.path.expanduser('~')
log_file = os.path.join(home_dir, 'kitty_bot.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - '
           '%(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

# Константы
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600  # 10 минут
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

    missing_tokens = []

    for key, value in tokens.items():
        if not value:
            logger.critical(f'Отсутствует переменная окружения: {key}')
            missing_tokens.append(key)

    if missing_tokens:
        raise Exception(
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}'
        )

    return True


class InvalidResponseCode(Exception):
    """Исключение для неверного кода ответа API."""

    def __init__(self, code, reason, text):
        """Исключения."""
        self.code = code
        self.reason = reason
        self.text = text
        super().__init__(
            f'Неверный код ответа API: {code}, '
            f'причина: {reason}, '
            f'текст: {text}'
        )


def get_api_answer(current_timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': current_timestamp}
    }

    logger.info(
        'Запрос к API: url={url}, headers={headers}, params={params}'.format(
            **request_params
        )
    )

    try:
        response = requests.get(**request_params)

    except RequestException as error:
        raise ConnectionError(
            'Сбой при запросе к API: url={url}'
            'headers={headers}, params={params}. '
            'Ошибка: {error}'.format(error=error, **request_params)
        )

    if response.status_code != HTTPStatus.OK:
        raise InvalidResponseCode(
            code=response.status_code,
            reason=response.reason,
            text=response.text
        )

    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        logger.error('Ответ API не является словарем')
        raise TypeError('Ответ API не является словарем')

    if 'homeworks' not in response:
        logger.error('Отсутствует ключ "homeworks" в ответе API')
        raise KeyError('Отсутствует ключ "homeworks" в ответе API')

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
        logger.error(
            f'Неожиданный статус домашней работы: {homework_status}')
        raise ValueError(
            f'Неожиданный статус домашней работы: {homework_status}')

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram и возвращает результат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug("Сообщение успешно отправлено в Telegram")
        return True
    except telebot.apihelper.ApiException:
        logger.error('Ошибка при отправке сообщения в Telegram')
        return False


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    previous_message = ""

    while True:
        try:
            process_homeworks(bot, current_timestamp, previous_message)
            current_timestamp = update_timestamp(current_timestamp)
        except InvalidResponseCode as error:
            handle_error(bot, f'Ошибка API: {error}', previous_message)
        except ConnectionError as error:
            handle_error(bot, f'Сбой подключения: {error}', previous_message)
        except Exception as error:
            handle_error(
                bot,
                f'Сбой в работе программы: {error}',
                previous_message
            )
        finally:
            time.sleep(RETRY_PERIOD)


def process_homeworks(bot, current_timestamp, previous_message):
    """Обрабатывает домашние работы и отправляет сообщения."""
    response = get_api_answer(current_timestamp)
    homeworks = check_response(response)

    if not homeworks:
        logger.debug('Нет новых статусов домашней работы')
        return previous_message

    homework = homeworks[0]
    current_message = parse_status(homework)

    if (current_message != previous_message
            and send_message(bot, current_message)):
        logger.debug("Сообщение успешно отправлено в Telegram")
        previous_message = current_message

    return previous_message


def update_timestamp(current_timestamp):
    """Обновляет временную отсечку для следующего запроса."""
    response = get_api_answer(current_timestamp)
    return response.get('current_date', current_timestamp)


def handle_error(bot, error_message, previous_message):
    """Обрабатывает ошибки и отправляет сообщения в Telegram."""
    logger.error(error_message)

    if error_message != previous_message and send_message(bot, error_message):
        logger.debug("Сообщение об ошибке отправлено в Telegram")
        previous_message = error_message

    return previous_message


if __name__ == '__main__':
    main()
