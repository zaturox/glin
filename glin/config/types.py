"""
COPYRIGHT NOTICE

This code is based on code taken from Mopidy project (https://github.com/mopidy/mopidy/)
Mopidy is copyright 2009-2017 Stein Magnus Jodal and contributors. Mopidy is licensed under the Apache License, Version 2.0.

This code is redistributed under the terms of LGPL Version 3
"""

import socket

from glin.config import validators


def decode(value):
    if isinstance(value, str):
        return value
    # TODO: only unescape \n \t and \\?
    return value.decode('string-escape').decode('utf-8')


def encode(value):
    if not isinstance(value, str):
        return value
    for char in ('\\', '\n', '\t'):  # TODO: more escapes?
        value = value.replace(char, char.encode('unicode-escape'))
    return value.encode('utf-8')

class DeprecatedValue(object):
    pass


class ConfigValue(object):

    """Represents a config key's value and how to handle it.

    Normally you will only be interacting with sub-classes for config values
    that encode either deserialization behavior and/or validation.

    Each config value should be used for the following actions:

    1. Deserializing from a raw string and validating, raising ValueError on
       failure.
    2. Serializing a value back to a string that can be stored in a config.
    3. Formatting a value to a printable form (useful for masking secrets).

    :class:`None` values should not be deserialized, serialized or formatted,
    the code interacting with the config should simply skip None config values.
    """

    def deserialize(self, value):
        """Cast raw string to appropriate type."""
        return value

    def serialize(self, value, display=False):
        """Convert value back to string for saving."""
        if value is None:
            return b''
        return bytes(value)


class Deprecated(ConfigValue):

    """Deprecated value

    Used for ignoring old config values that are no longer in use, but should
    not cause the config parser to crash.
    """

    def deserialize(self, value):
        return DeprecatedValue()

    def serialize(self, value, display=False):
        return DeprecatedValue()


class String(ConfigValue):

    """String value.

    Is decoded as utf-8 and \\n \\t escapes should work and be preserved.
    """

    def __init__(self, optional=False, choices=None):
        self._required = not optional
        self._choices = choices

    def deserialize(self, value):
        value = decode(value).strip()
        validators.validate_required(value, self._required)
        if not value:
            return None
        validators.validate_choice(value, self._choices)
        return value

    def serialize(self, value, display=False):
        if value is None:
            return b''
        return encode(value)


class Integer(ConfigValue):

    """Integer value."""

    def __init__(
            self, minimum=None, maximum=None, choices=None, optional=False):
        self._required = not optional
        self._minimum = minimum
        self._maximum = maximum
        self._choices = choices

    def deserialize(self, value):
        validators.validate_required(value, self._required)
        if not value:
            return None
        value = int(value)
        validators.validate_choice(value, self._choices)
        validators.validate_minimum(value, self._minimum)
        validators.validate_maximum(value, self._maximum)
        return value


class Boolean(ConfigValue):

    """Boolean value.

    Accepts ``1``, ``yes``, ``true``, and ``on`` with any casing as
    :class:`True`.

    Accepts ``0``, ``no``, ``false``, and ``off`` with any casing as
    :class:`False`.
    """
    true_values = ('1', 'yes', 'true', 'on')
    false_values = ('0', 'no', 'false', 'off')

    def __init__(self, optional=False):
        self._required = not optional

    def deserialize(self, value):
        validators.validate_required(value, self._required)
        if not value:
            return None
        if value.lower() in self.true_values:
            return True
        elif value.lower() in self.false_values:
            return False
        raise ValueError('invalid value for boolean: %r' % value)

    def serialize(self, value, display=False):
        if value:
            return b'true'
        else:
            return b'false'


class Hostname(ConfigValue):

    """Network hostname value."""

    def __init__(self, optional=False):
        self._required = not optional

    def deserialize(self, value, display=False):
        validators.validate_required(value, self._required)
        if not value.strip():
            return None
        try:
            socket.getaddrinfo(value, None)
        except socket.error:
            raise ValueError('must be a resolveable hostname or valid IP')
        return value


class Port(Integer):

    """Network port value.

    Expects integer in the range 0-65535, zero tells the kernel to simply
    allocate a port for us.
    """
    # TODO: consider probing if port is free or not?

    def __init__(self, choices=None, optional=False):
        super(Port, self).__init__(
            minimum=0, maximum=2 ** 16 - 1, choices=choices, optional=optional)
