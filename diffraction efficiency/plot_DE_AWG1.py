import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib import cm

from scipy.fft import fft, ifft
plt.close('all')
plt.style.use('default')

#%%
freqs_df = pd.read_csv('AWG1 DAQ traces/DE_freqs_AWG1.csv',names=['frequency (MHz)'])

DAQ_channel = ' Dev4/ai0'

segment_time = 0.0005 # length of each segment
buffer_time = 0.0001 # amount that should be discarded from the beginning/end of each segment

DAQ_file_dir = './AWG1 DAQ traces'
DAQ_file_names = [f for f in os.listdir(DAQ_file_dir) if os.path.isfile(os.path.join(DAQ_file_dir, f))]

for file_name in DAQ_file_names:
    try:
        amp_mV = float(file_name.rsplit('.',1)[0])
    except ValueError:
        continue
    print(file_name)
    file_path = os.path.join(DAQ_file_dir, file_name)
    DAQ_df = pd.read_csv(file_path,skiprows=2)
    
    plt.figure()
    plt.title(file_name)
    plt.plot(DAQ_df['# Time (s)'],DAQ_df[DAQ_channel])
    plt.xlim(0,0.110)
    plt.ylim(0,4.2)
    
    
    start_cutoff_voltage = 3
    start_index = DAQ_df[DAQ_df[DAQ_channel]>start_cutoff_voltage].index[0]
    start_time = DAQ_df['# Time (s)'][start_index]
    
    amplitudes = []
    
    time = start_time + buffer_time
    
    calibration_voltage = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
    plt.scatter([time],[calibration_voltage],c='C2')
    time += segment_time*2
    
    for freq in freqs_df['frequency (MHz)']:
        amplitude = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
        plt.scatter([time],[amplitude],c='C1')
        amplitudes.append(amplitude)
        time += segment_time*2
        
    amplitudes = np.array(amplitudes)/calibration_voltage
        
    # freqs_df[f'{amp_mV} mV'] = amplitudes
    freqs_df[amp_mV] = amplitudes
    plt.show()

freqs_df.sort_values(by=['frequency (MHz)'],inplace=True)
freqs_df = freqs_df.set_index('frequency (MHz)')

freqs_df = freqs_df[sorted(freqs_df.columns)]

plt.figure()
for col in freqs_df.columns:
    plt.plot(freqs_df.index,freqs_df[col],marker='None',label=col)
# plt.legend()
plt.xlabel('938 AWG frequency (MHz)')
plt.ylabel('driving amplitude (mV)')
plt.show()

freqs_df.to_csv('AWG1 DE measurement.csv')
# freq
# plt.yscale('log')  
# plt.show()
#%%
plt.style.use('default')

x = freqs_df.columns.astype(float) #[float(x.split(' mV')[0]) for x in freqs_df.columns]
y = freqs_df.index.astype(float)
X,Y = np.meshgrid(x,y)
Z = freqs_df
fig, ax = plt.subplots()
plt.pcolor(Y, X, Z)
plt.xlabel('938 AWG frequency (MHz)')
plt.ylabel('driving amplitude (mV)')
plt.colorbar(label='relative optical power')
plt.show()


fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.plot_surface(Y, X, Z, cmap=cm.viridis)
ax.set_xlabel('938 AWG frequency (MHz)')
ax.set_ylabel('driving amplitude (mV)')
ax.set_zlabel('relative optical power')
plt.show()

max_powers = freqs_df.max(axis=1)

fig, ax = plt.subplots()
ax.plot(freqs_df.index, max_powers,c='k')
ax.set_ylabel('max relative power')
ax.set_xlabel('938 AWG frequency (MHz)')
plt.show()

