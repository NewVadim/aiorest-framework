from .exceptions import ValidationError

__author__ = 'vadim'


class BaseValidator(object):
    compare = lambda self, a, b: a is not b
    clean = lambda self, x: x
    message = 'убедитесь что это значение равно "{limit_value}"'
    code = 'limit_value'

    def __init__(self, limit_value, message=None):
        self.limit_value = limit_value
        if message:
            self.message = message

    def __call__(self, value):
        if not value:
            return

        cleaned = self.clean(value)
        if self.compare(cleaned, self.limit_value):
            raise ValidationError(self.message.format(limit_value=self.limit_value))

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            (self.limit_value == other.limit_value) and
            (self.message == other.message) and
            (self.code == other.code)
        )


class MaxValueValidator(BaseValidator):
    compare = lambda self, a, b: a > b
    message = 'убедитесь что это значение меньше или равно "{limit_value}"'
    code = 'max_value'


class MinValueValidator(BaseValidator):
    compare = lambda self, a, b: a < b
    message = 'убедитесь что это значение больше или равно "{limit_value}"'
    code = 'min_value'


class MinLengthValidator(BaseValidator):
    compare = lambda self, a, b: a < b
    clean = lambda self, x: len(x)
    message = 'убедитесь что длина строки больше "{limit_value}"'
    code = 'min_length'


class MaxLengthValidator(BaseValidator):
    compare = lambda self, a, b: a > b
    clean = lambda self, x: len(x)
    message = 'убедитесь что длина строки меньше "{limit_value}"'
    code = 'max_length'
