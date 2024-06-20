"""AWG calibration measurer. 

This script allows for the automatic setting of values in AWG params and
subsequent autorunning of a Dexter routine. It does not perform any data
analysis; only obtains the data. 

If when running the measurer, it goes through all the amps very quickly, this
means that the AWG code had TCP messages queued and they were sent before they
could be deleted. To fix this, just restart the AWG code as well.

Note: this should be run in the pydexenv conda environment.
"""
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import time
import json
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex')
from networker import PyServer, TCPENUM
from client import PyClient
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QLabel)

class Measurer(QMainWindow):
    """Take measurements from the DAQ of the output optical power at different
    frequencies and use them to flatten the diffraction efficiency curve of 
    the AWG. Communicate with the DAQ by TCP.
    Take a measurement of the setpoint between every trial since the setpoint
    will probably vary over time.
    
    Arguments:
    f0    : bottom of frequency range, MHz
    f1    : top of frequency range, MHz
    nfreqs: number of frequencies to test in the range
    fset  : setpoint frequency, match the diffraction efficiency at this point, MHz
    pwr   : output power desired as a fraction of the setpoint
    tol   : tolerance to match to setpoint
    sleep : time to sleep betewen setting AWG freq and taking measurement, seconds
    """
    def __init__(self, awg, params, channel, amps, dexter_length):
        super().__init__()
        self.setWindowTitle("DE Measurer: AWG {}".format(awg))
        self.layout = QVBoxLayout()
        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        self.status_label = QLabel()
        self.layout.addWidget(self.status_label)

        self.status = 'checking'

        self.awg = awg
        self.params = os.path.abspath(params)
        self.channel = channel
        self.amps = amps
        self.amp = None # the last amp that was processed
        self.dexter_length = dexter_length

        if self.awg == 1:
            self.awgtcp = PyServer(host='', port=8623, name='AWG1') # AWG1 program runs separately
            self.awgrespond = PyClient(host='129.234.190.235', port=8626, name='AWG1 recv') # incoming from AWG
        elif self.awg == 2:
            self.awgtcp = PyServer(host='', port=8628, name='AWG2') # AWG2 program runs separately
            self.awgrespond = PyClient(host='129.234.190.233', port=8629, name='AWG2 recv') # incoming from AWG2
        else:
            self.awgtcp = PyServer(host='', port=8637, name='AWG3') # AWG3 program runs separately
            self.awgrespond = PyClient(host='129.234.190.234', port=8639, name='AWG3 recv') # incoming from AWG3
        self.awgtcp.start()
        self.awgtcp.priority_messages([[0,'clear_response_queue= '+'#'*1000]])

        self.awgrespond.start()
        


        self.s = PyServer(host='', port=8622) # server for DAQ
        self.s.start()
        self.dxs = PyServer(host='', port=8620) # server for DExTer
        self.dxs.start()

        self.send_params_to_AWG()
        self.get_num_segments()
        
        self.awgrespond.textin.connect(self.process_awg_response)
        self.process_next_amp()

    def set_status(self,status):
        print(status)
        every = 100 # add line breaks every 100 characters
        status = '\n'.join(status[i:i+every] for i in range(0, len(status), every))
        self.status_label.setText(status)

    def send_params_to_AWG(self):
        self.set_status('Loading AWG params {}'.format(self.params))
        self.awgtcp.force_add_message(0, 'AWG{} load='.format(self.awg)+self.params)

    def get_num_segments(self):
        with open(self.params) as f:
            params = json.load(f)
        self.num_segments = len(params['segments'])
        print('num_segments =',self.num_segments)

    def set_amps(self,amp):
        self.amp = amp
        segments_to_set = 'list(np.arange(2,{}-1,2))'.format(self.num_segments)
        self.set_status('Setting segments {} to amp {}'.format(segments_to_set,self.amp))

        data_template = [self.channel,0,'start_amp',amp,-1]
        msg = str([data_template,segments_to_set])
        self.awgtcp.force_add_message(0, 'set_multi_segment_data='+msg+'#'*2000)

    def save_daq_trace(self):
        save_dir = os.path.abspath('./AWG{} DAQ traces'.format(self.awg))
        trace_file = str(self.amp)+'.csv'
        self.set_status('Requesting DAQ save trace at {}'.format(os.path.join(save_dir, trace_file)))

        self.s.force_add_message(0, '{}=save_dir'.format(save_dir))
        self.s.force_add_message(0, '{}=trace_file'.format(trace_file))
        self.s.force_add_message(0, 'save trace')

    def trigger_dexter(self):
        """Sends a trigger to Dexter to run the sequence."""
        self.set_status('Triggering Dexter')
        self.dxs.force_add_message(TCPENUM['Run sequence'], 'run the sequence\n'+'0'*1600)

    def process_awg_response(self):
        """Triggered when the AWG has responded after it has finished 
        calculating a change to the AWG params."""
        self.set_status('AWG says go!')
        self.awgtcp.clear_queue()
        self.process_next_amp()

    def process_next_amp(self):
        """Triggered when the AWG responds to trigger Dexter and then save
        the DAQ trace."""
        if self.amp is not None: # at least one amp has been sent
            self.set_status('Sleeping for {} seconds'.format(self.dexter_length))
            time.sleep(self.dexter_length)
            
            self.trigger_dexter()

            self.set_status('Sleeping for {} seconds'.format(self.dexter_length))
            time.sleep(self.dexter_length)

            self.save_daq_trace()
        
        self.set_status('amps remaining = {}'.format(self.amps))
        try:
            self.amp = self.amps.pop()
        except IndexError: # all the amps have been processed
            self.set_status('All amps finished. Closing.')
            self.close()
        
        self.set_status('processing amp = {}'.format(self.amp))
        self.set_amps(self.amp)
        
if __name__ == "__main__":
    from random import shuffle

    awg = 3
    channel = 0
    # params = 'DE_params_AWG{}.awg'.format(awg)
    params = 'DE_params_AWG3_servo_AOM.awg'
    amps = list(np.linspace(0,1000,101))#[250,150,100]
    dexter_length = 5 # dexter length in seconds that is waited for the DAQ to aquire
    
    shuffle(amps)
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    m = Measurer(awg=awg, params=params, channel=channel, amps=amps, dexter_length=dexter_length)
    # o.s.textin.disconnect()
    # fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations\938_060422_aodcalibration'
    # o.t.load(fdir+r'\jump_static.txt')
    
    # from numpy.random import shuffle
    # fs = np.linspace(130, 200, 160)
    # # fs = np.delete(fs, np.array([154, 174, 152, 169, 155, 208, 140, 199, 173, 121, 189, 120])-120)
    # shuffle(fs)
    # fdir += r'\traces'
    # os.makedirs(fdir, exist_ok=True)
    # o.s.add_message(o.n, fdir+'=save_dir')
    # o.s.add_message(o.n, 'reset graph')
    # o.measure()
    # print('triggered AWG.')
    # time.sleep(0.3)
    # for f in fs:
    #     o.n = int(f)
    #     o.s.add_message(o.n, 'sets n') # sets the amplitude for reference
    #     o.s.add_message(o.n, 'sets n') # sets the amplitude for reference
    #     for j in range(10): 
    #         o.t.loadSeg([[0,15*j+i+1,"freqs_input_[MHz]",float(f),0] for i in range(15)])
    #     time.sleep(1.5)
    #     o.measure()
    #     o.s.add_message(o.n, '%.3fMHz.csv=trace_file'%f)
    #     time.sleep(1)
    #     o.s.add_message(o.n, 'save trace')
    # o.t.stop()
    m.show()
    app.exec()