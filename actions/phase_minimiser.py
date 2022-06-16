import numpy as np
from scipy.optimize import minimize
import time

def multisine(phases_deg, freqs_MHz, amps, time_us=np.linspace(0,1,1000)):
    return np.sum([amps[i]*np.sin(2*np.pi*time_us*freqs_MHz[i]+ phases_deg[i]*np.pi/180) for i in range(len(phases_deg))],axis=0)
   
def crest(phases_deg, freqs_MHz, amps, time_us=np.linspace(0,1,1000)):
    y = multisine(phases_deg, freqs_MHz, amps, time_us)
    return np.max(y)/np.sqrt(np.mean(y**2))

def phase_adjust(N):
    """Minimise the crest factor analytically. See DOI 10.5755/j01.eie.23.2.18001 """
    i = np.arange(N)
    phi = 180*(i+1)**2/N
    phi = (phi - phi[0])%360
    return phi

def crest_index(phi, phases_deg, ind, freqs_MHz=[85,87,89], amps=[1,1,1]):
    phases_deg[ind] = phi
    return crest(phases_deg, freqs_MHz, amps)

def phase_minimise(freqs_MHz=[85,87,89], amps=[1]*3):
    """Numerically optimise the phases to reduce the crest factor"""
    # if len(amps) != len(freqs_MHz):
    #     amps = [1]*len(freqs_MHz)
    # start by optimizing them all
    result = minimize(crest, phase_adjust(len(freqs_MHz)), args=(freqs_MHz, amps))
    phases_deg = result.x
    for i in range(len(freqs_MHz)): # then one by one
        result = minimize(crest_index, phases_deg[i], args=(phases_deg,i,freqs_MHz,amps))
        phases_deg[i] = result.x
    phases_deg = (phases_deg-phases_deg[0])%360
    return list(phases_deg)    

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    
    freqs_MHz = [100,101,102,103,104,105,106]
    amps = [1,1,1,1,1,1,1]
    
    print('--- analytical ---')
    start = time.time()
    phases = phase_adjust(len(freqs_MHz))
    # phases = ((phases-phases[0])*180/np.pi)%360
    print('phases',phases)
    print('crest factor',crest(phases,freqs_MHz,amps))
    print('time',time.time()-start)
    
    print('\n--- numerical ---')
    start = time.time()
    phases = phase_minimise(freqs_MHz, amps)
    print('phases',(phases))
    print('crest factor',crest(phases,freqs_MHz,amps))
    print('time',time.time()-start)
    
    y = multisine(phases,freqs_MHz,amps)
    plt.plot(multisine(phases,freqs_MHz,amps))