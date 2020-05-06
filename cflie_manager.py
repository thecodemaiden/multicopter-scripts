import logging
import logging.handlers
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie

from threading import Thread
import pdb


from queue import Queue
from queue import Empty as EmptyException



class ActionRequest(object):
    '''
          The callback should look like fn(cflie, request, status) where 
          cflie is the Crazyflie that completed the action,
          request is this ActionRequest object that was completed, and
          status is 0 for success, or some error code otherwise 
    '''
    def __init__(self, callback = None):
        super().__init__()
        self.cb = callback

    def complete(self, cflie, status = 0):
        # assume success :)
        if self.cb is not None:
            self.cb(cflie, self, status)

    def __repr__(self):
        if self.cb is None:
            cbString = '(no callback)'
        else:
            cbString = '(callback)'
        return 'ActionRequest{}'.format(cbString)

class SetpointRequest(ActionRequest):
    def __init__(self, thrust, pitch=0, roll=0, yaw=0, callback=None):
        super().__init__(callback)
        self.thrust = thrust
        self.pitch = pitch
        self.roll = roll
        self.yaw = yaw

    def __repr__(self):
        if self.cb is None:
            cbString = '(no callback)'
        else:
            cbString = '(callback)'
        return 'SetpointRequest{} \tPitch: {} \tRoll: {} \tYaw: {} \tThrust:{}'.format(
            cbString, self.pitch, self.roll, self.yaw, self.thrust)

class ParameterRequest(ActionRequest):
    def __init__(self, paramName, paramVal, callback=None):
        super().__init__(callback)
        self.name = paramName
        self.value = paramVal

    def __repr__(self):
        if self.cb is None:
            cbString = '(no callback)'
        else:
            cbString = '(callback)'

        return 'ParameterRequest{} \tName: {} \tValue: {}'.format(
            cbString, self.name, self.value)

class CrazyflieManager:

    def __init__(self, link_uri, callbackQueue = None):
        """ Initialize and run the example with the specified link_uri """
        # Create a Crazyflie object without specifying any cache dirs
        self._cf = Crazyflie()
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(logging.StreamHandler())
        self.logger.setLevel(logging.WARNING)

        # Connect some callbacks from the Crazyflie API
        self._cf.connected.add_callback(self._connected)
        self._cf.disconnected.add_callback(self._disconnected)
        self._cf.connection_failed.add_callback(self._connection_failed)
        self._cf.connection_lost.add_callback(self._connection_lost)

        self.logger.info('Connecting to %s' % link_uri)

        # Try to connect to the Crazyflie
        self._cf.open_link(link_uri)

        # Variable used to keep main loop occupied until disconnect
        self.is_connected = False

        self.params_set = {}
        self._willStop = False

        self._nextThrottle = 0 # TODO: next pitch/roll/yaw etc
        self._nextPitch = 0
        self._nextRoll = 0
        self._nextYaw = 0

        self._updateQueue = Queue()
        self._callbackQueue = callbackQueue
        self._currentTask = None

    # TODO: this should be a property
    def stop(self):
        self._willStop = True

    def isStopped(self):
        return self._willStop

    def addTask(self, task):
        if not isinstance(task, ActionRequest):
            raise RuntimeError('Should only put ActionRequests into the job queue')

        self._updateQueue.put(task)
        self.logger.debug("Added task {}".format(task))

    def isBusy(self):
        return (not self._updateQueue.empty()) and (self._currentTask is not None)

    def _connected(self, link_uri):
        """ This callback is called form the Crazyflie API when a Crazyflie
        has been connected and the TOCs have been downloaded."""
        self.logger.info('Connected to %s' % link_uri)
        self.is_connected = True
        p_toc = self._cf.param.toc.toc
        group = 'chirp'
        self.logger.debug('{}'.format(group))
        for param in sorted(p_toc[group].keys()):
            self.logger.debug('\t{}'.format(param))
        # register update callback for any parameter
        self.logger.debug('registering parameter callback')
        self._cf.param.add_update_callback(group=None, name=None,
                                           cb=self._param_callback)

        self.logger.debug('')
        Thread(target=self._main_loop).start()

    def _completeTask(self, task, status=0):
        if self._callbackQueue is None:
            task.complete(self, status)
        else:
            self._callbackQueue.put((self, task, status))

        self._updateQueue.task_done()
        self.logger.debug('Completed task {}'.format(task))
        if task == self._currentTask:
            self._currentTask = None
        elif self._currentTask is not None:
            # should we die?
            self.logger.error('Completed a task that was not next in queue!')
            
        

    def _main_loop(self):
        while not self._willStop:
            self.logger.debug("Current queue size is {}".format(self._updateQueue.qsize()))
            if self._currentTask is not None:
                self.logger.debug('Current task is {}'.format(self._currentTask))
            else:
                try:
                    self._currentTask = self._updateQueue.get_nowait()
                    # let's take care of the request
                    self.logger.debug('Popped a task: {}'.format(self._currentTask))
                    if isinstance(self._currentTask, ParameterRequest):
                        if not self._currentTask.name in self.params_set.keys():
                            self.params_set[self._currentTask.name] = None
                        self._cf.param.set_value(self._currentTask.name, str(self._currentTask.value))
                        #self.logger.debug("setting parameter {} to {}".format(self._currentTask.name, self._currentTask.value))
                    elif isinstance(self._currentTask, SetpointRequest):
                        # can be handled instantly
                        self._nextThrottle = self._currentTask.thrust
                        self._nextPitch = self._currentTask.pitch
                        self._nextRoll = self._currentTask.roll
                        self._nextYaw = self._currentTask.yaw
                        # TODO: XXX: make sure send_setpoint doesn't error
                        self._completeTask(self._currentTask)
                    else:
                        # assume it is some kind of ActionRequest
                        self._completeTask(self._currentTask)
                except EmptyException:
                    self._currentTask = None   
            # rpyt
            self._cf.commander.send_setpoint(self._nextRoll,self._nextPitch,self._nextYaw,self._nextThrottle)
            self._nextPitch = self._nextRoll = self._nextYaw = 0 # just little nudges for now
            time.sleep(0.05) # should be enough to keep the commander online
        # _willStop is true
        self._cf.close_link()
        

    def _param_callback(self, name, value):
        """Generic callback registered for all the groups"""
        if name in self.params_set.keys():
            self.params_set[name] = value
            self.logger.info('{} set to {}'.format(name, value))

        if (self._currentTask is not None):
            try:
                if (name == self._currentTask.name):
                    self._completeTask(self._currentTask)
            except AttributeError:
                self.logger.warn('Parameter request for {} made without task in queue!'.format(name))


    def _connection_failed(self, link_uri, msg):
        """Callback when connection initial connection fails (i.e no Crazyflie
        at the specified address)"""
        self.logger.error('Connection to %s failed: %s' % (link_uri, msg))
        self.is_connected = False

    def _connection_lost(self, link_uri, msg):
        """Callback when disconnected after a connection has been made (i.e
        Crazyflie moves out of range)"""
        self.logger.error('Connection to %s lost: %s' % (link_uri, msg))

    def _disconnected(self, link_uri):
        """Callback when the Crazyflie is disconnected (called in all cases)"""
        self.logger.warning('Disconnected from %s' % link_uri)
        self.is_connected = False
        self._willStop = True