import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import inspect
import numpy as np

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
        
    """
    
    def __init__(self,rearr_settings,card_settings):
        """Create the `RearrangementHandler` object and assign its attributes.        

        Parameters
        ----------
        rearr_settings : dict
            Dictionary containing the attributes to assign to the rearrangement 
            handler. These should be the attributes contained in the following 
            section.
        card_settings : dict
            Dictionary containing the AWG card settings from the GUI 
            `MainWindow` class. These are passed directly to the generated 
            `ActionContainer` objects.
            
        Attributes
        ----------
        start_freqs_MHz : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            to prevent traps being moved through each other.
        target_freqs_MHz : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            (the same order as `start_freqs_MHz`) to prevent traps being moved 
             through each other.
            
            The rearrangment handler will aim to fill this array as much as 
            possible. If behaviour similar to the old use_all mode is desired,
            simply make the len(target_freqs_MHz) == len(start_freqs_MHz).

        Returns
        -------
        None.

        """
        
        for key, value in rearr_settings.items():
            setattr(self,key,value)
        
        self.card_settings = card_settings
        
        if len(self.target_freqs_MHz) > len(self.start_freqs_MHz):
            logging.warning('target_freqs_MHz was longer than start_freqs_MHz. Discarding '
                            'extra target traps.')
            self.target_freqs_MHz = self.target_freqs_MHz[:len(self.start_freqs_MHz)]
        
        self.generate_segment_ids()
    
    def generate_segment_ids(self):
        """Generates the potential segment ids to index segments.
        
        Uses the itertools Cartesian product method then selects the correct 
        strings after all permuations have been generated. This was ~ 4 orders 
        of magnitude faster than generating different permutations of strings 
        due to lack of repition, which failed when scaling up to higher trap
        numbers.
        
        Ids are ordered to prioritise the earlier traps in the `start_freqs_MHz`
        attribute.
        
        Returns
        -------
        None. Generated occupations are stored as the attribute `occupations`.
        
        """
        occupations = [list(i) for i in itertools.product([1, 0], repeat=len(self.start_freqs_MHz))]
        occupations = [(''.join(str(x) for x in y)) for y in occupations if sum(y) == len(self.target_freqs_MHz)]
        # print(occupations)
        self.occupations = occupations
        
    def get_segments(self):
        """Returned segments are structured the same as the list of segments 
        in the `MainWindow` class.
        
        The indicies of the returned list take the following structure:
            0:                  The initial starting segment with the traps at 
                                `start_freqs_MHz`
            1 -> (len(list)-3): The sweeping segments to `target_freqs_MHz` 
                                that should be selected from when rearranging.
            len(list)-2:        The ramping segment to take traps to 
                                post-rearrangement amplitude.
            len(list)-1:        The final static segment before the rest of the
                                routine.
                                
        The entry of each list is another list containing the different AWG
        channels `ActionContainer` objects.
        
        The returned list should be inserted at the start of the lists of 
        other segments generated in the GUI.
        
        Returns
        -------
        list of lists of `ActionContainers`
        
        """
        
        initial_segment = 1
        
        
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
            where traps are indexed in the same order as the `start_freqs_MHz` 
            attribute.
            
        Returns
        -------
        int
            Index of the rearrangement segment list to be inserted into the 
            rearrangement sweeping step.
    
        """
        recieved_string = string
        occupied_traps = sum(int(x) for x in string)
        
        if len(string) > len(self.start_freqs_MHz):
            logging.warning('The length of the string recieved is too long '
                            'for the number of starting traps. Discarding '
                            'extra bits.')
            string = string[:len(self.start_freqs_MHz)]
        elif len(string) < len(self.start_freqs_MHz):
            logging.warning('The length of the string recieved is too short '
                            'for the number of starting traps. Assuming '
                            'missing bits are unoccupied.')
            string = string + '0'*(len(self.start_freqs_MHz)-len(string))
        
        if occupied_traps < len(self.target_freqs_MHz):
            logging.info('Not enough initial traps loaded for successful '
                         'rearrangement. Filling as many traps as possible.')
            for i in range(len(string)):
                string = string[:-(i+1)] + '1'*(i+1)
                if sum([int(x) for x in string]) == len(self.target_freqs_MHz):
                    break
        elif occupied_traps > len(self.target_freqs_MHz):
            logging.info('Rearrangement traps overfilled. Dicarding some.')
            occupied_subtotal = 0
            for i in range(len(string)):
                occupied_subtotal += int(string[i])
                if occupied_subtotal == len(self.target_freqs_MHz):
                    break
            string = string[:i+1] + '0'*(len(self.start_freqs_MHz)-(i+1))

        logging.info('Processed recieved string {} as {}'.format(
                     recieved_string, string))
        
        print(self.occupations)
        
        return self.occupations.index(string)

if __name__ == '__main__':
    rearr_settings = {'channel':0,
                      'start_freqs_MHz':[100,102],
                      'target_freqs_MHz':[101],
                      'rearr_amp':0.2,
                      'static_duration_ms':1,
                      'moving_duration_ms':1,
                      'moving_hybridicity':0,
                      'ramp_duration_ms':1,
                      'final_amp':1,
                      'alt_freqs':[100],
                      'alt_amp':1
                      }
    
    rh = RearrangementHandler(rearr_settings,None)
    rh.generate_segment_ids()
    
    index = rh.accept_string('1101011111')
    print(index)