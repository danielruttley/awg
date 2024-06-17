import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib import cm
import json
import pickle


from scipy.interpolate import RegularGridInterpolator,RectBivariateSpline,interp1d

plt.close('all')
plt.style.use('default')

#%%

freqs_df = pd.read_csv('AWG3 DE measurement.csv',index_col = 0)
freqs = np.linspace(min(freqs_df.index),max(freqs_df.index),1000)
x,y = np.meshgrid(freqs_df.columns.astype(float),freqs_df.index.astype(float))
de = freqs_df

PD = np.linspace(0.01, 0.3, 1000) # 1 will be set to this value
plt.figure()
c = plt.contour(y, x, de, PD)
plt.xlabel('Frequency (MHz)')
plt.ylabel('RF Amplitude (mV)')
plt.show()
DE = []
failed = []

PD = PD/max(PD)

contours = {}

contours[0] = {'Frequency (MHz)':[min(freqs_df.index),max(freqs_df.index)],'RF Amplitude (mV)':[0,0]}
for i, [optical_power,contour_line] in enumerate(zip(PD,c.allsegs)):
        print(contour_line)
        # [l.tolist() for l in contour_line]
        # remove extra loops in the contours
        contour_line = np.concatenate(list(reversed(contour_line)))
        contour_freqs = contour_line[:,0]
        contour_freqs_diff = np.concatenate([np.array([-1]),np.diff(contour_freqs)])
        
        contour_line = contour_line[contour_freqs_diff<0,:]
        # vertices = line.get_paths()[0].vertices
        if len(contour_line) > 2:
            contours[optical_power] = {'Frequency (MHz)':list(contour_line.T[0]),'RF Amplitude (mV)':list(contour_line.T[1])}
            # DE.append(line.get_paths()[0].vertices)
        # else: failed.append(i)
    # except Exception as e: 
    #     pass
        # print(e)
        # failed.append(i)
        


# PD = np.delete(PD, failed) # get rid of closed contours
# # show the DE curve:

# from collections import OrderedDict
# # import json

plt.figure()
for d in contours.values():
    plt.plot(d['Frequency (MHz)'], d['RF Amplitude (mV)'])
plt.xlabel('Frequency (MHz)')
plt.ylabel('RF Amplitude (mV)')
plt.show()



# d = {}
# [d.update({PD[i]:{'Frequency (MHz)':list(DE[i][:,0]), 'RF Amplitude (mV)':list(DE[i][:,1])}}) for i in range(len(PD)) if i not in failed]
# # d = OrderedDict([(PD[i], {'Frequency (MHz)':list(DE[i][:,0]), 'RF Amplitude (mV)':list(DE[i][:,1])}) for i in range(len(DE))])
powers = list(contours.keys())
voltages = np.zeros((len(powers), len(freqs)))
# failed = []
for i, power in enumerate(powers):
    freq_to_voltage = interp1d(contours[power]['Frequency (MHz)'], 
                               contours[power]['RF Amplitude (mV)'],
                               bounds_error=False,
                               fill_value = max(contours[power]['RF Amplitude (mV)']))
    voltages[i] = freq_to_voltage(freqs)

x,y = np.meshgrid(freqs,powers)
plt.figure()
c = plt.contour(x, y, voltages)
plt.xlabel('Frequency (MHz)')
plt.ylabel('optical power')
plt.show()

# for key in failed: d.pop(key)
# #
# ## invert the calibration and make a 2D interpolation

spline = RectBivariateSpline(powers, freqs, voltages)
x1, y1 = np.meshgrid(freqs, powers)
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
# ax.plot_wireframe(x, y, volts, color='k', alpha=0.3)
surface = ax.plot_surface(x1, y1, spline(powers,freqs), cmap='viridis') # power measured before AOD was 14mW, which is 4.5593 V
ax.set_xlabel('Frequency (MHz)')
ax.set_ylabel('Relative Optical Power')
ax.set_zlabel('RF Amplitude (mV)')
fig.tight_layout()
plt.show()

with open(r'AWG3_calibration_19_03_2024_85MHz_135MHz.awgde', 'w') as f:
    json.dump(contours, f)

#%%
freq_and_voltage_to_power = RectBivariateSpline(freqs_df.index.astype(float), freqs_df.columns.astype(float), freqs_df)

#%%
target_freqs = freqs
target_power = 1 # this is in normalised units, so what fraction of max power?

voltages = spline(target_power,target_freqs).T

plt.figure()
plt.plot(target_freqs,voltages)
plt.title(f'voltage to target relative power = 0.5')
plt.ylabel('RF amplitude (mV)')
plt.xlabel('938 AWG frequency (MHz)')
plt.show()

resultant_powers = []
for freq, voltage in zip(target_freqs,voltages):
    resultant_powers.append(freq_and_voltage_to_power(freq,voltage)[0][0])
    
max_powers = freqs_df.max(axis=1)

plt.figure()
plt.plot(freqs_df.index, max_powers,c='k',linestyle='--',label='without calibration')
plt.plot(target_freqs,resultant_powers,label='with calibration')
# plt.title(f'voltage to target relative power = {target_power}')
plt.ylabel('relative optical power')
plt.xlabel('1145 AWG frequency (MHz)')
plt.legend()
plt.show()


#%%
# plt.style.use('default')

# x = freqs_df.columns.astype(float) #[float(x.split(' mV')[0]) for x in freqs_df.columns]
# y = freqs_df.index.astype(float)
# X,Y = np.meshgrid(x,y)
# Z = freqs_df
# fig, ax = plt.subplots()
# plt.pcolor(Y, X, Z)
# plt.xlabel('938 AWG frequency (MHz)')
# plt.ylabel('driving amplitude (mV)')
# plt.colorbar(label='relative optical power')
# plt.show()


# fig = plt.figure()
# ax = fig.add_subplot(111, projection='3d')
# ax.plot_surface(Y, X, Z, cmap=cm.viridis)
# ax.set_xlabel('938 AWG frequency (MHz)')
# ax.set_ylabel('driving amplitude (mV)')
# ax.set_zlabel('relative optical power')
# plt.show()

# max_powers = freqs_df.max(axis=1)

# fig, ax = plt.subplots()
# ax.plot(freqs_df.index, max_powers,c='k')
# ax.set_ylabel('max relative power')
# ax.set_xlabel('938 AWG frequency (MHz)')
# plt.show()

