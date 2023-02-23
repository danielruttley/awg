import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import sys
import os
import numpy as np
import json
import time
from copy import deepcopy

os.system("color")

#from qtpy.QtCore import QThread,Signal,Qt
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QApplication,QMainWindow,QVBoxLayout,QWidget,
                            QAction,QListWidget,QFormLayout,QComboBox,QLineEdit,
                            QTextEdit,QPushButton,QFileDialog,QAbstractItemView,
                            QGridLayout,QLabel,QHBoxLayout,QCheckBox,QFrame,QListWidgetItem)
from qtpy.QtGui import QIcon,QColor

import pyqtgraph as pg

from . import qrc_resources

from .helpers import QHLine, QVLine
from .secondary_windows import (CardSettingsWindow, SegmentCreationWindow,
                                StepCreationWindow, RearrSettingsWindow,
                                AmpAdjusterSettingsWindow)

if __name__ == '__main__':
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

main_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from actions import ActionContainer, AmpAdjuster2D, shared_segment_params
from rearrangement import RearrangementHandler
from awg import AWG
from networking.networker import Networker

num_plot_points = 100

color_cs = '#f5b7a6'
color_rb = '#bdd7ee'
color_loop_until_trigger = '#ffff99'
color_rearr_off = '#e04848'
color_rearr_on = '#05a815'
color_rearr_other_segment = '#b8f2be'
color_rearr_segment = '#92f09b'
color_needs_to_calculate = '#dfbbf0'
color_loop_background = '#659ffc'
color_phase_jump = '#ff000020'

dicts_to_save = ['card_settings','amp_adjuster_settings']
datagen_settings_to_save = ['button_couple_steps_segments','button_prevent_freq_jumps',
                            'button_prevent_amp_jumps','button_freq_adjust_looped_segments',
                            'button_prevent_phase_jumps']

