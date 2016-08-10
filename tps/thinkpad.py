#!/usr/bin/python3
# -*- coding: utf-8 -*-
# PYTHON_ARGCOMPLETE_OK

# Copyright © 2016 Lukasz Czuja <pub@czuja.pl>
# Licensed under The GNU Public License Version 2 (or later)

import argparse
import logging
import os.path
import sys
import time

from argcomplete import autocomplete
from daemon import DaemonContext
from lockfile.pidlockfile import PIDLockFile

import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from tps.config import get_config, migrate_shell_config, \
                       print_config, set_up_logging
from tps.acpi.battery import ThinkpadAcpiBatteryController
from tps.acpi.thinkpad_acpi import ThinkpadAcpi
from tps.dock import dock, get_docking_state
from tps.compositor import toggle_input_state
from tps.compositor.x11.screen import xrandr_bug_fail_early
from tps.rotate import rotate_cmdline, rotate_daemon
from tps.sysfs.tp_smapi import TpSmapi
from tps.sysfs.power_supply import PowerSourceInfo, PowerSourceInfoLegacy
from tps.utils import check_call
from tps.__meta__ import short as version

logger = logging.getLogger(__name__)


def main():
    '''Entry point (/usr/bin/thinkpad)'''
    options = _parse_cmdline()
    config = get_config()

    set_up_logging(options.verbose)

    if options.command == 'config':
        print_config(get_config())
    elif options.command == 'battery':
        battery(options, config)
    elif options.command == 'beep':
        ThinkpadAcpi.beep(options.sound)
    elif options.command == 'dock':
        # Quickly abort if the call is by the hook and the user disabled 
        # the trigger.
        if options.via_hook and \
            not config['trigger'].getboolean('enable_dock'):
            sys.exit(0)
        dock(get_docking_state(options.state), config)
    elif options.command == 'fan':
        fan(options, config)
    elif options.command == 'input':
        device_name = config['input'][options.input + '_device']
        toggle_input_state(device_name, getState(options.state))
    elif options.command == 'led':
        led(options, config)
    elif options.command == 'mutemic':
        check_call(['amixer', 'sset', "'Capture',0", 'toggle'], logger)
    elif options.command == 'rotate':
        rotate(options, config)
    elif options.command == 'scripts-config-migration':
        migrate_shell_config()
    
    sys.exit(0)
    
def main_legacy():
    '''Entry point for legacy entry points (/usr/bin/thinkpad-<name>)'''
    
    # swap progname
    entrypoint_name = os.path.basename(sys.argv[0])
    sys.argv[0] = sys.argv[0].replace(entrypoint_name, "thinkpad")
    
    logger.warning(_('$entrypoint_name: is deprecated! Please use '
        '\'thinkpad <command>\' instead.'))
    
    # translate entrypoint name into command and insert onto argv
    # in the correct position
    i = 1
    while i < len(sys.argv):
        if sys.argv[i].startswith('-v'):
            i += 1
        elif sys.argv[i].startswith('--via-hook'):
            i += 1
            if i < len(sys.argv) and not sys.argv[i].startswith('-'):
                i += 1
        break
    
    command = entrypoint_name.replace('thinkpad-', '')
    input_device = None
    if command.startswith('touch') or command == 'trackpoint':
        input_device = command
        command = 'input'
    elif command.endswith('-hook'):
        command.replace('-hook', '')
        sys.argv.insert(i, "--via-hook")
        i += 1
        # positional argument to --via-hook
        if command == 'rotate' and not sys.argv[i].startswith('-'):
            i += 1
        
    sys.argv.insert(i, command)
    i += 1
    # positional argument to input command
    if input_device is not None:
        if input_device == 'touch':
            input_device = 'touchscreen'
        sys.argv.insert(i, input_device)
        
    main()

def displayThreshhold(level):
    if level == 0:
        print(str(level) + " (default)")
    elif level > 0 and level < 100:
        print(str(level) + " (relative percent)")
    else:
        print(str(level) + " (unknown)")

def displayInhibit(inhibit, timer):
    if inhibit:
        result_str = "yes";
        if timer == 0:
            result_str += " (unspecified min)"
        elif timer == 65535:
            result_str += " (forever)"
        else:
            result_str += " (%d min)" % timer
        print(result_str)
    else:
        print('no')
  
