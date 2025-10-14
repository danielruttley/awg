import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import sys
from qtpy.QtWidgets import QApplication
from gui import MainWindow

network_settings = {"client_ip": "192.168.23.10",
                    "client_port": 8623,
                    "server_ip": "",
                    "server_port": 8736}

app = QApplication(sys.argv)
boss = MainWindow('AWG1','default_params_AWG1.awg',network_settings)
boss.show()
app.exec()