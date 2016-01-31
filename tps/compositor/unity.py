#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright © 2014-2015 Martin Ueding <dev@martin-ueding.de>
# Licensed under The GNU Public License Version 2 (or later)

'''
Logic for Ubuntu Unity.
'''

import logging

from tps.utils import check_call, command_exists

logger = logging.getLogger(__name__)


def set_launcher(autohide):
    '''
    Sets the autohide property of the Unity launcher.

    In the back, this uses ``dconf``. If that is not installed, this just fails
    with a warning.

    :param bool autohide: True if autohide is desired
    '''
    if not command_exists('dconf'):
        logger.warning('dconf is not installed')
        return

    set_to = '1' if autohide else '0'
    check_call(
        ['dconf', 'write',
         '/org/compiz/profiles/unity/plugins/unityshell/launcher-hide-mode',
         set_to],
        logger)