def displayForceDischarge(discharge, acbreak):
    result_str = 'yes' if discharge else 'no'
    if acbreak:
        result_str += ' (break on AC detach)'
    print(result_str)
    
def timerType(forInhibitCharge):
    def getInhibitCharge(string):
        timer = 0 if string == '' else int(string)
        ############################################################
        #they are shifting a bit somewhere; the limit should be 1440
        #the same range in peak-shift-state is used, except shifted to the left
        #the value returned by peak-shift-state is the REAL duration, though
        if forInhibitCharge and timer != 65535:
            timer *= 2
        ############################################################

        if timer > 1440 and timer != 65535:
            raise argparse.ArgumentTypeError(_('Invalid value for <min>: '
                                             'number of minutes, or 0 for '
                                             'never, or 65535 for forever'))
        return timer
    return getInhibitCharge
    
def getPowerSourceInfoBackend(name):
    backend = None
    if name == 'smapi':
        backend = TpSmapi
    elif name == 'sysfs':
        backend = PowerSourceInfo
    elif name == 'acpi':
        backend = PowerSourceInfoLegacy
    else:
        raise ValueError(_('Unknown Power Source Info backend: $name'))
    if not backend.isAvailable():
        logger.error(_('Specified Power Source info backend: \'$name\' '
            'is not available on your machine!'))
        return None
    return backend()

def getPowerSourceActionBackend(name):
    backend = None
    if name == 'smapi':
        backend = TpSmapi
    elif name == 'acpi':
        backend = ThinkpadAcpiBatteryController
    else:
        raise ValueError(_('Unknown Power Source Action backend: $name'))
    if not backend.isAvailable():
        logger.error(_('Specified Power Source action backend: \'$name\' '
            'is not available on your machine!'))
        return None
    return backend()
        
def battery(options, config):
    # common option
    if options.action == 'smapi' and options.info == 'smapi':
        batteryController = batteryInfo = \
            getPowerSourceActionBackend(options.action)
    else:
        batteryController = getPowerSourceActionBackend(options.action)
        batteryInfo = getPowerSourceInfoBackend(options.info)
        
    if batteryController is None or batteryInfo is None:
        return

    if options.battery_command in ['ST', 'st', 'start', 'startThreshold']:
        if options.level is not None:
            batteryController.setStartThreshold(options.battery, options.level)
        else:
            result = batteryController.getStartThreshold(options.battery)
            displayThreshhold(result)
    elif options.battery_command in ['SP', 'sp', 'stop', 'stopThreshold']:
        if options.level is not None:
            batteryController.setStopThreshold(options.battery, options.level)
        else:
            result = batteryController.getStopThreshold(options.battery)
            displayThreshhold(result)
    elif options.battery_command in ['IC', 'ic', 'inhibit', 'inhibitCharge']:
        if options.inhibit is not None:
            batteryController.setInhibitCharge(options.battery, \
                options.inhibit, options.min)
        else:
            result = batteryController.getInhibitCharge(options.battery)
            displayInhibit(*result)
    elif options.battery_command in ['FD', 'fd', 'forceDischarge']:
        if options.discharge is not None:
            batteryController.setForceDischarge(options.battery, \
                options.discharge, options.acbreak)
        else:
            result = batteryController.getForceDischarge(options.battery)
            displayForceDischarge(*result)
    elif options.battery_command in ['PS', 'ps', 'peakShiftState']:
        batteryController.setPeakShiftState(options.inhibit, options.min)
    elif options.battery_command == 'list':
        for battery in batteryInfo.getBatteries():
            if battery.isInstalled():
                print (battery, "\n")
    elif options.battery_command == 'balance':
        while(True):
            try:
                if not batteryController.balanceCharge(config, \
                    batteryInfo, options.chargeStrategy, \
                    options.dischargeStrategy):
                    break
            except (KeyboardInterrupt, SystemExit):
                break
            time.sleep(config['battery']['update_interval'])
        
