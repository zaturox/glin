"""
COPYRIGHT NOTICE

This code is based on code taken from Mopidy project (https://github.com/mopidy/mopidy/)
Mopidy is copyright 2009-2017 Stein Magnus Jodal and contributors. Mopidy is licensed under the Apache License, Version 2.0.

This code is redistributed under the terms of LGPL Version 3
"""

import collections

import glin.config.types import types


class ConfigSchema(collections.OrderedDict):

    """Logical group of config values that correspond to a config section.

    Schemas are set up by assigning config keys with config values to
    instances. Once setup :meth:`deserialize` can be called with a dict of
    values to process. For convienience we also support :meth:`format` method
    that can used for converting the values to a dict that can be printed and
    :meth:`serialize` for converting the values to a form suitable for
    persistence.
    """

    def __init__(self, name):
        super(ConfigSchema, self).__init__()
        self.name = name

    def deserialize(self, values):
        """Validates the given ``values`` using the config schema.

        Returns a tuple with cleaned values and errors.
        """
        errors = {}
        result = {}

        for key, value in values.items():
            try:
                result[key] = self[key].deserialize(value)
            except KeyError:  # not in our schema
                errors[key] = 'unknown config key.'
            except ValueError as e:  # deserialization failed
                result[key] = None
                errors[key] = str(e)

        for key in self.keys():
            if isinstance(self[key], types.Deprecated):
                result.pop(key, None)
            elif key not in result and key not in errors:
                result[key] = None
                errors[key] = 'config key not found.'

        return result, errors

    def serialize(self, values, display=False):
        """Converts the given ``values`` to a format suitable for persistence.

        If ``display`` is :class:`True` secret config values, like passwords,
        will be masked out.

        Returns a dict of config keys and values."""
        result = collections.OrderedDict()
        for key in self.keys():
            if key in values:
                result[key] = self[key].serialize(values[key], display)
        return result


class MapConfigSchema(object):

    """Schema for handling multiple unknown keys with the same type.

    Does not sub-class :class:`ConfigSchema`, but implements the same
    serialize/deserialize interface.
    """

    def __init__(self, name, value_type):
        self.name = name
        self._value_type = value_type

    def deserialize(self, values):
        errors = {}
        result = {}

        for key, value in values.items():
            try:
                result[key] = self._value_type.deserialize(value)
            except ValueError as e:  # deserialization failed
                result[key] = None
                errors[key] = str(e)
        return result, errors

    def serialize(self, values, display=False):
        result = collections.OrderedDict()
        for key in sorted(values.keys()):
            result[key] = self._value_type.serialize(values[key], display)
        return result
