# coding=utf-8
from __future__ import unicode_literals

import datetime
from collections import OrderedDict

from aiorest_framework.utils import parse_datetime
from .validators import MaxLengthValidator
from .exceptions import ValidationError

__author__ = 'vadim'


class Field:
    _creation_counter = 0

    field_error_messages = {}
    default_error_messages = {
        'to_python': 'неверные данные',
        'required': 'обязательное поле',
    }

    def __init__(self, name=None, initial_data=None, required=True, read_only=False, default=None, partial=False):
        self._creation_counter = Field._creation_counter
        Field._creation_counter += 1

        self.name = name
        self.initial_data = initial_data or {}
        self.validated_data = {}
        self._errors = {}
        self.error_messages = {}
        self.error_messages.update(self.default_error_messages)
        self.error_messages.update(self.field_error_messages)
        self.required = required
        self.read_only = read_only
        self.default = default
        self.validators = []
        self.parent = None
        self.partial = partial

    def fail(self, key):
        raise ValidationError(self.error_messages[key])

    async def to_representation(self, value):
        return value

    async def get_attribute(self, instance):
        attr_name = self.get_attr_name()
        if isinstance(instance, dict):
            value = instance.get(attr_name)
        else:
            value = getattr(instance, attr_name, None)

        return value

    def get_attr_name(self):
        return self.name

    def bind(self, parent, name):
        self.parent = parent
        self.name = name
        self.partial = parent.partial

    async def run_validation(self, data):
        if not data and self.required and not self.parent:
            self.fail('required')

        elif not data and self.partial:
            return await self.get_attribute(self.parent.instance)

        elif not data and not self.required:
            return data

        data = await self.to_python(data)
        await self.run_validators(data)
        return data

    async def to_python(self, value):
        return value

    async def run_validators(self, data):
        for validator in self.validators:
            validator(data)


class IntegerField(Field):
    async def to_representation(self, value):
        return int(value)

    async def to_python(self, value):
        try:
            value = int(value)
        except Exception as exc:
            self.fail('to_python')

        return value


class SmallIntegerField(IntegerField):
    pass


class CharField(Field):
    def __init__(self, *args, max_length=None, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)

        if self.max_length:
            self.validators.append(MaxLengthValidator(max_length))

    async def to_representation(self, value):
        return str(value)


class DateTimeField(Field):
    ISO_8601 = 'iso-8601'
    input_formats = (ISO_8601,)
    field_error_messages = {
        'date': 'это значение просто дата',
        'invalid': 'не верный формат',
    }

    async def to_python(self, value):
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            self.fail('date')

        if isinstance(value, datetime.datetime):
            return value

        for input_format in self.input_formats:
            if input_format.lower() == self.ISO_8601:
                try:
                    parsed = parse_datetime(value)
                except (ValueError, TypeError):
                    pass
                else:
                    return parsed
                    # if parsed is not None:
                    #     return self.enforce_timezone(parsed)
            else:
                try:
                    parsed = self.datetime_parser(value, input_format)
                except (ValueError, TypeError):
                    pass
                else:
                    return parsed
                    # return self.enforce_timezone(parsed)

        self.fail('invalid')

    async def to_representation(self, value):
        return value.isoformat()


class ChoiceField(Field):
    field_error_messages = {
        'invalid_choice': '"{input}" неверный вариант'
    }

    def __init__(self, choices, **kwargs):
        self.choices = OrderedDict(choices)

        # Map the string representation of choices to the underlying value.
        # Allows us to deal with eg. integer choices while supporting either
        # integer or string input, but still get the correct datatype out.
        self.choice_strings_to_values = {
            str(key): key for key in self.choices
        }

        self.allow_blank = kwargs.pop('allow_blank', False)
        super(ChoiceField, self).__init__(**kwargs)

    async def to_python(self, data):
        if data == '' and self.allow_blank:
            return ''

        if not (self.choice_strings_to_values.get(data) or self.choices.get(data)):
            raise ValidationError(self.error_messages['invalid_choice'].format(input=data))

        return data

    async def to_representation(self, value):
        if value in ('', None):
            return value
        return self.choice_strings_to_values.get(value, value)


class BooleanField(Field):
    TRUE_VALUES = {'t', 'T', 'true', 'True', 'TRUE', '1', 1, True}
    FALSE_VALUES = {'f', 'F', 'false', 'False', 'FALSE', '0', 0, 0.0, False}

    field_error_messages = {
        'invalid': '"{input}" не верное булевое значение'
    }

    async def to_internal_value(self, data):
        try:
            if data in self.TRUE_VALUES:
                return True
            elif data in self.FALSE_VALUES:
                return False
        except TypeError:  # Input is an unhashable type
            pass
        self.fail('invalid')

    async def to_representation(self, value):
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        return bool(value)


class SerializerMethodField(Field):
    def __init__(self, *args, method_name=None, **kwargs):
        self.method_name = method_name
        kwargs['read_only'] = True
        super(SerializerMethodField, self).__init__(**kwargs)

    async def get_attribute(self, instance):
        method_name = self.method_name or 'get_{field_name}'.format(field_name=self.name)
        method = getattr(self.parent, method_name)
        return method(instance)
