import json
import numpy as np
from random import shuffle
from copy import deepcopy

frequencies = np.linspace(85,135,301)
# frequencies = np.linspace(160,200,11)
shuffle(frequencies)

with open(r"DE_base_params_AWG3.awg") as f:
    params = json.load(f)
    # print(d)
    
params['card_settings']['number_of_segments'] = 1024 # so that we don't run out of segments

for amp_adjuster in params['amp_adjuster_settings']:
    amp_adjuster['enabled'] = False
    amp_adjuster['non_adjusted_amp_mV'] = 1
    
base_static_segment = params['segments'][0]

channel = 0
amp_mV = 132
duration_ms = 0.5

# amps and freqs used to tell when the sequence is starting (should be near full amp)
calibration_freq = 110
calibration_amp = 380

# amp used when the AWG is waiting between segments
off_freq = 110
off_amp = 0

static_segments = []

base_static_segment['duration_ms'] = duration_ms

segment = deepcopy(base_static_segment)
segment['Ch0']['freq']['start_freq_MHz'] = [calibration_freq]
segment['Ch0']['amp']['start_amp'] = [calibration_amp]
static_segments.append(segment)

segment = deepcopy(base_static_segment)
segment['Ch0']['freq']['start_freq_MHz'] = [calibration_freq]
segment['Ch0']['amp']['start_amp'] = [0]
static_segments.append(segment)

for frequency in frequencies:
    segment = deepcopy(base_static_segment)
    segment['Ch{}'.format(channel)]['freq']['start_freq_MHz'] = [frequency]
    segment['Ch{}'.format(channel)]['amp']['start_amp'] = [amp_mV]
    static_segments.append(segment)
    
    segment = deepcopy(base_static_segment)
    segment['Ch{}'.format(channel)]['freq']['start_freq_MHz'] = [frequency]
    segment['Ch{}'.format(channel)]['amp']['start_amp'] = [0]
    static_segments.append(segment)

segment = deepcopy(base_static_segment)
segment['duration_ms'] = 0.001
segment['Ch0']['freq']['start_freq_MHz'] = [off_freq]
segment['Ch0']['amp']['start_amp'] = [off_amp]
static_segments.append(segment)

params['segments'] = static_segments

base_step = params['steps'][0]

steps = []
for i, segment in enumerate(static_segments):
    step = deepcopy(base_step)
    step['segment'] = i
    step['after_step'] = 'continue'
    steps.append(step)
steps[-1]['after_step'] = 'loop_until_trigger'
params['steps'] = steps

with open(r"DE_params_AWG3.awg", 'w', encoding='utf-8') as f:
    json.dump(params, f, ensure_ascii=False, indent=4)
    
np.savetxt(r"DE_freqs_AWG3.csv", frequencies, delimiter=",")
