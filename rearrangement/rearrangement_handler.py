import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import inspect
import numpy as np
import re
import json

import itertools
import time
from copy import copy

from os import path, makedirs
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from actions import ActionContainer, shared_segment_params

params_to_save = ['start_freq_MHz','target_freq_MHz','channel','segment','mode']

max_tone_num = 100

class RearrangementHandler():
    """Handler for rearrangement functionality. Takes strings from 
    Pydex and returns the index of the segment which the rearrangement 
    step should be changed to.

    Attributes
    ----------
    start_freq_MHz : list of floats
        The frequencies of the ROIs in AtomChecker. Strings specifiying 
        the loaded traps from the Pydex `AtomChecker` should be in the 
        same order as this list. The traps should be in either 
        ascending or descending frequency order to prevent traps being 
        moved through each other.
    target_freq_MHz : list of floats
        List of the initial starting array frequencies of the loading 
        array in MHz. Strings specifiying the loaded traps from the 
        Pydex `AtomChecker` should be in the same order as this list. 
        The traps should be in either ascending or descending frequency 
        order (the same order as `start_freq_MHz`) to prevent traps 
        being moved through each other.
        
        The rearrangment handler will aim to fill this array as much as 
        possible. If behaviour similar to the old use_all mode is desired,
        simply make the len(target_freq_MHz) == len(start_freq_MHz).
    segment : int
        The index of the segment to make copies of when using 
        rearrangement. This is the segment that will be modified during 
        runtime to move the atom to the correct place.
    channel : int
        The channel that rearrangement takes place in. The other 
        channel's data is duplicated among the rearrangement segments.
    base_segments : list of lists of `ActionContainers`
        The ActionContainers containing the base rearrangement data to 
        send to the card with all other segments.
    rearr_segments : list of lists of `ActionContainers`
        The ActionContainers containing the segment data to be sent 
        to the card during runtime.
    """
    
    def __init__(self,main_window,filename):
        """Create the `RearrangementHandler` object and assign its attributes.        

        Parameters
        ----------
        filename : str
            The location of the filename to load the default 
            rearrangement parameters from.

        Returns
        -------
        None.

        """
        self.mode = 'simultaneous' # specified here to maintain compatability with older .awgrr files.
        self.main_window = main_window
        self.load_params(filename)
        
    def create_actions(self,segment_params_list=None):
        """Creates the `ActionContainer` objects that contains the 
        segment data to send to the card. The data to be sent at runtime
        when in rearrangement mode is also created.

        Parameters
        ----------
        segment_params_list : list of dict or None
            List of dictionaries containing the parameters used to 
            create the actions. If None, no new actions will be 
            created but the already exisiting ones will be modified 
            to reflect any changes in the rearrangement parameters.

        Returns
        -------
        None.

        """
        if segment_params_list != None:
            self.base_segments = []
            for segment_index, segment_params in enumerate(segment_params_list):
                segment = []
                for channel in range(self.main_window.card_settings['active_channels']):
                    channel_params = {}
                    for shared_segment_param in shared_segment_params:
                        channel_params[shared_segment_param] = segment_params[shared_segment_param]
                    if segment_index in [0, self.segment, len(segment_params_list)-1]:
                        channel_params['phase_behaviour'] = 'optimise'
                    print('check active channels',channel,segment_params)
                    try:
                        channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
                    except KeyError:
                        channel_params = {**channel_params,**segment_params['Ch0']} #will fall back on Ch0 if there are not enough channels in rr params
                    action = ActionContainer(channel_params,self.main_window.card_settings,self.main_window.amp_adjusters[channel])
                    segment.append(action)
                self.base_segments.append(segment)
        
        for segment_index, segment in enumerate(self.base_segments):
            for channel, action in enumerate(segment):
                if channel == self.channel:
                    if segment_index < self.segment:
                        action.update_param('freq','start_freq_MHz',self.start_freq_MHz)
                        action.update_param('freq','end_freq_MHz',self.target_freq_MHz)
                    elif segment_index == self.segment:
                        action.update_param('freq','start_freq_MHz',self.start_freq_MHz)
                        action.update_param('freq','end_freq_MHz',self.target_freq_MHz)
                    else:
                        action.update_param('freq','start_freq_MHz',self.target_freq_MHz)
                        action.update_param('freq','end_freq_MHz',self.target_freq_MHz)

        self.create_rearr_actions()

    def create_rearr_actions(self):
        """Creates a list of movements for the different rearrangement
        segments and assigns these to a rearrangement keys. During runtime 
        the correct tones are picked from the dictionary and summed.
        """
        np.random.seed(817)
        base_segment = self.base_segments[self.segment]

        occupation_start_freqs = self.get_occupation_freqs()
        
        self.rearr_movements = []

        for start_freqs_MHz,occupation in zip(occupation_start_freqs,self.occupations):
            num_occupied_traps = occupation.count('1')
            rr_start_freqs_MHz = start_freqs_MHz[:num_occupied_traps]
            rr_target_freqs_MHz = self.target_freq_MHz[:num_occupied_traps]

            freq_movements = tuple(zip(rr_start_freqs_MHz,rr_target_freqs_MHz))
            self.rearr_movements.append(freq_movements)
        
        self.rearr_unique_movements = set(itertools.chain.from_iterable([list(x) for x in self.rearr_movements]))

        logging.debug('Calculated rearrangement movements {}'.format(self.rearr_movements))
        logging.debug('Unique rearrangement movements are {}'.format(self.rearr_unique_movements))

        self.rearr_segments = {}
        for start_freq_MHz,end_freq_MHz in self.rearr_unique_movements:
            try:
                start_freq_dict = self.rearr_segments[start_freq_MHz]
            except KeyError: # key does not exist yet so make the dict and store it
                self.rearr_segments[start_freq_MHz] = {}
                start_freq_dict = self.rearr_segments[start_freq_MHz]
            actions = [] # store the action for all channels
            for channel in range(self.main_window.card_settings['active_channels']):
                if channel == self.channel:
                    rearr_action_params = base_segment[channel].get_action_params()
                    freq_params = rearr_action_params['freq']
                    amp_params = rearr_action_params['amp']                   

                    for key,value in freq_params.items():
                        if key == 'start_freq_MHz':
                            freq_params[key] = [start_freq_MHz]
                        elif key == 'end_freq_MHz':
                            freq_params[key] = [end_freq_MHz]
                        elif key == 'function':
                            pass
                        else:
                            freq_params[key] = [freq_params[key][0]] # only want one tone so only keep the first entry in the list
                    for key,value in amp_params.items():
                        if key == 'function':
                            pass
                        else:
                            amp_params[key] = [amp_params[key][0]]

                    action = ActionContainer(rearr_action_params,self.main_window.card_settings,self.main_window.amp_adjusters[channel])
                    action.rearr = True
                    action.update_param(param='phase_behaviour',value=['manual'])
                    action.set_start_phase([np.random.random()*360]) # sets phase to random in degrees
                    actions.append(action)
                else:
                    actions.append(base_segment[channel])
            start_freq_dict[end_freq_MHz] = actions

        # make an empty action that can be used to pad out extra segments if not needed in sequential rearrangement mode
        # just use the last defined start_freq_MHz,end_freq_MHz because the freq doesn't matter
        actions = [] # store the action for all channels
        for channel in range(self.main_window.card_settings['active_channels']):

            # just make the same empty segment for all channels
            rearr_action_params = base_segment[channel].get_action_params()
            freq_params = rearr_action_params['freq']
            rearr_action_params['amp'] = {'function':'empty','null':[0]}

            for key,value in freq_params.items():
                if key == 'start_freq_MHz':
                    freq_params[key] = [start_freq_MHz]
                elif key == 'end_freq_MHz':
                    freq_params[key] = [end_freq_MHz]
                elif key == 'function':
                    pass
                else:
                    freq_params[key] = [freq_params[key][0]] # only want one tone so only keep the first entry in the list

            action = ActionContainer(rearr_action_params,self.main_window.card_settings,self.main_window.amp_adjusters[channel])
            action.rearr = True
            action.update_param(param='phase_behaviour',value=['manual'])
            action.set_start_phase([np.random.random()*360]) # sets phase to random in degrees
            actions.append(action)
        self.rearr_segments['empty'] = {}
        self.rearr_segments['empty']['empty'] = actions # still make dict 2 levels deep so that the rest of the code works

        print(self.rearr_segments)

    def get_number_rearrangement_segments_needed(self):
        """Returns the number of rearrangement segments that the need to be
        reserved for the RearrangementHandler to dynamically send data to
        at runtime. If self.mode == 'simultaneous'; this will be 1, otherwise
        the mode is 'sequential' and the returned number will be equal to the
        number of target rearrangement sites."""
        if self.mode == 'simultaneous':
            return 1
        else:
            return len(self.target_freq_MHz)
        
    def calculate_rearr_segment_data(self):
        """Takes the data from the ActionContainers for the rearrangement 
        segments and precalculates the int16 data to be sent to the card at 
        runtime. Each tone corresponding to the movement from one trap to 
        another is calculated. These tones will then be summed at runtime so 
        that the transfer is performed as quickly as possible whilst minimising
        the number of initial calculations needed.
        
        Returns
        -------
        None.
        """
        self.rearr_segments_data = {}

        i_seg = 1
        for start_freq_MHz in self.rearr_segments:
            try:
                start_freq_dict = self.rearr_segments_data[start_freq_MHz]
            except KeyError: # key does not exist yet so make the dict and store it
                self.rearr_segments_data[start_freq_MHz] = {}
                start_freq_dict = self.rearr_segments_data[start_freq_MHz]
            for end_freq_MHz in self.rearr_segments[start_freq_MHz]:
                segment = self.rearr_segments[start_freq_MHz][end_freq_MHz]
                segment_data = []
                for action_index, action in enumerate(segment):
                    if action.needs_to_calculate:
                        logging.debug(f'Calculating rearrangement movement {start_freq_MHz} MHz -> {end_freq_MHz} MHz '
                                      f'({i_seg}/{len(self.rearr_unique_movements)}) data, channel {action_index}.')
                        # action.set_start_phase(None)
                        action.calculate()
                    segment_data.append(np.int16(action.data*(2**15/self.main_window.awg.max_output_mV))) # convert to int16 here to save time later
                # can't multiplex here because we need to sum the rearrangement channel first
                if self.mode == 'sequential': # if mode is sequential, we can multiplex here to save time later.
                    if self.main_window.card_settings['active_channels'] > 1: # note we've assumed max 2 active channels
                        segment_data_multiplexed = np.empty((segment_data[0].size + segment_data[0].size,), dtype=segment_data[0].dtype)
                        segment_data_multiplexed[0::2] = segment_data[0]
                        segment_data_multiplexed[1::2] = segment_data[1]
                        segment_data = segment_data_multiplexed
                    else:
                        segment_data = segment_data[0] # remove from list because we have done the multiplexing (but only 1 channel)
                i_seg += 1
                self.rearr_segments_data[start_freq_MHz][end_freq_MHz] = segment_data
        print(self.rearr_segments_data)
    
    def generate_segment_ids(self):
        """Generates the potential segment ids to index segments.
        
        Uses the itertools Cartesian product method then selects the correct 
        strings after all permuations have been generated. This was ~ 4 orders 
        of magnitude faster than generating different permutations of strings 
        due to lack of repition, which failed when scaling up to higher trap
        numbers.
        
        Ids are ordered to prioritise the earlier traps in the `start_freq_MHz`
        attribute.
        
        Returns
        -------
        None. Generated occupations are stored as the attribute `occupations`.
        
        """
        if len(self.target_freq_MHz) > len(self.start_freq_MHz):
            logging.warning('target_freq_MHz was longer than start_freq_MHz. Discarding '
                            'extra target traps.')
            self.target_freq_MHz = self.target_freq_MHz[:len(self.start_freq_MHz)]

        # occupations = [list(i) for i in itertools.product([1, 0], repeat=len(self.start_freq_MHz))]
        # occupations = [(''.join(str(x) for x in y)) for y in occupations if sum(y) == len(self.target_freq_MHz)]
        final_occupations = []
        for occupation in reversed(range(2**(len(self.start_freq_MHz)))):
            occupation = '{:0{}b}'.format(occupation, len(self.start_freq_MHz))
            if 0 < occupation.count('1') <= len(self.target_freq_MHz):
                last_1_index = occupation.rindex('1')
                cut_final_occupations = [x[:last_1_index] for x in final_occupations]
                if occupation[:last_1_index] not in cut_final_occupations:
                    final_occupations.append(occupation)
                    print(occupation)
        self.occupations = final_occupations
        self.num_segments = len(self.occupations)
        
    def accept_string(self,string):
        """Takes the string recieved from Pydex and converts it to a matching 
        id string.
        
        If there are too few occupied traps, the correct id is generated by 
        successively switching bits from the right hand side to occupied until 
        the correct number of traps register as occupied.
        
        If there are too many occupied traps, the correct id is generated by 
        successively switching bits from the right hand side to unoccupied 
        until the correct number of traps register as occupied.

        Checks are minimal here to make runtime as quick as possible.
        
        This means that the minimum number of segment combinations need to be 
        precalculated, however this gain is minimal now that the segments are
        summed at runtime.
        
        Parameters
        ----------
        string : str
            Occupation string from Pydex. This should be a single string 
            containing only the characters '0' (unoccupied) and '1' (occupied) 
            where traps are indexed in the same order as the `start_freq_MHz` 
            attribute.
            
        Returns
        -------
        rearr_segment_data
            The rearrangement segment data prepared for immediate 
            uploaded to the AWG card immediately.
    
        """

        # discard any extra bits and add missing bits
        string = string[:len(self.start_freq_MHz)]+'0'*(len(self.start_freq_MHz)-len(string))
        
        final_string = ''
        for trap in string:
            if final_string.count('1') == len(self.target_freq_MHz):
                final_string += '0'
            elif final_string.count('1') >= string.count('1'):
                final_string += '1'
            else:
                final_string += trap

        # get occupation index then retrieve the movements to make based on this index
        rearr_segment_index = self.occupations.index(final_string)
        movements = self.rearr_movements[rearr_segment_index]

        logging.debug(f'Preparing rearrangement movements: {movements}.')

        # prepare data to be sent to the AWG
        rearr_channel_data = []
        segment_data = []
        for (start_freq_MHz, end_freq_MHz) in movements:
            if self.mode == 'simultaneous': # data has not yet been multiplexed so need to only get the correct channels data
                rearr_channel_data.append(self.rearr_segments_data[start_freq_MHz][end_freq_MHz][self.channel])
            else: # data has already been multiplexed so don't need to pick based on channel
                segment_data.append(self.rearr_segments_data[start_freq_MHz][end_freq_MHz])

        if self.mode == 'simultaneous': # all data should be in 1 segment so needs to be summed. It will also not have yet been multiplexed
            rearr_channel_data = np.add.reduce(rearr_channel_data, dtype=np.int16, axis=0) # faster than np.sum

            if self.main_window.card_settings['active_channels'] > 1:
                other_channel_data = self.rearr_segments_data[start_freq_MHz][end_freq_MHz][int(not self.channel)] # note here we expect only maximum of 2 channels
                segment_data = np.empty((rearr_channel_data.size + other_channel_data.size,), dtype=rearr_channel_data.dtype)
                segment_data[self.channel::2] = rearr_channel_data
                segment_data[int(not(self.channel))::2] = other_channel_data
            else:
                segment_data = rearr_channel_data
            return [segment_data] # returns as a list containing a single value

        else: # mode is sequential so return a list of segments to be sent to the AWG. Data will have already been mutliplexed when calculated.
            while len(segment_data) < self.get_number_rearrangement_segments_needed():
                segment_data.append(self.rearr_segments_data['empty']['empty'])
            return segment_data
    
    def get_occupation_freqs(self):
        """Returns the same information as the occupation array but instead 
        of binary strings saying whether to use a trap, returns the actual 
        trap positions
        
        Returns
        -------
        list of lists of floats
            The `occupation` attribute converted into the loaded trap 
            frequencies.
        
        """
        indicies = [list(i.start() for i in re.finditer('1', x)) for x in self.occupations]
        freqs = [[self.start_freq_MHz[i] for i in x] for x in indicies]
        return freqs

    def save_params(self,filename):
        """Saves the parameters needed to recreate this object to a 
        .txt file at the specified filename.
        
        Parameters
        ----------
        filename : str
            The filename to save the params file at.
        
        Returns
        -------
        None.
        """
        logging.info("Saving rearrangement params to '{}'.".format(filename))
              
        data = {}

        for param in params_to_save:
            data[param] = getattr(self,param)
            
        segments_data = []
        for segment in self.base_segments:
            segment_data = {}
            for i,action in enumerate(segment):
                action_params = action.get_action_params()
                for shared_segment_param in shared_segment_params:
                    segment_data[shared_segment_param] = action_params.pop(shared_segment_param)
                segment_data['Ch{}'.format(i)] = action_params
            segments_data.append(segment_data)
        
        data['base_segments'] = segments_data

        try:
            makedirs(path.dirname(filename),exist_ok=True)
        except FileExistsError as e:
            logging.warning('FileExistsError thrown when saving '
                            'rearrangement params file',e)
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        logging.info("Rearrangement params saved to '{}'".format(filename))

    def load_params(self,filename):
        """Loads the rearrangment parameters from a provided file to 
        set up the RearrangementHandler.
        
        Parameters
        ----------
        filename : str
            The location of the filename to load the rearrangement 
            parameters from.
        
        Returns
        -------
        None.

        """
        with open(filename, 'r') as f:
            data = json.load(f)

        for param in params_to_save:
            try:
                setattr(self,param,data[param])
            except KeyError: # allow older param files which didn't specify mode to skip this
                pass

        if len(self.target_freq_MHz) > len(self.start_freq_MHz):
            logging.warning('target_freq_MHz was longer than start_freq_MHz. Discarding '
                            'extra target traps.')
            self.target_freq_MHz = self.target_freq_MHz[:len(self.start_freq_MHz)]
        
        self.generate_segment_ids()
        self.create_actions(data['base_segments'])

    def update_params(self,params_dict):
        """Dictionary containing new values to update the attributes of 
        the `RearrangementHandler` to.
        
        Parameters
        ----------
        params_dict : dict
            Each key in the dict should be an attribute to update with 
            the value contained in the dict.

        Returns
        -------
        None.
        
        """
        for key,value in params_dict.items():
            setattr(self,key,value)

        self.generate_segment_ids()
        self.create_actions()


if __name__ == '__main__':
    rearr_settings = {'channel':0,
                      'start_freq_MHz':[100,102],
                      'target_freq_MHz':[101],
                      'rearr_amp':0.2,
                      'static_duration_ms':1,
                      'moving_duration_ms':1,
                      'moving_hybridicity':0,
                      'ramp_duration_ms':1,
                      'final_amp':1,
                      'alt_freqs':[100],
                      'alt_amp':1
                      }
    
    # rh = RearrangementHandler(rearr_settings,None)
    rr = RearrangementHandler(r"Z:\Tweezer\Code\Python 3.9\awg\rearrangement\default_rearr_params_AWG1.txt")
    print(rr.occupations)