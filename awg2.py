import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)
# logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
from qtpy.QtWidgets import QApplication
from gui import MainWindow

network_settings = {"client_ip": "129.234.190.164",
                    "client_port": 8628,
                    "server_ip": "",
                    "server_port": 8629}

app = QApplication(sys.argv)
boss = MainWindow('AWG2','default_params_AWG2.awg',network_settings)
boss.show()
app.exec()