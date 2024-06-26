import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import sys
from qtpy.QtWidgets import QApplication
from gui import MainWindow

network_settings = {"client_ip": "localhost",
                    "client_port": 8742,
                    "server_ip": "",
                    "server_port": 8743}

app = QApplication(sys.argv)
boss = MainWindow('AWG3','default_params_AWG3.awg',network_settings)
boss.show()
app.exec()