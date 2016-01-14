#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright © 2014-2015 Martin Ueding <dev@martin-ueding.de>

import sys

print('This is running on:')
print(sys.version)
print()

from setuptools import setup, find_packages

import getversion

if __name__ == '__main__':
    packages = find_packages()

    setup(
        author="Martin Ueding",
        author_email="dev@martin-ueding.de",
        description="Scripts for ThinkPad®",
        license="GNU GPLv2+",
        classifiers=[
            "Environment :: Console",
            "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
            "Programming Language :: Python"
        ],
        name="thinkpad-scripts",
        packages=packages,
        entry_points={
            'console_scripts': [
                'thinkpad = tps.thinkpad:main',
                # legacy EPs - use 'thinkpad' for all purposes
                'thinkpad-config = tps.thinkpad:main_legacy',
                'thinkpad-dock = tps.thinkpad:main_legacy',
                'thinkpad-dock-hook = tps.thinkpad:main_legacy',
                'thinkpad-mutemic = tps.thinkpad:main_legacy',
                'thinkpad-rotate = tps.thinkpad:main_legacy',
                'thinkpad-rotate-hook = tps.thinkpad:main_legacy',
                'thinkpad-scripts-config-migration = tps.thinkpad:main_legacy',
                'thinkpad-touch = tps.thinkpad:main_legacy',
                'thinkpad-touchpad = tps.main_touchpad:main',
                'thinkpad-trackpoint = tps.main_trackpoint:main',
            ],
        },
        test_suite='tps.testsuite',
        #install_requires=[
        #],
        package_data={
            'tps': ['default.ini'],
            '' : ['system/*']
        },
        url="https://github.com/martin-ueding/thinkpad-scripts",
        download_url="http://martin-ueding.de/download/thinkpad-scripts/",
        version=getversion.get_version(),
    )
