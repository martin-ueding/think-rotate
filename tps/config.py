#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2014 Martin Ueding <dev@martin-ueding.de>
# Licensed under The GNU Public License Version 2 (or later)

'''
Config module.

Takes care of the INI style config file for global and user configuration.
'''

import configparser
import logging
import logging.handlers
import os.path
import re
import shlex
import sys

import pkg_resources

import termcolor

CONFIGFILE = os.path.expanduser('~/.config/thinkpad-scripts/config.ini')
'Path of global config file'

logger = logging.getLogger(__name__)

def get_config():
    '''
    Loads the config from the config files.

    The global config file is read first, then the user config file is read.
    That way, options can be overwritten in the user config file.

    :returns: Config
    :rtype: configparser.ConfigParser
    '''
    config = configparser.ConfigParser(interpolation=None)

    default_filename = pkg_resources.resource_filename(__name__, "default.ini")

    config.read(default_filename)
    if os.path.isfile(CONFIGFILE):
        config.read(CONFIGFILE)

    return config

def print_config(config):
    '''
    Pretty prints config with colors.

    :param configparser.ConfigParser config: Config to print
    :returns: None
    '''
    for section in sorted(config.sections()):
        termcolor.cprint(section, attrs=('bold',))

        for key in sorted(config[section]):
            print(termcolor.colored(key, 'yellow'), config[section][key])

def migrate_shell_config():
    config = configparser.ConfigParser(interpolation=None)

    old_files = [
        os.path.expanduser('~/.config/thinkpad-scripts/rotate.sh'),
        os.path.expanduser('~/.config/thinkpad-scripts/dock.sh'),
    ]

    errors = []

    for old_file in old_files:
        if os.path.isfile(old_file):
            with open(old_file) as handle:
                for line in handle:
                    try:
                        interpret_shell_line(line, config)
                    except ShellParseException as exception:
                        errors.append(str(exception))

    if len(errors) > 0:
        print()
        print('The following errors occured:')
        for error in errors:
            print('-', termcolor.colored(error, 'red'))

    print()
    print('This is the interpreted configuration:')
    print_config(config)

    print()
    if os.path.isfile(CONFIGFILE):
        termcolor.cprint('File will be overwritten!', 'yellow')
    user_input = input('Do you want to write this config? [Y/n]')

    if user_input == 'Y' or user_input == 'y' or user_input == '':
        with open(CONFIGFILE, 'w') as handle:
            config.write(handle)

def interpret_shell_line(line, config):
    '''
    Interprets a single Bash line to parse for variable assignments.

    The given line is searched for a config option was allowed in the 3.x
    series. It will use the ``shlex`` module to parse the value of the variable
    assignment. If it could be parsed correctly, it will add the value to the
    config. The keys are translated into the new config sections.

    :param str line: Line to check
    :param configparser.ConfigParser config: Config to store parsed variables
    :raise: tps.config.ShellParseException
    :returns: None
    '''
    # Strip out leading and trailing whitespace; it is ignored by the shell
    line = line.strip()

    # Filter out comments.
    if line.startswith('#'):
        return

    known_options = {
        'disable_wifi': ('network', 'disable_wifi'),
        'internal': ('screen', 'internal'),
        'unmute': ('sound', 'unmute'),
        'dock_loudness': ('sound', 'dock_loudness'),
        'undock_loudness': ('sound', 'undock_loudness'),
        'set_brightness': ('screen', 'set_brightness'),
        'brightness': ('screen', 'brightness'),
        'relative_position': ('screen', 'relative_position'),
        'kdialog': ('gui', 'kdialog'),
        'default_rotation': ('rotate', 'default_rotation'),
        'toggle_unity_launcher': ('unity', 'toggle_unity_launcher'),
        'virtual_kbd': ('vkeyboard', 'program'),
    }

    matcher = re.match(r'([^=]+)=(.*)$', line)
    if matcher:
        option = matcher.group(1)
        if not option in known_options:
            raise ShellParseException(
                'Cannot parse “{}”: Not a known option'.format(line))

        try:
            arguments = list(shlex.split(matcher.group(2)))
        except ValueError as e:
            raise ShellParseException('Cannot parse “{}”: {}'.format(line, e))

        if len(arguments) != 1:
            raise ShellParseException(
                'Cannot parse “{}”: Not a single value'.format(line))

        argument = arguments[0]

        if '$' in argument:
            raise ShellParseException(
                'Cannot parse “{}”: Contains “$”, indicates complex value'
                .format(line))

        print(option, '→', argument)

        section, subsection = known_options[option]
        if not section in config:
            config[section] = {}
        config[section][subsection] = argument

def set_up_logging(verbosity):
    '''
    Sets up the logging to console and syslog.

    This is taken from the `Python Docs – Logging Cookbook`__.

    __ http://docs.python.org/3/howto/logging-cookbook.html#logging-to-multiple-destinations.

    The ``address`` parameter for the syslog is taken from an answer from `dr
    jimbob`__.
    
    __ http://stackoverflow.com/a/3969772
    '''
    if verbosity == 1:
        console_log_level = logging.INFO
    elif verbosity == 2:
        console_log_level = logging.DEBUG
    else:
        console_log_level = logging.WARN

    console_format = '%(name)-13s %(levelname)-8s %(message)s'
    syslog_format = 'thinkpad-scripts: %(name)s %(levelname)s %(message)s'

    config = get_config()

    logging.basicConfig(level=console_log_level, format=console_format)

    if config['logging'].getboolean('syslog'):
        syslog = logging.handlers.SysLogHandler(address='/dev/log')
        syslog.setLevel(logging.DEBUG)
        formatter = logging.Formatter(syslog_format)
        syslog.setFormatter(formatter)
        logging.getLogger('').addHandler(syslog)

    logger.debug('----------------------------------')
    logger.debug('Program was started with arguments: {}'.format(sys.argv))


class ShellParseException(Exception):
    '''
    Bash code could not be parsed.

    The parser here is very limited, it can only detect variable assignments.
    If something more complicated is found on a given line, this exception is
    raised.
    '''
    pass

def main():
    '''
    Command line entry point.

    :returns: None
    '''
    print_config(get_config())

if __name__ == '__main__':
    main()
