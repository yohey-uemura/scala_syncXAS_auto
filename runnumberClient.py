import sys, os, string, io, glob, re, yaml, math, time, shutil, queue
from itertools import count
import numpy as np
import pandas as pd
import subprocess as sub
from silx.gui.qt import QObject, QThread, QTimer, pyqtSignal as Signal, pyqtSlot as Slot

try:
    import dbpy
    import stpy
except:
    print ('Failed to load dbpy/stpy')
    sys.exit()

class Worker(QThread):
    data_queued = Signal()
    message = Signal(str)
    new_data = Signal(list,list,list)
    HOMEDIR = os.environ['HOME']
    PYDIR = HOMEDIR+'/python'
    PROGRAMDIR = PYDIR+'/py_SyncDAQ_autoXAS_CC_dev'
    confdir = PROGRAMDIR+'/Event_Conf'

    def __init__(self, BL, rstart, r_end, stop_after=0, parent=None):
        super().__init__(parent)
        self.BL = BL
        self.runnumber = rstart
        self.runnumber_max = r_end
        self.stop_after = stop_after

    def run(self):
        while self.runnumber < self.runnumber_max:
            _runnumber = dbpy.read_runnumber_newest(self.BL)
            if _runnumber > self.runnumber:
                self.message.emit('process')
                #self.data_queued.emit()
                #print (self.runnumber)
                print (" >>>>> Make Taglist run:{self.runnumber}<<<<<")
                try:
                    taglist_all = []
                    filterlist = self.confdir + '/' + 'FEL_openshutter_beamon.txt'
                    args = ['MakeTagList', '-r', str(self.runnumber), '-b', str(self.BL), '-inp', filterlist]
                    P_MkTagList = sub.Popen(args, stdout=sub.PIPE)
                    stdout, stderror = P_MkTagList.communicate()
                    for term in io.StringIO(stdout.decode('utf-8')):
                        if re.match(r'^\d+$', term.rstrip()):
                            taglist_all.append(int(term.rstrip()))

                    taglist_laseron = []
                    filterlist = self.confdir + '/' + 'FEL_LH1_openshutter_beamon.txt'
                    args = ['MakeTagList', '-r', str(self.runnumber), '-b', str(self.BL), '-inp', filterlist]
                    P_MkTagList = sub.Popen(args, stdout=sub.PIPE)
                    stdout, stderror = P_MkTagList.communicate()
                    for term in io.StringIO(stdout.decode('utf-8')):
                        if re.match(r'^\d+$', term.rstrip()):
                            taglist_laseron.append(int(term.rstrip()))

                    taglist_laseroff = [x for x in taglist_all if not x in taglist_laseron]
                    #print (taglist_all)
                    self.new_data.emit(taglist_all,taglist_laseron,taglist_laseroff)

                except Exception as e:
                    print (e)
                    return
                
                self.runnumber = self.runnumber+1
        self.message.emit('end')
            

class QBridgeClient(QObject):
    worker = None
    _dequeuing = False
    stopped = Signal()


    def __init__(self, BL, rstart, r_end, parent=None):
        super().__init__(parent)
        self.BL = BL
        self.rstart = rstart
        self.r_end = r_end


    def set_endpoint(self, rstart, r_end):
        self.rstart = rstart
        self.r_end = r_end

    def start(self, stop_after=0):
        """Start receiving data

        Connect to the ``new_data`` signal to handle incoming data.

        If stop_after > 0, it will automatically stop once N trains have been
        received. Otherwise, it continues until ``.stop()`` is called.
        """
        if self.worker is not None:
            raise RuntimeError("Client is already running")
        self.worker = worker = Worker(
            self.BL,self.rstart, self.r_end,
            stop_after=stop_after, parent=self,
        )
        # worker.data_queued.connect(self._dequeue_one)
        worker.finished.connect(self._worker_finished)
        worker.start()

    @property
    def is_active(self):
        return self.worker is not None

    # Sending received data as signals from the thread causes issues if they
    # are emitted faster than they are processed. This mechanism uses a bounded
    # queue to limit how much data is buffered, and uses QTimer to pull data
    # out of the queue and turn it into signals in cooperation with the event
    # loop. User code should be able to connect to the new_data signal without
    # knowing about this.
    # @Slot()
    # def _start_dequeueing(self):
    #     if not self._dequeuing:
    #         self._dequeuing = True
    #        QTimer.singleShot(0, self._dequeue_one)

    def stop(self):
        """Stop receiving data"""
        if self.worker is None:
            return
        else:
            self.worker.runnumber = self.r_end + 1

    def _worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.stopped.emit()
