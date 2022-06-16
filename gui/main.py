import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

import sys
import os
import numpy as np
import json
from copy import copy

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

from actions import ActionContainer, AmpAdjuster2D
from rearrangement import RearrangementHandler
from awg import AWG
from networking.networker import Networker

num_plot_points = 100

color_cs = '#f5b7a6'
color_rb = '#bdd7ee'
color_loop_until_trigger = '#ffff99'
color_rearr_off = '#e04848'
color_rearr_on = '#05a815'
color_rearr_on_background = '#92f09b'
color_needs_to_calculate = '#dfbbf0'
color_loop_background = '#659ffc'
color_phase_jump = '#ff000020'

dicts_to_save = ['card_settings','network_settings','amp_adjuster_settings',
                 'rearr_settings']
datagen_settings_to_save = ['button_couple_steps_segments','button_prevent_freq_jumps',
                            'button_prevent_amp_jumps','button_freq_adjust_static_segments',
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
        
    """
    def __init__(self,name='AWG1',params_filename='default_params.txt',dev_mode=False):
        super().__init__()

        self.name = name        
        self.last_AWGparam_folder = '.'
        
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
        self.rr = None
        self.segments = []
        self.steps = []
        
        self.load_params(params_filename)
        self.networker = Networker(main_window=self,server_name=self.name,**self.network_settings)

    def _create_menu_bar(self):
        action_load_params = QAction(self)
        action_load_params.setText("Load AWGparam")

        action_save_params = QAction(self)
        action_save_params.setText("Save AWGparam")
        
        action_load_params.triggered.connect(self.load_params_dialogue)
        action_save_params.triggered.connect(self.save_params_dialogue)
        
        menu_bar = self.menuBar()
        menu_main = menu_bar.addMenu("Menu")
        menu_main.addAction(action_load_params)
        menu_main.addAction(action_save_params)

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
    
        self.button_check_current_step = QPushButton("Check current step: ?")
        self.button_check_current_step.clicked.connect(self.awg_update_current_step)
        layout_step_control.addWidget(self.button_check_current_step)

        self.layout_datagen.addLayout(layout_step_control)
        
        self.layout_datagen.addWidget(QHLine())
        
        layout_prevent_jumps = QGridLayout()
        self.button_couple_steps_segments = QCheckBox("Couple steps with segments")
        self.button_couple_steps_segments.clicked.connect(self.couple_steps_segments)
        # self.button_couple_steps_segments.setEnabled(False)
        layout_prevent_jumps.addWidget(self.button_couple_steps_segments,0,0,1,1)

        self.button_prevent_freq_jumps = QCheckBox("Prevent frequency jumps \n(will not edit rearr. segs.)")
        self.button_prevent_freq_jumps.setEnabled(False)
        # self.button_prevent_freq_jumps.clicked.connect(self.prevent_freq_jumps)
        self.button_prevent_freq_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_freq_jumps,1,0,1,1)

        self.button_prevent_amp_jumps = QCheckBox("Prevent amplitude jumps \n(will not edit rearr. segs.)")
        self.button_prevent_amp_jumps.setEnabled(False)
        # self.button_prevent_amp_jumps.clicked.connect(self.prevent_amp_jumps)
        self.button_prevent_amp_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_amp_jumps,2,0,1,1)

        layout_prevent_jumps.addWidget(QLabel("Prevent phase jumps:"),0,1,1,1)
        
        self.button_freq_adjust_static_segments = QCheckBox("Frequency adjust freq = static and amp = static segments")
        # self.button_freq_adjust_static_segments.clicked.connect(self.freq_adjust_static_segments)
        self.button_freq_adjust_static_segments.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_freq_adjust_static_segments,1,1,1,1)
        
        self.button_prevent_phase_jumps = QCheckBox("Enforce phase continuity between segments")
        self.button_prevent_phase_jumps.setEnabled(False)
        layout_prevent_jumps.addWidget(self.button_prevent_phase_jumps,2,1,1,1)

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

        self.layout_datagen.addWidget(QLabel('<h3>segments<\h3>'))

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
        self.button_step_edit.setEnabled(False)
        # layout_step_buttons.addWidget(self.button_step_edit)
        
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
        self.button_autoplot.setChecked(True)
        layout_autoplot_options.addWidget(self.button_autoplot)
        
        self.button_autoplot_condense_rearr = QCheckBox("Condense rearrange segments")
        self.button_autoplot_condense_rearr.clicked.connect(self.plot_autoplot_graphs)
        layout_autoplot_options.addWidget(self.button_autoplot_condense_rearr)
        
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
        # self.button_calculate_send.setEnabled(False)
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
                    
    def load_params(self,filename):
        logging.info("Loading AWG params from '{}'.".format(filename))
        
        with open(filename, 'r') as f:
            data = json.load(f)
        
        for name in dicts_to_save:
            setattr(self,name,data[name])
            
        self.set_datagen_settings(data['datagen_settings'])
        self._create_layout_autoplotter()
        self.set_amp_adjuster_settings()
            
        self.segments = []
        for segment in data['segments']:
            self.segment_add(segment)
            
        self.steps = data['steps']
        
        self.segment_list_update()
        
        if data['rearr_state'] == None:
            self.rr = None
            self.button_rearr.setChecked(False)
        else:
            self.rr = RearrangementHandler([0],[0])
            rr_start_index = data['rearr_state']['segments'][0]
            self.rr.set_state(data['rearr_state'])
            self.button_rearr.setChecked(False)
            self.rearr_toggle()
            
            self.list_segments.setCurrentRow(rr_start_index)
            self.button_rearr.setChecked(True)
        
        try:
            self.awg.close()
        except Exception as e:
            logging.error("Failed to close AWG object. This might be okay if one wasn't expected to exist.")
        self.awg = AWG(**self.card_settings)
        
    def load_params_dialogue(self):
        filename = QFileDialog.getOpenFileName(self, 'Load AWGparam','.',"Text documents (*.txt)")[0]
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
            segment_data = {}
            for i,action in enumerate(segment):
                action_params = action.get_action_params()
                segment_data['duration_ms'] = action_params.pop('duration_ms')
                segment_data['phase_behaviour'] = action_params.pop('phase_behaviour')
                segment_data['Ch{}'.format(i)] = action_params
            segments_data.append(segment_data)
        
        data['segments'] = segments_data
        data['steps'] = self.steps
        
        if self.rr == None:
            data['rearr_state'] = None
        else:
            data['rearr_state'] = self.rr.get_state()

        try:
            os.makedirs(os.path.dirname(filename),exist_ok=True)
        except FileExistsError as e:
            logging.warning('FileExistsError thrown when saving AWGParams file',e)
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        logging.info('AWGparam saved to "{}"'.format(filename))

    def save_params_dialogue(self):
        filename = QFileDialog.getSaveFileName(self, 'Save AWGparam',self.last_AWGparam_folder,"Text documents (*.txt)")[0]
        if filename != '':
            self.save_params(filename)
            self.last_AWGparam_folder = os.path.dirname(filename)
            
    def open_rearr_settings_window(self):
        self.w = RearrSettingsWindow(self,self.rearr_settings)
        self.w.show()
        
    def get_datagen_settings(self):
        settings = {}
        for name in datagen_settings_to_save:
            button = getattr(self,name)
            settings[name] = button.isChecked()
        return settings
    
    def set_datagen_settings(self,settings):
        for name,value in settings.items():
            button = getattr(self,name)
            button.setChecked(value)
        
    def update_rearr_settings(self,rearr_settings):
        """Update the rearrangement settings with a new dictionary. Called 
        when the `RearrSettingsWindow` saves the parameters. Also closes the 
        settings window.
        
        The dictionary is merged with the old dictionary so any values that 
        aren't specified are kept at their old value.

        Parameters
        ----------
        rearr_settings : dict
            Dictionary to update the rearrangement settings to.

        Returns
        -------
        None. The attribute `rearr_settings` is modified.

        """
        old_rearr_settings = self.rearr_settings
        new_rearr_settings = {**old_rearr_settings,**rearr_settings}
        for setting in rearr_settings.keys():
            old_value = old_rearr_settings[setting]
            new_value = new_rearr_settings[setting]
            if new_value != old_value:
                logging.warning('Changed rearrangement setting {} from {} to {}'.format(setting,old_value,new_value))
        for setting in new_rearr_settings.keys():
            self.rearr_settings[setting] = new_rearr_settings[setting]
        self.w = None
        logging.debug(self.rearr_settings)
        self.rearr_toggle()
    
    def calculate_all_segments(self):
        for segment_index, segment in enumerate(self.segments):
            for action_index, action in enumerate(segment):
                if segment_index == 0:
                    action.set_start_phase(None)
                else:
                    end_phase = self.segments[segment_index-1][action_index].end_phase
                    action.set_start_phase(end_phase)
                action.calculate()
        self.segment_list_update()

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
                if (self.rr != None) and (row in self.rr.segments):
                    logging.error('Cannot delete a rearrangement segment. '
                                  'Deactivate rearrangement first.')
                else:
                    try:
                        del self.segments[row]
                        for segment in self.segments[row:]:
                            for action in segment:
                                action.needs_to_transfer = True
                        if (self.rr != None) and all(row < i for i in self.rr.segments):
                            self.rr.segments = [i-1 for i in self.rr.segments]
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
            
            current_segment = int(self.list_segments.currentItem().text().split(' ')[0])
            
            if self.rr != None:
                if current_segment in self.rr.segments:
                    logging.error('Cannot move rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
                elif current_segment == self.rr.segments[-1] + 1:
                    logging.error('Cannot move segments through the '
                                  'rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
            self.segments[current_segment],self.segments[current_segment-1] = self.segments[current_segment-1],self.segments[current_segment]
            for segment in self.segments[current_segment-1:current_segment+1]:
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
            
            current_segment = int(self.list_segments.currentItem().text().split(' ')[0])
            
            if self.rr != None:
                if current_segment in self.rr.segments:
                    logging.error('Cannot move rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
                elif current_segment == self.rr.segments[0] - 1:
                    logging.error('Cannot move segments through the '
                                  'rearrangement segments. Turn off '
                                  'rearrangement first.')
                    return
            self.segments[current_segment],self.segments[current_segment+1] = self.segments[current_segment+1],self.segments[current_segment]
            for segment in self.segments[current_segment:current_segment+2]:
                for action in segment:
                    action.needs_to_transfer = True
            self.segment_list_update()
            self.list_segments.setCurrentRow(currentRow+1)
    
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
        one of the segments.

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
            channel_params = {'duration_ms':segment_params['duration_ms'],
                              'phase_behaviour':segment_params['phase_behaviour']}
            channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
            action = ActionContainer(channel_params,self.card_settings,self.amp_adjusters[channel])
            segment.append(action)
        if editing_segment is None:
            try:
                selected_row = [x.row() for x in self.list_segments.selectedIndexes()][0]
            except:
                selected_row = self.list_segments.count()-1
            if (self.rr != None) and (selected_row in self.rr.segments):
                selected_row = max(self.rr.segments)
            self.segments.insert(selected_row+1,segment)
            for segment in self.segments[selected_row+1:]:
                for action in segment:
                    action.needs_to_transfer = True
            if (self.rr != None) and all(selected_row < i for i in self.rr.segments):
                self.rr.segments = [i+1 for i in self.rr.segments]
        else:
            if (self.rr != None) and (editing_segment in self.rr.segments):
                base_rr_segment = self.rr.segments[0]
                self.button_rearr.setChecked(False)
                self.segments[base_rr_segment] = segment
                self.list_segments.setCurrentRow(base_rr_segment)
                self.button_rearr.setChecked(True)
            else:
                self.segments[editing_segment] = segment
        self.segment_list_update()

    def rearr_toggle(self):
        """Converts a sweeping frequency segment into one handled by the
        `RearrangementHandler` class to dynamically change the played segment.
        
        The start frequencies are extracted from the frequency step before and 
        the target frequencies are taken from the `rearr_settings` attribute.
        
        All other parameters are taken from the parameters of the first tone
        of the function being converted.
        
        If another channel is in use, this is unaffected and its parameters 
        will be duplicated across all affected segments.
        
        """
        #TODO ensure phase continuity is still obeyed.
        if self.button_rearr.isChecked():       
            selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
            if self.rr == None:
                if len(selectedRows) == 0:
                    logging.error('A segment must be selected before it can be made '
                                  'into a rearrange segment.')
                    self.button_rearr.setChecked(False)
                    return
                elif len(selectedRows) > 1:
                    logging.error('Only one segment can be made into a rearrange '
                                  'segment at once.')
                    self.button_rearr.setChecked(False)
                    return
                index = selectedRows[0]
                if index == 0:
                    logging.error('Segment 0 cannot be converted into a rearrangement '
                                  'segment.')
                    self.button_rearr.setChecked(False)
                    return
                
                segment = self.segments[index]
                rearr_channel = self.rearr_settings['channel']
                
                if not 'end_freq_MHz' in segment[rearr_channel].freq_params.keys():
                    logging.error('The selected segment does not sweep the frequency '
                                  'in the rearrangement axis so can not be made into '
                                  'a rearrangement segment.')
                    self.button_rearr.setChecked(False)
                    return
            else:
                for i in self.rr.segments[:0:-1]:
                    self.segments.pop(i)
                    
                index = self.rr.segments[0]
                
                segment = self.segments[index]
                rearr_channel = self.rearr_settings['channel']
                    
            # prev_segment = self.segments[index-1]
            # try:
            #     start_freq_MHz = prev_segment[rearr_channel].freq_params['end_freq_MHz']
            # except:
            #     start_freq_MHz = prev_segment[rearr_channel].freq_params['start_freq_MHz']
            
            start_freq_MHz = self.rearr_settings['start_freq_MHz']
            target_freq_MHz = self.rearr_settings['target_freq_MHz']
            
            self.rr = RearrangementHandler(start_freq_MHz,target_freq_MHz)
            
            occupation_start_freqs = self.rr.get_occupation_freqs()
            
            rr_segments = []
            
            for start_freqs in occupation_start_freqs:
                rr_seg = []
                for channel in range(self.card_settings['active_channels']):
                    if channel == rearr_channel:
                        rearr_action_params = segment[rearr_channel].get_action_params()
                        freq_params = rearr_action_params['freq']
                        amp_params = rearr_action_params['amp']
                        for key,value in freq_params.items():
                            if key == 'start_freq_MHz':
                                freq_params[key] = start_freqs
                            elif key == 'end_freq_MHz':
                                freq_params[key] = target_freq_MHz
                            elif key == 'function':
                                pass
                            else:
                                freq_params[key] = [freq_params[key][0]]*len(target_freq_MHz)
                        for key,value in amp_params.items():
                            if key == 'function':
                                pass
                            else:
                                amp_params[key] = [amp_params[key][0]]*len(target_freq_MHz)
                        action = ActionContainer(rearr_action_params,self.card_settings,self.amp_adjusters[channel])
                        action.rearr = True
                        rr_seg.append(action)
                    else:
                        rr_seg.append(segment[channel])
                rr_segments.append(rr_seg)
            
            
            self.rr.set_start_index(index)
            self.segments.pop(index)
            self.segments[index:index] = rr_segments
            
            self.segment_list_update()
            
            self.button_rearr.setText("Rearrangement ON: segments {} - {}".format(self.rr.segments[0],self.rr.segments[-1]))
            self.button_rearr.setStyleSheet('background-color: '+color_rearr_on)
                
        else:
            if self.rr != None:
                for i in self.rr.segments[:0:-1]:
                    self.segments.pop(i)
                for action in self.segments[self.rr.segments[0]]:
                    action.rearr = False
                self.rr = None
            self.button_rearr.setText("Rearrangement OFF")
            self.button_rearr.setStyleSheet('background-color: '+color_rearr_off)
            self.segment_list_update()
            
    def rearr_step_update(self):
        """Iterates through the `steps` attribute list and finds the first one
        with the boolean rearr set to True. This step is set to the 
        rearrangement step that will be modified with the correct segment when 
        recieving a string from PyDex.
        
        Sets all other rearr booleans to false.
        
        """
        if self.rr == None:
            return
        self.rr.steps = []
        for i,step in enumerate(self.steps):
            if (step['rearr']):
                self.rr.steps.append(i)
                logging.debug('Set step {} to a rearrangement step'.format(i))
        logging.debug('Rearrangement steps: {}'.format(self.rr.steps))
        
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
        
        try:
            rr_segment = self.rr.accept_string(string)
        except AttributeError:
            logging.error('Recieved rearrangement string, but rearrangement '
                          'mode is not active. Ignoring.')
            return
        
        rr_steps = self.rr.steps
        
        for step_index in rr_steps:
            step_params = self.steps[step_index].copy()
            step_params['segment'] = rr_segment    
            
            if step_index == len(self.steps)-1:
                next_step_index = 0
            else:
                next_step_index = step_index+1
                
            self.awg._set_step(step_index,**step_params,next_step_index=next_step_index)
            
            
    def segment_remove_all(self):
        self.segments = []
        self.rr = None
        self.button_rearr.setChecked(False)
        self.segment_list_update()

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
    
    def step_add(self,step_params):
        """Adds a step with the parameters passed through to the function.
        
        If rearrangement mode is active and one of the rearrangement 
        segments is chosen, the step will default to the first rearrangement 
        segment and the rearr boolean will be set to True.
        
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
        self.steps.insert(selected_row+1,step_params)
        self.step_list_update()
    
    def step_remove_all(self):
        self.steps = []
        self.step_list_update()

    def segment_list_update(self):
        self.prevent_amp_jumps()
        self.prevent_freq_jumps()
        
        for i in range(self.list_segments.count()):
            self.list_segments.takeItem(0)
        for i,segment in enumerate(self.segments):
            item = QListWidgetItem()
            needs_to_calculate = False
            if (self.rr != None) and (i in self.rr.segments):
                label = '{} - {}: REARRANGE: duration_ms={}'.format(self.rr.segments[0],self.rr.segments[0]+self.rr.num_segments-1,segment[0].duration_ms)
                label += ", phase_behaviour = '{}'".format(segment[0].phase_behaviour)
                if any([action.needs_to_transfer for segment in self.segments[self.rr.segments[0]:self.rr.segments[0]+self.rr.num_segments] for action in segment]):
                    label += ' (NEED TO TRANSFER)'
                for channel in range(self.card_settings['active_channels']):
                    action = segment[channel]
                    label += '\n     Ch{}:'.format(channel) + self.get_segment_list_label(action,i)
                    if action.needs_to_calculate:
                        needs_to_calculate = True
                item.setText(label)
                if needs_to_calculate:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                item.setBackground(QColor(color_rearr_on_background))
                self.list_segments.addItem(item)
                if i != self.rr.segments[0]:
                    self.list_segments.setRowHidden(i,True)
            else:
                label = '{} : duration_ms={}'.format(i,segment[0].duration_ms)
                label += ", phase_behaviour = '{}'".format(segment[0].phase_behaviour)
                if any([action.needs_to_transfer for action in segment]):
                    label += ' (NEEDS TO TRANSFER)'
                for channel in range(self.card_settings['active_channels']):
                    action = segment[channel]
                    label += '\n     Ch{}:'.format(channel) + self.get_segment_list_label(action,i)
                    item.setText(label)
                    if action.needs_to_calculate:
                        needs_to_calculate = True
                if needs_to_calculate:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                self.list_segments.addItem(item)
            
        self.couple_steps_segments()
        
    def get_segment_list_label(self,action,segment_number):
        """Returns a string summarising the parameters of the action.
        

        Parameters
        ----------
        action : ActionContainer
            Single channel `action` object.
        segment_number : int
            Index of the segment that the label is being generated for. If
            `segment_number` is 0, start parameters are always displayed.

        Returns
        -------
        label : str
            String describing the frequency and amplitude parameters.
        
        """
        label = '\n          freq: '+action.freq_function_name + ': '
        for key in action.freq_params.keys():
            if ((segment_number > 0) and (key == 'start_freq_MHz') and 
                (self.button_prevent_freq_jumps.isChecked())):
                pass
            elif ((segment_number > 0) and (key == 'start_phase') and 
                  (self.button_prevent_phase_jumps.isChecked())):
                pass
            else:
                label += key + '=' + str(action.freq_params[key])+', '
        label = label[:-2]
        label += '\n          amp: '+action.amp_function_name + ': '
        for key in action.amp_params.keys():
            if (segment_number > 0) and (key == 'start_amp') and (self.button_prevent_amp_jumps.isChecked()):
                pass
            else:
                label += key + '=' + str(action.amp_params[key])+', '
        label = label[:-2]
        return label

    def step_list_update(self):
        self.rearr_step_update()
        
        for i in range(self.list_steps.count()):
            self.list_steps.takeItem(0)
        for i,step in enumerate(self.steps):
            item = QListWidgetItem()
            if (self.rr != None) and (i in self.rr.steps):
                label = '{}: REARRANGE: segments {} - {}'.format(i,self.rr.segments[0],self.rr.segments[-1])
                item.setBackground(QColor(color_rearr_on_background))
            else:
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
            
    def open_amp_adjuster_settings_window(self):
        self.refresh_amp_adjuster_settings()
        self.w = AmpAdjusterSettingsWindow(self,self.amp_adjuster_settings)
        self.w.show()
        
    def set_amp_adjuster_settings(self):
        """Accepts new amp adjuster settings and passes them through to the 
        `AmpAdjuster2D` objects to update their parameters.
        
        Once the AmpAdjuster settings update is complete, all segment 
        `ActionContainers` are told that they will need to recalculate 
        before data is sent to the card (this may not be necessary if that 
        channel's AmpAdjuster is not updated, but skipped making a check 
        like this for simplicity).
        
        Parameters
        ----------
        new_amp_adjuster_settings : list of dicts
            A list of dicts containing the parameters of the AmpAdjusters to 
            set. The parameters should be ordered in the same order as the 
            AWG channels. Each dict is passed through to the corresponding 
            AmpAdjuster.
            
            For the required dictonary keys, see the Attributes section of the
            `AmpAdjuster2D` class docstring.
        
        """
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
        self.segment_list_update()
        self.plot_autoplot_graphs()
    
    def update_card_settings(self,card_settings):
        old_card_settings = self.card_settings
        new_card_settings = {**old_card_settings,**card_settings}
        for setting in card_settings.keys():
            old_value = old_card_settings[setting]
            new_value = new_card_settings[setting]
            if new_value != old_value:
                logging.warning('Changed card setting {} from {} to {}'.format(setting,old_value,new_value))
                if setting == 'active_channels':
                    self.segment_remove_all()
        for setting in new_card_settings.keys():
            self.card_settings[setting] = new_card_settings[setting]
        self._create_layout_autoplotter()
        self.plot_autoplot_graphs()
        self.w = None

    def prevent_freq_jumps(self):
        """Ensures frequency continuity between segments by ensuring that all
        values in the `start_freq_MHz` list of one action appear in the 
        `end_freq_MHz` list of the previous action (or the `start_freq_MHz`
        if that kwarg doesn't exist for the previous action).
        
        Could clash with the `freq_adjust_static_segments` method because the
        the static frequency of a segment could be set to a non-adjusted one to
        enforce frequency continuity. To prevent this, the frequencies are 
        adjusted for continuity first. Then, static frequency segments are 
        frequency adjusted, and then given special standing and not adjusted 
        further, changing the `end_freq_MHz` of the previous segment instead.
        
        Note that this means that a frequency jump can still occur if two 
        static frequencies are successive and different enough to be frequency 
        adjusted to different values (e.g. if they have different `duration_ms`
        values).
        
        Rearrangement segments are completely unaffected.

        Returns
        -------
        None.

        """
        if self.button_prevent_freq_jumps.isChecked():
            logging.debug('Preventing frequency jumps.')
            for i,segment in enumerate(self.segments):
                if (i > 0) and (not ((self.rr != None) and (i in self.rr.segments))):
                    for channel in range(self.card_settings['active_channels']):
                        current_action = segment[channel]
                        prev_action = self.segments[i-1][channel]
                        try:
                            prev_freqs = prev_action.freq_params['end_freq_MHz']
                        except:
                            prev_freqs = prev_action.freq_params['start_freq_MHz']
                        new_start_freqs = []
                        for tone in range(len(current_action.freq_params['start_freq_MHz'])):
                            start_freq = current_action.freq_params['start_freq_MHz'][tone]
                            if not start_freq in prev_freqs:
                                new_start_freq = min(prev_freqs, key=lambda x:abs(x-start_freq))
                                logging.info('Changed segment {} Ch{} start_freq_MHz from {} to {} to avoid a frequency jump'.format(i,channel,start_freq,new_start_freq))
                                new_start_freqs.append(new_start_freq)
                            else:
                                new_start_freqs.append(start_freq)       
                        current_action.update_param('freq','start_freq_MHz',new_start_freqs)
        
        self.freq_adjust_static_segments()
        
        if self.button_prevent_freq_jumps.isChecked():
            for i,segment in enumerate(self.segments):
                if (i > 0) and (not ((self.rr != None) and (i in self.rr.segments))):
                    for channel in range(self.card_settings['active_channels']):
                        current_action = segment[channel]
                        prev_action = self.segments[i-1][channel]
                        if current_action.freq_function_name == 'static':
                            current_freqs = current_action.freq_params['start_freq_MHz']
                            new_prev_seg_end_freqs = []
                            try:
                                for tone in range(len(prev_action.freq_params['end_freq_MHz'])):
                                    end_freq = prev_action.freq_params['end_freq_MHz'][tone]
                                    print(end_freq)
                                    if not end_freq in current_freqs:
                                        new_prev_seg_end_freq = min(current_freqs, key=lambda x:abs(x-end_freq))
                                        logging.info('Changed segment {} Ch{} end_freq_MHz from {} to {} to avoid a frequency jump'.format(i-1,channel,end_freq,new_prev_seg_end_freq))
                                        new_prev_seg_end_freqs.append(new_prev_seg_end_freq)
                                    else:
                                        new_prev_seg_end_freqs.append(end_freq)       
                                prev_action.update_param('freq','end_freq_MHz',new_prev_seg_end_freqs)
                            except Exception:
                                logging.warning('Might not have prevented '
                                                'frequency jump due to two '
                                                'consecutive static segments. '
                                                'If they were close enough '
                                                'to be frequency adjusted to '
                                                'the same frequency, this is '
                                                'safe to ignore.')
                        else:
                            try:
                                prev_freqs = prev_action.freq_params['end_freq_MHz']
                            except:
                                prev_freqs = prev_action.freq_params['start_freq_MHz']
                            new_start_freqs = []
                            for tone in range(len(current_action.freq_params['start_freq_MHz'])):
                                start_freq = current_action.freq_params['start_freq_MHz'][tone]
                                if not start_freq in prev_freqs:
                                    new_start_freq = min(prev_freqs, key=lambda x:abs(x-start_freq))
                                    logging.info('Changed segment {} Ch{} start_freq_MHz from {} to {} to avoid a frequency jump'.format(i,channel,start_freq,new_start_freq))
                                    new_start_freqs.append(new_start_freq)
                                else:
                                    new_start_freqs.append(start_freq)       
                            current_action.update_param('freq','start_freq_MHz',new_start_freqs)

    def prevent_amp_jumps(self):
        """Ensures amplitude continuity between segments by ensuring that all
        values in the `start_amp` list of one action appear in the 
        `end_amp` list of the previous action (or the `start_amp`
        if that kwarg doesn't exist for the previous action).
        
        Rearrangement segments are completely unaffected.

        Returns
        -------
        None.

        """
        if self.button_prevent_amp_jumps.isChecked():
            for i,segment in enumerate(self.segments):
                if (i > 0) and (not ((self.rr != None) and (i in self.rr.segments))):
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
            
    def freq_adjust_static_segments(self):
        if self.button_freq_adjust_static_segments.isChecked():
            for i, segment in enumerate(self.segments):
                for channel in range(self.card_settings['active_channels']):
                    action = segment[channel]
                    if (action.freq_function_name == 'static') and (action.amp_function_name == 'static'):
                        duration_ms = action.duration_ms
                        adjusted_freqs = []
                        for unadjusted_freq in action.freq_params['start_freq_MHz']:
                            adjusted_freq = round(unadjusted_freq*(duration_ms*1e3))/(duration_ms*1e3)
                            if adjusted_freq != unadjusted_freq:
                                logging.warning('Adjusted static frequency of segment {} Ch{} from {} to {}'.format(i,channel,unadjusted_freq,adjusted_freq))
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
        required_segments = list(range(len(self.segments)))
        if self.rr != None:
            required_segments = [x for x in required_segments if not x in self.rr.segments[1:]]
        
        if self.button_couple_steps_segments.isChecked():
            new_steps = []
            for segment in required_segments:
                found_existing_step = False
                if (self.rr != None) and (segment == self.rr.segments[0]):
                    new_steps.append({'segment': segment, 'number_of_loops': 1, 'after_step' : 'continue','rearr' : True})
                else:
                    for step in self.steps:
                        if step['segment'] == segment:
                            step['rearr'] = False
                            new_steps.append(step)
                            found_existing_step = True
                            break
                    if not found_existing_step:
                        new_steps.append({'segment': segment, 'number_of_loops': 1, 'after_step' : 'continue', 'rearr' : False})
            self.steps = new_steps
        
            logging.debug('Coupled steps with segments.')
        
        self.step_list_update()

        self.button_step_add.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_remove.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        # self.button_step_edit.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_up.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_down.setEnabled(not(self.button_couple_steps_segments.isChecked()))

        self.button_prevent_freq_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        self.button_prevent_amp_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        # self.button_prevent_phase_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        if not(self.button_couple_steps_segments.isChecked()):
            self.button_prevent_freq_jumps.setChecked(False)
            self.button_prevent_amp_jumps.setChecked(False)
            self.button_prevent_phase_jumps.setChecked(False)

    def plot_autoplot_graphs(self):
        """Populates the autoplotter frequency graph with the steps."""
        if self.button_autoplot.isChecked():
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
                segment_xlabels = {}
                current_pos = 0
                for step_index, step in enumerate(self.steps):
                    step_segments = [step['segment']]
                    if (self.rr != None) and (step_index in self.rr.steps) and (not self.button_autoplot_condense_rearr.isChecked()):
                        step_segments = self.rr.segments
                    for segment in step_segments:
                        if self.rr != None:
                            if (self.button_autoplot_condense_rearr.isChecked()) and (segment in self.rr.segments[1:]):
                                continue
                            elif segment in self.rr.segments:
                                freq_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                            brush=color_rearr_on_background,movable=False))
                                amp_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                            brush=color_rearr_on_background,movable=False))

                        action = self.segments[segment][channel]
                        freqs, amps = action.get_autoplot_traces(show_amp_in_mV = self.button_autoplot_amp_mV.isChecked())
                        xs = np.linspace(current_pos,current_pos+1,len(freqs[0]))
                        if step['number_of_loops'] > 1:
                            freq_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color_loop_background,movable=False,
                                                                        span = (0.8,1)))
                            amp_plot.addItem(pg.LinearRegionItem(values=(current_pos,current_pos+1),orientation='vertical',
                                                                        brush=color_loop_background,movable=False,
                                                                        span = (0.8,1)))
                            duration_xlabels[current_pos+0.5] = '{}\n({} loops = {})'.format(action.duration_ms,step['number_of_loops'],action.duration_ms*step['number_of_loops'])
                        else:
                            duration_xlabels[current_pos+0.5] = action.duration_ms
                        segment_xlabels[current_pos+0.5] = segment
                        for j,(freq,amp) in enumerate(zip(freqs,amps)):
                            freq_plot.plot(xs,freq, pen=pg.mkPen(color=j,width=2))
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
                        
                freq_plot.getAxis('top').setTicks([segment_xlabels.items()])
                amp_plot.getAxis('top').setTicks([segment_xlabels.items()])
                
                freq_plot.getAxis('bottom').setTicks([duration_xlabels.items()])
                amp_plot.getAxis('bottom').setTicks([duration_xlabels.items()])
    
    def export_segments_to_csv_dialogue(self):
        export_directory = QFileDialog.getExistingDirectory(self, 'Select segment export directory','.')
        if export_directory != '':
            self.export_segments_to_csv(export_directory)
            
    def export_segments_to_csv(self,export_directory):
        self.calculate_all_segments()
        for seg_num,segment in enumerate(self.segments):
            for channel in range(self.card_settings['active_channels']):
                data = segment[channel].data
                filename = export_directory+"/seg{}ch{}.csv".format(seg_num,channel)
                np.savetxt(filename, data, delimiter=",")
                
    def calculate_send(self):
        """Sends the data to the AWG card."""
        self.awg.load_all(self.segments, self.steps)
        self.segment_list_update()
        
    def awg_trigger(self):
        """Forces the AWG to trigger with a software trigger. The check 
        current step button is also updated.
        
        """
        self.awg.trigger()
        self.awg_update_current_step()
        
    def awg_update_current_step(self):
        """Gets the current step of the AWG and writes the value to the 
        check current step button in the GUI.
        
        """
        step = self.awg.get_current_step()
        self.button_check_current_step.setText('Check current step: {}'.format(step))

    def list_step_toggle_next_condition(self):
        """Toggles the next step condition of the selected step in the 
        `list_step` in the GUI. Toggles between continue and 
        loop_until_trigger.
        

        Returns
        -------
        None. The list of steps in the attribute `list_steps` is updated.

        """
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be edited at once.')
        else:
            selected_step = selectedRows[0]
            if self.steps[selected_step]['after_step'] == 'continue':
                self.steps[selected_step]['after_step'] = 'loop_until_trigger'
            else:
                self.steps[selected_step]['after_step'] = 'continue'
            self.step_list_update()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()