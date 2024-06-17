import logging
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
    
    Attributes
    ----------
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
    
    def __init__(self, settings):
        """2D amp adjuster class for handling the frequency and optical power 
        to RF power (mV) conversion.
        
        Parameters
        ----------
        settings : dict
            Settings dictonary for the AmpAdjuster. This should contain the 
            AmpAdjuster attributes to set (see class docstring).

        """
        
        self.update_settings(settings)
        
    def update_settings(self,settings):
        for key,value in settings.items():
            setattr(self,key,value)
        
        fs = np.linspace(self.freq_limit_1_MHz,self.freq_limit_2_MHz,100)
        power = np.linspace(self.amp_limit_1,self.amp_limit_2,200)
        
        try:     
            self.calibration = self.load_calibration(self.filename,fs,power)
        except FileNotFoundError:
            self.enabled = False
            logging.error('Calibration file {} not found. Amplitudes will not '
                          'be frequency adjusted by this '
                          'AmpAdjuster.'.format(self.filename))
        except json.decoder.JSONDecodeError:
            self.enabled = False
            logging.error('Failed to decode calibration file {}. Is the '
                          'format correct? Amplitudes will not be frequency '
                          'adjusted by this AmpAdjuster.'.format(self.filename))
            
    def get_settings(self):
        """Compiles and returns the settings dictionary that specifies the 
        behaviour of this AmpAdjuster.
        
        This is the dictionary that is displayed in the 
        `AmpAdjusterSettingsWindow` when the AmpAdjuster settings are 
        changed.
        
        Returns
        -------
        dict
            Dictionary containing the attributes of this AmpAdjuster that can 
            be used to recreate it.
        """
        
        attributes = ['enabled','filename','freq_limit_1_MHz',
                      'freq_limit_2_MHz','amp_limit_1','amp_limit_2',
                      'non_adjusted_amp_mV']
        settings = {}
        for attribute in attributes:
            settings[attribute] = getattr(self,attribute)
        return settings

    def load_calibration(self, filename, fs = np.linspace(135,190,150), power = np.linspace(0,1,100)):
        """Convert saved diffraction efficiency data into a 2D freq/amp 
        calibration or just load a preprepared calibration file in.
        
        Parameters
        ----------
        filename : str
            The name of the AmpAdjuster file.

            The file extension should either be .txt for non-pre-prepared
            AmpAdjust files (old format), or .awgde for pre-prepared 
            AmpAdjust files (new format).

            For the old format files the max amplitude will be set to 
            be the same across the entire array, this is not true for 
            the new format files where this is set at data creation
            (see LabBook 22/02/2023).

        fs : np.array
            Frequencies to use when creating the 2D amp adjuster spline.
            Not used with the .awgde file format.
        
        power : np.array
            Powers to use when creating the 2D amp adjuster spline. Not
            used with the .awgde file format.
        """
        if not filename.rsplit('.',1)[-1] == 'awgde': # old file format so construct the AmpAdjuster1d objects
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
                    logging.warning('Power calibration overflow: required power is > 280mV. This has been truncated.')
                    y[y>280] = 280
                return y
        
            mv = np.zeros((len(power), len(fs)))
            for i, p in enumerate(power):
                try:
                    mv[i] = ampAdjuster1d(fs, p)
                except Exception as e: print('Warning: could not create power calibration for %s\n'%p+str(e))
                
            return RectBivariateSpline(power, fs, mv)

        else: # new .awgde format, see Labbook 22/02/2023 for more info
            with open(filename) as json_file:
                contours = json.load(json_file)
            optical_powers = list(contours.keys())
            first_key = next(iter(contours))
            fs = np.linspace(min(contours[first_key]['Frequency (MHz)']),max(contours[first_key]['Frequency (MHz)']),len(fs)) # remake fs array with freqs of the .awgde file
            voltages = np.zeros((len(optical_powers), len(fs)))
            for i, power in enumerate(optical_powers):
                freq_to_voltage = interp1d(contours[power]['Frequency (MHz)'], 
                                           contours[power]['RF Amplitude (mV)'],
                                           bounds_error=False,
                                           fill_value = max(contours[power]['RF Amplitude (mV)']))
                voltages[i] = freq_to_voltage(fs)
                
            optical_powers = [float(x) for x in optical_powers]

            return RectBivariateSpline(optical_powers, fs, voltages)

    
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
        if self.enabled:
            cal = self.calibration
            return cal.ev(optical_powers, freqs_MHz)
        else:
            return np.array(optical_powers)*self.non_adjusted_amp_mV

if __name__ == '__main__':
    # fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations'
    filename = r"Z:\Tweezer\Code\Python 3.9\awg\diffraction efficiency\AWG1_calibration_22_02_2023_90MHz_255MHz.awgde"
    
    settings = {'enabled':True,
                'non_adjusted_amp_mV':100,
                'filename':filename,
                'freq_limit_1_MHz':85,
                'freq_limit_2_MHz':115,
                'amp_limit_1':0,
                'amp_limit_2':1}
    
    aa = AmpAdjuster2D(settings)
    aa.update_settings(settings)
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