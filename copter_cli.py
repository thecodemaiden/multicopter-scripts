import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflie_manager import CrazyflieManager, ParameterRequest, ActionRequest, SetpointRequest

import sys
import random

logging.basicConfig(level=logging.WARNING)


logger = logging.getLogger('MAIN')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

# Initialize the low-level drivers (don't list the debug drivers)
cflib.crtp.init_drivers(enable_debug_driver=False)
callbackQ = None

def findCopterWithAddress(addr):
    logger.info('Scanning interfaces for Crazyflies...')
    available = cflib.crtp.scan_interfaces(addr) # TODO: variable address

    if len(available) == 0:
        return None

    logger.debug('Crazyflies found:')
    chosen = available[0]
    for i in available:
        logger.debug(i[0])
        if '125' in i[0]:
            chosen = i
    pe = CrazyflieManager(chosen[0], callbackQ)
    while not(pe.is_connected):
        time.sleep(0.1)
    return pe


        

