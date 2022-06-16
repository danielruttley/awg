import logging
from .client import PyClient

class Networker():
    """Handles the PyClient and calls the correct methods of the parent 
    window class when the correct message is recieved via TCP message.
    
    """
    
    def __init__(self,main_window,ip_address,port,server_name):
        """Defines the class, including setting up the TCP server.

        Parameters
        ----------
        main_window : MainWindow
            The MainWindow class that is the parent of this object. Passing 
            through this reference allows the networker to call the relevant 
            methods of the MainWindow when the correct TCP message is 
            recieved.
        ip_address : str
            The IP address for the client to listen for messages from. This 
            should typically be the address of the PyDex PC.
        port : int
            The port of the TCP server.
        server_name : str
            The name of the TCP server.

        Returns
        -------
        None.

        """
        
        self.main_window = main_window
        
        self.tcp_client = PyClient(host=ip_address,port=int(port),name=server_name)
        self.tcp_client.start()
        self.tcp_client.textin.connect(self.recieved_tcp_msg)
        
    def recieved_tcp_msg(self,msg):
        """Takes the recieved TCP messages and performs the action that 
        corresponds to that TCP message.
        
        Accepted commands (in order of evaluation, * is a wildcard)
        -----------------------------------------------------------
        *load* = filename
            Loads the AWGparams file located in the path defined by filename 
            (str) into the interface. It then sends this data to the card.
        *save* = filename
            Saves the AWGparams loaded into the interface to the path defined 
            by filename (str). Note that the parameters in the interface are 
            saved; if these have been changed without updating the card, these
            might not be the settings currently on the card!
        *trigger* = None
            Forces a trigger on the AWG card.
        *rearrange* = rearrange_occupancy (e.g. 001001)
            Triggers the segment of the rearrangement step to be updated based 
            on the rearrange_occupancy (binary string)
        *set_data* = [channel (int), segment (int), param (str), value (float),
                      tone_index (int)]
            Updates the parameter of a given action with the supplied value. 
        
        Other commands are ignored.
        
        """
        # import time
        # start = time.time()
        msg = msg.replace('#','')
        logging.info('TCP message recieved: "'+msg+'"')
        try:
            split_msg = msg.split('=')
            command = split_msg[0]
            arg = split_msg[1]
        except:
            logging.error("Could not parse command TCP message '{}'. Message ignored.".format(msg))
            return
        
        if 'rearrange' in command:
            if all(x in '01' for x in arg):
                logging.info("Rearrangement string '{}' recieved.".format(arg))
                self.main_window.rearr_recieve(arg)
                # print('time',time.time()-start)
            else:
                logging.error("Invalid rearrangement string '{}' recieved. Message ignored.".format(arg))
                return
        elif 'set_data' in command:
            try:
                arg = eval(arg)
                self.main_window.data_recieve(*arg)
            except NameError:
                logging.error("NameError in data string '{}' (the param name must be contained in ''). Message ignored.".format(arg))
            except SyntaxError:
                logging.error("SyntaxError in data string '{}'. Message ignored.".format(arg))
        elif 'load' in command:
            self.main_window.load_params(arg)
        elif 'save' in command:
            self.main_window.save_params(arg)
        elif 'trigger' in command:
            logging.info('Triggering AWG as requested by TCP command.')
            self.main_window.awg.trigger()
        elif 'rearrange' in command:
            if all(x in '01' for x in arg):
                logging.info("Rearrangement string '{}' recieved.".format(arg))
                self.main_window.rearr_recieve(arg)
                # print('time',time.time()-start)
            else:
                logging.error("Invalid rearrangement string '{}' recieved. Message ignored.".format(arg))
                return
        else:
            logging.error("Command '{}' not recognised. Ignoring TCP message.".format(command))
            return