def fan(options, config):
    if not ThinkpadAcpi.hasFan():
        print('No fan available')
    elif options.level is not None:
        ThinkpadAcpi.setFanSpeed(ThinkpadAcpi.getFanLevelInt(options.level))
    else:
        fanState = ThinkpadAcpi.getFanState()
        print (fanState['status'], \
            ThinkpadAcpi.getFanLevelStr(fanState['level']), \
            fanState['rpm'])
        
def getState(string):
    '''Booleanize on/off'''
    if string == 'on':
        return True
    elif string == 'off':
        return False
    else:
        return string
        
def led(options, config):
    if options.led is not None:
        if options.state is None:
            print('on' if ThinkpadAcpi.getLedState(options.led) else 'off')
        else:
            ThinkpadAcpi.setLedState(options.led, getState(options.state))
    else:
        print("\n".join(ThinkpadAcpi.getAvailableLeds()))
        
def ledType(string):
    if string is not None and string.isdigit():
        return int(string)
    return string
        
def rotate(options, config):
    if options.via_hook is not None:
        # TODO: get rid of this if possible to remain compositor agnostic
        xrandr_bug_fail_early(config)
    
    # acpi hook values
    if options.via_hook in ('00000001', '00005009'):
        options.direction = None
    elif options.via_hook in ('00000000', '0000500a'):
        options.direction = 'normal'
        
    if not options.daemonize:
        # Quickly abort if the call is by the hook and the user disabled the trigger.
        if options.via_hook is not None and \
            not config['trigger'].getboolean('enable_rotate'):
            sys.exit(0)
            
        rotate_cmdline(options, config)
    else:
        with DaemonContext(pidfile = PIDLockFile(options.pidfile), \
            stdout = sys.stdout, stderr = sys.stderr):
            rotate_daemon(options, config)
            
def _tpacpi_bat_cmdline_compat():
    '''Modify argv to make the cmdline api compatibile with tpacpi-bat'''
    if len(sys.argv) > 2 and 'battery' in sys.argv:
        i = 1
        args = ','.join(['--st', '--start', '--startThreshold'
                '--sp', '--stop', '--stopThreshold'
                '--ic', '--inhibit', '--inhibitCharge'
                '--fd', '--forceDischarge'
                '--ps', '--peakShiftState'])
        while i < len(sys.argv):
            if sys.argv[i] in args:
                sys.argv[i] = sys.argv[i].replace('--', '')
            i += 1
            
def _parse_cmdline():
    '''Parses the command line arguments.

    :return: Namespace with arguments.
    :rtype: Namespace
    '''
    
    _tpacpi_bat_cmdline_compat()
    
    parser = argparse.ArgumentParser(description=_('ThinkPad Scripts - '
                        'A collection of thinkpad utilility commands.'),
                        epilog=_('Consult various thinkpad* man pages for '
                        'more information about available commands.'))
                        #, version='x.y')

