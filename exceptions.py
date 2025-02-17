class MissingEnvironmentVariableError(Exception):
    """Исключение, выбрасываемое при отсутствии переменных."""

    def __init__(self, message):
        """Исключение."""
        super().__init__(message)


class InvalidResponseCode(Exception):
    """Исключение для неверного кода ответа API."""

    pass
