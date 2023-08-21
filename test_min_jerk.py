from actions import ActionContainer

card_settings = {'active_channels':1,
                 'sample_rate_Hz':625000000,
                 'max_output_mV':100,
                 'number_of_segments':8,
                 'segment_min_samples':192,
                 'segment_step_samples':32
                 }
action_params = {'duration_ms' : 1,
                 'phase_behaviour' : 'manual',
                 'freq' : {'function' : 'static',
                           'start_freq_MHz': [100],
                           'start_phase' : [0]},
                 'amp' : {'function' : 'static',
                          'start_amp': [1]}}
action = ActionContainer(action_params,card_settings,None)

import matplotlib.pyplot as plt
import numpy as np

plt.style.use('default')

time = np.linspace(1e-3,2e-3,20)
freq = action.freq_sweep(start_freq_MHz=100,end_freq_MHz=101,hybridicity=0.9,start_phase=0,_time=time)
plt.plot(time,freq,'-',label='20 points')
# time = np.linspace(1e-3,2e-3,1000)
# freq = action.freq_sweep(start_freq_MHz=100,end_freq_MHz=101,hybridicity=0.,start_phase=0,_time=time)
# plt.plot(time,freq,'-',label='1000 points')
plt.xlabel('time (s)')
plt.ylabel('frequency (MHz)')
plt.legend()
plt.show()