import importlib
import actions
import matplotlib.pyplot as plt
import numpy as np

importlib.reload(actions)

card_settings = {'active_channels':1,
                 'sample_rate_Hz':625000000,
                 'max_output_mV':100,
                 'number_of_segments':8,
                 'segment_min_samples':192,
                 'segment_step_samples':32
                 }
action_params = {'duration_ms' : 10,
                 'phase_behaviour' : 'manual',
                 'freq' : {'function' : 'static',
                           'start_freq_MHz': [100],
                           'start_phase' : [0]},
                 'amp' : {'function' : 'static',
                          'start_amp': [1]}}

action = actions.ActionContainer(action_params,card_settings,None)

for hybridicity in [0,0.25,0.5,0.75,1]:
    time = action.time
    sweep = action.freq_sweep(100,101,hybridicity,0,time)
    plt.plot(time,sweep,label=hybridicity)
    # plt.axvline((0.5+hybridicity/2)*time[-1],c='k',linestyle='--',alpha=0.2)
    # plt.axvline((0.5-hybridicity/2)*time[-1],c='k',linestyle='--',alpha=0.2)
plt.legend(title='hybridicity')
plt.show()

# hybridicity = 0.6
# time = action.time
# sweep = action.freq_sweep(105,102,hybridicity,0,time)
# plt.plot(time,sweep,label=hybridicity)
# plt.axvline((0.5+hybridicity/2)*time[-1],c='k',linestyle='--',alpha=0.2)
# plt.axvline((0.5-hybridicity/2)*time[-1],c='k',linestyle='--',alpha=0.2)
# # plt.legend(title='hybridicity')
# plt.show()

# index = 0
# time = action.time
# amp = action.amp_approx_exp(1,-1,index,time)
# print(max(amp),min(amp))
# plt.plot(time,amp,label=index)
# plt.show()

index = 0
time = action.time
amp = action.amp_modulate(1,0.2,15,time)
print(max(amp),min(amp))
plt.plot(time,amp,label=index)
plt.show()