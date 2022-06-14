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
        logging.info('TCP message recieved: "'+msg+'"')
        try:
            split_msg = msg.split('=')
            command = split_msg[0]
            arg = split_msg[1]
        except:
            logging.error("Could not parse command TCP message '{}'. Message ignored.".format(msg))
            return
        
        if 'load' in command:
            self.main_window.load_params(arg)
        elif command == 'save_all':
            self.save_params_file(arg)