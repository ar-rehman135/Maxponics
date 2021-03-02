# coding=utf-8
#
#  difference.py - Calculate difference between two measurements
#
#  Copyright (C) 2015-2020 Kyle T. Gabriel <mycodo@kylegabriel.com>
#
#  This file is part of Mycodo
#
#  Mycodo is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mycodo is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mycodo. If not, see <http://www.gnu.org/licenses/>.
#
#  Contact at kylegabriel.com
#
import threading
import time

from flask_babel import lazy_gettext

from mycodo.controllers.base_controller import AbstractController
from mycodo.databases.models import CustomController
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.influx import write_influxdb_value


def constraints_pass_positive_value(mod_controller, value):
    """
    Check if the user controller is acceptable
    :param mod_controller: SQL object with user-saved Input options
    :param value: float or int
    :return: tuple: (bool, list of strings)
    """
    errors = []
    all_passed = True
    # Ensure value is positive
    if value <= 0:
        all_passed = False
        errors.append("Must be a positive value")
    return all_passed, errors, mod_controller


measurements_dict = {
    0: {
        'measurement': '',
        'unit': '',
        'name': 'Difference'
    }
}

FUNCTION_INFORMATION = {
    'function_name_unique': 'calculate_difference',
    'function_name': 'Difference',
    'measurements_dict': measurements_dict,
    'enable_channel_unit_select': True,

    'message': 'This function acquires 2 measurements, calculates the difference, and stores the '
               'resulting value as the selected measurement and unit.',

    'options_enabled': [
        'measurements_select_measurement_unit',
        'custom_options'
    ],

    'custom_options': [
        {
            'id': 'period',
            'type': 'float',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': lazy_gettext('The duration (seconds) between measurements or actions')
        },
        {
            'id': 'select_measurement_a',
            'type': 'select_measurement',
            'default_value': '',
            'options_select': [
                'Input',
                'Math',
                'Function'
            ],
            'name': 'Measurement A',
            'phrase': 'Measurement A'
        },
        {
            'id': 'measurement_max_age_a',
            'type': 'integer',
            'default_value': 360,
            'required': True,
            'name': 'Measurement A Max Age',
            'phrase': 'The maximum allowed age of Measurement A'
        },
        {
            'id': 'select_measurement_b',
            'type': 'select_measurement',
            'default_value': '',
            'options_select': [
                'Input',
                'Math',
                'Function'
            ],
            'name': 'Measurement B',
            'phrase': 'Measurement B'
        },
        {
            'id': 'measurement_max_age_b',
            'type': 'integer',
            'default_value': 360,
            'required': True,
            'name': 'Measurement B Max Age',
            'phrase': 'The maximum allowed age of Measurement B'
        },
        {
            'id': 'difference_reverse_order',
            'type': 'bool',
            'default_value': False,
            'required': True,
            'name': 'Reverse Order',
            'phrase': 'Reverse the order in the calculation'
        },
        {
            'id': 'difference_absolute',
            'type': 'bool',
            'default_value': False,
            'required': True,
            'name': 'Absolute Difference',
            'phrase': 'Return the absolute value of the difference'
        }
    ]
}


class CustomModule(AbstractController, threading.Thread):
    """
    Class to operate custom controller
    """
    def __init__(self, ready, unique_id, testing=False):
        threading.Thread.__init__(self)
        super(CustomModule, self).__init__(ready, unique_id=unique_id, name=__name__)

        self.unique_id = unique_id
        self.log_level_debug = None
        self.timer_loop = time.time()

        self.control = DaemonControl()

        # Initialize custom options
        self.period = None
        self.select_measurement_a_device_id = None
        self.select_measurement_a_measurement_id = None
        self.measurement_max_age_a = None
        self.select_measurement_b_device_id = None
        self.select_measurement_b_measurement_id = None
        self.measurement_max_age_b = None
        self.difference_reverse_order = None
        self.difference_absolute = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

    def initialize_variables(self):
        controller = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.log_level_debug = controller.log_level_debug
        self.set_log_level_debug(self.log_level_debug)

        self.logger.debug(
            "Custom controller started with options: "
            "{}, {}, {}, {}, {}, {}".format(
                self.select_measurement_a_device_id,
                self.select_measurement_a_measurement_id,
                self.measurement_max_age_a,
                self.select_measurement_a_device_id,
                self.select_measurement_a_measurement_id,
                self.measurement_max_age_a))

    def loop(self):
        if self.timer_loop < time.time():
            while self.timer_loop < time.time():
                self.timer_loop += self.period

            last_measurement_a = self.get_last_measurement(
                self.select_measurement_a_device_id,
                self.select_measurement_a_measurement_id,
                max_age=self.measurement_max_age_a)

            if last_measurement_a:
                self.logger.debug(
                    "Most recent timestamp and measurement for "
                    "select_measurement_a: {timestamp}, {meas}".format(
                        timestamp=last_measurement_a[0],
                        meas=last_measurement_a[1]))
            else:
                self.logger.debug(
                    "Could not find a measurement in the database for "
                    "select_measurement_a in the past {} seconds".format(
                        self.measurement_max_age_a))

            last_measurement_b = self.get_last_measurement(
                self.select_measurement_b_device_id,
                self.select_measurement_b_measurement_id,
                max_age=self.measurement_max_age_b)

            if last_measurement_b:
                self.logger.debug(
                    "Most recent timestamp and measurement for "
                    "select_measurement_b: {timestamp}, {meas}".format(
                        timestamp=last_measurement_b[0],
                        meas=last_measurement_b[1]))
            else:
                self.logger.debug(
                    "Could not find a measurement in the database for "
                    "select_measurement_b in the past {} seconds".format(
                        self.measurement_max_age_b))

            if last_measurement_a and last_measurement_b:
                if self.difference_reverse_order:
                    difference = last_measurement_b - last_measurement_a
                else:
                    difference = last_measurement_a -last_measurement_b
                if self.difference_absolute:
                    difference = abs(difference)

                self.logger.debug("Output: {}".format(difference))

                write_influxdb_value(
                    self.unique_id,
                    self.channels_measurement[0].unit,
                    value=difference,
                    measure=self.channels_measurement[0].measurement,
                    channel=0)
