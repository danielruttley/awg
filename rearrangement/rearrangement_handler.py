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
    
    def __init__(self,start_freqs,target_freqs,card_settings):
        """        

        Parameters
        ----------
        start_freqs : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            to prevent traps being moved through each other.
        target_freqs : list of floats
            List of the initial starting array frequencies of the loading 
            array in MHz. Strings specifiying the loaded traps from the 
            Pydex `AtomChecker` should be in the same order as this list. The 
            traps should be in either ascending or descending frequency order 
            (the same order as `start_freqs`) to prevent traps being moved 
             through each other.
            
            The rearrangment handler will aim to fill this array as much as 
            possible. If behaviour similar to the old use_all mode is desired,
            simply make the len(target_freqs) == len(start_freqs).

        Returns
        -------
        None.

        """
        
        if len(target_freqs) > len(start_freqs):
            logging.warning('target_freqs was longer than start_freqs. Discarding '
                            'extra target traps.')
            target_freqs = target_freqs[:len(start_freqs)]
        
        self.start_freqs = start_freqs
        self.target_freqs = target_freqs
        
        self.generate_segment_ids()
    
    def generate_segment_ids(self):
        """Generates the potential segment ids to index segments.
        
        Uses the itertools Cartesian product method then selects the correct 
        strings after all permuations have been generated. This was ~ 4 orders 
        of magnitude faster than generating different permutations of strings 
        due to lack of repition, which failed when scaling up to higher trap
        numbers.
        
        Ids are ordered to prioritise the earlier traps in the `start_freqs`
        attribute.
        
        Returns
        -------
        None. Generated occupations are stored as the attribute `occupations`.
        
        """
        occupations = [list(i) for i in itertools.product([1, 0], repeat=len(self.start_freqs))]
        occupations = [(''.join(str(x) for x in y)) for y in occupations if sum(y) == len(self.target_freqs)]
        # print(occupations)
        self.occupations = occupations
        
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
            where traps are indexed in the same order as the `start_freqs` 
            attribute.
        """
        recieved_string = string
        occupied_traps = sum(int(x) for x in string)
        
        if len(string) > len(self.start_freqs):
            logging.warning('The length of the string recieved is too long '
                            'for the number of starting traps. Discarding '
                            'extra bits.')
            string = string[:len(self.start_freqs)]
        elif len(string) < len(self.start_freqs):
            logging.warning('The length of the string recieved is too short '
                            'for the number of starting traps. Assuming '
                            'missing bits are unoccupied.')
            string = string + '0'*(len(self.start_freqs)-len(string))
        
        if occupied_traps < len(self.target_freqs):
            logging.info('Not enough initial traps loaded for successful '
                         'rearrangement. Filling as many traps as possible.')
            for i in range(len(string)):
                string = string[:-(i+1)] + '1'*(i+1)
                if sum([int(x) for x in string]) == len(self.target_freqs):
                    break
        elif occupied_traps > len(self.target_freqs):
            logging.info('Rearrangement traps overfilled. Dicarding some.')
            occupied_subtotal = 0
            for i in range(len(string)):
                occupied_subtotal += int(string[i])
                if occupied_subtotal == len(self.target_freqs):
                    break
            string = string[:i+1] + '0'*(len(self.start_freqs)-(i+1))

        logging.info('Processed recieved string {} as {}'.format(
                     recieved_string, string))

if __name__ == '__main__':
    rh = RearrangementHandler([100,101,102,1,1,1],[100,101,102],None)
    rh.generate_segment_ids()
    
    start = time.time()
    rh.accept_string('1101011111')
    print(time.time()-start)