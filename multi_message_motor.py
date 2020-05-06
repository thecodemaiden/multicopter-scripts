import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflie_manager import CrazyflieManager, ParameterRequest, ActionRequest, SetpointRequest

from math import floor, ceil

from queue import Queue
from queue import Empty as EmptyException

import sys
import random


MAX_THRUST = 2**16 -1

logging.basicConfig(level=logging.WARNING)


logger = logging.getLogger('MAIN')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.WARNING)

# Initialize the low-level drivers (don't list the debug drivers)
cflib.crtp.init_drivers(enable_debug_driver=False)

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
    return pe

def initChirpParams(cflie):
    cflie.addTask(SetpointRequest(0))
    cflie.addTask(ParameterRequest('chirp.center', cflie.centerF))
    cflie.addTask(ParameterRequest('chirp.slope', 1500))
    cflie.addTask(ParameterRequest('chirp.length', 750, startNextMessage))
    cflie.doneAt = 0
# TODO: check the status
# TODO: attach extra data to the request for better cc

MSG_WAIT = 10.0

def startNextMessage(cflie, req, status):
 
    # now prepare to send a message
    cflie.addTask(SetpointRequest(cflie.defaultThrust))
    msg = cflie.msgList[cflie.msgNum]
    cflie.msgNum += 1
    logger.info('Transmitting {}'.format(msg))
    # update the message parameter
    cflie.addTask(ParameterRequest('chirp.message', msg))
    cflie.doneAt = time.time() +  MSG_WAIT
    cflie.addTask(ParameterRequest('chirp.goChirp', 1, messageStarted))


def messageStarted(cflie, req, status):
    while (time.time() < cflie.doneAt):
        time.sleep(0.5)
    logger.info('Message completed')

    time.sleep(2.0+random.uniform(0,2)) # separate the messages randomly in time

    if (cflie.msgNum >= len(cflie.msgList)):
        cflie.addTask(SetpointRequest(thrust=0, callback=allTasksComplete)) 
    else:
        cflie.addTask(ActionRequest(startNextMessage))

def allTasksComplete(cflie, req, status):
    time.sleep(1.0)
    cflie.stop()

nChirping = 4
copterAddresses = [0xe7e7e7e7e4, 0xe7e7e7e7e6, 0xe7e7e7e7e7, 0xe7e7e7e7e9]
centerFs = [23250, 22000, 20750, 19500]
random.shuffle(centerFs)

#copterAddresses = [ 0xe7e7e7e7e7, 0xe7e7e7e7e6]
#centerFs = [22000]*2
callbackQ =  None#Queue()
nonChirpingCopters = []
chirpingCopters = []

#[6553, 16383 ,32767 ,49151 ,58981]

chirpThrust = ceil(0.5*MAX_THRUST)
nonchirpThrust = floor(0.5*MAX_THRUST)

# let's do 20 msgs for the simultaneous test, drawn from the 50 in msgList
msgList = [108, 167, 183, 134, 28, 158, 32, 34, 25, 35, 42, 48, 78, 77, 53, 
        61, 214, 168, 132, 44, 50, 19, 213, 164, 129, 73, 39, 142, 225, 229, 
        59, 89, 17, 152, 224, 217, 221, 136, 248, 83, 246, 163, 186, 75, 145,
        62, 111, 174, 124, 70]

def chooseMessages(n):
    return random.sample(msgList, n)



#msgList = [104, 71]




def allConnected():
    flag = True
    for cf in nonChirpingCopters+chirpingCopters:
        if not cf.is_connected:
            flag = False
            break
    return flag

def anyConnected():
    flag = False
    for cf in nonChirpingCopters+chirpingCopters:
        if cf.is_connected:
            flag = True
            break
    return flag

'''
try:
    chirpDc = float(input('Chirping duty cycle: '))
    chirpThrust = ceil(chirpDc*MAX_THRUST)
except ValueError:
    print('Defaulting to 50% duty cycle')
    chirpThrust = ceil(0.5*MAX_THRUST)
except KeyboardInterrupt:
    sys.exit(0)

try:
    nChirping = int(input('Number of chirping copters: '))
except ValueError:
    nChirping = len(copterAddresses)
    print('Defaulting to {}'.format(nChirping))
except KeyboardInterrupt:
    sys.exit(0)
'''

for addr in copterAddresses:
    cf = None
    while cf is None: #failure is no longer an option
        cf = findCopterWithAddress(addr)
        time.sleep(0.1)
    
    cf.msgNum = 0
    if (len(chirpingCopters) < nChirping):
        idx = len(chirpingCopters)
        chirpingCopters.append(cf)
        chosenMsgs = chooseMessages(5)
        cf.msgList = chosenMsgs
        cf.defaultThrust = chirpThrust
        freq = centerFs[idx]
        cf.centerF = freq
        print('Copter {} has frequency {},  messages: {}'.format(idx, freq, chosenMsgs))
    else:
        nonChirpingCopters.append(cf)
        cf.msgList = []
        cf.defaultThrust = nonchirpThrust
    

while not allConnected():
    time.sleep(0.5)

for cf in nonChirpingCopters:
    cf.addTask(SetpointRequest(cf.defaultThrust))

for cf in chirpingCopters:
    initChirpParams(cf)

# TODO: make a callback queue to receive back from copter threads
busy = True
while busy:
    busy = False
    try:
        # (copter, task, status)
        taskCompletion = callbackQ.get(timeout=0.5)
        busy = True
        (cflie, task, status) = taskCompletion
        task.complete(cflie, status)
        callbackQ.task_done()
    except (EmptyException, AttributeError, KeyboardInterrupt) as e: # attribute error if we have no main thread callback queue
        if isinstance(e, KeyboardInterrupt):
            sys.exit(2)
        if isinstance(e, AttributeError):
            time.sleep(0.5)
        # nothing left to process, wait for crazyflies to disconnect
        busy = anyConnected()
        # check that all the chirping copters are done, and if so, turn off the non chirping copters
        nDone = 0
        for cf in chirpingCopters:
            if not cf.is_connected:
                nDone += 1
        if nDone == len(chirpingCopters):
            for cf in nonChirpingCopters:
                cf.stop()
        

