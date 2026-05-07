"""исключения ML-сервиса"""


class DomainError(Exception):
    """базовое исключение доменного слоя"""


class NotFoundError(DomainError):
    """ошибка, возникающая при обращении к отсутствующей сущности"""


class UserAlreadyExistsError(DomainError):
    """ошибка, возникающая при попытке создать уже существующего пользователя"""


class AuthenticationError(DomainError):
    """ошибка аутентификации пользователя"""


class AuthorizationError(DomainError):
    """ошибка авторизации пользователя"""


class InsufficientBalanceError(DomainError):
    """ошибка, возникающая при недостаточном балансе пользователя"""


class InvalidAmountError(DomainError):
    """ошибка, возникающая при некорректной сумме транзакции"""


class TaskExecutionError(DomainError):
    """ошибка выполнения ML-задачи"""


class ModelUnavailableError(DomainError):
    """ошибка, возникающая при обращении к недоступной ML-модели"""


class FileSizeLimitError(DomainError):
    """ошибка, возникающая при превышении допустимого размера загружаемого файла или задачи"""