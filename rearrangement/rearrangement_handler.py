import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import inspect
import numpy as np
import re
import json

import itertools
import time

from os import path, makedirs
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from actions import ActionContainer, shared_segment_params

params_to_save = ['start_freq_MHz','target_freq_MHz','channel','segment']

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
                        print('optimise',segment_index)
                        channel_params['phase_behaviour'] = 'optimise'
                    channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
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
        """Creates duplicates of the necessary `ActionContainer` for 
        the rearrangement segments, one of which will be picked at 
        runtime."""
        base_segment = self.base_segments[self.segment]

        occupation_start_freqs = self.get_occupation_freqs()
        
        self.rearr_segments = []

        for start_freqs_MHz,occupation in zip(occupation_start_freqs,self.occupations):
            rr_seg = []
            for channel in range(self.main_window.card_settings['active_channels']):
                if channel == self.channel:
                    rearr_action_params = base_segment[channel].get_action_params()
                    freq_params = rearr_action_params['freq']
                    amp_params = rearr_action_params['amp']
                    
                    num_occupied_traps = occupation.count('1')

                    for key,value in freq_params.items():
                        if key == 'start_freq_MHz':
                            freq_params[key] = start_freqs_MHz[:num_occupied_traps]
                        elif key == 'end_freq_MHz':
                            freq_params[key] = self.target_freq_MHz[:num_occupied_traps]
                        elif key == 'function':
                            pass
                        else:
                            freq_params[key] = [freq_params[key][0]]*num_occupied_traps
                    for key,value in amp_params.items():
                        if key == 'function':
                            pass
                        else:
                            amp_params[key] = [amp_params[key][0]]*num_occupied_traps

                    print(occupation,freq_params)

                    action = ActionContainer(rearr_action_params,self.main_window.card_settings,self.main_window.amp_adjusters[channel])
                    action.rearr = True
                    rr_seg.append(action)
                else:
                    rr_seg.append(base_segment[channel])
            self.rearr_segments.append(rr_seg)
        
    def calculate_rearr_segment_data(self):
        """Takes the data from the ActionContainers for the 
        rearrangement segments and precalculates the int16 data 
        to be sent to the card at runtime so that the transfer 
        is performed as quickly as possible.
        
        Returns
        -------
        None.
        """
        self.rearr_segments_data = []

        for segment_index, segment in enumerate(self.rearr_segments):
            segment_data = []
            for action_index, action in enumerate(segment):
                if action.needs_to_calculate:
                    logging.debug('Calculating rearrangement segment R{} data, channel {}.'.format(segment_index,action_index))
                    action.set_start_phase(None)
                    action.calculate()
                segment_data.append(action.data)
            segment_data = self.main_window.awg.multiplex(segment_data)
            segment_data = self.main_window.awg.prepare_segment_data(segment_data)
            self.rearr_segments_data.append(segment_data)
    
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
        
        This means that the minimum number of segments are needed to be loaded 
        onto the card.
        
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
        recieved_string = string
        occupied_traps = sum(int(x) for x in string)
        
        if len(string) > len(self.start_freq_MHz):
            logging.warning('The length of the string recieved is too long '
                            'for the number of starting traps. Discarding '
                            'extra bits.')
            string = string[:len(self.start_freq_MHz)]
        elif len(string) < len(self.start_freq_MHz):
            logging.warning('The length of the string recieved is too short '
                            'for the number of starting traps. Assuming '
                            'missing bits are unoccupied.')
            string = string + '0'*(len(self.start_freq_MHz)-len(string))
        
        final_string = ''
        for trap in string:
            if final_string.count('1') == len(self.target_freq_MHz):
                final_string += '0'
            else:
                final_string += trap
        if final_string.count('1') == 0:
            final_string = '1' + final_string[1:]
        string = final_string

        # if occupied_traps < len(self.target_freq_MHz):
        #     logging.debug('Not enough initial traps loaded for successful '
        #                   'rearrangement. Filling as many traps as possible.')
        #     for i in range(len(string)):
        #         string = string[:-(i+1)] + '1'*(i+1)
        #         if sum([int(x) for x in string]) == len(self.target_freq_MHz):
        #             break
        # elif occupied_traps > len(self.target_freq_MHz):
        #     logging.debug('Rearrangement traps overfilled. Dicarding some.')
        #     occupied_subtotal = 0
        #     for i in range(len(string)):
        #         occupied_subtotal += int(string[i])
        #         if occupied_subtotal == len(self.target_freq_MHz):
        #             break
        #     string = string[:i+1] + '0'*(len(self.start_freq_MHz)-(i+1))

        rearr_segment_index = self.occupations.index(string)

        logging.debug('Processed recieved string {} as {} to get '
                      'rearrangement segment R{}'.format(
                       recieved_string, string, rearr_segment_index))

        try:
            return self.rearr_segments_data[rearr_segment_index]
        except AttributeError:
            logging.error('Could not return rearrangement segment data '
                          'because it has not yet been calculated.')
    
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
            setattr(self,param,data[param])

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