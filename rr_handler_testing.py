import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import matplotlib.pyplot as plt
import numpy as np

from gui import main

fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations'
filename = fdir + r'\814_H_calFile_17.02.2022_0=0.txt'

settings = {'enabled':True,
            'non_adjusted_amp_mV':100,
            'filename':filename,
            'freq_limit_1_MHz':85,
            'freq_limit_2_MHz':110,
            'amp_limit_1':0,
            'amp_limit_2':1}

aa = main.AmpAdjuster2D(settings)

card_settings = {'active_channels':1,
                    'sample_rate_Hz':1024*10**6,
                    'max_output_mV':282,
                    'number_of_segments':8,
                    'segment_min_samples':192,
                    'segment_step_samples':32
                    }
action_params = {'duration_ms' : 0.04,
                    'phase_behaviour' : 'optimise',
                    'freq' : {'function' : 'static',
                            'start_freq_MHz': [102,99,96,93],
                            'start_phase' : [0,0,0,0]},
                    'amp' : {'function' : 'static',
                            'start_amp': [0.3]*4}}

action = main.ActionContainer(action_params,card_settings,aa)
action.freq_params['start_phase'] = phases
# action.set_start_phase() # adds a global phase but otherwise the same
action.calculate()
data_new = action.data

plt.plot(data_old/2**15*282)
plt.plot(data_new)
plt.show()
print('The same, just new is displaced by 1 sample, as expected')

sys.path.pop()

#%%

plt.figure()
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg')
from spcm_home_functions import static
from spcm_home_functions import adjuster, phase_minimise
from spcm_home_functions import load_calibration

phases = phase_minimise([102],10,1024,[0.3])

cal = load_calibration(r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations\814_H_calFile_17.02.2022_0=0.txt', np.linspace(85,110,100), np.linspace(0,1,200))
data_old = static(np.array([102])*10**6,1,1,0.04,150,[0.3],phases,False,True,1024*10**6,0.329,cal)

sys.path.pop()

#%%
sys.path.append(r'Z:\Tweezer\Code\Python 3.9\awg')
from gui import main

fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations'
filename = fdir + r'\814_H_calFile_17.02.2022_0=0.txt'

settings = {'enabled':True,
            'non_adjusted_amp_mV':100,
            'filename':filename,
            'freq_limit_1_MHz':85,
            'freq_limit_2_MHz':110,
            'amp_limit_1':0,
            'amp_limit_2':1}

aa = main.AmpAdjuster2D(settings)

card_settings = {'active_channels':1,
                    'sample_rate_Hz':1024*10**6,
                    'max_output_mV':282,
                    'number_of_segments':8,
                    'segment_min_samples':192,
                    'segment_step_samples':32
                    }
action_params = {'duration_ms' : 0.04,
                    'phase_behaviour' : 'optimise',
                    'freq' : {'function' : 'static',
                            'start_freq_MHz': [102],
                            'start_phase' : [0,0,0,0]},
                    'amp' : {'function' : 'static',
                            'start_amp': [0.3]}}
action = main.ActionContainer(action_params,card_settings,aa)
action.freq_params['start_phase'] = phases
# action.set_start_phase() # adds a global phase but otherwise the same
action.calculate()
data_new = action.data

plt.plot(data_old/2**15*282)
plt.plot(data_new)
plt.show()
print('The same, just new is displaced by 1 sample, as expected')

sys.path.pop()
# sys.path.pop()