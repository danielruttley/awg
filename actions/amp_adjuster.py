import numpy as np
import time
import json
from collections import OrderedDict
from scipy.interpolate import interp1d, RectBivariateSpline

class AmpAdjuster2D():
    """Class to read in and process the calibration files for the amp_adjust 
    functionality of the AWG.
    
    Once initialised, the main functionality of the class is accessed with the
    `adjuster` method.
    
    """
    
    def __init__(self, calibration_filename, freq_limits_MHz, power_limits):
        """2D amp adjuster class for handling the frequency and optical power 
        to RF power (mV) conversion.
        
        calibration_filename : str
            The filename that the calibration should be loaded from
        freq_limits_MHz: list of floats
            List in the format [min_freq,max_freq] that the interpolation 
            should be performed over. A wider frequency range will reduce the 
            maximum optical power.
        power_limits: list of floats
            List in the format [min_power,max_power] that the interpolation 
            should be performed over.
        """
        
        fs = np.linspace(*freq_limits_MHz,100)
        power = np.linspace(*power_limits,200)
        
        self.calibration = self.load_calibration(calibration_filename,fs,power)

    def load_calibration(self, filename, fs = np.linspace(135,190,150), power = np.linspace(0,1,100)):
        """Convert saved diffraction efficiency data into a 2D freq/amp calibration"""
        with open(filename) as json_file:
            calFile = json.load(json_file) 
        contour_dict = OrderedDict(calFile["Power_calibration"]) # for flattening the diffraction efficiency curve: keep constant power as freq is changed
        failed = [] # keep track of keys that couldn't produce a calibration
        for key in contour_dict.keys():
            try:
                contour_dict[key]['Calibration'] = interp1d(contour_dict[key]['Frequency (MHz)'], contour_dict[key]['RF Amplitude (mV)'])
            except Exception as e: 
                failed.append(key)
                print(key, e)
        for key in failed: contour_dict.pop(key) # remove failed calibrations
        
        def ampAdjuster1d(freq, optical_power):
            """Find closest optical power in the presaved dictionary of contours, 
            then use interpolation to get the RF amplitude at the given frequency"""
            i = np.argmin([abs(float(p) - optical_power) for p in contour_dict.keys()]) 
            key = list(contour_dict.keys())[i]
            y = np.array(contour_dict[key]['Calibration'](freq), ndmin=1) # return amplitude in mV to keep constant optical power
            if (np.size(y)==1 and y>280) or any(y > 280):
                print('WARNING: power calibration overflow: required power is > 280mV')
                y[y>280] = 280
            return y
    
        mv = np.zeros((len(power), len(fs)))
        for i, p in enumerate(power):
            try:
                mv[i] = ampAdjuster1d(fs, p)
            except Exception as e: print('Warning: could not create power calibration for %s\n'%p+str(e))
            
        return RectBivariateSpline(power, fs, mv)
    
    def adjuster(self,freqs_MHz,optical_powers):
        """Sort the arguments into ascending order and then put back so that we can 
        use the 2D calibration.
        
        Parameters
        ----------
        freqs_MHz : list of floats
            List of the frequencies to use. Each should be paired with the 
            corresponding index in `optical_powers`.
        optical_powers : list of floats
            List of optical powers to use. Each should be paired with the 
            corresponding index in `freqs_MHz`.
        """
        cal = self.calibration
        return cal.ev(optical_powers, freqs_MHz)

if __name__ == '__main__':
    fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations'
    filename = fdir + r'\814_V_calFile_17.02.2022.txt'
    
    aa = AmpAdjuster2D(filename,[85,115],[0,1])
    start = time.time()
    rf_powers = aa.adjuster([101.375,101],[1,1])
    print(time.time()-start)
    print(rf_powers)
    
    import matplotlib.pyplot as plt
    
    fs = np.linspace(85,115,int(1e5))
    powers = np.ones_like(fs)*0.5
    
    start = time.time()
    amps = aa.adjuster(fs,powers)
    print(time.time()-start)
    
    plt.plot(fs,amps)
    plt.show()