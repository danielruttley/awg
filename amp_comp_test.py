import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

# amp = 2*np.linspace(4,8,100)**2
amp = np.linspace(0.165,0.165,100000)
plt.plot(amp,label='desired amp')

# amp_comp = np.linspace(4,8,50)**2
# amp_comp += 10*(np.random.rand(len(amp_comp))-0.5)
amp_comp = np.genfromtxt(r"Z:\Tweezer\Experimental Results\2022\September\16\AWG sweeping noise\V 100MHz to 97MHz 5ms\100MHz_97MHz_5ms.csv", delimiter=',')
amp_comp = amp_comp.clip(min=0)

fig, axs = plt.subplots(2,1)
axs[0].plot(amp)
axs[0].set_ylabel('desired amp')
axs[1].plot(amp_comp, c='C1')
axs[1].set_ylabel('measured amp (mV)')
for ax in axs:
    ax.set_xlabel('index')
    # ax.set_ylim(bottom=0)
fig.tight_layout()
plt.show()

amp_comp_interp = interp1d(np.arange(amp_comp.size),amp_comp)
amp_comp_adjusted = amp_comp_interp(np.linspace(0,amp_comp.size-1,amp.size))

plt.plot(amp_comp_adjusted,label='measured amp')
plt.legend()
plt.show()

amp_scaled = amp/amp.mean()
amp_comp_scaled = amp_comp_adjusted/amp_comp_adjusted.mean()

amp_corrected = np.nan_to_num(amp*(amp_scaled/amp_comp_scaled))
amp_corrected = amp_corrected.clip(min=np.min(amp)/2,max=2*np.max(amp))

plt.plot(amp_scaled,label='scaled desired amp')
plt.plot(amp_comp_scaled,label='scaled measured amp')
plt.plot(amp_corrected/amp_corrected.mean(),label='scaled compensated amp')
plt.ylabel('amp')
plt.xlabel('index')
plt.legend()
plt.show()

plt.plot(amp,label='desired amp')
# plt.plot(amp_comp_adjusted,label='measured amp')
plt.plot(amp_corrected,label='compensated amp')
# plt.ylim(top=1000)
plt.legend()
plt.show()
