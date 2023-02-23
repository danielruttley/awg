import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import sys
from qtpy.QtWidgets import QApplication
from gui import MainWindow

network_settings = {"client_ip": "localhost",
                    "client_port": 8740,
                    "server_ip": "",
                    "server_port": 8741}

app = QApplication(sys.argv)
boss = MainWindow('AWG2','default_params_AWG2.awg',network_settings,testing=True)
boss.show()
app.exec()