import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import numpy as np
import ctypes

from copy import copy

from .pyspcm import *
from .spcm_tools import *

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
        
    lNumChannels : ctypes.c_long
        The number of active channels that the AWG card reports. The actual
        number is accessed with self.lNumChannels.value
    lBytesPerSample : ctypes.c_long
        The number of bytes each sample takes. Expect this to be 2. The actual 
        number is accessed with self.lBytesPerSample.value
        
    Methods
    -------
    init
        Initialises the card with the parameters defined when the class is 
        created. No data will be loaded onto the card yet.
        
    load_all
        Loads the segments and steps onto the card from the lists from the 
        `MainWindow` class. Then calls start to prepare for playback.
    
    start
        Starts the AWG card. This step should be called after the steps and 
        segments have been loaded onto the card.
        
    stop
        Stops the card but doesn't close the connection.
        
    trigger
        Forces a software trigger of the AWG card that will take effect even 
        if the card is waiting for an external trigger.
        
    reinit
        Deletes the connection to the AWG card and then calls init to make a 
        new connection after reinitialisation.
    
    _set_segment
        Internal method for sending preprepared data to the card to save in 
        a certain segment.
    
    _set_step
        Internal method for sending preprepared data to the card to save in 
        a certain segment.
        
    """
    
    def __init__(self,active_channels=1,sample_rate_Hz=int(625e6),max_output_mV=100,number_of_segments=16,**kwargs):
        """Create the class and set basic attributes. Kwargs are those 
        expected by the controller card_settings dict.
        
        The card initialise (self.init) method is then called. This is moved 
        to a seperate method so that the card can restart and reinitialise 
        itself without having to recreate the class.
        
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
        
        self.active_channels = int(active_channels)
        self.sample_rate_Hz = int(sample_rate_Hz)
        self.max_output_mV = int(max_output_mV)
        self.number_of_segments = int(number_of_segments)
        
        self.init()
    
    def init(self):        
        self.hCard = spcm_hOpen(create_string_buffer(b'/dev/spcm0'))
        if self.hCard == None:
            logging.error("No AWG card found")
        
        #spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_RESET)
        
        #Initialisation of reading parameters and definition of memory type.
        lCardType     = int32(0) 
        lSerialNumber = int32(0)
        lFncType      = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_PCITYP, byref(lCardType))                  # Enquiry of the pointer (lCardType.value) should return 484898. In manual p.56, this number should correspond to our device M4i.6622
        spcm_dwGetParam_i32(self.hCard, SPC_PCISERIALNO, byref(lSerialNumber))         # Enquiry of the pointer should return 14926. This can be cross-checked with the Spectrum documentation (check the Certificate)
        spcm_dwGetParam_i32(self.hCard, SPC_FNCTYPE, byref(lFncType))                  # Enquiry of the pointer should return 2. In manual p.59, this value corresponds to the arb. function generator. 
        spcm_dwSetParam_i32(self.hCard, SPC_CLOCKOUT, 0)                              # Disables the clock output (tristate). A value of 1 enables on external connector. Check p.83 on manual for more details.
        
        if self.max_output_mV > 282:
            self.max_output_mV = 282
            logging.error('Maxmimum output amplitude exceeds damage threshold '
                          'amplifier. Maximum amplitude (Vp) has been set to '
                          '{} mV'.format(self.max_output_mV))
        elif self.max_output_mV < 80:
            self.max_output_mV = 80
            logging.error('Maxmimum output amplitude must be at least 80 mV. '
                          'The output amplitude has been set to {} mV'.format(self.max_output_mV))
        
        if lCardType.value in [TYP_M4I6620_X8, TYP_M4I6621_X8, TYP_M4I6622_X8]:
            self.max_sample_rate_Hz = int(625e6)
        elif lCardType.value in [TYP_M4I6630_X8, TYP_M4I6631_X8]:
            self.max_sample_rate_Hz = int(1250e6)
        else:
            self.max_sample_rate_Hz = int(625e6)
            logging.error('Unknown AWG card model. Setting max_sample_rate_Hz '
                          '= {} S/s'.format(self.max_sample_rate_Hz))
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
        
        # Set up the channels and checks the number of active channels
        self.lNumChannels = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_CHCOUNT, byref(self.lNumChannels))
        logging.debug('number of active channels = {}'.format(self.lNumChannels.value))
        for lChannel in range (0, self.lNumChannels.value, 1):
            logging.debug('Setting up channel {}'.format(lChannel))
            spcm_dwSetParam_i32(self.hCard, SPC_ENABLEOUT0 + lChannel * (SPC_ENABLEOUT1 - SPC_ENABLEOUT0), 1)
            spcm_dwSetParam_i32(self.hCard, SPC_AMP0       + lChannel * (SPC_AMP1       - SPC_AMP0      ),  int32(self.max_output_mV))
            
            lmax_output_mV = int32(0)
            spcm_dwGetParam_i32(self.hCard, SPC_AMP0+lChannel*(SPC_AMP1 - SPC_AMP0), byref(lmax_output_mV))
            self.max_output_mV = lmax_output_mV.value
            logging.debug('channel {} output limit set to {} mV'.format(lChannel,self.max_output_mV))
            
            spcm_dwSetParam_i32 (self.hCard, SPC_CH0_STOPLEVEL + lChannel * (SPC_CH1_STOPLEVEL - SPC_CH0_STOPLEVEL), SPCM_STOPLVL_HOLDLAST)

        
        # Use internal clock source and set the sample rate
        spcm_dwSetParam_i32(self.hCard, SPC_CLOCKMODE, SPC_CM_INTPLL)
        spcm_dwSetParam_i64(self.hCard, SPC_SAMPLERATE, int32(self.sample_rate_Hz))
        regSrate = int64(0)                                        # Although we request a certain value, it does not mean that this is what the machine is capable of. 
        spcm_dwGetParam_i64(self.hCard, SPC_SAMPLERATE, byref(regSrate))    # We instead store the one the machine will use in the end.  
        self.sample_rate_Hz = regSrate.value
        logging.debug('sample rate set to {} S/s'.format(self.sample_rate_Hz))

        # Generate the data and transfer it to the card
        lMaxADCValue = int32(0) # decimal code of the full scale value
        spcm_dwGetParam_i32(self.hCard, SPC_MIINST_MAXADCVALUE, byref(lMaxADCValue))
        logging.debug('decimal code of full scale value {}'.format(lMaxADCValue.value))

        # Checks the number of bytes used per sample
        self.lBytesPerSample = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_MIINST_BYTESPERSAMPLE, byref(self.lBytesPerSample))
        logging.debug('bytes per sample {}'.format(self.lBytesPerSample.value))
                
        # Set the start step to zero
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_STARTSTEP, 0)
        
    def start(self,timeout = 10000):
        """Starts the AWG card. Unlike in the previous AWG code, errors in 
        steps and segments are not checked when performing this check. This 
        error checking has instead been moved to the data generation parts of 
        the code, which will not allow data to be submitted this far if an 
        error was encountered.
        
        The check for the start_step == 0 that was previously in the main 
        script when the start_awg command was recieved has been moved to here.
        
        The AWG will trigger once when started to set the step to 0.
        
        Parameters
        ----------
        timeout : int
            Defines the timeout, in ms, for any following wait command. Set to 
            0 to disable the timeout. The default is 10000.
        
        Returns
        -------
        None.
        
        """
        self.stop()
        status = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_M2STATUS, byref(status))
        
        # TODO test this status value. In the manual (p. 77) looks like other values could be returned.
        if status.value == 7:
            spcm_dwSetParam_i32(self.hCard, SPC_TIMEOUT, int(timeout))
            logging.debug("AWG started.")
            dwError = spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER | M2CMD_CARD_WAITPREFULL)
            if dwError == ERR_TIMEOUT:
                logging.error('Timeout error after requesting AWG card to '
                              'start. Requesting AWG to stop.')
                spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
                return
            
            if spcm_dwGetParam_i32(self.hCard, SPC_SEQMODE_STARTSTEP, byref(int32(0))) == 0:
                logging.info('AWG started.')
            else:
                logging.error('AWG crashed. Reset the AWG.')
            
        else:
            logging.error("AWG was asked to start but AWG is already running.")
        
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_STARTSTEP, 0)
        self.trigger()
        
    def stop(self):
        """Stops the AWG. The connection to the card is not closed, so the 
        card can be restarted by rerunning the start command.

        Returns
        -------
        None.

        """
        spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
        
    def trigger(self):
        """Triggers the AWG via a software trigger. This trigger is forced so 
        will trigger even if the card is waiting for an external trigger.

        Returns
        -------
        None.
        
        """
        spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_FORCETRIGGER)
        
    def close(self):
        """Closes the connection to the AWG card.
        
        Returns
        -------
        None.
        
        """
        spcm_vClose(self.hCard)
        
    def reinit(self):
        """Stops the card, disconnects, and reinitialises the card. The card 
        is not started yet so that segments/steps can be reloaded.

        Returns
        -------
        None.

        """
        self.stop()
        self.close()
        self.init()
        
    def load_all(self,segments,steps):
        """Loads all segment and step data onto the card and then starts it 
        to prepare for playback.
        
        All actions will be requested to calculate prior to the data being 
        sent. If have already been calculated and are eady for transfer, this 
        will not slow down the data transfer because they will not recalculate.
        
        Once an action has been trasferred the flag needs_to_transfer in the 
        ActionContainer will be marked as False. This will mean that the data 
        is not tranferred again unless the is flag is reset to True, such as 
        when the action is recalculated.

        Parameters
        ----------
        segments : list of list of ActionContainer
            The list of actions from the MainWindow class. Each entry in this 
            list is the data for the segment of the same index, and is itself 
            a list. Within these lists are ActionContainer objects, the index 
            of which refers to the channel the data should be outputted on.
        steps : list of dicts
            The list of dicts from the MainWindow class that defines the steps.
            Steps are loaded sequentially, apart from the last step which is 
            set to return to the first step after playback.

        Returns
        -------
        None.

        """
        self.stop()
        
        for segment_index,segment in enumerate(segments):
            segment_data = []
            # for action in segment: # removed because this function should only be called once all segments are calculated
            #     action.calculate()
            if any([action.needs_to_transfer for action in segment]):
                for action in segment:
                    segment_data.append(action.data)
                segment_data = self._multiplex(segment_data)
                self._set_segment(segment_index,segment_data)
                for action in segment:
                    action.needs_to_transfer = False
            else:
                logging.info('Skipped transferring segment {} to card because '
                             'all actions reported that they are already '
                             'transferred.'.format(segment_index))
            
        for step_index,step in enumerate(steps):
            if step_index == len(steps)-1:
                next_step_index = 0
            else:
                next_step_index = step_index + 1
            self._set_step(step_index,**step,next_step_index=next_step_index)
            
        self.start()
        
    def get_current_step(self):
        """Returns the current step and segment that the AWG card is on.
        
        Returns
        -------
        int
            The index of the current step being replayed by the card.

        """
        current_step = int64(0)
        spcm_dwGetParam_i64(self.hCard, SPC_SEQMODE_STATUS, byref(current_step))
        
        return current_step.value
        
            
    def _multiplex(self,arrays):
        """Converts a list of np.ndarrays in the form of [a,a,,...], 
        [b,b,,...] into a multiplexed sequence [a,b,a,b,...].
        
        Parameters
        ----------
        arrays : list of np.ndarrays
            The arrays to multiplex together.
        
        Returns
        -------
        np.ndarray
            The multiplexed arrays.
            
        """
        logging.debug('Multiplexing data.')
        l = len(arrays)
        c = np.empty((len(arrays[0]) * l,), dtype=arrays[0].dtype)
        for x in range(l):
            c[x::l] = arrays[x]
        return c
        
    def _set_segment(self,segment_index,segment_data):
        """
        This method is responsible for sending the data to the card to be 
        played. Data will be converted to the required signed integer format.
        
        Parameters
        ----------
        segment_index : int
            The index of the segment to write the data to.
            
        segment_data : numpy.ndarray
            The data to write in the segment. This should already be 
            multiplexed if using more than one channel. The data should be 
            floats with the value of the data in mV.
            
        Returns
        -------
        None.
        
        """     
        segment_data /= self.max_output_mV
        print(max(segment_data))
        
        if any(segment_data > 1) or any(segment_data < -1):
            logging.warning('Some of the data in segment {} was '
                            'larger than the maximum amplitude of '
                            '+/-{} mV. This data has been clipped to '
                            'stay within the bounds.'.format(segment_index,self.max_output_mV))
            # segment_data = segment_data.clip(max=1, min=-1)
            segment_data /= max(segment_data)
        segment_data = np.int16(segment_data*2**15)
        
        dwSegmentLenSample = len(segment_data)
        
        logging.debug('Preparing to transfer {} samples to segment {}.'.format(dwSegmentLenSample,segment_index))
        
        dwSegLenByte = uint32(dwSegmentLenSample * self.lBytesPerSample.value) 
        
        # Set the segment number to edit and the segment size
        dwError = spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_WRITESEGMENT, segment_index)
        if dwError == ERR_OK:
            dwError = spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_SEGMENTSIZE,  int(dwSegmentLenSample/self.lNumChannels.value))
        else:
            logging.error('Failed to set active segment to segment {}.'.format(segment_index))
            
        # Write data to board (main) sample memory (manual p. 78). Most of the following code comes from the old AWG code.
        qwBufferSize = uint64(dwSegmentLenSample * self.lBytesPerSample.value)
        
        # We try to use continuous memory if available and big enough
        pvBuffer = c_void_p() ## creates a void pointer -to be changed later.
        qwContBufLen = uint64(0)
        
        """
        The important part here is that we use byref(pvBuffer), meaning that
        you send to the card the POINTER to the POINTER of pvBuffer. So even
        if the memory spot of pvBuffer changes, that should not be an issue.
        """
        
        spcm_dwGetContBuf_i64 (self.hCard, SPCM_BUF_DATA, byref(pvBuffer), byref(qwContBufLen)) #assigns the pvBuffer the address of the memory block and qwContBufLen the size of the memory.
        if qwContBufLen.value >= qwBufferSize.value:
            logging.debug("Using continuous buffer")
        else:
            """
            You can use the following line to understand what is happening in pvBuffer after pvAllocMempageAligned.
            list(map(ord,pvBuffer.raw.decode('utf-8')))
            Effectively what you do is to allocate the memory needed (as a multiple of 4kB) and initialised it.
            """
            pvBuffer = pvAllocMemPageAligned(qwBufferSize.value) 
            
            logging.debug("Using buffer allocated by user program")
        
        # Takes the void pointer to a int16 POINTER type.
        # This only changes the way that the program reads that memory spot.
        pnBuffer = cast(pvBuffer, ptr16)
        
        # print(segment_data)

        lib = ctypes.cdll.LoadLibrary(r"Z:\Tweezer\Code\Python 3.9\awg\awg\memCopier\bin\Debug\memCopier.dll")
        lib.memCopier(pvBuffer,np.ctypeslib.as_ctypes(segment_data),int(dwSegmentLenSample))
        
        dwNotifySize = uint32(0)
        
        if dwError == ERR_OK:
            dwError = spcm_dwDefTransfer_i64(self.hCard, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, dwNotifySize, pvBuffer, 0, qwBufferSize)
        else:
            logging.error('Did not transfer data to buffer')
            
        if dwError == ERR_OK:
            dwError = spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA)
        else:
            logging.error('Failed to define the transfer buffer (check 4kB size limit on dwNotifySize).')
            
        if dwError != ERR_OK:
            logging.error('Failed to transfer data to card for segment {}'.format(segment_index))
        
    def _set_step(self,step_index,segment,number_of_loops,after_step,next_step_index,**kwargs):
        """
        Sets the parameters for a single step in the routine.

        Parameters
        ----------
        step_index : int
            The index of the step to write to.
        segment : int
            The segment index to use in this step.
        number_of_loops : int
            The number of times to repeat the segment in the step before 
            moving on to the continuation check.
        after_step : {'loop_until_trigger','continue'}
            Whether to keep replaying the step until a trigger is recieved 
            ('loop_until_trigger') or to advance to the next step once this 
            step is completed ('continue').
        next_step_index : int
            The next step to play after this one. This will typically either 
            be step_index+1 (to continue through the list of steps) or 0 (to 
            reset to the start of the sequence).

        Returns
        -------
        None.

        """
        
        max_steps = 4096
        if step_index > max_steps:
            logging.error('Requested step_index {} is larger than the maximum '
                          'number of steps ({}). Cancelling step '
                          'modification.'.format(step_index,max_steps))
            return
    
        if (segment < 0) or (segment >= self.number_of_segments):
            logging.error('Step {} is invalid. The segment index ({}) must be a '
                          'non-zero integer smaller than the number of '
                          'segments ({}). Cancelling step modification.'
                          ''.format(step_index, segment,self.number_of_segments))
            return
        
        max_loops = 1048575
        if (number_of_loops <= 0) or (number_of_loops >= max_loops):
            logging.error('Step {} is invalid. The number_of_loops must be '
                          'a positive integer smaller than the maximum number '
                          'of loops ({}). Cancelling step creation.'
                          ''.format(step_index,max_loops))
            return
        
        if next_step_index > max_steps:
            logging.error('Step {} is invalid. '
                          'Requested next_step_index {} is larger than the  '
                          'maximum number of steps ({}). Cancelling step '
                          'modification.'.format(step_index,next_step_index,max_steps))
            return

        if after_step == 'loop_until_trigger':
            llCondition = SPCSEQ_ENDLOOPONTRIG
        elif after_step == 'continue':
            llCondition = SPCSEQ_ENDLOOPALWAYS
        else:
            logging.error("Step {} is invalid. "
                          "after_step must be either 'loop_until_trigger' or "
                          "'continue', but is currently '{}'. Cancelling step "
                          "creation".format(step_index,after_step))
            return
            
        logging.debug('Setting step {} to segment {}.'.format(step_index,segment))
        
        llvals=int64((llCondition<<32) | (number_of_loops<<32) | (next_step_index<<16) | segment)
        spcm_dwSetParam_i64(self.hCard,SPC_SEQMODE_STEPMEM0 + step_index,llvals)
    
if __name__ == '__main__':
    awg = AWG(sample_rate_Hz = 1000e6,max_output_mV=300)