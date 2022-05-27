import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

from pyspcm import *
from spcm_tools import *
import ctypes

class AWG():
    """Defines the AWG wrapper class for handling interfacing with the AWG.
    The class is designed to use the sequence mode of the AWG.
    
    Attributes
    ----------
    hCard : LP_c_ulonglong
        The AWG card which is directly communicated with using the register 
        tables as outlined in the M4i.66xx-x8/M4i.66xx-x4 manual p. 61.
    active_channels : {1,2}
        The number of active channels on the AWG. This is specified at object 
        creation.
    sample_rate_Hz : int
        The current sample rate setting of the AWG card. This is specified at 
        object creation, but is then read from the card in case the actual 
        setting has been set to a different number.
    max_output_mV : float
        The maximum amplitude (Vp) that the card will output.
    number_of_segments : int
        The number of segments the AWG memory has been divided into. This must 
        be a power of 2.
        
    """
    
    def __init__(self,active_channels=1,sample_rate_Hz=int(625e6),max_output_mV=100,number_of_segments=16):
        """Create the class and set basic attributes. Kwargs are those 
        expected by the controller card_settings dict.
        
        The card is initialised in sequence replay mode.
        
        Parameters
        ----------
        active_channels : {1,2}
            The number of channels to activate on the AWG. Channel 0 will 
            always be the first channel activated.
        sample_rate_Hz : int
            The sample rate of the card in S/s.
        max_output_mV : float
            The maximum peak amplitude of the output of the card in mV.
        number_of_segments : int
            The number of segments to divide the card memory into for 
            sequence replay mode. This number must be a power of 2.
        
        """
        self.hCard = spcm_hOpen(create_string_buffer(b'/dev/spcm0'))
        if self.hCard == None:
            logging.error("No AWG card found")
            
        #Initialisation of reading parameters and definition of memory type.
        lCardType     = int32 (0) 
        lSerialNumber = int32 (0)
        lFncType      = int32 (0)
        spcm_dwGetParam_i32(self.hCard, SPC_PCITYP, byref(lCardType))                  # Enquiry of the pointer (lCardType.value) should return 484898. In manual p.56, this number should correspond to our device M4i.6622
        spcm_dwGetParam_i32(self.hCard, SPC_PCISERIALNO, byref(lSerialNumber))         # Enquiry of the pointer should return 14926. This can be cross-checked with the Spectrum documentation (check the Certificate)
        spcm_dwGetParam_i32(self.hCard, SPC_FNCTYPE, byref(lFncType))                  # Enquiry of the pointer should return 2. In manual p.59, this value corresponds to the arb. function generator. 
        spcm_dwSetParam_i32(self.hCard, SPC_CLOCKOUT, 0)                              # Disables the clock output (tristate). A value of 1 enables on external connector. Check p.83 on manual for more details.
        
        self.active_channels = int(active_channels)
        self.sample_rate_Hz = int(sample_rate_Hz)
        self.max_output_mV = float(max_output_mV)
        self.number_of_segments = int(number_of_segments)
        
        if self.max_output_mV > 282:
            self.max_output_mV = 282
            logging.error('Maxmimum output amplitude exceeds damage threshold '
                          'amplifier. Maximum amplitude (Vp) has been set to '
                          '{} mV'.format(self.max_output_mV))
        
        if lCardType.value in [TYP_M4I6620_X8, TYP_M4I6621_X8, TYP_M4I6622_X8]:
            self.max_sample_rate_Hz = int(625e6)
        elif lCardType.value in [TYP_M4I6630_X8, TYP_M4I6631_X8]:
            self.max_sample_rate_Hz = int(1250e6)
        else:
            self.max_sample_rate_Hz = int(625e6)
            logging.error('Unknown card model. Setting max_sample_rate_Hz = '
                          '{} S/s'.format(self.max_sample_rate_Hz))
        if self.sample_rate_Hz > self.max_sample_rate_Hz:
            self.sample_rate_Hz = self.max_sample_rate_Hz
            logging.error('Sample rate exceeded maximum so has been reduced '
                          'to maximum value {} S/s'.format(self.sample_rate_Hz))
       
        # Activate sequence replay mode
        spcm_dwSetParam_i32(self.hCard, SPC_CARDMODE, SPC_REP_STD_SEQUENCE)
        
        # Enable the correct number of channels
        if self.active_channels == 2:
            llChEnable = int64(CHANNEL0|CHANNEL1)
        else:
            llChEnable = int64(CHANNEL0)
        spcm_dwSetParam_i64(self.hCard, SPC_CHENABLE, llChEnable)
        
        # Set the number of segments
        lMaxSegments = int32(self.number_of_segments)
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_MAXSEGMENTS, lMaxSegments)
        
        # Set the trigger mode of the card to external trigger, positive slope across level0 (see p.102)
        trig_level0 = 2000 # trigger level 0, in mV
        trig_level1 = 0 # trigger level 1, in mV (not used in this mode)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_ORMASK, SPC_TMASK_NONE)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_ORMASK, SPC_TMASK_EXT0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_EXT0_LEVEL0, int(trig_level0)) # Sets the trigger level for Level0 (principle level)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_EXT0_LEVEL1, int(trig_level1)) # Sets the trigger level for Level1 (ancilla level)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_EXT0_MODE, SPC_TM_POS)  # Sets the trigger mode
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_ANDMASK, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ORMASK0, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ORMASK1, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ANDMASK0, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ANDMASK1, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIGGEROUT, 0)
        logging.debug('Set external trigger to crossing {} mV on a positive slope'.format(trig_level0))
        
        # Set up the channels
        lNumChannels = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_CHCOUNT, byref(lNumChannels))
        for lChannel in range (0, lNumChannels.value, 1):
            spcm_dwSetParam_i32 (self.hCard, SPC_ENABLEOUT0    + lChannel * (SPC_ENABLEOUT1    - SPC_ENABLEOUT0),    1)
            spcm_dwSetParam_i32 (self.hCard, SPC_AMP0          + lChannel * (SPC_AMP1          - SPC_AMP0),          1000)
            spcm_dwSetParam_i32 (self.hCard, SPC_CH0_STOPLEVEL + lChannel * (SPC_CH1_STOPLEVEL - SPC_CH0_STOPLEVEL), SPCM_STOPLVL_HOLDLAST)
        
        # Use internal clock source and set the sample rate
        spcm_dwSetParam_i32(self.hCard, SPC_CLOCKMODE, SPC_CM_INTPLL)
        spcm_dwSetParam_i64(self.hCard, SPC_SAMPLERATE, int32(self.sample_rate_Hz))
        regSrate = int64(0)                                        # Although we request a certain value, it does not mean that this is what the machine is capable of. 
        spcm_dwGetParam_i64 (self.hCard, SPC_SAMPLERATE, byref(regSrate))    # We instead store the one the machine will use in the end.  
        self.sample_rate_Hz = regSrate
        logging.debug('sample rate set to {} S/s'.format(self.sample_rate_Hz))

        # Prints the number of bytes used in memory by one sample. p.59 of manual for more info
        lBytesPerSample = int32(0)
        bytes_per_sample = spcm_dwGetParam_i32(self.hCard, SPC_MIINST_BYTESPERSAMPLE, byref(lBytesPerSample))
        logging.debug('bytes per sample {}'.format(bytes_per_sample))
        
        # Prints the number of currently active channels
        lSetChannels = int32(0)
        active_channels = spcm_dwGetParam_i32(self.hCard, SPC_CHCOUNT, byref(lSetChannels))
        logging.debug('number of active channels {}'.format(active_channels))
                
        # Set the start step to zero
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_STARTSTEP, 0)
        

if __name__ == '__main__':
    awg = AWG(sample_rate_Hz = 1000e6,max_output_mV=300)