#    parser.add_argument('--backend', '-b', nargs='?', 
#                        choices=('proc', 'sys', 'auto'), default='auto',
#                        help=_('Most of the commands interact with '
#                        'hardware via thinkpad_acpi kernel module. This '
#                        'module exposes its functionality via proc and '
#                        'sys filesystems for userspace tools. By '
#                        'default use sys interface and fallback to proc'
#                        'if the needed functionality is not implemented'
#                        'via sys yet. Specify value to force to a '
#                        'specific fs.'))

    parser.add_argument('-v', dest='verbose', action='count',
                        help=_('Enable verbose output. Can be supplied '
                        'multiple times for even more verbosity.'))
    parser.add_argument('--via-hook', nargs='?',
                        help=_('Let the program know that it was called '
                        'using a system hook. End user should not use '
                        'this switch!'))
                        
    parser.add_argument('--version', action='version', 
                        version='%(prog)s ' + version)
    
    commands = parser.add_subparsers(title=_('Available commands'),
                                     description=_('ThinkPad specific '
                                     'commands that utilize hardware '
                                     'builtin functionality and expose '
                                     'it to userspace'), 
                                     help=_('commands'), dest='command')
    
    commands.add_parser('config', help=_('Display current configuration'))
    
    battery = commands.add_parser('battery', 
                                  description=_('''
Query and control battery parameters through various subcommands.

Depending on the '--action' and/or '--info' you choose, kernel version 
and hardware some or all of the battery commands may be unavailable. 
For a more or less accurate capability of tp_smapi please refer to: 
www.thinkwiki.org/wiki/Tp_smapi#Model-specific_status'''),
                                  help=_('Battery management'))
    
    battery.add_argument('--action', '-a', nargs='?', 
                         choices=('acpi', 'smapi'), default='acpi',
                         help=_('Backend method to execute actions: '
                         '\'acpi\' use direct ACPI calls (unoffical API), '
                         '\'smapi\' use tp_smapi kernel driver.'))
    
    battery.add_argument('--info', '-i', nargs='?', 
                         choices=('acpi', 'sysfs', 'smapi'), default='smapi',
                         help=_('Backend method to obtain power source info: '
                         '\'acpi\' use deprecated /proc/acpi/battery, '
                         '\'sysfs\' use /sys/class/power_supply, '
                         '\'smapi\' use tp_smapi kernel driver.'))
    
    # only to achieve compatibility with tpacpi-bat utility - NO OP
    battery_ops = battery.add_mutually_exclusive_group(required=False)
    battery_ops.add_argument('--get', '-g', action='store_const', 
                             dest='batop', const='get', 
                             help=_('Get value. No action argument - for '
                             'CLI compatibility with tpacpi-bat'))
    battery_ops.add_argument('--set', '-s', action='store_const', 
                             dest='batop', const='set', 
                             help=_('Set value. No action argument - for '
                             'CLI compatibility with tpacpi-bat'))
    
    battery_cmds = battery.add_subparsers(title=_('Available battery '
                                          'commands'), description=_('''
Exposes commands to query and control battery charging status:
start/stop charge thresholds, inhibit charge, force discharge,
peak shift state and charge balancing'''),
                                       help=_('Battery commands with aliases'),
                                       dest='battery_command')
    
    battery_st = battery_cmds.add_parser('ST', aliases=['st', 'start', 
                                        'startThreshold'],
                                         description=_('''
Control of battery charging thresholds (in percents of current full 
charge capacity).
Battery charging thresholds can be used to keep Li-Ion and Li-Polymer 
batteries partially charged, in order to increase their lifetime. 
This is useful since those batteries wear out much faster at very 
high or low charge levels. When using the tp_smapi driver it will also 
keep the thresholds across suspend-to-disk with AC disconnected - this 
isn't done automatically by the hardware.'''), 
                                         help=_('Start charge threshold'))
    
    battery_st.add_argument('battery', type=int, choices=range(0,3),
                            help=_('Battery selection: 1 for main, 2 for '
                            'secondary, 0 for either/both'))
                            
    battery_st.add_argument('level', nargs='?', type=int, 
                            choices=range(0, 100), default=None,
                            help=_('Charge level: 0 for default, 1-99 for '
                            'percentage. A value of 0 is translated to '
                            'the hardware default 96%%.'))
    
    battery_sp = battery_cmds.add_parser('SP', aliases=['sp', 'stop', 
                                         'stopThreshold'], 
                                         description=battery_st.description,
                                         help=_('Stop charge threshold'))
                                         
    battery_sp.add_argument('battery', type=int, choices=range(0,3),
                            help=_('Battery selection: 1 for main, 2 for '
                            'secondary, 0 for either/both'))
                            
    battery_sp.add_argument('level', nargs='?', type=int, 
                            choices=range(0, 100), default=None,
                            help=_('Charge level: 0 for default, 1-99 for '
                            'percentage. A value of 0 is translated to '
                            'the hardware default 100%%.'))
    
    battery_ic = battery_cmds.add_parser('IC', aliases=['ic', 'inhibit',
                                         'inhibitCharge'],
                                         description=_('''
Inhibiting battery charging for 'min' minutes (overriding thresholds).
Charge inhibiting can be used to reduce the power draw of the laptop, 
in order to use an under-spec power supply that can't handle the 
combined power draw of running and charging. This can be used to 
control which battery is charged when using an Ultrabay battery.'''),
                                         help=_('Inhibit Charge'))
                                         
    battery_ic.add_argument('battery', type=int, choices=range(0,3),
                            help=_('Battery selection: 1 for main, 2 for '
                            'secondary, 0 for either/both'))
                            
    battery_ic.add_argument('inhibit', nargs='?', type=int, 
                            choices=range(0, 2), default=None,
                            help=_('Charging inhibition: 1 to inhibit '
                            'charge, 0 for stop inhibiting charge '
                            '(not available via smapi)'))
                            
    battery_ic.add_argument('min', nargs='?', type=timerType(True), default=0,
                            help=_('Time in minutes: 1-720 or 0 for never, '
                            'or 65535 for forever.'))
                                         
    battery_fd = battery_cmds.add_parser('FD', aliases=['fd', 
                                         'forceDischarge'],
                                         description=_('''
Forcing battery discharging even if AC power available.
When AC is connected, forced discharging will automatically stop 
when battery is fully depleted - this is useful for calibration. 
Also, this attribute can be used to control which battery is discharged 
when both a system battery and an Ultrabay battery are connected.'''), 
                                         help=_('Force discharge'))
                                         
    battery_fd.add_argument('battery', type=int, choices=range(0,3),
                            help=_('Battery selection: 1 for main, 2 for '
                            'secondary, 0 for either/both'))
                            
    battery_fd.add_argument('discharge', nargs='?', type=int, choices=range(0, 2),
                            default=None, help=_('Force Discharge: 1 for force '
                            'discharge, 0 for stop forcing discharge'))
                            
    battery_fd.add_argument('acbreak', nargs='?', type=int, choices=range(0,2),
                            default=0, help=_('AC Detached stop: 1 to '
                            'stop forcing when AC is detached, 0 '
                            'to continue (not available via smapi)'))
                                         
    battery_ps = battery_cmds.add_parser('PS', aliases=['ps', 
                                         'peakShiftState'], 
                                         description=_('''
The concept of 'peak shift' is to switch temporarily electrical devices 
on battery during a power peak consumption period so as to unload the 
grid. This power management strategy is relevant for country like Japan, 
where these peak periods represent a risk of electrical black out.'''),
                                         help=_('Peak shift state'))
                                         
    battery_ps.add_argument('inhibit', type=int, choices=range(0, 2),
                            help=_('Charging inhibition: 1 to inhibit '
                            'charge, 0 for stop inhibiting charge'))
                            
    battery_ps.add_argument('min', nargs='?', type=timerType(False), default=0,
                            help=_('Time in minutes: 1-1440 or 0 for '
                            'never, or 65535 for forever.'))
                            
    battery_cmds.add_parser('list', help=_('List known batteries '
                            'with properties'))
                            
    battery_balancer = battery_cmds.add_parser('balance', description=_('''
Evenly distribute system power consumption among available batteries 
(if more than one battery is available) by querying and comparing 
battery charge and forcing discharge/inhibiting charge.'''),
                            help=_('Charge/discharge batteries evenly'))
                            
    battery_balancer.add_argument('chargeStrategy', nargs='?', 
                                  default='brackets', choices=('system',
                                  'leapfrog', 'chasing', 'brackets'),
                                  help=_('Strategy algorithm for '
                                  'selecting battery to charge'))
    
    battery_balancer.add_argument('dischargeStrategy', nargs='?', 
                                  default='leapfrog', choices=('system',
                                  'leapfrog', 'chasing'),
                                  help=_('Strategy algorithm for '
                                  'selecting battery to discharge'))
    
    # Indicate charging/discharing by orange/green led blinking
    
    beep = commands.add_parser('beep', help=_('Emit BIOS beep sound'))
    
    beep.add_argument('sound', type=int, choices=(0, 2, 3, 4, 5, 6, 7, 
                      9, 10, 12, 15, 16, 17), help=_('''Beep sound code:
	0 - stop a sound in progress (but use 17 to stop 16),
	2 - two beeps, pause, third beep ("low battery"),
	3 - single beep,
	4 - high, followed by low-pitched beep ("unable"),
	5 - single beep,
	6 - very high, followed by high-pitched beep ("AC/DC"),
	7 - high-pitched beep,
	9 - three short beeps,
	10 - very long beep,
	12 - low-pitched beep,
	15 - three high-pitched beeps repeating constantly, stop with 0,
	16 - one medium-pitched beep repeating constantly, stop with 17,
	17 - stop 16.
'''))

    fan = commands.add_parser('fan', help=_('Control Fan speed'))
    
    fan.add_argument('level', nargs='?', type=ThinkpadAcpi.getFanLevelInt,
                     choices=('auto', 'disengaged', 'full-speed', \
                     0, 1, 2, 3, 4, 5, 6, 7, 254, 255, 256),
                     help=_('Sets the fan speed (0=off, 1-7=normal, '
                     '254=disengaged, 255=auto, 256=full-speed)'))
    
    dock = commands.add_parser('dock', help=_('Toggle Docking station state'))
    
    dock.add_argument('state', nargs='?', choices=('on', 'off'),
                      help=_('Desired docking station state. '
                      'Toggle if not specified'))
                      
    inputs = commands.add_parser('input', help=_('Input devices'))
    
    inputs.add_argument('input',
                        choices=('touchpad', 'touchscreen', 'trackpoint'),
                        help=_('Input device'))
    inputs.add_argument('state', nargs='?', choices=('on', 'off'),
                        help=_('Desired input device state. '
                        'Toggle if not specified'))
                        
    led = commands.add_parser('led', help=_('Led state management'))
    
    led.add_argument('led', nargs='?', type=ledType,
                     choices=['power', 'orange:batt', 'green:batt',
                     'dock_active', 'bay_active', 'dock_batt',
                     'unknown_led', 'standby', 'dock_status1',
                     'dock_status2', 'unknown_led2', 'unknown_led3',
                     'thinkvantage', 'thinklight'] + list(range(0, 16)),
                     help=_('''The led to operate on. Leds can be accessed
by LED ID (numered 0-15, via depreceated procfs interface) or by name 
(via sysfs interface). Leave this argument empty to obtain list of LEDs 
by name currently available on your Thinkpad.

The LEDs are named (in LED ID order, from 0 to 12):
'power', 'orange:batt', 'green:batt',
'dock_active', 'bay_active', 'dock_batt',
'unknown_led', 'standby', 'dock_status1',
'dock_status2', 'unknown_led2', 'unknown_led3',
'thinkvantage'.

LEDs with IDs 13-15 may have no known name mapping (no spec in docs).

Additionally you may specify a value of 'thinklight' wich will operate 
on builtin ThinkLight or (on newer models) will enable keyboard backlight.

@see: http://www.thinkwiki.org/wiki/Table_of_thinkpad-acpi_LEDs for more 
information.
'''))

    led.add_argument('state', nargs='?',
                     choices=('on', 'off', 'blink', 'toggle'),
                     help=_('Desired led state. Read LED state if not '
                     'specified. The blink operation is available only '
                     'via procfs interface.'))
                        
    commands.add_parser('mutemic', help=_('Toggle Microphone state'))
    
    rotate = commands.add_parser('rotate', help=_('Rotate screen'))
    
    rotate.add_argument('--force-direction', action='store_true', 
                        help=_('Do not try to be smart. Actually rotate '
                        'in the direction given even it already is the '
                        'case'))
    rotate.add_argument('direction', nargs='?',
                        choices=('normal', 'none', 'left', 'ccw', 
                        'right', 'cw', 'flip', 'inverted', 'half', 
                        'tablet-normal', 'cycle', 'cycle-cw', 'cycle-ccw'),
                        help=_('Desired screen orientation'))
    rotate.add_argument('state', nargs='?', choices=('on', 'off'),
                        help=_('Forced input devices state after change'))
                        
    rotate.add_argument('--daemonize', '-d', action='store_true',
                        help=_('Daemonize screen rotation to take use of '
                        'HDAPS accelerometer for automatic rotation.'))
    rotate.add_argument('--pidfile', '-p', action='store', 
                        default='/var/run/thinkpad-rotated.pid',
                        help=_('Pid File location for daemon mode'))
                        
    commands.add_parser('scripts-config-migration', 
                        help=_('Migrate configuration'))
                        
    autocomplete(parser)
                          
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    return parser.parse_args()
    
if __name__ == '__main__':
    main()