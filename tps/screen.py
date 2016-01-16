#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright © 2014-2015 Martin Ueding <dev@martin-ueding.de>
# Copyright © 2015 Jim Turner <jturner314@gmail.com>
# Licensed under The GNU Public License Version 2 (or later)

'''
Screen related logic.
'''

import logging
import re
import subprocess

from tps.utils import check_call, check_output, command_exists

logger = logging.getLogger(__name__)


class ScreenNotFoundException(Exception):
    '''
    ``xrandr`` device could not be found.
    '''
    pass


def get_rotation(screen):
    '''
    Gets the current rotation of the given screen.

    :param str screen: Find rotation of given output
    :returns: Current direction
    :rtype: tps.rotate.Direction
    '''
    output = check_output(['xrandr', '-q', '--verbose'], logger).decode()
    lines = output.split('\n')
    for line in lines:
        if screen in line:
            matcher = re.search(r'\) (normal|left|inverted|right) \(', line)
            if matcher:
                rotation = tps.translate_direction(matcher.group(1))
                logger.info('Current rotation is “{}”.'.format(rotation))
                return rotation
    else:
        raise ScreenNotFoundException(
            'Screen "{}" is not enabled. Do you have a screen like that in '
            'the output of "xrandr", and is it enabled? Maybe you have to '
            'adjust the option of screen.internal in the '
            'configuration.'.format(screen))


def get_externals(internal):
    '''
    Gets the external screens.

    You have to specify the internal screen to exclude that from the listing.

    ;param str internal: Name of the internal screen
    :returns: List of external screen names
    :rtype: str
    '''
    externals = []
    lines = check_output(['xrandr'], logger).decode().split('\n')
    for line in lines:
        if not line.startswith(internal):
            matcher = re.search(r'^(\S+) connected', line)
            if matcher:
                externals.append(matcher.group(1))
    return externals


def rotate(screen, direction):
    '''
    Rotates the screen into the direction.

    :param str screen: Name of the output to rotate
    :param tps.Direction direction: New direction
    :returns: None
    '''
    check_call(['xrandr', '--output', screen, '--rotate',
                    direction.xrandr], logger)


def set_subpixel_order(direction):
    '''
    Sets the text subpixel anti-alias order.

    :param tps.Direction direction: New direction
    :returns: None
    '''
    if command_exists('xfconf-query'):
        try:
            check_call(['xfconf-query', '-c', 'xsettings', '-p',
                            '/Xft/RGBA', '-s', direction.subpixel], logger)
        except subprocess.CalledProcessError as e:
            logger.error(e)

    elif command_exists('gsettings'):
        try:
            schemas = check_output(
                ['gsettings', 'list-schemas'], logger).decode().split('\n')
            schema = 'org.gnome.settings-daemon.plugins.xsettings'
            if schema in schemas:
                check_call(['gsettings', 'set', schema, 'rgba-order',
                                direction.subpixel], logger)
            else:
                logger.warning('gsettings is installed, but the "{}" schema '
                               'is not available'.format(schema))
        except subprocess.CalledProcessError as e:
            logger.error(e)
    else:
        logger.warning('neither xfconf-query nor gsettings is installed')


def set_brightness(brightness):
    '''
    Sets the brightness with ``xbacklight``.

    :param str brightness: Percent value of brightness, e. g. ``60%``
    :returns: None
    '''
    if not command_exists('xbacklight'):
        logger.warning('xbacklight is not installed')
        return

    check_call(['xbacklight', '-set', brightness], logger)


def disable(screen):
    '''
    Disables the given screen using ``xrandr``.

    :param str screen: Name of the output to disable
    :returns: None
    '''
    check_call(['xrandr', '--output', screen, '--off'], logger)


def enable(screen, primary=False, position=None):
    '''
    Enables given screen using ``xrandr``.

    :param str screen: Name of the output to enable
    :param bool primary: Set output as primary
    :param tuple position: Tuple with (0) relative position and (1) other
        output. This could be ``('right-of', 'LVDS1')``.
    :returns: None
    '''
    command = ['xrandr', '--output', screen, '--auto']

    if position is not None:
        command += ['--{}'.format(position[0]), position[1]]

    if primary:
        command += ['--primary']

    check_call(command, logger)


def get_resolution_and_shift(output):
    '''
    Retrieves the total resolution of the virtual screen and the position of
    the given output within that.

    The X server seems to generate a huge screen which is then displayed by the
    physical displays. ``xrandr`` gives the size of that (virtual) screen as
    well as the positions of each display in that.

    For example, I currently have the 12.5" 1366×768 ThinkPad X220 display on
    the right of a 23" 1920×1080 pixel display. ``xrandr`` tells me the
    following::

        Screen 0: … current 3286 x 1080 …
        LVDS1 … 1366x768+1920+0
        DP2 … 1920x1080+0+0

    This only shows the interesting parts. The size of the (virtual) screen is
    3286×1080 and the position of the internal screen is 1366×768+1920+0. This
    allows to compute the transformation matrix for this.
    '''
    xrandr_output = check_output(['xrandr', '-q'], logger).strip().decode()
    lines = xrandr_output.split('\n')

    pattern_output = re.compile(r'''
                                {}
                                \D+
                                (?P<width>\d+)
                                x
                                (?P<height>\d+)
                                \+
                                (?P<x>\d+)
                                \+
                                (?P<y>\d+)
                                '''.format(output), re.VERBOSE)
    pattern_screen = re.compile('current (?P<width>\d+) x (?P<height>\d+)')

    result = {}

    for line in lines:
        m_output = pattern_output.search(line)
        if m_output:
            result['output_width'] = int(m_output.group('width'))
            result['output_height'] = int(m_output.group('height'))
            result['output_x'] = int(m_output.group('x'))
            result['output_y'] = int(m_output.group('y'))

        m_screen = pattern_screen.search(line)
        if m_screen:
            result['screen_width'] = int(m_screen.group('width'))
            result['screen_height'] = int(m_screen.group('height'))

    if len(result) != 6:
        raise ScreenNotFoundException(
            'The screen and output dimensions could not be gathered from '
            'xrandr. Maybe the "{}" output is not attached or enabled? Please '
            'report a bug otherwise.'.format(output))

    return result
