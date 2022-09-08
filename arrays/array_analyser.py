import numpy as np
import PIL.Image as PILImage
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
import os

import pandas as pd
from datetime import datetime
import matplotlib.dates as mdates

df = pd.DataFrame()

freqs = [106,104,102,100]

image_dir = r"Z:\Tweezer\Experimental Results\2022\August\12\AWG2 array images\autoimager monitoring\\"
directory = os.fsencode(image_dir)
    
for file in os.listdir(directory):
    filename = os.fsdecode(file)#
    if filename[-4:] == '.png':
        print(filename)
        time = filename.split('.png')[0]
        print(time)
        filename_full = image_dir+filename
        array = np.asarray(PILImage.open(filename_full)).astype('uint16')
        
        max_pixel = np.unravel_index(np.argmax(array, axis=None), array.shape)
        
        y_axis = np.argmax(array.sum(axis=0))
        
        # plt.imshow(array)
        # plt.axvline(y_axis,c='k',linestyle='--')
        # plt.ylabel('y (pixels)')
        # plt.xlabel('x (pixels)')
        # plt.show()
        
        array_slice = array[:,y_axis]
        peaks, props = find_peaks(array_slice, distance = 50, height = max(array_slice)/4)
        df.loc[time,'datetime'] = datetime.fromtimestamp(int(float(time)))
        
        # plt.plot(array_slice)
        for i,peak in enumerate(peaks):
            # plt.scatter(peak,array_slice[peak])
            df.loc[time,'peak_{}'.format(i)] = array_slice[peak]

        # plt.ylabel('intensity (arb.)')
        # plt.xlabel('y position (pixels)')
        # plt.show()
    
for i,freq in zip(range(4),freqs):
    plt.scatter(df['datetime'],df['peak_{}'.format(i)],c='C{}'.format(i),label=freq)
    plt.plot(df['datetime'],df['peak_{}'.format(i)],c='C{}'.format(i))
plt.ylabel('peak intensity (arb.)')
plt.xlabel('time')
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
plt.legend(title='freq (MHz)')
plt.show()
