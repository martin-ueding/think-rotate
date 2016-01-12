#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2014-2015 Martin Ueding <dev@martin-ueding.de>
# Copyright © 2014 Jim Turner <jturner314@gmail.com>
# Licensed under The GNU Public License Version 2 (or later)

'''
Main module for thinkpad-scripts.
'''

import collections
import functools
import subprocess
import logging
import os

Direction = collections.namedtuple(
    'Direction', ['xrandr', 'subpixel', 'rot_mat']
)
'''
Holds the direction names of different tools.

``xrandr`` and other programs use different names for the rotations. To avoid
proliferation of various names, this class holds the differing names. The
module provides constants which have to be used within :mod:`tps`.
'''

LEFT = Direction('left', 'vrgb', [0,-1, 1,
                                  1, 0, 0,
                                  0, 0, 1])

RIGHT = Direction('right', 'vbgr', [0, 1, 0,
                                   -1, 0, 1,
                                    0, 0, 1])

NORMAL = Direction('normal', 'rgb', [1, 0, 0,
                                     0, 1, 0,
                                     0, 0, 1])

INVERTED = Direction('inverted', 'bgr', [-1, 0, 1,
                                          0,-1, 1,
                                          0, 0, 1])

TABLET_NORMAL = NORMAL

logger = logging.getLogger(__name__)


class UnknownDirectionException(Exception):
    '''
    Unknown direction given at the command line.
    '''


def translate_direction(direction):
    '''
    :param str direction: Direction string
    :returns: Direction object
    :rtype: tps.Direction
    :raises tps.UnknownDirectionException:
    '''

    if direction in ['normal', 'none']:
        result = NORMAL

    elif direction in ['left', 'ccw']:
        result = LEFT

    elif direction in ['right', 'cw']:
        result = RIGHT

    elif direction in ['flip', 'inverted', 'half']:
        result = INVERTED

    elif direction == 'tablet-normal':
        result = TABLET_NORMAL

    else:
        raise UnknownDirectionException(
            'Direction “{}” cannot be understood.'.format(direction))

    logger.debug('Converted “{}” to “{}”.'.format(direction, result))

    return result


def has_program(command):
    '''
    Checks whether given program is installed on this computer.

    :param str command: Name of command
    :returns: Whether program is installed
    :rtype: bool
    '''
    def is_exe(path):
        return os.path.isfile(path) and os.access(path, os.X_OK)

    # Check if `command` is a path to an executable
    if os.sep in command:
        if is_exe(os.path.expanduser(command)):
            logger.debug('Command “{}” found.'.format(command))
            return True

    # Check if `command` is an executable on PATH
    else:
        for dir in os.get_exec_path():
            if is_exe(os.path.join(dir, command)):
                logger.debug('Command “{}” found.'.format(command))
                return True

    logger.debug('Command “{}” not found.'.format(command))
    return False


def print_command_decorate(function):
    '''
    Decorates a func from the subprocess module to log the `command` parameter.

    Note that the wrapper adds an additional `local_logger` parameter following
    the `command` parameter that is used for the logging. All other parameters
    are passed to the wrapped function.

    :param function: Function to wrap
    :returns: Decorated function
    '''
    @functools.wraps(function)
    def wrapper(command, local_logger, *args, **kwargs):
        local_logger.debug('subprocess “{}”'.format(' '.join(command)))
        #kwargs['stderr'] = subprocess.STDOUT
        return function(command, *args, **kwargs)
    return wrapper


def assert_python3():
    '''
    Asserts that this is running with Python 3
    '''
    assert sys.version_info >= (3, 0), 'You need Python 3 to run this!'


check_call = print_command_decorate(subprocess.check_call)
call = print_command_decorate(subprocess.call)
check_output = print_command_decorate(subprocess.check_output)


if __name__ == '__main__':
    assert_python3()
