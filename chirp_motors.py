# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2014 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.
"""
Simple example that connects to the first Crazyflie found, triggers
reading of all the parameters and displays their values. It then modifies
one parameter and reads back it's value. Finally it disconnects.
"""
import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie

# Only output errors from the logging framework
logging.basicConfig(level=logging.ERROR)



class MotorController:
    """
    Simple logging example class that logs the Stabilizer from a supplied
    link uri and disconnects after 5s.
    """

    def __init__(self, link_uri):
        """ Initialize and run the example with the specified link_uri """

        # Create a Crazyflie object without specifying any cache dirs
        self._cf = Crazyflie()

        # Connect some callbacks from the Crazyflie API
        self._cf.connected.add_callback(self._connected)
        self._cf.disconnected.add_callback(self._disconnected)
        self._cf.connection_failed.add_callback(self._connection_failed)
        self._cf.connection_lost.add_callback(self._connection_lost)

        print('Connecting to %s' % link_uri)

        # Try to connect to the Crazyflie
        self._cf.open_link(link_uri)

        # Variable used to keep main loop occupied until disconnect
        self.is_connected = False

        self._param_check_list = []
        self._param_groups = []
        #self.params_set = {'mtrsnd.freq1':[0,f1], 'mtrsnd.freq2':[0,f2], 
        #        'mtrsnd.freq3':[0,f3], 'mtrsnd.freq4':[0,f4], 
        #        'mtrsnd.enable':[0,1]}


    def _connected(self, link_uri):
        """ This callback is called form the Crazyflie API when a Crazyflie
        has been connected and the TOCs have been downloaded."""
        print('Connected to %s' % link_uri)
        self.is_connected = True
        p_toc = self._cf.param.toc.toc
        group = 'mtrsnd'
        print('{}'.format(group))
        for param in sorted(p_toc[group].keys()):
            print('\t{}'.format(param))
            self._param_check_list.append('{0}.{1}'.format(group, param))
        self._param_groups.append('{}'.format(group))
        # register update callback for mtrsnd
        print('registering callback')
        self._cf.param.add_update_callback(group='mtrsnd', name=None,
                                           cb=self._param_callback)

        print('')

    def try_update(self):
        # set each of the desired params
        finished = True
        for p,opts in self.params_set.items():
            if str(opts[0]) != str(opts[1]):
                finished = False
                print('{} is {}, setting to {}'.format(p, opts[0], opts[1]))
                self._cf.param.set_value(p, str(opts[1]))
                break
        return finished

    def _param_callback(self, name, value):
        """Generic callback registered for all the groups"""
        if name in self.params_set.keys():
            self.params_set[name][0] = value
        print('{} set to {}'.format(name, value))



    def _connection_failed(self, link_uri, msg):
        """Callback when connection initial connection fails (i.e no Crazyflie
        at the specified address)"""
        print('Connection to %s failed: %s' % (link_uri, msg))
        self.is_connected = False

    def _connection_lost(self, link_uri, msg):
        """Callback when disconnected after a connection has been made (i.e
        Crazyflie moves out of range)"""
        print('Connection to %s lost: %s' % (link_uri, msg))

    def _disconnected(self, link_uri):
        """Callback when the Crazyflie is disconnected (called in all cases)"""
        print('Disconnected from %s' % link_uri)
        self.is_connected = False


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        addr = int(sys.argv[1],16)
    else:
        addr = None
    # Initialize the low-level drivers (don't list the debug drivers)
    cflib.crtp.init_drivers(enable_debug_driver=False)
    # Scan for Crazyflies and use the first one found
    print('Scanning interfaces for Crazyflies...')
    available = cflib.crtp.scan_interfaces(addr)
    print('Crazyflies found:')
    for i in available:
        print(i[0])

    cNames = [x[0] for x in available]
    trueName = [n for n in cNames if "80" in n]
    if len(trueName) > 0:
        pe = MotorController(trueName[0])
        pe.params_set = {'mtrsnd.freq':[0,27000], 'mtrsnd.chirpF1':[0, 15000],
                'mtrsnd.chirpF2':[0, 16000]} 
        while (not pe.is_connected):
            time.sleep(0.5)
        # Keep trying to set the values
        done = False
        while not done:
            time.sleep(1) 
            if pe.is_connected:
                done = pe.try_update()
            else:
                sys.exit(1)
        print('Start')
        time.sleep(1)

        pause_time = 2.0
        now = time.time()
        chirped = False
        thrust = 48000
        done = False
        for i in range(10):
            pe._cf.commander.send_setpoint(0,0,0,0);
            pe.try_update()
            time.sleep(0.05)

        # spin up the motors
        while not done:
            if not chirped:
                if time.time()-now > pause_time:
                    chirped = True
                    pe.params_set = {'mtrsnd.goChirp': [0,1]}
                    pe.try_update()
            pe._cf.commander.send_setpoint(0,0,0,thrust);
            time.sleep(0.05)
            done = time.time()-now > 2*pause_time

        # chirped and waited: done
        pe._cf.close_link()
    else:
        print('No Crazyflies found, cannot run example')
