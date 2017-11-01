"""
COPYRIGHT NOTICE

This code is based on code taken from Mopidy project (https://github.com/mopidy/mopidy/)
Mopidy is copyright 2009-2017 Stein Magnus Jodal and contributors. Mopidy is licensed under the Apache License, Version 2.0.

This code is redistributed under the terms of LGPL Version 3
"""

import io
import itertools
import logging
import os.path
import re

import configparser
from glin.config.schemas import *
from glin.config.types import *

logger = logging.getLogger(__name__)

# flake8: noqa:
# TODO: Update this to be flake8 compliant

_core_schema = ConfigSchema('core')

_hwcomm_schema = ConfigSchema('hwcomm')
_hwcomm_schema['host'] = Hostname()
_hwcomm_schema['port'] = Port()



# NOTE: if multiple outputs ever comes something like LogLevelConfigSchema
# _outputs_schema = config.AudioOutputConfigSchema()

_schemas = [ _core_schema, _hwcomm_schema ]

_INITIAL_HELP = """
# For further information about options in this file see:
#   http://docs.mopidy.com/
#
# The initial commented out values reflect the defaults as of:
#   %(versions)s
#
# Available options and defaults might have changed since then,
# run `mopidy config` to see the current effective config and
# `mopidy --version` to check the current version.
"""


def read(config_file):
    """Helper to load config defaults in same way across core and extensions"""
    return open(config_file, 'r')


def load(files, ext_schemas, ext_defaults, overrides):
    config_dir = os.path.dirname(__file__)
    defaults = [os.path.join(config_dir, 'default.conf')]
    #defaults.extend(ext_defaults)
    raw_config = _load(files, defaults, (overrides or []))

    schemas = _schemas[:]
    schemas.extend(ext_schemas)
    return _validate(raw_config, schemas)

def _load(files, defaults, overrides):
    parser = configparser.RawConfigParser()

    # TODO: simply return path to config file for defaults so we can load it
    # all in the same way?
    logger.info('Loading config from builtin defaults')
    for default in defaults:
        f = open(default, "r")
        parser.read_file(f)

    # Load config from a series of config files
    for name in files:
        if os.path.isdir(name):
            for filename in os.listdir(name):
                filename = os.path.join(name, filename)
                if os.path.isfile(filename) and filename.endswith('.conf'):
                    _load_file(parser, filename)
        else:
            _load_file(parser, name)

    # If there have been parse errors there is a python bug that causes the
    # values to be lists, this little trick coerces these into strings.
    parser.readfp(io.BytesIO())

    raw_config = {}
    for section in parser.sections():
        raw_config[section] = dict(parser.items(section))

    logger.info('Loading config from command line options')
    for section, key, value in overrides:
        raw_config.setdefault(section, {})[key] = value

    return raw_config


def _load_file(parser, filename):
    if not os.path.exists(filename):
        logger.debug(
            'Loading config from %s failed; it does not exist', filename)
        return
    if not os.access(filename, os.R_OK):
        logger.warning(
            'Loading config from %s failed; read permission missing',
            filename)
        return

    try:
        logger.info('Loading config from %s', filename)
        with io.open(filename, 'r') as filehandle:
            parser.read_file(filehandle)
    except configparser.MissingSectionHeaderError as e:
        logger.warning('%s does not have a config section, not loaded.',
                       filename)
    except configparser.ParsingError as e:
        linenos = ', '.join(str(lineno) for lineno, line in e.errors)
        logger.warning(
            '%s has errors, line %s has been ignored.', filename, linenos)
    except IOError:
        # TODO: if this is the initial load of logging config we might not
        # have a logger at this point, we might want to handle this better.
        logger.debug('Config file %s not found; skipping', filename)


def _validate(raw_config, schemas):
    # Get validated config
    config = {}
    errors = {}
    sections = set(raw_config)
    for schema in schemas:
        sections.discard(schema.name)
        values = raw_config.get(schema.name, {})
        result, error = schema.deserialize(values)
        if error:
            errors[schema.name] = error
        if result:
            config[schema.name] = result

    for section in sections:
        logger.debug('Ignoring unknown config section: %s', section)

    return config, errors
