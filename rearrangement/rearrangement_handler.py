import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import inspect
import numpy as np
import re

from os import path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
# import actions as ac
import itertools
# from custom_logging import error, warning, info

import time

max_tone_num = 100

class RearrangementHandler():
    """Handler for rearrangement functionality. Takes strings from Pydex and 
    returns the index of the segment which the rearrangement step should be
    changed to.

    Attributes
    ----------
    segments : dict of lists of `ActionHandler`
        dictionary containing the `RearrangementHandler` segments which 
        are accessed on demand
    occupations : list
        the possible ids that can be used to access segments
    segments : int
        The indicies of the segments used in the rearrangement sweep, in 
        ascending order. When rearrangement is turned off, only the segment 
        at the start of this list will remain.
    steps : int or None
        The rearrangement steps. This parameter is set by the `MainWindow` 
        class to keep track of which steps should be modified when recieving 
        a TCP message.
        
        This value will default to [] if a step has not already been set.
    start_index : int
        the index of the first rearrangement segment
        
    """
    
    def __init__(self,start_freq_MHz,target_freq_MHz):
        """Create the `RearrangementHandler` object and assign its attributes.        

        Parameters
        ----------
        rearr_settings : dict
            Dictionary containing the attributes to assign to the rearrangement 
            handler. These should be the attributes contained in the following 
            section.
            
        Attributes
        ----------
        start_freq_MHz : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            to prevent traps being moved through each other.
        target_freq_MHz : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            (the same order as `start_freq_MHz`) to prevent traps being moved 
             through each other.
            
            The rearrangment handler will aim to fill this array as much as 
            possible. If behaviour similar to the old use_all mode is desired,
            simply make the len(target_freq_MHz) == len(start_freq_MHz).

        Returns
        -------
        None.

        """
        
        # for key, value in rearr_settings.items():
        #     setattr(self,key,value)
        
        self.start_freq_MHz = start_freq_MHz
        self.target_freq_MHz = target_freq_MHz
        self.start_index = 0
        self.steps = []
        
        if len(self.target_freq_MHz) > len(self.start_freq_MHz):
            logging.warning('target_freq_MHz was longer than start_freq_MHz. Discarding '
                            'extra target traps.')
            self.target_freq_MHz = self.target_freq_MHz[:len(self.start_freq_MHz)]
        
        self.generate_segment_ids()
        self.set_start_index(0)
        
    def get_state(self):
        """Gets the current state of the handler. This allows the settings to 
        be saved for the purposes of saving the overall AWG parameters.
        
        """
        return {'segments':self.segments}
    
    def set_state(self,state):
        """Sets the current state of the handler. This allows the settings to 
        be set from saved AWG parameters.
        
        """
        self.segments = state['segments']
    
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
        occupations = [list(i) for i in itertools.product([1, 0], repeat=len(self.start_freq_MHz))]
        occupations = [(''.join(str(x) for x in y)) for y in occupations if sum(y) == len(self.target_freq_MHz)]
        # print(occupations)
        self.occupations = occupations
        self.num_segments = len(self.occupations)
        
    def set_start_index(self,index):
        """Sets the index that the rearrangement has started from. Allows the 
        rearrangement handler to keep track of the used segments.
        
        Parameters
        ----------
        index : int
            The index to set the first segment to. Other segments are 
            incremented from this.
            
        """
        self.start_index = index
        self.segments = list(range(index,index+len(self.occupations)))
        
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
        int
            Index of the rearrangement segment list to be inserted into the 
            rearrangement sweeping step.
    
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
        
        if occupied_traps < len(self.target_freq_MHz):
            logging.debug('Not enough initial traps loaded for successful '
                          'rearrangement. Filling as many traps as possible.')
            for i in range(len(string)):
                string = string[:-(i+1)] + '1'*(i+1)
                if sum([int(x) for x in string]) == len(self.target_freq_MHz):
                    break
        elif occupied_traps > len(self.target_freq_MHz):
            logging.debug('Rearrangement traps overfilled. Dicarding some.')
            occupied_subtotal = 0
            for i in range(len(string)):
                occupied_subtotal += int(string[i])
                if occupied_subtotal == len(self.target_freq_MHz):
                    break
            string = string[:i+1] + '0'*(len(self.start_freq_MHz)-(i+1))

        segment = self.segments[self.occupations.index(string)]

        logging.debug('Processed recieved string {} as {} to get '
                     'rearrangement segment {}'.format(
                     recieved_string, string, segment))
        
        return segment
    
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
        # print(self.occupations)
        # print(indicies)
        # print(freqs)
        
        return freqs

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
    rh = RearrangementHandler([100,102,104,503],[100,102],None)
    rh.generate_segment_ids()
    
    index = rh.accept_string('1101011111')
    
    rh.get_occupation_freqs()