import copy
import inspect
from collections import OrderedDict

from . import fields
from .exceptions import ValidationError

__author__ = 'vadim'


class Options:
    def __init__(self, meta):
        self.model = None
        self.fields = ()
        self.validators = {}

        meta_kwargs = {key: value for key, value in meta.__dict__.items()
                       if not key.startswith('__')}
        self.__dict__.update(meta_kwargs)


class SerializerMetaclass(type):
    @classmethod
    def _get_declared_fields(cls, bases, attrs):
        declared_fields = [
            (field_name, attrs.pop(field_name))
            for field_name, obj in list(attrs.items())
            if isinstance(obj, fields.Field)
        ]
        declared_fields.sort(key=lambda x: x[1]._creation_counter)

        # If this class is subclassing another Serializer, add that Serializer's
        # fields.  Note that we loop over the bases in *reverse*. This is necessary
        # in order to maintain the correct order of fields.
        for base in reversed(bases):
            if hasattr(base, '_declared_fields'):
                declared_fields = list(base._declared_fields.items()) + declared_fields

        return OrderedDict(declared_fields)

    def __new__(cls, name, bases, attrs):
        meta = attrs.get('Meta')
        if meta:
            attrs['_meta'] = Options(meta)

        attrs['_declared_fields'] = cls._get_declared_fields(bases, attrs)

        return super(SerializerMetaclass, cls).__new__(cls, name, bases, attrs)


class BaseSerializer(fields.Field):
    LIST_SERIALIZER_KWARGS = []

    def __new__(cls, *args, **kwargs):
        # We override this method in order to automagically create
        # `ListSerializer` classes instead when `many=True` is set.
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super(BaseSerializer, cls).__new__(cls)

    def __init__(self, instance=None, *args, **kwargs):
        super(BaseSerializer, self).__init__(*args, **kwargs)
        self.instance = instance
        kwargs.update(name=self.__class__.__name__)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """
        This method implements the creation of a `ListSerializer` parent
        class when `many=True` is used. You can customize it if you need to
        control which keyword arguments are passed to the parent, and
        which are passed to the child.

        Note that we're over-cautious in passing most arguments to both parent
        and child classes in order to try to cover the general case. If you're
        overriding this method you'll probably want something much simpler, eg:

        @classmethod
        def many_init(cls, *args, **kwargs):
            kwargs['child'] = cls()
            return CustomListSerializer(*args, **kwargs)
        """
        # allow_empty = kwargs.pop('allow_empty', None)
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {
            'child': child_serializer,
        }
        # if allow_empty is not None:
        #     list_kwargs['allow_empty'] = allow_empty
        # list_kwargs.update({
        #    key: value for key, value in kwargs.items()
        #    if key in cls.LIST_SERIALIZER_KWARGS
        # })
        list_serializer_class = getattr(cls.Meta, 'list_serializer_class', ListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def get_fields(self):
        return OrderedDict([[field, self.build_field(field, self)]
                            for field in self._meta.fields])

    def build_field(self, name, parent):
        field = self._declared_fields.get(name)
        field and field.bind(self, name)
        return field

    def get_writable_fields(self):
        return OrderedDict([
            [field.name, field] for field in self.fields.values()
            if not field.read_only or field.default
        ])

    @property
    async def data(self):
        if self.initial_data and self.validated_data is None:
            msg = (
                'When a serializer is passed a `data` keyword argument you '
                'must call `.is_valid()` before attempting to access the '
                'serialized `.data` representation.\n'
                'You should either call `.is_valid()` first, '
                'or access `.initial_data` instead.'
            )
            raise AssertionError(msg)

        if not hasattr(self, '_data'):
            if self.instance is not None and not self._errors:
                self._data = await self.to_representation(self.instance)
            elif self.validated_data and not self._errors:
                self._data = await self.to_representation(self.validated_data)
            else:
                self._data = self.initial_data

        return self._data

    async def is_valid(self, raise_exception=False):
        assert hasattr(self, 'initial_data'), (
            'Cannot call `.is_valid()` as no `data=` keyword argument was '
            'passed when instantiating the serializer instance.'
        )

        if not self.validated_data:
            try:
                self.validated_data = await self.run_validation(self.initial_data)
            except ValidationError as exc:
                self._errors = exc.detail

        if self._errors and raise_exception:
            raise ValidationError(self._errors)

        return not bool(self._errors)

    async def run_validation(self, data):
        data = data if isinstance(data, dict) else {}

        ret = OrderedDict()
        errors = OrderedDict()
        check_fields = self.writable_fields
        for name, field in check_fields.items():
            value = data.get(name)
            try:
                ret[field.name] = await field.run_validation(value)
            except ValidationError as exc:
                errors[name] = exc.detail

        self._errors = errors
        if self._errors:
            raise ValidationError(self._errors)

        return ret

    async def save(self, **kwargs):
        assert not self._errors, (
            'You hav errors. '
            'You must call `.is_valid()` with valid data before calling `.save()`.'
        )

        self.validated_data.update(kwargs)

        if self.instance is None:
            self.instance = await self.create()
        else:
            self.instance = await self.update(self.instance)

        assert self.instance is not None, (
            '`{method}()` did not return an object instance.'.format(
                method='create' if self.instance is None else 'update')
        )
        return self.instance

    async def create(self, validated_data):
        return validated_data

    async def update(self, instance, validated_data):
        instance = instance.update(validated_data)
        return instance

    async def to_representation(self, instance):
        """
        Object instance -> Dict of primitive datatypes.
        """
        ret = OrderedDict()
        for name, field in self.fields.items():
            attribute = await field.get_attribute(instance)
            ret[field.name] = attribute and await field.to_representation(attribute)
        return ret


class Serializer(BaseSerializer, metaclass=SerializerMetaclass):
    def __init__(self, *args, **kwargs):
        super(Serializer, self).__init__(*args, **kwargs)
        self.fields = self.get_fields()
        self.writable_fields = self.get_writable_fields()
        for field_name, validators in self._meta.validators.items():
            self.writable_fields[field_name].validators = validators


class ListSerializer(BaseSerializer, metaclass=SerializerMetaclass):
    child = None
    many = True

    default_error_messages = {
        'not_a_list': 'Expected a list of items but got type "{input_type}".',
        'empty': 'This list may not be empty.',
    }

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        self.allow_empty = kwargs.pop('allow_empty', True)
        assert self.child is not None, '`child` is a required argument.'
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        super(ListSerializer, self).__init__(*args, **kwargs)

    def run_validation(self, data):
        """
        We override the default `run_validation`, because the validation
        performed by validators and the `.validate()` method should
        be coerced into an error dictionary with a 'non_fields_error' key.
        """
        ret = []
        errors = []
        for item in data:
            try:
                validated = self.child.run_validation(item)
            except ValidationError as exc:
                errors.append(exc.detail)
            else:
                ret.append(validated)
                errors.append({})

        if any(errors):
            raise ValidationError(errors)

        return ret

    async def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        ret = []

        for item in data:
            ret.append(await self.child.to_representation(item))

        return ret