class MainWindow(QMainWindow):
    """Acts as controller for the AWG program.

    Attributes
    ----------
    segments : list of lists
        List of segments to upload to the AWG. Each entry in the list is 
        itself a list which contains the `ActionContainer` classes for each 
        channel in the segments. 
        
        Segments will be uploaded to in the order they are present in this 
        list. Interleaving of channel data is handled in the `AWG` class.
    steps: list of dicts
        List of steps to be uploaded to the AWG. The steps are uploaded with 
        the indicies present in this list.
    card_settings : dict
        Global card settings for the AWG, including the number of active 
        channels and the sample rate. This dictionary is passed through to 
        the `ActionContainer` objects when they are generating their data.
    amp_adjusters : list of AmpAdjuster2D
        AmpAdjusters for the different AWG channels. These are objects defined 
        once for each channel and then passed through to the ActionContainer 
        classes so that they can convert their amplitudes to mV.
        
        Even if amp_adjust is turned off, the AmpAdjuster classes are still 
        used (and just don't adjust the amplitudes depending on the frequency).
    rr : RearrangementHandler or None
        The `RearrangementHandler` object which generates the parameters for 
        rearrangement actions. If rearrangement is disabled, this attribute is 
        set to None.
        
        When rearrangement parameters are changed or rearrangement is toggled 
        this object will be recreated.
    w : RearrSettingsWindow or CardSettingsWindow or StepCreationWindow or SegmentCreationWindow
        The external settings window currently open in the GUI. All these 
        windows share the same attribute name so that only one can be open
        at once. This prevents clashes if one changes some information that 
        the other relies on.
    testing : bool
        Whether the GUI is in testing mode or not. Testing mode prevents 
        data being sent to the card which otherwise causes a memory violation
        error if no card is detected.
        
    """
    def __init__(self,name='AWG1',params_filename='default_params_AWG1.awg',
                    network_settings={'client_ip': 'localhost',
                                    "client_port": 5063,
                                    "server_ip": "",
                                    "server_port": 5064},
                    testing=False):
        super().__init__()

        self.name = name        
        self.last_AWGparam_folder = '.'
        self.freq_setting_segments = None
        self.testing = testing
        
        self.card_settings = {'active_channels':1}

        self.setWindowTitle("{} control".format(self.name))
        self.layout = QVBoxLayout()

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        
        self._create_menu_bar()
        self._create_awg_header()
        self._create_columns()
        self._create_layout_datagen()
        self._create_layout_autoplotter()
        self._create_calculate_buttons()

        self.update_label_awg()
        
        self.amp_adjusters = [None,None]
        self.segments = []
        self.steps = []
        
        self.load_params(params_filename,update_list_when_loaded=False)
        self.networker = Networker(main_window=self,**network_settings)
        self.rr = RearrangementHandler(self,main_directory+r"\rearrangement\default_rearr_params_{}.awgrr".format(name))

        self.calculate_send()

    def _create_menu_bar(self):
        action_load_params = QAction(self)
        action_load_params.setText("Load AWGparam")

        action_save_params = QAction(self)
        action_save_params.setText("Save AWGparam")
        
        action_load_params.triggered.connect(self.load_params_dialogue)
        action_save_params.triggered.connect(self.save_params_dialogue)

        action_load_rearr_params = QAction(self)
        action_load_rearr_params.setText("Load AWGrearrparam")

        action_save_rearr_params = QAction(self)
        action_save_rearr_params.setText("Save AWGrearrparam")

        action_load_rearr_params.triggered.connect(self.load_rearr_params_dialogue)
        action_save_rearr_params.triggered.connect(self.save_rearr_params_dialogue)
        
        menu_bar = self.menuBar()
        menu_main = menu_bar.addMenu("Menu")
        menu_main.addAction(action_load_params)
        menu_main.addAction(action_save_params)
        menu_main.addSeparator()
        menu_main.addAction(action_load_rearr_params)
        menu_main.addAction(action_save_rearr_params)


    def _create_awg_header(self):
        layout = QGridLayout()

        self.label_awg = QLabel(self.name)
        layout.addWidget(self.label_awg,0,0,2,2)

        self.button_card_settings = QPushButton('card settings')
        self.button_card_settings.clicked.connect(self.open_card_settings_window)
        layout.addWidget(self.button_card_settings,0,2,1,2)

        self.button_amp_adjuster_settings = QPushButton('AmpAdjuster settings')
        self.button_amp_adjuster_settings.clicked.connect(self.open_amp_adjuster_settings_window)
        layout.addWidget(self.button_amp_adjuster_settings,1,2,1,1)

        self.button_pydex_settings = QPushButton('PyDex settings')
        self.button_pydex_settings.setEnabled(False)
        layout.addWidget(self.button_pydex_settings,1,3,1,1)

        self.layout.addLayout(layout)
        self.layout.addWidget(QHLine())
    
    def _create_columns(self):
        layout = QHBoxLayout()

        self.layout_datagen = QVBoxLayout()
        layout.addLayout(self.layout_datagen)

        layout.addWidget(QVLine())

        self.layout_autoplotter = QVBoxLayout()
        layout.addLayout(self.layout_autoplotter)

        self.layout.addLayout(layout)

    def _create_layout_datagen(self):
        layout_step_control = QHBoxLayout()
    
        self.button_trigger = QPushButton("Trigger AWG")
        self.button_trigger.clicked.connect(self.awg_trigger)
        layout_step_control.addWidget(self.button_trigger)
    
        self.button_check_current_step = QPushButton("Check current step: ? (segment: ?)")
        self.button_check_current_step.clicked.connect(self.awg_update_current_step)
        layout_step_control.addWidget(self.button_check_current_step)

        self.layout_datagen.addLayout(layout_step_control)
        
        self.layout_datagen.addWidget(QHLine())
        
        layout_prevent_jumps = QGridLayout()
        self.button_couple_steps_segments = QCheckBox("Couple steps with segments")
        self.button_couple_steps_segments.clicked.connect(self.couple_steps_segments)
        self.button_couple_steps_segments.setChecked(True)
        self.button_couple_steps_segments.setEnabled(False)
        layout_prevent_jumps.addWidget(self.button_couple_steps_segments,0,0,1,1)

        self.button_prevent_freq_jumps = QCheckBox("Prevent frequency jumps \n(will not edit rearr. segs.)")
        self.button_prevent_freq_jumps.setEnabled(False)
        self.button_prevent_freq_jumps.setChecked(False)
        # self.button_prevent_freq_jumps.clicked.connect(self.prevent_freq_jumps)
        self.button_prevent_freq_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_freq_jumps,1,0,1,1)

        self.button_prevent_amp_jumps = QCheckBox("Prevent amplitude jumps \n(will not edit rearr. segs.)")
        self.button_prevent_amp_jumps.setEnabled(False)
        # self.button_prevent_amp_jumps.clicked.connect(self.prevent_amp_jumps)
        self.button_prevent_amp_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_amp_jumps,2,0,1,1)

        # layout_prevent_jumps.addWidget(QLabel("Prevent phase jumps:"),0,1,1,1)
        
        self.button_freq_adjust_looped_segments = QCheckBox("Frequency adjust looped segments")
        # self.button_freq_adjust_looped_segments.clicked.connect(self.freq_adjust_looped_segments)
        self.button_freq_adjust_looped_segments.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_freq_adjust_looped_segments,1,1,1,1)
        
        self.button_prevent_phase_jumps = QCheckBox("Enforce phase continuity between segments")
        self.button_prevent_phase_jumps.setEnabled(False)
        # layout_prevent_jumps.addWidget(self.button_prevent_phase_jumps,2,1,1,1)

        self.layout_datagen.addLayout(layout_prevent_jumps)

        self.layout_datagen.addWidget(QHLine())
        
        rearr_layout = QHBoxLayout()
        self.button_rearr = QPushButton("Rearrangement OFF")
        self.button_rearr.setCheckable(True)
        self.button_rearr.setStyleSheet('background-color: '+color_rearr_off)
        self.button_rearr.toggled.connect(self.rearr_toggle)
        rearr_layout.addWidget(self.button_rearr)
        
        self.button_rearr_settings = QPushButton('rearrangement settings')
        rearr_layout.addWidget(self.button_rearr_settings)
        self.button_rearr_settings.clicked.connect(self.open_rearr_settings_window)
        self.layout_datagen.addLayout(rearr_layout)

        self.layout_datagen.addWidget(QHLine())
        
        layout_segment_title = QHBoxLayout()
        layout_segment_title.addWidget(QLabel('<h3>segments<\h3>'))
        self.button_condense_segment_data = QCheckBox("Condense segment data")
        self.button_condense_segment_data.clicked.connect(self.write_segment_list_labels)
        layout_segment_title.addWidget(self.button_condense_segment_data)
        self.layout_datagen.addLayout(layout_segment_title)

        layout_segment_buttons = QHBoxLayout()

        self.button_segment_add = QPushButton()
        self.button_segment_add.setIcon(QIcon(":add.svg"))
        self.button_segment_add.clicked.connect(self.segment_add_dialogue)
        layout_segment_buttons.addWidget(self.button_segment_add)

        self.button_segment_remove = QPushButton()
        self.button_segment_remove.setIcon(QIcon(":subtract.svg"))
        self.button_segment_remove.clicked.connect(self.segment_remove)
        layout_segment_buttons.addWidget(self.button_segment_remove)

        self.button_segment_edit = QPushButton()
        self.button_segment_edit.setIcon(QIcon(":edit.svg"))
        self.button_segment_edit.clicked.connect(self.segment_edit_dialogue)
        layout_segment_buttons.addWidget(self.button_segment_edit)
        
        self.button_segment_up = QPushButton()
        self.button_segment_up.setIcon(QIcon(":up.svg"))
        self.button_segment_up.clicked.connect(self.segment_up)
        layout_segment_buttons.addWidget(self.button_segment_up)

        self.button_segment_down = QPushButton()
        self.button_segment_down.setIcon(QIcon(":down.svg"))
        self.button_segment_down.clicked.connect(self.segment_down)
        layout_segment_buttons.addWidget(self.button_segment_down)

        self.layout_datagen.addLayout(layout_segment_buttons)

        self.list_segments = QListWidget()
        self.list_segments.itemDoubleClicked.connect(self.segment_edit_dialogue)
        self.layout_datagen.addWidget(self.list_segments)

        self.layout_datagen.addWidget(QHLine())

        self.layout_datagen.addWidget(QLabel('<h3>steps<\h3>'))

        layout_step_buttons = QHBoxLayout()

        self.button_step_add = QPushButton()
        self.button_step_add.setIcon(QIcon(":add.svg"))
        self.button_step_add.clicked.connect(self.step_add_dialogue)
        layout_step_buttons.addWidget(self.button_step_add)

        self.button_step_remove = QPushButton()
        self.button_step_remove.setIcon(QIcon(":subtract.svg"))
        self.button_step_remove.clicked.connect(self.step_remove)
        layout_step_buttons.addWidget(self.button_step_remove)

        self.button_step_edit = QPushButton()
        self.button_step_edit.setIcon(QIcon(":edit.svg"))
        self.button_step_edit.clicked.connect(self.step_edit)
        layout_step_buttons.addWidget(self.button_step_edit)
        
        self.button_step_up = QPushButton()
        self.button_step_up.setIcon(QIcon(":up.svg"))
        self.button_step_up.clicked.connect(self.step_up)
        layout_step_buttons.addWidget(self.button_step_up)

        self.button_step_down = QPushButton()
        self.button_step_down.setIcon(QIcon(":down.svg"))
        self.button_step_down.clicked.connect(self.step_down)
        layout_step_buttons.addWidget(self.button_step_down)

        self.layout_datagen.addLayout(layout_step_buttons)

        self.list_steps = QListWidget()
        self.list_steps.itemDoubleClicked.connect(self.list_step_toggle_next_condition)
        self.layout_datagen.addWidget(self.list_steps)
       
    def _create_layout_autoplotter(self):
        """Creates/updates the layout for the autoplotting graphs. The layout 
        is intially cleared; this allows for the number of graphs to be 
        dynamically updated as more/less channels are used.        

        Returns
        -------
        None.

        """
        self._clear_layout(self.layout_autoplotter)
        self.layout_autoplotter.addWidget(QLabel('<h2>Autoplotter™</h2>'))
        
        layout_autoplot_options = QHBoxLayout()
        
        self.button_autoplot = QCheckBox("Autoplot")
        self.button_autoplot.clicked.connect(self.plot_autoplot_graphs)
        # self.button_autoplot.setChecked(True)
        layout_autoplot_options.addWidget(self.button_autoplot)
        
        self.button_autoplot_condense_rearr = QCheckBox("Condense rearrange segments")
        self.button_autoplot_condense_rearr.setChecked(True)
        self.button_autoplot_condense_rearr.setEnabled(False)
        # self.button_autoplot_condense_rearr.clicked.connect(self.plot_autoplot_graphs)
        # layout_autoplot_options.addWidget(self.button_autoplot_condense_rearr) # don't show on GUI because this does nothing anymore
        
        self.button_autoplot_amp_mV = QCheckBox("Show amplitude in mV")
        self.button_autoplot_amp_mV.clicked.connect(self.plot_autoplot_graphs)
        layout_autoplot_options.addWidget(self.button_autoplot_amp_mV)

        self.layout_autoplotter.addLayout(layout_autoplot_options)
        
        layout_channel_columns = QHBoxLayout()
        
        self.freq_plots = []
        self.amp_plots = []
        
        for channel in range(self.card_settings['active_channels']):
            layout = QVBoxLayout()
            layout.addWidget(QLabel('<h3>Channel {}</h3>'.format(channel)))

            freq_plot = pg.plot(labels={'left': ('frequency (MHz)'), 'bottom': ('duration (ms)'),'top': ('segment')})
            freq_plot.setBackground(None)
            freq_plot.getAxis('left').setTextPen('k')
            freq_plot.getAxis('bottom').setTextPen('k')
            freq_plot.getAxis('top').setTextPen('k')
            # freq_plot.setRange(xRange=[-1,1],yRange=[-1,1])
            freq_plot.enableAutoRange()
    
            layout.addWidget(freq_plot)
            self.freq_plots.append(freq_plot)
    
            amp_plot = pg.plot(labels={'left': ('amplitude',''), 'bottom': ('duration (ms)'),'top': ('segment')})
            amp_plot.setBackground(None)
            amp_plot.getAxis('left').setTextPen('k')
            amp_plot.getAxis('bottom').setTextPen('k')
            amp_plot.getAxis('top').setTextPen('k')
            # self.amp_plot.setRange(xRange=[-1,1],yRange=[-1,1])
            amp_plot.enableAutoRange()
    
            layout.addWidget(amp_plot)
            self.amp_plots.append(amp_plot)
            
            layout_channel_columns.addLayout(layout)
            layout_channel_columns.addWidget(QVLine())
        
        self.layout_autoplotter.addLayout(layout_channel_columns)
        
    def _create_calculate_buttons(self):
        layout = QVBoxLayout()
        
        self.button_calculate_send = QPushButton('Calculate and send data to card')
        self.button_calculate_send.clicked.connect(self.calculate_send)
        layout.addWidget(self.button_calculate_send)

        self.button_calculate_csv = QPushButton('Calculate and save segment data to .csv files')
        self.button_calculate_csv.clicked.connect(self.export_segments_to_csv_dialogue)
        layout.addWidget(self.button_calculate_csv)

        self.layout.addWidget(QHLine())
        self.layout.addLayout(layout)
    
    def _clear_layout(self,layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self._clear_layout(item.layout())
                    
    def load_params(self,filename,update_list_when_loaded=True):
        """Load the params from a saved .txt file.
        
        If rearrangement is active when loading in the file, it is disabled 
        to remove all but the first rearrangement segment, then re-enabled to
        ensure the RearrangementHandler is set up correctly.
        
        """
        logging.info("Loading AWG params from '{}'.".format(filename))
        
        with open(filename, 'r') as f:
            data = json.load(f)
        
        for name in dicts_to_save:
            try:
                if data[name] != getattr(self,name):
                    logging.debug('Updating attribute {}.'.format(name))
                    setattr(self,name,data[name])
            except AttributeError:
                setattr(self,name,data[name])
                    
        self.update_card_settings()
        self.set_datagen_settings(data['datagen_settings'])
        self._create_layout_autoplotter()
        self.set_amp_adjuster_settings(update_segment_list=False)
        
        self.segment_add_all(data['segments'])

        self.steps = data['steps']

        if self.button_rearr.isChecked():
            try:
                for step in self.steps:
                    step['segment'] += len(self.rr.base_segments)
            except AttributeError:
                pass

        if update_list_when_loaded:
            self.segment_list_update()

        logging.debug("Finished loading AWG params from '{}'.".format(filename))
        # self.calculate_send()
        
    def load_params_dialogue(self):
        filename = QFileDialog.getOpenFileName(self, 'Load AWGparam',self.last_AWGparam_folder,"AWG parameters (*.awg)")[0]
        if filename != '':
            self.load_params(filename)
            self.last_AWGparam_folder = os.path.dirname(filename)
    
    def save_params(self,filename):
        logging.info("Saving AWG params to '{}'.".format(filename))
              
        data = {}
        
        self.refresh_amp_adjuster_settings()
        
        for name in dicts_to_save:
            data[name] = getattr(self,name)
            
        data['datagen_settings'] = self.get_datagen_settings()
            
        segments_data = []
        for segment in self.segments:
            if segment not in self.rr.base_segments:
                segment_data = {}
                for i,action in enumerate(segment):
                    action_params = action.get_action_params()
                    for shared_segment_param in shared_segment_params:
                        segment_data[shared_segment_param] = action_params.pop(shared_segment_param)
                    segment_data['Ch{}'.format(i)] = action_params
                segments_data.append(segment_data)
        
        data['segments'] = segments_data

        print(self.get_non_rearr_steps())
        
        data['steps'] = self.get_non_rearr_steps()

        try:
            os.makedirs(os.path.dirname(filename),exist_ok=True)
        except FileExistsError as e:
            logging.warning('FileExistsError thrown when saving AWGParams file',e)
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        logging.info('AWGparam saved to "{}"'.format(filename))

    def save_params_dialogue(self):
        filename = QFileDialog.getSaveFileName(self, 'Save AWGparam',self.last_AWGparam_folder,"AWG parameters (*.awg)")[0]
        if filename != '':
            self.save_params(filename)
            self.last_AWGparam_folder = os.path.dirname(filename)
        
    def load_rearr_params(self,filename):
        logging.info('Loading rearrangement from "{}"'.format(filename))

        rearr_on = self.button_rearr.isChecked()
        self.button_rearr.blockSignals(True)
        self.button_rearr.setChecked(False)
        self.rearr_toggle()

        self.rr.load_params(filename)
        
        if rearr_on:
            self.button_rearr.setChecked(True)
            self.rearr_toggle()
        self.button_rearr.blockSignals(False)

        logging.info('Rearrangement loaded from "{}"'.format(filename))
        
    def load_rearr_params_dialogue(self):
        filename = QFileDialog.getOpenFileName(self, 'Load AWGrearrparam',self.last_AWGparam_folder,"AWG rearrangement parameters (*.awgrr)")[0]
        if filename != '':
            self.load_rearr_params(filename)
            self.last_AWGparam_folder = os.path.dirname(filename)

    def save_rearr_params_dialogue(self):
        filename = QFileDialog.getSaveFileName(self, 'Save AWGrearrparam',self.last_AWGparam_folder,"AWG rearrangement parameters (*.awgrr)")[0]
        if filename != '':
            self.rr.save_params(filename)
            self.last_AWGparam_folder = os.path.dirname(filename)
            
    def open_rearr_settings_window(self):
        self.w = RearrSettingsWindow(self)
        self.w.show()
        
    def get_datagen_settings(self):
        settings = {}
        for name in datagen_settings_to_save:
            button = getattr(self,name)
            settings[name] = button.isChecked()
        return settings
    
    def set_datagen_settings(self,settings):
        """Set the datagen GUI settings when loading in all the parameters 
        with the load_all function. Signals from the objects are blocked 
        whilst loading with this method to prevent them triggering as each 
        of them are set (they are all checked when the segment list is updated 
        at the end of load_all).
        
        Returns
        -------
        None.
        
        """
        for name,value in settings.items():
            if name != 'button_prevent_freq_jumps':
                button = getattr(self,name)
                button.blockSignals(True)
                button.setChecked(value)
                button.blockSignals(False)
        
    def update_rearr_settings(self,rearr_settings):
        """Update the rearrangement settings with a new dictionary of 
        parameters to pass through to the rearrangement handler. Called 
        when the `RearrSettingsWindow` saves the parameters.

        Parameters
        ----------
        rearr_settings : dict
            Dictionary to update the rearrangement settings to.

        Returns
        -------
        None. The attributes of the `RearrangmentHandler` are modified.

        """
        rearr_on = self.button_rearr.isChecked()

        self.button_rearr.blockSignals(True)
        self.button_rearr.setChecked(False)
        self.rearr_toggle()

        self.rr.update_params(rearr_settings)
        
        if rearr_on:
            self.button_rearr.setChecked(True)
            self.rearr_toggle()
        self.button_rearr.blockSignals(False)

        self.w = None
    
    def calculate_all_segments(self):
        logging.debug('Calculating all segments.')
        for segment_index, segment in enumerate(self.segments):
            for action_index, action in enumerate(segment):
                if action.needs_to_calculate:
                    logging.debug('Calculating segment {}, channel {}.'.format(segment_index,action_index))
                    if segment_index == 0:
                        action.set_start_phase(None)
                    else:
                        end_phase = self.segments[segment_index-1][action_index].end_phase
                        action.set_start_phase(end_phase)
                    action.calculate()
        if self.button_rearr.isChecked():
            self.rr.calculate_rearr_segment_data()
        # self.segment_list_update()

    def update_label_awg(self):
        self.label_awg.setText('<h2>{}</h2>'.format(self.name))
        self.label_awg.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if self.name == 'AWG1':
            color = color_cs
        elif self.name == 'AWG2':
            color = color_rb
        else:
            color = '#ffffff'
        self.label_awg.setStyleSheet('border: 1px solid black; background: {}'.format(color))

    def segment_add_dialogue(self):
        self.w = SegmentCreationWindow(self)
        self.w.show()

    def segment_remove(self):
        """Deletes the selected segments from the segment list. All segments 
        will a later index now have a new index, so they will be flagged that 
        they need to retransfer to the AWG card.
        
        If the currently selected row is one of the rearrangement rows, this is
        not deleted. Rearrangement should be deactivated first.
        
        If rearrangement is active and the segment is deleted before the 
        rearrangement segments, the rearrangement segments are incremented by 
        -1.
        
        """
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) != 0:
            selectedRows.sort(reverse=True)
            for row in selectedRows:
                if self.segments[row] in self.rr.base_segments:
                    logging.error('Cannot delete a rearrangement segment. '
                                  'Deactivate rearrangement first.')
                else:
                    try:
                        del self.segments[row]
                        for segment in self.segments[row:]:
                            for action in segment:
                                action.needs_to_transfer = True
                        if self.button_couple_steps_segments.isChecked():
                            step_index = self.get_step_from_segment(row)
                            del self.steps[step_index]
                            for step in self.steps[step_index:]:
                                step['segment'] = step['segment'] - 1
                    except IndexError:
                        pass
            self.segment_list_update()

    def segment_up(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be moved.')
            return
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be moved at once.')
            return
        else:
            currentRow = selectedRows[0]
            if currentRow == 0:
                logging.error('Cannot move the first segment up.')
                return
            
            segment_index = int(self.list_segments.currentItem().text().split(' ')[0])
            segment = self.segments[segment_index]

            if self.rr != None:
                if segment in self.rr.base_segments:
                    logging.error('Cannot move rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
                elif self.segments[segment_index-1] in self.rr.base_segments:
                    logging.error('Cannot move segments through the '
                                  'rearrangement segments.')
                    return
            if self.button_couple_steps_segments.isChecked():
                step_index = self.get_step_from_segment(currentRow)
                self.steps[step_index]['segment'] = self.steps[step_index]['segment'] - 1
                self.steps[step_index-1]['segment'] = self.steps[step_index-1]['segment'] + 1
                self.steps[step_index],self.steps[step_index-1] = self.steps[step_index-1],self.steps[step_index]
            self.segments[segment_index],self.segments[segment_index-1] = self.segments[segment_index-1],self.segments[segment_index]
            for segment in self.segments[segment_index-1:segment_index+1]:
                for action in segment:
                    action.needs_to_transfer = True
            self.segment_list_update()
            self.list_segments.setCurrentRow(currentRow-1)

    def segment_down(self):
        """Moves the selected segment in the list attribute `list_segments` 
        down one row. Rearrangement steps are not allowed to move to prevent 
        complications if the steps were to become seperated.
        
        The moved segments are marked that they need to transfer to the AWG 
        because they now have different indicies than they did before.
        
        """
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be moved.')
            return
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be moved at once.')
            return
        else:
            currentRow = selectedRows[0]
            if currentRow == self.list_segments.count()-1:
                logging.error('Cannot move the final segment down.')
                return
            
            segment_index = int(self.list_segments.currentItem().text().split(' ')[0])
            segment = self.segments[segment_index]

            if self.rr != None:
                if segment in self.rr.base_segments:
                    logging.error('Cannot move rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
                elif self.segments[segment_index+1] in self.rr.base_segments:
                    logging.error('Cannot move segments through the '
                                  'rearrangement segments.')
                    return
            if self.button_couple_steps_segments.isChecked():
                step_index = self.get_step_from_segment(currentRow)
                self.steps[step_index]['segment'] = self.steps[step_index]['segment'] + 1
                self.steps[step_index+1]['segment'] = self.steps[step_index+1]['segment'] - 1
                self.steps[step_index],self.steps[step_index+1] = self.steps[step_index+1],self.steps[step_index]
            self.segments[segment_index],self.segments[segment_index+1] = self.segments[segment_index+1],self.segments[segment_index]
            for segment in self.segments[segment_index:segment_index+2]:
                for action in segment:
                    action.needs_to_transfer = True
            self.segment_list_update()
            self.list_segments.setCurrentRow(currentRow+1)
    
    def segment_add_all(self,segment_params_list):
        """Deletes the current segment list and adds new ones based on the 
        supplied parameters. Skips all the checks like frequency continuity 
        until the end.

        Rearrangement segments are added back in if needed.
        
        Parameters
        ----------
        segment_params_list : list
              Each entry should be a list of parameters like would be used 
              in the segment_add function.
              
        """
        self.segments = []
        for segment_params in segment_params_list:
            segment = []
            for channel in range(self.card_settings['active_channels']):
                channel_params = {}
                for shared_segment_param in shared_segment_params:
                    channel_params[shared_segment_param] = segment_params[shared_segment_param]
                channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
                action = ActionContainer(channel_params,self.card_settings,self.amp_adjusters[channel])
                segment.append(action)
            self.segments.append(segment)
        
        self.rearr_toggle()
    
    def segment_add(self,segment_params,editing_segment=None):
        """Add a new segment to the segment list or edits an exisiting 
        segment based on the kwargs in the segment_params dict.
        
        When adding a segment all segments after this are set to need to be 
        retransferred to the AWG card because they will have changed index.
        
        Segments cannot be added in the middle of the rearrange segments; they
        will be added at the end instead.
        
        If rearrangement is active and the segment is added before the 
        rearrangement segments, the rearrangement segments are incremented by 
        1.
        
        If a rearrangement segment is edited, then all the rearrangement 
        segments will be edited. This means that a parameter for all the 
        rearrangement segments can be edited by sending the parameter to just 
        one of the segments. This is done by deactivating rearrangement, 
        editing just the base segment, and then reactivating rearrangement.

        Parameters
        ----------
        segment_params : dict
            Dict of segment params for the different channels of the segment.
            Keys should be 'Ch0', 'Ch1', ... and values should be parameter
            dictionaries to be passed though to the `ActionContainer` object; 
            see that docstring for required format.
            
            There should also be a key `duration_ms` which specifies the 
            duration of the action: this must be the same for all channels 
            in the segment.
        editing_segment : None or int, optional
            Index of the segment to be overwritten with the supplied
            `segment_params` The default is None, and will instead result in
            a new segment being added.

        Returns
        -------
        None.

        """
        self.w = None
        segment = []
        for channel in range(self.card_settings['active_channels']):
            channel_params = {}
            for shared_segment_param in shared_segment_params:
                channel_params[shared_segment_param] = segment_params[shared_segment_param]
            channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
            action = ActionContainer(channel_params,self.card_settings,self.amp_adjusters[channel])
            segment.append(action)
        if editing_segment is None:
            try:
                selected_row = [x.row() for x in self.list_segments.selectedIndexes()][0]
            except:
                selected_row = self.list_segments.count()-1
            if (self.button_rearr.isChecked()) and (self.segments[selected_row] in self.rr.base_segments[:-1]):
                logging.error('Cannot add a segment in the middle of '
                              'rearrangement segments. The segment '
                              'will be added at the end.')
                selected_row = len(self.rr.base_segments)-1
            self.segments.insert(selected_row+1,segment)
            for segment in self.segments[selected_row+1:]:
                for action in segment:
                    action.needs_to_transfer = True
            if self.button_couple_steps_segments.isChecked():
                step_index = self.get_step_from_segment(selected_row)
                try:
                    self.steps.insert(step_index,{'segment': selected_row+1, 'number_of_loops': 1, 'after_step' : 'continue', 'rearr' : False})
                    try:
                        for step in self.steps[step_index+1:]:
                            step['segment'] = step['segment'] + 1
                    except IndexError:
                        pass
                except TypeError:
                    logging.debug('Could not insert step because steps list does not exist.')
        else:
            if (self.button_rearr.isChecked()) and (self.segments[editing_segment] in self.rr.base_segments):
                logging.debug('Editing rearrangement segment.')
                autoplot = self.button_autoplot.isChecked()
                self.button_autoplot.blockSignals(True)
                self.button_autoplot.setChecked(False)

                rearr_on = self.button_rearr.isChecked()
                self.button_rearr.blockSignals(True)
                self.button_rearr.setChecked(False)
                self.rearr_toggle()
                
                self.rr.base_segments[editing_segment] = segment
                self.rr.create_actions()

                if rearr_on:
                    self.button_rearr.setChecked(True)
                    self.rearr_toggle()
                self.button_rearr.blockSignals(False)

                self.button_autoplot.setChecked(autoplot)
                self.button_autoplot.blockSignals(False)
            else:
                self.segments[editing_segment] = segment
        self.segment_list_update()

    def rearr_toggle(self, start_index=None):
        """Converts a sweeping frequency segment into one handled by the
        `RearrangementHandler` class to dynamically change the played segment.
        
        The start frequencies are extracted from the frequency step before and 
        the target frequencies are taken from the `rearr_settings` attribute.
        
        All other parameters are taken from the parameters of the first tone
        of the function being converted.
        
        If another channel is in use, this is unaffected and its parameters 
        will be duplicated across all affected segments.
        
        Parameters
        ----------
        start_index : int or None
            The index to use as the first rearrangement segment. If None, the 
            currently selected row in the segment list will be used. The 
            default is None.
        
        """
        try:
            if self.button_rearr.isChecked():
                logging.debug('Activating rearrangement.')
                len_before = len(self.segments)
                self.segments[0:0] = self.rr.base_segments
                for _ in range(self.rr.get_number_rearrangement_segments_needed()-1): # if needed copy the rearrangement segment multiple times
                    self.segments.insert(self.rr.segment+1,self.rr.base_segments[self.rr.segment])
                segments_added =len(self.segments) -  len_before
                print('segments added =',segments_added)
                print('steps before',self.steps)
                for step in self.steps:
                    step['segment'] += segments_added #len(self.rr.base_segments) + (self.rr.get_number_rearrangement_segments_needed()-1)
                print('steps after',self.steps)
                self.button_rearr.setText(f'Rearrangement ON ({self.rr.mode})')
                self.button_rearr.setStyleSheet('background-color: '+color_rearr_on)
            else:
                logging.debug('Deactivating rearrangement.')
                segments_removed = 0
                len_before = len(self.segments)
                self.segments = [x for x in self.segments if x not in self.rr.base_segments]
                # for seg in self.rr.base_segments:
                #     try:
                #         self.segments.remove(seg)
                #         segments_removed += 1
                #     except ValueError:
                #         pass
                segments_removed = len_before - len(self.segments)
                print('segments removed =',segments_removed)
                self.steps = [x for x in self.steps if x['segment'] >= segments_removed]
                for step in self.steps:
                    step['segment'] -= segments_removed
                self.button_rearr.setText('Rearrangement OFF')
                self.button_rearr.setStyleSheet('background-color: '+color_rearr_off)
            print(self.steps)
            self.segment_list_update()
        except AttributeError:
            logging.debug('Could not toggle rearrangement because the '
                          'RearrangmentHandler does not yet exist.')
        
        
    def rearr_recieve(self,string):
        """Accepts a rearrangement binary string from the Networker that it 
        has recieved over TCP. Asks the rearrangement handler which step 
        should be updated with which segment, then sends this command to the 
        AWG class.
        
        The next step is set to the index+1. This will cause strange results on
        the card if the rearrangement step is the last step, but this would be
        a very 
        
        Parameters
        ----------
        string : str
            Occupation string from Pydex. This should be a single string 
            containing only the characters '0' (unoccupied) and '1' (occupied) 
            where traps are indexed in the same order as the `start_freq_MHz` 
            attribute.
            
        Returns
        -------
        None.
        
        """
        
        if not self.button_rearr.isChecked():
            logging.error('Recieved rearrangement string, but rearrangement '
                          'mode is not active. Ignoring.')
            return
        
        segment_data = self.rr.accept_string(string) # segments data is returned as a list in case simultaneous rearrangements needed
        logging.debug(f'Recieved {len(segment_data)} segments, uploading to segments {self.rr.segment} - {self.rr.segment+len(segment_data)-1}.')
        for data_i, data in segment_data:
            self.awg.transfer_segment_data(self.rr.segment+data_i,data)
            
    def data_recieve(self,data_list):
        """Accepts data recieved from PyDex over TCP from the Networker to 
        update the data of a single tone in a given action.
        
        Parameters
        ----------
        data : list of list
            The data to update segments with. Each entry in this list is 
            itself a list that contains the following parameters (in order):
                
                
        channel : int
            The channel to change the data of.
        segment : int
            The segment to change the data of.
        param : str
            The function kwarg to change.
        value : float
            The value to change the arguement to.
        tone_index : int
            The index of the tone to change. This should be a non-negative 
            integer if only one tone should be changed. If a negative integer 
            is supplied, all tones will be changed to the given value.
            
        Returns
        -------
        None.
        
        """
        
        recalculate_rearr = False

        for data in data_list:
            [channel, segment, param, value, tone_index] = data
        
            channel = int(channel)
            segment = int(segment)
            try:
                tone_index = int(tone_index)
            except ValueError:
                logging.debug('tone_index {} not valid integer. Setting to '
                              '-1 (will affect all tones).'.format(tone_index))
                tone_index = -1
            
            logging.info("Changing channel {}, segment {}, parameter '{}', tone {}"
                         " to {}.".format(channel,segment,param,tone_index,value))

            if param in shared_segment_params:
                logging.debug('Param {} is shared across all actions in the '
                                'segment, so all actions will be updated.'.format(param))
                actions = self.segments[segment]
            else:
                try:
                    actions = [self.segments[segment][channel]]
                except IndexError:
                    logging.error('Channel {} is not active. Ignoring.'.format(channel))
                    continue
            
            for action in actions:
                action.update_param_single_tone(param, value, tone_index)
            
            if (self.button_rearr.isChecked()) and (segment == self.rr.segment):
                logging.info('Segment {} is the changing rearrangment, '
                             'so all of the changing segments will '
                             'be changed and recalculated.'.format(segment))
                self.rr.create_rearr_actions()
                self.rr.calculate_rearr_segment_data()
        
        self.segment_list_update()
        
        #TODO: uncomment the below line to send to the AWG when recieving.
        self.calculate_send()

    def multi_segment_data_recieve(self,data_template,segments):
        """Accepts data recieved from PyDex over TCP from the Networker to 
        update the data of a single tone in a given action for multiple 
        segments.
        
        Parameters
        ----------
        data : list of list
            The data to update segments with. Each entry in this list is 
            itself a list that contains the following parameters (in order):
                
                
        channel : int
            The channel to change the data of.
        segment : int
            The segment to change the data of.
        param : str
            The function kwarg to change.
        value : float
            The value to change the arguement to.
        tone_index : int
            The index of the tone to change. This should be a non-negative 
            integer if only one tone should be changed. If a negative integer 
            is supplied, all tones will be changed to the given value.

        segments : list of int
            Segments to apply the data_template to.
            
        Returns
        -------
        None.
        
        """
        data = []
        for segment in segments:
            seg_data = deepcopy(data_template)
            seg_data[1] = segment
            data.append(seg_data)
        self.data_recieve(data)
        
    def complete_data_recieve(self,data_list):
        """Accepts a complete values list for a parameter of an action.
        The length of the other settings in the action are set to the length 
        of this list.
        
        Parameters
        ----------
        data : list of list
            The data to update segments with. Each entry in this list is 
            itself a list that contains the following parameters (in order):
                
                
        channel : int
            The channel to change the data of.
        segment : int
            The segment to change the data of.
        param : str
            The function kwarg to change.
        values : float
            The values list to change the arguement to.
            
        Returns
        -------
        None.
        
        """
        
        recalculate_rearr = False

        for data in data_list:
            [channel, segment, param, values] = data
        
            channel = int(channel)
            segment = int(segment)
            
            logging.info("Changing channel {}, segment {}, parameter '{}'"
                         " to {}.".format(channel,segment,param,values))
            
            if segment == self.rr.base_segments[self.rr.segment]:
                logging.info('Segment {} is the rearrangement segment, so all '
                             'rearrangement segments will be recalculated.'.format(segment))
                recalculate_rearr = True
            
            if param in shared_segment_params:
                logging.debug('Param {} is shared across all actions in the '
                                'segment, so all actions will be updated.'.format(param))
                actions = self.segments[segment]
            else:
                try:
                    actions = [self.segments[segment][channel]]
                except IndexError:
                    logging.error('Channel {} is not active. Ignoring.'.format(channel))
                    continue
            
            for action in actions:
                action.update_param(None, param, values)
        
        if recalculate_rearr:
            self.rr.create_rearr_actions()
        
        self.segment_list_update()
        self.calculate_send()
            
    def segment_remove_all(self):
        self.segments = []
        self.steps = []
        # self.rr = None
        self.button_rearr.blockSignals(True)
        self.button_rearr.setChecked(False)
        self.button_rearr.blockSignals(False)
        self.rearr_toggle()

    def step_add_dialogue(self):
        self.w = StepCreationWindow(self)
        self.w.show()
        
    def segment_edit_dialogue(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be edited at once.')
        else:
            self.w = SegmentCreationWindow(self,selectedRows[0])
            self.w.show()

    def step_remove(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) != 0:
            selectedRows.sort(reverse=True)
            for row in selectedRows:
                try:
                    del self.steps[row]
                except IndexError:
                    pass
            self.step_list_update()

    def step_edit(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A step must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one step can be edited at once.')
        else:
            self.w = StepCreationWindow(self,selectedRows[0])
            self.w.show()

    def step_up(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A step must be selected before it can be moved.')
        elif len(selectedRows) > 1:
            logging.error('Only one step can be moved at once.')
        else:
            currentRow = selectedRows[0]
            if currentRow != 0:
                self.steps[currentRow],self.steps[currentRow-1] = self.steps[currentRow-1],self.steps[currentRow]
                self.step_list_update()
                self.list_steps.setCurrentRow(currentRow-1)

    def step_down(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A step must be selected before it can be moved.')
        elif len(selectedRows) > 1:
            logging.error('Only one step can be moved at once.')
        else:
            currentRow = selectedRows[0]
            if currentRow != self.list_steps.count()-1:
                self.steps[currentRow],self.steps[currentRow+1] = self.steps[currentRow+1],self.steps[currentRow]
                self.step_list_update()
                self.list_steps.setCurrentRow(currentRow+1)
    
    def step_add(self,step_params,edit_index=None):
        """Adds a step with the parameters passed through to the function.
        
        If rearrangement mode is active and one of the rearrangement 
        segments is chosen, the step will default to the first rearrangement 
        segment and the rearr boolean will be set to True.
        
        Parameters
        ----------
        edit_index : None or int
            The step to overwrite with the new params. If None a new step will 
            be added instead. The default is None.
        
        """
        self.w = None
        if not step_params['segment'] in list(range(len(self.segments))):
            logging.error('The selected segment {} does not exist. Cancelling '
                          'step creation.'.format(step_params['segment']))
            return
        try:
            selected_row = [x.row() for x in self.list_steps.selectedIndexes()][0]
        except:
            selected_row = self.list_steps.count()-1
        
        if self.rr != None:
            if (step_params['segment'] in self.rr.segments) and (not step_params['rearr']):
                logging.warning('Rearrangement segment {} has been selected '
                                'for step {} but this step does not have '
                                'rearrangment active.'.format(step_params['segment'],selected_row))
            elif step_params['rearr']:
                step_params['segment'] = self.rr.segments[0]
        elif step_params['rearr']:
            logging.error('Step {} has rearrangment toggled on but there is '
                          'no rearrangement segments. Turning rearrangement '
                          'toggle off.'.format(selected_row))
            step_params['rearr'] = False
        if edit_index != None:
            self.steps[edit_index] = step_params
        else:
            self.steps.insert(selected_row+1,step_params)
        self.step_list_update()
    
    def step_remove_all(self):
        self.steps = []
        self.step_list_update()

    def segment_list_update(self):
        """Updates the segment list. This includes updating the parameters of 
        each action in the list, so things like frequency and amp adjustment 
        are also done here.
        
        To just update the list based on the already set parameters of the 
        action, use write_segment_list_labels() instead.
        
        """
        
        autoplot = self.button_autoplot.isChecked()
        self.button_autoplot.blockSignals(True)
        self.button_autoplot.setChecked(False)

        self.couple_steps_segments()
        self.prevent_amp_jumps()
        self.prevent_freq_jumps()
        
        self.update_needs_to_calculates()
        self.write_segment_list_labels()

        if ((any(any([action.needs_to_calculate for action in segment]) for segment in self.segments))
            or (any(any([action.needs_to_transfer for action in segment]) for segment in self.segments))):
            self.button_calculate_send.setStyleSheet('background-color: red')
        else:
            self.button_calculate_send.setStyleSheet('')

        self.button_autoplot.setChecked(autoplot)
        self.button_autoplot.blockSignals(False)
        self.couple_steps_segments()
        
    def write_segment_list_labels(self):
        """Takes the updated segment_list and poplulates it with the correct
        labels. This has been moved to its own function to allow some GUI 
        elements to update only the labels without having to do all the 
        calculations that normally take place when the segment list is updated.
        
        """
        for i in range(self.list_segments.count()):
            self.list_segments.takeItem(0)
        for i,segment in enumerate(self.segments):
            item = QListWidgetItem()
            label = '{} : duration_ms={}'.format(i,segment[0].duration_ms)
            label += ", phase_behaviour = '{}'".format(segment[0].phase_behaviour)
            if any([action.needs_to_transfer for action in segment]):
                label += ' (NEEDS TO TRANSFER)'
            for channel in range(self.card_settings['active_channels']):
                action = segment[channel]
                label += '\n     Ch{}:'.format(channel) + self.get_segment_list_label(action,i,channel)
                item.setText(label)
            if any([action.needs_to_calculate for action in segment]):
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
            try:
                if segment in self.rr.base_segments:
                    if i == self.rr.segment:
                        item.setBackground(QColor(color_rearr_segment))
                    else:
                        item.setBackground(QColor(color_rearr_other_segment))
            except AttributeError:
                pass
            self.list_segments.addItem(item)
        
    def get_segment_list_label(self,action,segment_number,channel=0):
        """Returns a string summarising the parameters of the action.
        

        Parameters
        ----------
        action : ActionContainer
            Single channel `action` object.
        segment_number : int
            Index of the segment that the label is being generated for. If
            `segment_number` is 0, start parameters are always displayed.
        channel : int
            The channel number of the segment. The default is 0.

        Returns
        -------
        label : str
            String describing the frequency and amplitude parameters.
        
        """
        label = '\n          freq: '+action.freq_function_name + ': '
        for key in action.freq_params.keys():
            if (self.button_prevent_freq_jumps.isChecked()) and (self.button_condense_segment_data.isChecked()) and (key in ['start_freq_MHz','end_freq_MHz']):
                if self.freq_setting_segments != None:
                    if segment_number not in self.freq_setting_segments[channel]:
                        pass
                    else:
                        label += key + '=' + str(action.freq_params[key])+', '
            else:
                label += key + '=' + str(action.freq_params[key])+', '
        label = label[:-2]
        label += '\n          amp: '+action.amp_function_name + ': '
        for key in action.amp_params.keys():
            if (self.button_prevent_amp_jumps.isChecked()) and (segment_number > 0) and (key == 'start_amp') and (self.button_condense_segment_data.isChecked()):
                pass
            else:
                label += key + '=' + str(action.amp_params[key])+', '
        label = label[:-2]
        return label

    def step_list_update(self):
        logging.debug('Updating step list.')
        
        for i in range(self.list_steps.count()):
            self.list_steps.takeItem(0)
        for i,step in enumerate(self.steps):
            item = QListWidgetItem()
            # if (self.rr != None) and (i in self.rr.steps):
            #     label = '{}: REARRANGE: segments {} - {}'.format(i,self.rr.segments[0],self.rr.segments[-1])
            #     item.setBackground(QColor(color_rearr_on_background))
            # else:
            label = '{}: segment {}'.format(i,step['segment'])
            if step['number_of_loops'] != 1:
                label += ' ({} loops)'.format(step['number_of_loops'])
            if step['after_step'] == 'loop_until_trigger':
                label += '\n     WAIT'
                item.setBackground(QColor(color_loop_until_trigger))
            item.setText(label)
            self.list_steps.addItem(item)
        self.plot_autoplot_graphs()

    def open_card_settings_window(self):
        self.w = CardSettingsWindow(self,self.card_settings)
        self.w.show()    
    
    def refresh_amp_adjuster_settings(self):
        """Updates the amp_adjuster_settings list of dicts by requesting each 
        AmpAdjuster to report its settings.
        
        """
        self.amp_adjuster_settings = []
        for adjuster in self.amp_adjusters:
            self.amp_adjuster_settings.append(adjuster.get_settings())
        print(self.amp_adjuster_settings)
        label = 'AmpAdjuster settings ('
        for settings in self.amp_adjuster_settings:
            label += ['off, ','on, '][settings['enabled']]
        label = label[:-2] +')'
        self.button_amp_adjuster_settings.setText(label)
            
    def open_amp_adjuster_settings_window(self):
        self.refresh_amp_adjuster_settings()
        self.w = AmpAdjusterSettingsWindow(self,self.amp_adjuster_settings)
        self.w.show()
        
    def set_amp_adjuster_settings(self,new_amp_adjuster_settings=None,update_segment_list=True):
        """Accepts new amp adjuster settings and passes them through to the 
        `AmpAdjuster2D` objects to update their parameters.
        
        Once the AmpAdjuster settings update is complete, all segment 
        `ActionContainers` are told that they will need to recalculate 
        before data is sent to the card (this may not be necessary if that 
        channel's AmpAdjuster is not updated, but skipped making a check 
        like this for simplicity).
        
        Parameters
        ----------
        new_amp_adjuster_settings : list of dicts or None
            A list of dicts containing the parameters of the AmpAdjusters to 
            set. The parameters should be ordered in the same order as the 
            AWG channels. Each dict is passed through to the corresponding 
            AmpAdjuster.
            
            If None, the current attribute amp_adjuster_settings will be used 
            instead. This is used when loading in from a file.
            
            For the required dictonary keys, see the Attributes section of the
            `AmpAdjuster2D` class docstring.
        
        """
        logging.debug('Setting AmpAdjuster settings.')
        if new_amp_adjuster_settings == None:
            new_amp_adjuster_settings = self.amp_adjuster_settings
        if len(new_amp_adjuster_settings) < len(self.amp_adjusters):
            logging.error('Less AmpAdjuster settings are specified that the '
                          'number of AmpAdjusters ({}). Cancelling the new '
                          'settings.'.format(len(self.amp_adjusters)))
            self.refresh_amp_adjuster_settings()
            return
        for i,(settings,adjuster) in enumerate(zip(new_amp_adjuster_settings,self.amp_adjusters)):
            if adjuster == None:
                self.amp_adjusters[i] = AmpAdjuster2D(settings)
            else:
                adjuster.update_settings(settings)
        self.w = None
        for segment in self.segments:
            for action in segment:
                action.needs_to_calculate = True
        
        self.refresh_amp_adjuster_settings()
        if update_segment_list:
            self.segment_list_update()
    
    def update_card_settings(self,card_settings=None):
        """Updates the AWG settings with a new dictionary. The AWG object is 
        closed if it already exists before being recreated with the new
        settings.
        
        Parameters
        ----------
        card_settings : dict or None
            The new card settings to apply to the AWG. If None the current 
            card settings in the self.card_settings attribute are applied to 
            the AWG by closing and reopening the object.
        
        """
        self.w = None
        
        if card_settings != None:
            channels_changed = False
            old_card_settings = self.card_settings
            new_card_settings = {**old_card_settings,**card_settings}
            
            for setting in card_settings.keys():
                old_value = old_card_settings[setting]
                new_value = new_card_settings[setting]
                if new_value != old_value:
                    logging.warning('Changed card setting {} from {} to {}'.format(setting,old_value,new_value))
                    if setting == 'active_channels':
                        channels_changed = True
            for setting in new_card_settings.keys():
                self.card_settings[setting] = new_card_settings[setting]
                
            if channels_changed:
                self._create_layout_autoplotter()
                self.segment_remove_all()
                self.segment_list_update()
            else:
                for segment in self.segments:
                    for action in segment:
                        action.calculate_time()
                self.segment_list_update()
            
        try:
            self.awg.close()
        except Exception:
            logging.debug("Tried to close AWG object but failed. This might be okay if one wasn't expected to exist.")
            
        self.awg = AWG(**self.card_settings)

    def prevent_freq_jumps(self):
        """Ensures frequency continuity between segments by ensuring that all
        values in the `start_freq_MHz` list of one action appear in the 
        `end_freq_MHz` list of the previous action (or the `start_freq_MHz`
        if that kwarg doesn't exist for the previous action).
        
        Firstly, all looped segments are frequency adjusted to prevent phase 
        slips when the segment loops.
        
        Then, the other frequencies are frequency adjusted around these 
        segments. The frequency of the looped segments are propogated forwards
        and backwards along the steps until a frequency change is allowed 
        as defined by the segment.
        
        If two looped segments are found that should have the same adjusted 
        frequency, but have different durations that prevent them both being 
        set to the same frequency, there will be a frequency jump. A warning 
        will be issued in the console.
        
        For the rearrangement channel, rearrangement segments are completely 
        unaffected, so a frequency jump could occur before/after a 
        rearrangement segment. However, a phase jump almost certainly will 
        occur at the rearrangment segment, so the small amount of heating from 
        a frequency jump is of little consequence.
        
        After the frequencies have been made continuous, the looped segments 
        are readjusted just in case they have been overwritten (this shouldn't 
        happen unless two looping segments have different durations in the 
        same adjustment group).

        Returns
        -------
        None.

        """
        self.freq_adjust_looped_segments()
        
        if not self.button_prevent_freq_jumps.isChecked():
            logging.debug('Disabling frequency jump prevention.')
            self.freq_setting_segments = None
            return
        
        logging.debug('Preventing frequency jumps.')
        self.freq_setting_segments = [] # record the segments that actually affect the frequency for autoplotting
        for channel in range(self.card_settings['active_channels']):
            channel_freq_setting_segments = []
            steps_to_modify = list(range(len(self.steps)))

            # remove rearrangement segments
            steps_to_modify = [step for step in steps_to_modify if (self.segments[self.steps[step]['segment']] not in self.rr.base_segments[:-1])]

            freq_changing_steps = [step_i for step_i in steps_to_modify if self.segments[self.steps[step_i]['segment']][channel].is_freq_changing()]
            
            # get the groups of the steps to change to have the same frequency
            freq_changing_i = [i for i, x in enumerate(steps_to_modify) if x in freq_changing_steps]
            freq_changing_i = [0] + freq_changing_i + [len(steps_to_modify)]
            step_groups = []
            for i in range(len(freq_changing_i)):
                if i > 0:
                    step_groups.append(steps_to_modify[freq_changing_i[i-1]:freq_changing_i[i]+1])
            
            # prevent frequency jumps within each group            
            for group in step_groups:
                looping = [step_i for step_i in group if ((self.steps[step_i]['after_step'] == 'loop_until_trigger') or
                                                          (self.steps[step_i]['number_of_loops'] > 1))]
                initial_action = self.segments[self.steps[group[0]]['segment']][channel]
                
                if len(looping) > 0:
                    if len(looping) > 1:
                        durations = [self.segments[self.steps[step_i]['segment']][channel].duration_ms for step_i in group]
                        if not all(x == durations[0] for x in durations):
                            logging.warning('Steps {} are looping with different '
                                            'durations but without a frequency '
                                            'adjusting step between them. Cannot '
                                            'prevent a frequency jump.'.format(looping))
                    looping_action = self.segments[self.steps[looping[0]]['segment']][channel]
                    freqs_MHz = looping_action.freq_params['start_freq_MHz']
                    channel_freq_setting_segments.append(self.steps[looping[0]]['segment'])
                    
                    try:
                        initial_action.update_param('freq','end_freq_MHz',freqs_MHz)
                    except NameError:
                        initial_action.update_param('freq','start_freq_MHz',freqs_MHz)
                else:
                    freqs_MHz = initial_action.freq_params['start_freq_MHz']
                    channel_freq_setting_segments.append(self.steps[group[0]]['segment'])
                    
                for segment in [self.steps[step_i]['segment'] for step_i in group][1:]:
                    action = self.segments[segment][channel]
                    logging.debug('Updating segment {} start_freq_MHz to {}'.format(segment,freqs_MHz))
                    action.update_param('freq','start_freq_MHz',freqs_MHz)
            self.freq_setting_segments.append(channel_freq_setting_segments)
                    
        self.freq_adjust_looped_segments()

    def prevent_amp_jumps(self):
        """Ensures amplitude continuity between segments by ensuring that all
        values in the `start_amp` list of one action appear in the 
        `end_amp` list of the previous action (or the `start_amp`
        if that kwarg doesn't exist for the previous action).
        
        Rearrangement segments are completely unaffected for the rearrangement
        channel.

        Returns
        -------
        None.

        """
        if self.button_prevent_amp_jumps.isChecked():
            for i,segment in enumerate(self.segments):
                if (i>0) and (segment not in self.rr.base_segments):
                    for channel in range(self.card_settings['active_channels']):
                        try:
                            prev_amps = self.segments[i-1][channel].amp_params['end_amp']
                        except:
                            prev_amps = self.segments[i-1][channel].amp_params['start_amp']
                        new_start_amps = []
                        for tone in range(len(segment[channel].amp_params['start_amp'])):
                            start_amp = segment[channel].amp_params['start_amp'][tone]
                            if not start_amp in prev_amps:
                                new_start_amp = min(prev_amps, key=lambda x:abs(x-start_amp))
                                logging.warning('Changed segment {} Ch{} start_amp from {} to {} to avoid an amplitude jump'.format(i,channel,start_amp,new_start_amp))
                                new_start_amps.append(new_start_amp)
                            else:
                                new_start_amps.append(start_amp)
                        segment[channel].update_param('amp','start_amp',new_start_amps)
        else:
            self.write_segment_list_labels()
            
    def freq_adjust_looped_segments(self):
        """Frequency adjust segments which correspond to steps that are looped 
        until a trigger is recieved. This function can only be called when 
        the steps are coupled with segments, and only static traps can be set 
        to loop.
        
        This behaviour replaces the old approach of frequency adjusting all 
        static traps, and means that only the segments that actually need to 
        be frequency adjusted are frequency adjusted.
        
        Returns
        -------
        None.
        
        """
        logging.debug('Frequency adjusting looped segments.')
        if self.button_freq_adjust_looped_segments.isChecked():
            for step_index, step in enumerate(self.steps):
                if (step['after_step'] == 'loop_until_trigger') or (step['number_of_loops']>1):
                    segment = self.segments[step['segment']]
                    for channel, action in enumerate(segment):
                        duration_ms = action.duration_ms
                        adjusted_freqs = []
                        for unadjusted_freq in action.freq_params['start_freq_MHz']:
                            adjusted_freq = round(unadjusted_freq*(duration_ms*1e3))/(duration_ms*1e3)
                            if adjusted_freq != unadjusted_freq:
                                logging.warning('Adjusted static frequency of '
                                                'looping step {} (segment {}) '
                                                'channel {} from {} to {}'
                                                ''.format(step_index, step['segment'],channel,unadjusted_freq,adjusted_freq))
                            adjusted_freqs.append(adjusted_freq)
                        segment[channel].update_param('freq','start_freq_MHz',adjusted_freqs)                       

    def couple_steps_segments(self):
        """Creates a single step for each segment, with the exception of any
        segments currently being used for rearrangement where only one step
        is created for all the rearrangement segments.
        
        Done such that the after_step and number_of_loops for the steps 
        is conserved for a particular segment if it is already in use. If the 
        segment is used more than once, the first instance will take priority.
        
        """
        if self.button_couple_steps_segments.isChecked():
            new_steps = []
            for i,segment in enumerate(self.segments):
                found_existing_step = False
                try:
                    if segment in self.rr.base_segments:
                        if (i == self.rr.segment-1) or (i == len(self.rr.base_segments)-1):
                            new_steps.append({'segment': i, 'number_of_loops': 1, 'after_step' : 'loop_until_trigger','rearr' : True})
                        else:
                            new_steps.append({'segment': i, 'number_of_loops': 1, 'after_step' : 'continue','rearr' : True})
                        continue
                except AttributeError:
                    pass
                for step in self.steps:
                    if step['segment'] == i:
                        step['rearr'] = False
                        new_steps.append(step)
                        found_existing_step = True
                        break
                if not found_existing_step:
                    new_steps.append({'segment': i, 'number_of_loops': 1, 'after_step' : 'continue', 'rearr' : False})
            self.steps = new_steps
            # try:
            #     self.steps[-1]['after_step'] = 'loop_until_trigger'
            # except IndexError:
            #     pass
        
            logging.debug('Coupled steps with segments.')
        self.step_list_update()

        self.button_step_add.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_remove.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        # self.button_step_edit.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_up.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_down.setEnabled(not(self.button_couple_steps_segments.isChecked()))

        # self.button_prevent_freq_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        self.button_prevent_freq_jumps.setEnabled(False)
        self.button_prevent_amp_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        self.button_freq_adjust_looped_segments.setEnabled(self.button_couple_steps_segments.isChecked())
        if not(self.button_couple_steps_segments.isChecked()):
            self.button_prevent_freq_jumps.setChecked(False)
            self.button_prevent_amp_jumps.setChecked(False)
            self.button_prevent_phase_jumps.setChecked(False)

    def plot_autoplot_graphs(self):
        """Populates the autoplotter frequency graph with the steps."""
        if self.button_autoplot.isChecked():
            logging.debug('Beginning Autoplotting...')
            # if not self.button_autoplot_condense_rearr.isChecked():
            #     logging.warning('Autoplotting all rearrangemnt steps. This may take some time...')
            # else:
            #     pass
            logging.debug('Condensing rearrangement segments in Autoplot.')
            for channel in range(self.card_settings['active_channels']):
                freq_plot = self.freq_plots[channel]
                amp_plot = self.amp_plots[channel]
                freq_plot.clear()
                amp_plot.clear()
                if self.button_autoplot_amp_mV.isChecked():
                    amp_plot.setLabel(axis='left', text='amplitude (mV)')
                else:
                    amp_plot.setLabel(axis='left', text='amplitude')
                duration_xlabels = {}
                freq_segment_xlabels = {}
                amp_segment_xlabels = {}
                current_pos = 0
                for step in self.steps:
                    segment = self.segments[step['segment']]
                    segments = [segment]
                    color = None
                    is_rearr_seg = False

                    if segment in self.rr.base_segments:
                        if segment == self.rr.base_segments[self.rr.segment]:
                            color = color_rearr_segment
                            is_rearr_seg = True
                            if not self.button_autoplot_condense_rearr.isChecked():
                                pass # can no longer plot uncondensed rearrangement segments because data is not stored like this anymore
                                # segments = self.rr.rearr_segments
                        else:
                            color = color_rearr_other_segment

                    for index, segment in enumerate(segments):
                        if color != None:
                            freq_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color,movable=False))
                            amp_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color,movable=False))

                        action = segment[channel]
                        freqs, amps = action.get_autoplot_traces(show_amp_in_mV = self.button_autoplot_amp_mV.isChecked())
                        xs = np.linspace(current_pos,current_pos+1,len(freqs[0]))
                        if step['number_of_loops'] > 1:
                            freq_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color_loop_background,movable=False,
                                                                        span = (0.8,1)))
                            amp_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color_loop_background,movable=False,
                                                                        span = (0.8,1)))
                            duration_xlabels[current_pos+0.5] = '{:.3f}\n({} loops = {:.3f})'.format(action.duration_ms,step['number_of_loops'],action.duration_ms*step['number_of_loops'])
                        else:
                            duration_xlabels[current_pos+0.5] = '{:.3f}'.format(action.duration_ms)

                        label = '{}'.format(step['segment'])
                        if is_rearr_seg:
                            label += ' (R{})'.format(index)
                        freq_segment_xlabels[current_pos+0.5] = label + '\n{}'.format(action.freq_function_name)
                        amp_segment_xlabels[current_pos+0.5] = label + '\n{}'.format(action.amp_function_name)

                        if (self.freq_setting_segments != None) and (step['segment'] not in self.freq_setting_segments[channel]):
                            style = Qt.DashLine
                        else:
                            style = None 
                        for j,(freq,amp) in enumerate(zip(freqs,amps)):
                            freq_plot.plot(xs,freq, pen=pg.mkPen(color=j,width=2,style=style))
                            amp_plot.plot(xs,amp, pen=pg.mkPen(color=j,width=2))
                        freq_plot.addItem(pg.InfiniteLine(current_pos,pen={'color': "#000000"}))
                        amp_plot.addItem(pg.InfiniteLine(current_pos,pen={'color': "#000000"}))
                        
                        if action.phase_behaviour != 'continue':
                            freq_plot.addItem(pg.LinearRegionItem(values=(current_pos-0.05,current_pos+0.05),orientation='vertical',
                                                                        brush=color_phase_jump,movable=False))
                            amp_plot.addItem(pg.LinearRegionItem(values=(current_pos-0.05,current_pos+0.05),orientation='vertical',
                                                                        brush=color_phase_jump,movable=False))
                        
                        current_pos += 1
                        if step['after_step'] == 'loop_until_trigger':
                            freq_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+0.2),orientation='vertical',
                                                                        brush=color_loop_until_trigger,movable=False))
                            amp_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+0.2),orientation='vertical',
                                                                        brush=color_loop_until_trigger,movable=False))
                            current_pos += 0.2
                        
                freq_plot.getAxis('top').setTicks([freq_segment_xlabels.items()])
                amp_plot.getAxis('top').setTicks([amp_segment_xlabels.items()])
                
                freq_plot.getAxis('bottom').setTicks([duration_xlabels.items()])
                amp_plot.getAxis('bottom').setTicks([duration_xlabels.items()])
            logging.debug('Autoplotting complete.')
    
    def export_segments_to_csv_dialogue(self):
        export_directory = QFileDialog.getExistingDirectory(self, 'Select segment export directory','.')
        if export_directory != '':
            self.export_segments_to_csv(export_directory)
            
    def export_segments_to_csv(self,export_directory):
        logging.debug('Saving all segments to csv.')
        self.calculate_all_segments()
        for seg_num,segment in enumerate(self.segments):
            for channel in range(self.card_settings['active_channels']):
                data = segment[channel].data
                logging.debug('Saving segment {}, channel {} to csv.'.format(seg_num,channel))
                filename = export_directory+"/seg{}ch{}.csv".format(seg_num,channel)
                np.savetxt(filename, data, delimiter=",")
        logging.debug('Saving all segments to csv complete.')
                
    def calculate_send(self):
        """Sends the data to the AWG card."""
        self.calculate_all_segments()
        if not self.testing:
            self.awg.load_all(self.segments, self.steps)
        self.segment_list_update()
    
    def awg_trigger(self):
        """Forces the AWG to trigger with a software trigger. This is 
        wrapped in a seperate function so that this method can be 
        mapped to GUI elements even when the AWG object does not 
        exist.
        
        """
        self.awg.trigger()
    
    def awg_update_current_step(self):
        """Gets the current step of the AWG and writes the value to the 
        check current step button in the GUI.
        
        """
        step, segment = self.awg.get_current_step_segment()
        self.button_check_current_step.setText('Check current step: {} (segment: {})'.format(step,segment))

    def list_step_toggle_next_condition(self):
        """Toggles the next step condition of the selected step in the 
        `list_step` in the GUI. Toggles between continue and 
        loop_until_trigger.
        

        Returns
        -------
        None. The list of steps in the attribute `list_steps` is updated.

        """
        print(self.steps)
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be edited at once.')
        else:
            selected_step = selectedRows[0]
            if self.steps[selected_step]['after_step'] == 'continue':
                segment = self.segments[self.steps[selected_step]['segment']]
                if any([not action.is_static() for action in segment]):
                    logging.error('Only steps corresponding to segments where '
                                  'all actions are static in both frequency '
                                  'and amplitude can be set to loop.')
                else:
                    self.steps[selected_step]['after_step'] = 'loop_until_trigger'
            else:
                self.steps[selected_step]['after_step'] = 'continue'
            self.segment_list_update()
            # self.step_list_update()
            
    def update_needs_to_calculates(self):
        """Iterate through the actions list and check that all segments that 
        need to recalculate are flagged to recalculate. This is important when 
        using phase continuity because if one segment is changed, all later 
        segments must be recalculated until the next allowed phase jump.
        
        Returns
        -------
        None.
        """
        
        for segment_index, segment in enumerate(self.segments):
            if segment_index > 0:
                for channel, action in enumerate(segment):
                    action = segment[channel]
                    if action.phase_behaviour == 'continue':
                        prev_action = self.segments[segment_index-1][channel]
                        if prev_action.needs_to_calculate:
                            action.needs_to_calculate = True
                            logging.debug('Channel {}, segment {} needs to '
                                          'calculate because its '
                                          'phase_behaviour is '
                                          'continue and segment {} needs to '
                                          'calculate.'.format(channel,segment_index,segment_index-1))
                            
    def get_step_from_segment(self,segment_index):
        """Helper function to get the index of the first matching step for a 
        given segment index.
        
        Parameters
        ----------
        segment_index : int
            The index of the segment to find the first matching step for.
        
        Returns
        -------
        int or None.
            The index of the first matching step. None is returned if the 
            segment does not have a matching step.
        """
        
        try:
            step_index = [step['segment'] for step in self.steps].index(segment_index)
            logging.debug("Segment {}'s first match is step {}.".format(segment_index,step_index))
            return step_index
        except ValueError:
            logging.debug('Segment {} does not have a matching step.'.format(segment_index))
            return None

    def get_non_rearr_steps(self):
        """Returns only the steps that aren't rearrangement steps 
        for saving to the AWGparam file. This assumes that 
        all rearrangement segments begin from index 0."""
        steps = deepcopy(self.steps)
        print(steps)
        if not self.button_rearr.isChecked():
            return steps
        
        non_rearr_steps = []

        for step in steps:
            if step['segment'] >= len(self.rr.base_segments):
                step['segment'] -= len(self.rr.base_segments)
                non_rearr_steps.append(step)
        
        print(non_rearr_steps)
        return non_rearr_steps
            
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()