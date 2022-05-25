import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import sys
import os
import numpy as np
os.system("color")
import inspect

#from qtpy.QtCore import QThread,Signal,Qt
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QApplication,QMainWindow,QVBoxLayout,QWidget,
                            QAction,QListWidget,QFormLayout,QComboBox,QLineEdit,
                            QTextEdit,QPushButton,QFileDialog,QAbstractItemView,
                            QGridLayout,QLabel,QHBoxLayout,QCheckBox,QFrame,QListWidgetItem)
from qtpy.QtGui import QIcon,QIntValidator,QDoubleValidator,QColor

import pyqtgraph as pg

from . import qrc_resources
from .networking.client import PyClient

if __name__ == '__main__':
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions import ActionContainer
from rearrangement import RearrangementHandler

freq_functions = [x[5:] for x in dir(ActionContainer) if x[:5] == 'freq_']
amp_functions = [x[4:] for x in dir(ActionContainer) if x[:4] == 'amp_']

num_plot_points = 100

color_cs = '#f5b7a6'
color_rb = '#bdd7ee'
color_loop_until_trigger = '#ffff99'

class QHLine(QFrame):
    """Helper widget to draw horizontal lines in the GUI."""
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)

class QVLine(QFrame):
    """Helper widget to draw vertical lines in the GUI."""
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)

class MainWindow(QMainWindow):
    """Acts as controller for the AWG program.
    ...

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
    rr : RearrangementHandler or None
        The `RearrangementHandler` object which generates the parameters for 
        rearrangement actions. If rearrangement is disabled, this attribute is 
        set to None.
        
        When rearrangement parameters are changed or rearrangement is toggled 
        this object will be recreated.
        
    """
    def __init__(self,name='AWG1',dev_mode=False):
        super().__init__()

        self.name = name

        # if dev_mode:
        self.tcp_client = PyClient(host='localhost',port=6830,name='AWG')
        # else:
        #     self.tcp_client = PyClient(host='129.234.190.164',port=8627,name='SLM')
        # self.tcp_client.start()
        self.last_AWGparam_folder = '.'
        
        self.card_settings = {'active_channels':1,
                              'static_duration_us':2,
                              'sample_rate_Hz':625000000,
                              'max_output_mV':100,
                              'number_of_segments':8
                              }
        
        self.rr = None#RearrangementHandler()

        self.setWindowTitle("{} control".format(self.name))
        self.layout = QVBoxLayout()

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)

        self._create_awg_header()
        self._create_columns()
        self._create_layout_datagen()
        self._create_layout_autoplotter()
        self._create_calculate_buttons()

        self.update_label_awg()

        self.segments = []
        self.steps = []

    def _create_awg_header(self):
        layout = QGridLayout()

        self.label_awg = QLabel(self.name)
        layout.addWidget(self.label_awg,0,0,2,1)

        self.button_card_settings = QPushButton('card settings')
        self.button_card_settings.clicked.connect(self.open_card_settings_window)
        layout.addWidget(self.button_card_settings,0,1,1,1)

        self.button_pydex_settings = QPushButton('PyDex settings')
        layout.addWidget(self.button_pydex_settings,1,1,1,1)

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
        self.button_check_current_segment = QPushButton("Check current segment: ?")
        self.layout_datagen.addWidget(self.button_check_current_segment)

        self.layout_datagen.addWidget(QHLine())
        
        layout_prevent_jumps = QGridLayout()
        self.button_couple_steps_segments = QCheckBox("Couple steps with segments")
        self.button_couple_steps_segments.clicked.connect(self.couple_steps_segments)
        layout_prevent_jumps.addWidget(self.button_couple_steps_segments,0,0,1,1)

        self.button_prevent_freq_jumps = QCheckBox("Prevent frequency jumps")
        self.button_prevent_freq_jumps.setEnabled(False)
        # self.button_prevent_freq_jumps.clicked.connect(self.prevent_freq_jumps)
        self.button_prevent_freq_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_freq_jumps,1,0,1,1)

        self.button_prevent_amp_jumps = QCheckBox("Prevent amplitude jumps")
        self.button_prevent_amp_jumps.setEnabled(False)
        # self.button_prevent_amp_jumps.clicked.connect(self.prevent_amp_jumps)
        self.button_prevent_amp_jumps.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_prevent_amp_jumps,2,0,1,1)

        layout_prevent_jumps.addWidget(QLabel("Prevent phase jumps:"),0,1,1,1)
        
        self.button_freq_adjust_static_segments = QCheckBox("Frequency adjust static segments")
        # self.button_freq_adjust_static_segments.clicked.connect(self.freq_adjust_static_segments)
        self.button_freq_adjust_static_segments.clicked.connect(self.segment_list_update)
        layout_prevent_jumps.addWidget(self.button_freq_adjust_static_segments,1,1,1,1)
        
        self.button_prevent_phase_jumps = QCheckBox("Enforce phase continuity between segments")
        self.button_prevent_phase_jumps.setEnabled(False)
        layout_prevent_jumps.addWidget(self.button_prevent_phase_jumps,2,1,1,1)

        self.layout_datagen.addLayout(layout_prevent_jumps)

        self.layout_datagen.addWidget(QHLine())

        self.button_rearr_mode = QCheckBox("Rearrange mode")
        self.button_rearr_mode.setEnabled(False)
        self.layout_datagen.addWidget(self.button_rearr_mode)

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

        self.button_autoplot = QCheckBox("Autoplot")
        self.button_autoplot.clicked.connect(self.plot_autoplot_graphs)
        self.button_autoplot.setChecked(True)
        self.layout_autoplotter.addWidget(self.button_autoplot)
        
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
        self.button_calculate_send.setEnabled(False)
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
    
    def calculate_all_segments(self):
        for segment in self.segments:
            for channel in range(self.card_settings['active_channels']):
                segment['Ch{}'.format(channel)].calculate()
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
        self.window_segment_add = SegmentCreationWindow(self)
        self.window_segment_add.show()

    def segment_remove(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        print(selectedRows)
        if len(selectedRows) != 0:
            selectedRows.sort(reverse=True)
            for row in selectedRows:
                try:
                    del self.segments[row]
                except IndexError:
                    pass
            self.segment_list_update()
        print(self.segments)

    def segment_up(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be moved.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be moved at once.')
        else:
            currentRow = selectedRows[0]
            if currentRow != 0:
                self.segments[currentRow],self.segments[currentRow-1] = self.segments[currentRow-1],self.segments[currentRow]
                self.segment_list_update()
                self.list_segments.setCurrentRow(currentRow-1)

    def segment_down(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be moved.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be moved at once.')
        else:
            currentRow = selectedRows[0]
            if currentRow != self.list_segments.count()-1:
                self.segments[currentRow],self.segments[currentRow+1] = self.segments[currentRow+1],self.segments[currentRow]
                self.segment_list_update()
                self.list_segments.setCurrentRow(currentRow+1)
    
    def segment_add(self,segment_params,editing_segment=None):
        """Add a new segment to the segment list or edits an exisiting 
        segment based on the kwargs in the segment_params dict.

        Parameters
        ----------
        segment_params : dict
            Dict of segment params for the different channels of the segment.
            Keys should be 'Ch0', 'Ch1', ... and values should be parameter
            dictionaries to be passed though to the `ActionContainer` object; 
            see that docstring for required format.
        editing_segment : None or int, optional
            Index of the segment to be overwritten with the supplied
            `segment_params` The default is None, and will instead result in
            a new segment being added.

        Returns
        -------
        None.

        """
        print(segment_params)
        self.window_segment_add = None
        segment = {}
        for channel in range(self.card_settings['active_channels']):
            channel_params = {'duration_ms':segment_params['duration_ms']}
            channel_params = {**channel_params,**segment_params['Ch{}'.format(channel)]}
            action = ActionContainer(channel_params,self.card_settings)
            segment['Ch{}'.format(channel)] = action
        if editing_segment is None:
            try:
                selected_row = [x.row() for x in self.list_segments.selectedIndexes()][0]
            except:
                selected_row = self.list_segments.count()-1
            self.segments.insert(selected_row+1,segment)
        else:
            self.segments[editing_segment] = segment
        self.segment_list_update()
    
    # def segment_calculate(self,index):
    #     segment = self.list_segments[index]
    #     for channel in range(self.card_settings['active_channels']):
    #         segment['Ch{}'.format(channel)].calculate()

    def segment_remove_all(self):
        self.segments = []
        self.segment_list_update()

    def step_add_dialogue(self):
        self.window_step_add = StepCreationWindow(self)
        self.window_step_add.show()
        
    def segment_edit_dialogue(self):
        selectedRows = [x.row() for x in self.list_segments.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A segment must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one segment can be edited at once.')
        else:
            self.window_segment_add = SegmentCreationWindow(self,selectedRows[0])
            self.window_segment_add.show()

    def step_remove(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        print(selectedRows)
        if len(selectedRows) != 0:
            selectedRows.sort(reverse=True)
            for row in selectedRows:
                try:
                    del self.steps[row]
                except IndexError:
                    pass
            self.step_list_update()
        print(self.steps)

    def step_edit(self):
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        if len(selectedRows) == 0:
            logging.error('A step must be selected before it can be edited.')
        elif len(selectedRows) > 1:
            logging.error('Only one step can be edited at once.')
        else:
            self.window_step_add = StepCreationWindow(self,selectedRows[0])
            self.window_step_add.show()

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
        print(step_params)
        self.window_step_add = None
        try:
            selected_row = [x.row() for x in self.list_steps.selectedIndexes()][0]
        except:
            selected_row = self.list_steps.count()-1
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
            label = '{}: duration_ms={}'.format(i,segment['Ch0'].duration_ms)
            for channel in range(self.card_settings['active_channels']):
                action = segment['Ch{}'.format(channel)]
                label += '\n     Ch{}:'.format(channel) + self.get_segment_list_label(action,i)
                if action.needs_to_calculate:
                    item.setBackground(QColor('#dfbbf0'))  
            item.setText(label)
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
        for i in range(self.list_steps.count()):
            self.list_steps.takeItem(0)
        for i,step in enumerate(self.steps):
            item = QListWidgetItem()
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
        self.card_settings_window = CardSettingsWindow(self,self.card_settings)
        self.card_settings_window.show()

    def get_slm_settings(self):
        return self.slm_settings
    
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
        self.card_settings_window = None

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

        Returns
        -------
        None.

        """
        if self.button_prevent_freq_jumps.isChecked():
            for i,segment in enumerate(self.segments):
                if i > 0:
                    for channel in range(self.card_settings['active_channels']):
                        current_action = segment['Ch{}'.format(channel)]
                        prev_action = self.segments[i-1]['Ch{}'.format(channel)]
                        try:
                            prev_freqs = prev_action.freq_params['end_freq_MHz']
                        except:
                            prev_freqs = prev_action.freq_params['start_freq_MHz']
                        new_start_freqs = []
                        for tone in range(len(current_action.freq_params['start_freq_MHz'])):
                            print(i,tone,current_action.freq_params['start_freq_MHz'])
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
                if i > 0:
                    for channel in range(self.card_settings['active_channels']):
                        current_action = segment['Ch{}'.format(channel)]
                        prev_action = self.segments[i-1]['Ch{}'.format(channel)]
                        if current_action.freq_function_name == 'static':
                            current_freqs = current_action.freq_params['start_freq_MHz']
                            new_prev_seg_end_freqs = []
                            try:
                                for tone in range(len(prev_action.freq_params['end_freq_MHz'])):
                                    end_freq = prev_action.freq_params['start_freq_MHz'][tone]
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
            # self.segment_list_update()

    def prevent_amp_jumps(self):
        if self.button_prevent_amp_jumps.isChecked():
            for i,segment in enumerate(self.segments):
                if i > 0:
                    for channel in range(self.card_settings['active_channels']):
                        try:
                            prev_amps = self.segments[i-1]['Ch{}'.format(channel)].amp_params['end_amp']
                        except:
                            prev_amps = self.segments[i-1]['Ch{}'.format(channel)].amp_params['start_amp']
                        new_start_amps = []
                        for tone in range(len(segment['Ch{}'.format(channel)].amp_params['start_amp'])):
                            start_amp = segment['Ch{}'.format(channel)].amp_params['start_amp'][tone]
                            if not start_amp in prev_amps:
                                new_start_amp = min(prev_amps, key=lambda x:abs(x-start_amp))
                                logging.warning('Changed segment {} Ch{} start_amp from {} to {} to avoid an amplitude jump'.format(i,channel,start_amp,new_start_amp))
                                new_start_amps.append(new_start_amp)
                            else:
                                new_start_amps.append(start_amp)
                        segment['Ch{}'.format(channel)].update_param('amp','start_amp',new_start_amps)
            # self.segment_list_update()
            
    def freq_adjust_static_segments(self):
        if self.button_freq_adjust_static_segments.isChecked():
            for i, segment in enumerate(self.segments):
                for channel in range(self.card_settings['active_channels']):
                    action = segment['Ch{}'.format(channel)]
                    if action.freq_function_name == 'static':
                        duration_ms = action.duration_ms
                        adjusted_freqs = []
                        for unadjusted_freq in action.freq_params['start_freq_MHz']:
                            adjusted_freq = round(unadjusted_freq*(duration_ms*1e3))/(duration_ms*1e3)
                            if adjusted_freq != unadjusted_freq:
                                logging.warning('Adjusted static frequency of segment {} Ch{} from {} to {}'.format(i,channel,unadjusted_freq,adjusted_freq))
                            adjusted_freqs.append(adjusted_freq)
                        segment['Ch{}'.format(channel)].update_param('freq','start_freq_MHz',adjusted_freqs)
            # self.segment_list_update()
                    #     try:
                    #         pass
                    #     except Exception as e:
                    #         logging.error('Error when freq adjusting',e)
                    # try:
                    #     prev_amps = self.segments[i-1]['Ch{}'.format(channel)].amp_params['end_amp']
                    # except:
                    #     prev_amps = self.segments[i-1]['Ch{}'.format(channel)].amp_params['start_amp']
                    # new_start_amps = []
                    # for tone in range(len(segment['Ch{}'.format(channel)].amp_params['start_amp'])):
                    #     start_amp = segment['Ch{}'.format(channel)].amp_params['start_amp'][tone]
                    #     if not start_amp in prev_amps:
                    #         new_start_amp = min(prev_amps, key=lambda x:abs(x-start_amp))
                    #         logging.warning('Changed segment {} Ch{} start_amp from {} to {} to avoid an amplitude jump'.format(i,channel,start_amp,new_start_amp))
                    #         new_start_amps.append(new_start_amp)
                    #     else:
                    #         new_start_amps.append(start_amp)
                    # segment['Ch{}'.format(channel)].update_param('amp','start_amp',new_start_amps)

    def couple_steps_segments(self):
        """Creates a single step for each segment.
        Done such that the after_step and number_of_loops for the steps is conserved where possible.
        """

        if self.button_couple_steps_segments.isChecked():
            if len(self.steps) > len(self.segments):
                self.steps = self.steps[:len(self.segments)]
            elif len(self.steps) < len(self.segments):
                self.steps += [{'segment': 0, 'number_of_loops': 1, 'after_step': 'continue'} for _ in range(len(self.segments)-len(self.steps))]
            for i,step in enumerate(self.steps):
                step['segment'] = i
        self.step_list_update()

        self.button_step_add.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_remove.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        # self.button_step_edit.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_up.setEnabled(not(self.button_couple_steps_segments.isChecked()))
        self.button_step_down.setEnabled(not(self.button_couple_steps_segments.isChecked()))

        self.button_prevent_freq_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        self.button_prevent_amp_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        self.button_prevent_phase_jumps.setEnabled(self.button_couple_steps_segments.isChecked())
        if not(self.button_couple_steps_segments.isChecked()):
            self.button_prevent_freq_jumps.setChecked(False)
            self.button_prevent_amp_jumps.setChecked(False)
            self.button_prevent_phase_jumps.setChecked(False)

    def set_holos_from_list(self,holo_list):
        """
        Set holograms from a list.

        Parameters
        ----------
        holos : list
            Should be a list of sublists containing the holo name and a dict 
            containing the holo arguments in the form [[holo1_name,{holo1_args}],...]
        """
        self.holos = []
        for i,(name,args) in enumerate(holo_list):
            try:
                holo_params = {'name':name}
                holo_params['type'],holo_params['function'] = get_holo_type_function(name)
                holo_params = {**holo_params,**args}
                holo = get_holo_container(holo_params,self.global_holo_params)
                self.holos.append(holo)
            except Exception:
                logging.error('Error when creating Hologram {}. The hologram has been skipped.\n'.format(i))
        self.update_holo_list()
        self.w = None

    def generate_holo_list(self):
        holo_list = []
        for holo in self.holos:
            name = holo.get_name()
            args = holo.get_local_args()
            holo_list.append([name,args])
        return holo_list

    def save_holo_file(self,filename):
        holo_list = self.generate_holo_list()
        msg = [self.slm_settings,holo_list]
        with open(filename, 'w') as f:
            f.write(str(msg))
        logging.info('SLM settings and holograms saved to "{}"'.format(filename))
    
    def save_current_holo_dialogue(self):
        filename = QFileDialog.getSaveFileName(self, 'Save hologram',self.last_SLMparam_folder,"PNG (*.png);;24-bit Bitmap (*.bmp)")[0]
        if filename != '':
            hg.misc.save(self.total_holo,filename)

    def save_holo_file_dialogue(self):
        filename = QFileDialog.getSaveFileName(self, 'Save SLMparam',self.last_SLMparam_folder,"Text documents (*.txt)")[0]
        if filename != '':
            self.save_holo_file(filename)
            self.last_SLMparam_folder = os.path.dirname(filename)
            print(self.last_SLMparam_folder)

    def recieved_tcp_msg(self,msg):
        logging.info('TCP message recieved: "'+msg+'"')
        split_msg = msg.split('=')
        command = split_msg[0]
        arg = split_msg[1]
        if command == 'save':
            pass
        elif command == 'save_all':
            self.save_holo_file(arg)
        elif command == 'load_all':
            self.load_holo_file(arg)
        elif command == 'set_data':
            for update in eval(arg):
                try:
                    ind,arg_name,arg_val = update
                    logging.info('Updating Hologram {} with {} = {}'.format(ind,arg_name,arg_val))
                    holo = self.holos[ind]
                    holo.update_arg(arg_name,arg_val)
                    self.holos[ind] = holo
                except NameError: 
                    logging.error('{} is an invalid argument for Hologram {}\n'.format(arg_name,ind))
                except IndexError: 
                    logging.error('Hologram {} does not exist\n'.format(ind))
        self.update_holo_list()
    
    def load_holo_file_dialogue(self):
        filename = QFileDialog.getOpenFileName(self, 'Load SLMparam',self.last_SLMparam_folder,"Text documents (*.txt)")[0]
        if filename != '':
            self.load_holo_file(filename)
            self.last_SLMparam_folder = os.path.dirname(filename)

    def load_holo_file(self,filename):
        try:
            with open(filename, 'r') as f:
                msg = f.read()
        except FileNotFoundError:
            logging.error('"{}" does not exist'.format(filename))
            return
        try:
            msg = eval(msg)
            slm_settings = msg[0]
            holo_list = msg[1]
            self.update_slm_settings(slm_settings)
            try:
                self.slm
            except AttributeError:
                # logging.info('SLM settings loaded from "{}"'.format(filename))
                pass
            else:
                self.set_holos_from_list(holo_list)
                logging.info('SLM settings and holograms loaded from "{}"'.format(filename))
        except (SyntaxError, IndexError):
            logging.error('Failed to evaluate file "{}". Is the format correct?'.format(filename))

    def plot_autoplot_graphs(self):
        """Populates the autoplotter frequency graph with the steps."""
        if self.button_autoplot.isChecked():
            for channel in range(self.card_settings['active_channels']):
                freq_plot = self.freq_plots[channel]
                amp_plot = self.amp_plots[channel]
                freq_plot.clear()
                amp_plot.clear()
                duration_xlabels = {}
                segment_xlabels = {}
                current_pos = 0
                for step in self.steps:
                    for i in range(step['number_of_loops']):
                        action = self.segments[step['segment']]['Ch{}'.format(channel)]
                        freqs, amps = action.get_autoplot_traces()
                        xs = np.linspace(current_pos,current_pos+1,len(freqs[0]))
                        for j,(freq,amp) in enumerate(zip(freqs,amps)):
                            freq_plot.plot(xs,freq, pen=pg.mkPen(color=j,width=2))
                            amp_plot.plot(xs,amp, pen=pg.mkPen(color=j,width=2))
                            
                        duration_xlabels[current_pos+0.5] = action.duration_ms
                        segment_xlabels[current_pos+0.5] = step['segment']
                        freq_plot.addItem(pg.InfiniteLine(current_pos,pen={'color': "#000000"}))
                        amp_plot.addItem(pg.InfiniteLine(current_pos,pen={'color': "#000000"}))
                        
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
                data = segment['Ch{}'.format(channel)].data
                filename = export_directory+"/seg{}ch{}.csv".format(seg_num,channel)
                print(filename)
                np.savetxt(filename, data, delimiter=",")
                
    def calculate_send(self):
        pass
    
    def list_step_toggle_next_condition(self):
        """Toggles the next step condition of the selected step in the 
        `list_step` in the GUI. Toggles between continue and 
        loop_until_trigger.
        

        Returns
        -------
        None. The list of steps in the attribute `list_steps` is updated.

        """
        selectedRows = [x.row() for x in self.list_steps.selectedIndexes()]
        print(self.steps)
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

class CardSettingsWindow(QWidget):
    def __init__(self,mainWindow,card_settings):
        super().__init__()
        self.mainWindow = mainWindow
        self.card_settings = card_settings
        self.setWindowTitle("card settings")

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.layout_card_settings = QFormLayout()
        for key in list(self.card_settings.keys()):
            if key == 'active_channels':
                widget = QComboBox()
                widget.addItems(['1','2'])
                widget.setCurrentText(str(self.card_settings[key]))
            else:
                widget = QLineEdit()
                widget.setText(str(self.card_settings[key]))
                if key == 'number_of_segments':
                    widget.setValidator(QIntValidator())
                else:
                    widget.setValidator(QDoubleValidator())
            self.layout_card_settings.addRow(key, widget)
        layout.addLayout(self.layout_card_settings)

        self.button_save = QPushButton("Save")
        self.button_save.clicked.connect(self.update_card_settings)
        layout.addWidget(self.button_save)
           
    def update_card_settings(self):
        new_card_settings = self.card_settings.copy()
        for row in range(self.layout_card_settings.rowCount()):
            key = self.layout_card_settings.itemAt(row,0).widget().text()
            widget = self.layout_card_settings.itemAt(row,1).widget()
            if key == 'active_channels':
                value = int(widget.currentText())
            elif key == 'number_of_segments':
                value = int(widget.text())
            else:
                value = float(widget.text())
            new_card_settings[key] = value
        self.mainWindow.update_card_settings(new_card_settings)

    def get_card_settings(self):
        return self.card_settings

class SegmentCreationWindow(QWidget):
    def __init__(self,main_window,editing_segment=None):
        """
        Container window for adding/editing segments. Most of the actual 
        functionality is handled by the `SegmentChannelWidget` class which 
        can be iterated if using multiple channels.

        Parameters
        ----------
        main_window : MainWindow
            The parent window of this class. Passed through to allow this 
            window to close itself when the Add/Edit button is pressed.
        editing_segment : None or int, optional
            The segment currently being edited. The default is None, and will
            cause the dialogue box to add a new segment instead.

        Returns
        -------
        None. The `main_window.segment_add` or `main_window.segment_edit` 
        function is called to save the segment parameters.

        """
        super().__init__()
        self.main_window = main_window
        # if edit_holo is None:
        self.setWindowTitle("New segment")
        self.editing_segment = editing_segment
        
        if self.editing_segment is not None:
            self.setWindowTitle("Edit segment {}".format(self.editing_segment))

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout_duration = QFormLayout()
        self.box_duration = QLineEdit()
        self.box_duration.setValidator(QDoubleValidator())
        if self.editing_segment is not None:
            self.box_duration.setText(str(self.main_window.segments[self.editing_segment]['Ch0'].duration_ms))
        else:
            self.box_duration.setText(str(1))
            
        layout_duration.addRow('duration_ms', self.box_duration)
        layout.addLayout(layout_duration)

        self.channel_widgets = [SegmentChannelWidget(i,self.main_window,self.editing_segment) for i in range(main_window.card_settings['active_channels'])]

        for channel_widget in self.channel_widgets:
            layout.addWidget(QHLine())
            layout.addWidget(channel_widget)

        if self.editing_segment is not None:
            self.button_segment_add = QPushButton("Edit")
        else:
            self.button_segment_add = QPushButton("Add")
        self.button_segment_add.clicked.connect(self.segment_add)
        layout.addWidget(QHLine())
        layout.addWidget(self.button_segment_add)
    
    def segment_add(self):
        """Collect the parameters from the `SegmentChannelWidget` objects 
        before submitting them back to the `MainWindow` parent object.
        
        """
        segment_params = {}
        segment_params['duration_ms'] = float(self.box_duration.text())
        success = True
        for channel_widget in self.channel_widgets:
            index = channel_widget.channel_index

            channel_params = {}
            channel_success, channel_params['freq'], channel_params['amp'] = channel_widget.get_params()

            segment_params['Ch{}'.format(index)] = channel_params
            
            if not channel_success:
                success = False
        
        if success:
            self.main_window.segment_add(segment_params,self.editing_segment)

class SegmentChannelWidget(QWidget):
    def __init__(self,channel_index,main_window,editing):
        """Widget for defining the parameters of a segment for the channel 
        defined by `channel_index`.
        

        Parameters
        ----------
        channel_index : int
            Index of the channel that this object is setting the parameters of.
        main_window : MainWindow
            The `MainWindow` object of the GUI (the double parent of this 
            object). This is passed through to allow this window to access the
            segment actions and allow the current parameters to be read (but 
            NOT written; this is handled by the `main_window` when parameters
            are passed back via this objects `SegmentCreationWindow` parent).
        editing : None or int
            The segment currently being edited. None will cause the parameters
            to be set to their default values, whilst int will autopopulate the
            parameters from the relevant `ActionContainer` object if the 
            function is correct.

        Returns
        -------
        None.

        """
        super().__init__()
        self.channel_index = channel_index
        self.main_window = main_window
        self.editing = editing
        print(self.editing)
        
        if self.editing is not None:
            self.segment = self.main_window.segments[self.editing]['Ch{}'.format(self.channel_index)]
        else:
            self.segment = None

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QLabel('<h3>Channel {}</h3>'.format(self.channel_index)))

        layout.addWidget(QLabel('<h4>Frequency</h4>'))
        self.box_freq_function = QComboBox()
        self.box_freq_function.addItems(freq_functions)
        if self.editing is not None:
            self.box_freq_function.setCurrentText(self.segment.freq_function_name)
        else:
            self.box_freq_function.setCurrentText('static')
        self.box_freq_function.currentTextChanged.connect(self.update_freq_arguments)
        layout.addWidget(self.box_freq_function)

        self.layout_freq_params = QFormLayout()
        layout.addLayout(self.layout_freq_params)

        layout.addWidget(QLabel('<h4>Amplitude</h4>'))
        self.box_amp_function = QComboBox()
        self.box_amp_function.addItems(amp_functions)
        if self.editing is not None:
            self.box_amp_function.setCurrentText(self.segment.amp_function_name)
        else:
            self.box_amp_function.setCurrentText('static')
        self.box_amp_function.currentTextChanged.connect(self.update_amp_arguments)
        layout.addWidget(self.box_amp_function)

        self.layout_amp_params = QFormLayout()
        layout.addLayout(self.layout_amp_params)

        self.update_freq_arguments()
        self.update_amp_arguments()
    
    def update_freq_arguments(self):
        self.clear_freq_params()
        freq_function = self.box_freq_function.currentText()
        if (self.editing is not None) and (freq_function == self.segment.freq_function_name):
            arguments = self.segment.freq_params.keys()
            defaults = self.segment.freq_params.values()
        else:
            arguments,_,_,defaults = inspect.getfullargspec(eval('ActionContainer.freq_'+freq_function))[:4]
        if len(arguments) != len(defaults):
            pad = ['']*(len(arguments)-len(defaults))
            defaults = pad + list(defaults)
        card_settings = self.main_window.card_settings

        for argument,default in zip(arguments,defaults):
            if default != '':
                if (argument not in card_settings.keys()) and (argument[0] != '_'):
                    self.layout_freq_params.addRow(argument, QLineEdit())
                    text_box = self.layout_freq_params.itemAt(self.layout_freq_params.rowCount()-1, 1).widget()
                    text_box.returnPressed.connect(self.return_freq_params)
                    # if (self.editing == True) and (current == self.current_name):
                    #     text_box.setText(str(self.current_params[argument]))
                    text_box.setText(str(default))
        # self.holoDocBox.setText(self.function.__doc__.split('Returns')[0])

    def clear_freq_params(self):
        for i in range(self.layout_freq_params.rowCount()):
            self.layout_freq_params.removeRow(0)

    def update_amp_arguments(self):
        self.clear_amp_params()
        amp_function = self.box_amp_function.currentText()
        if (self.editing is not None) and (amp_function == self.segment.amp_function_name):
            arguments = self.segment.amp_params.keys()
            defaults = self.segment.amp_params.values()
        else:
            arguments,_,_,defaults = inspect.getfullargspec(eval('ActionContainer.amp_'+amp_function))[:4]
        if len(arguments) != len(defaults):
            pad = ['']*(len(arguments)-len(defaults))
            defaults = pad + list(defaults)
        card_settings = self.main_window.card_settings

        for argument,default in zip(arguments,defaults):
            if default != '':
                if (argument not in card_settings.keys()) and (argument[0] != '_'):
                    self.layout_amp_params.addRow(argument, QLineEdit())
                    text_box = self.layout_amp_params.itemAt(self.layout_amp_params.rowCount()-1, 1).widget()
                    text_box.returnPressed.connect(self.return_amp_params)
                    # if (self.editing == True) and (current == self.current_name):
                    #     text_box.setText(str(self.current_params[argument]))
                    text_box.setText(str(default))
        # self.holoDocBox.setText(self.function.__doc__.split('Returns')[0])

    def clear_amp_params(self):
        for i in range(self.layout_amp_params.rowCount()):
            self.layout_amp_params.removeRow(0)

    def return_freq_params(self):
        pass

    def return_amp_params(self):
        pass

    def get_params(self):
        success = True
        freq_params = {}
        freq_params['function'] = self.box_freq_function.currentText()
        
        for row in range(self.layout_freq_params.rowCount()):
            key = self.layout_freq_params.itemAt(row,0).widget().text()
            widget = self.layout_freq_params.itemAt(row,1).widget()
            value = widget.text()
            try:
                print(value)
                value = self.convert_str_to_list(value)
                print(value)
            except Exception:
                logging.error('Failed to evaluate {} for amplitude parameter {}'.format(value,key))
                widget.setStyleSheet('background-color: red')
                success = False
            else:
                widget.setStyleSheet('')
                freq_params[key] = value
        
        amp_params = {}
        amp_params['function'] = self.box_amp_function.currentText()
        
        for row in range(self.layout_amp_params.rowCount()):
            key = self.layout_amp_params.itemAt(row,0).widget().text()
            widget = self.layout_amp_params.itemAt(row,1).widget()
            value = widget.text()
            try:
                value = self.convert_str_to_list(value)
            except Exception:
                logging.error('Failed to evaluate {} for amplitude parameter {}'.format(value,key))
                widget.setStyleSheet('background-color: red')
                success = False
            else:
                widget.setStyleSheet('')
                amp_params[key] = value

        print(freq_params, amp_params)

        return success, freq_params, amp_params
    
    def convert_str_to_list(self,string):
        string = str(string)
        string = string.replace('[','')
        string = string.replace(']','')
        string = '['+string+']'
        return eval(string)

class StepCreationWindow(QWidget):
    def __init__(self,mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
        self.setWindowTitle("New step")

        layout = QVBoxLayout()
        self.setLayout(layout)

        step_settings = ['segment','number_of_loops','after_step']
        after_step_options = ['continue','loop_until_trigger']

        self.layout_step_settings = QFormLayout()

        for key in step_settings:
            if key == 'after_step':
                widget = QComboBox()
                widget.addItems(after_step_options)
                widget.setCurrentText(after_step_options[0])
            else:
                widget = QLineEdit()
                if key == 'number_of_loops':
                    widget.setText(str(1))
                else:
                    widget.setText(str(0))
                widget.setValidator(QIntValidator())
            self.layout_step_settings.addRow(key, widget)
        layout.addLayout(self.layout_step_settings)

        self.button_save = QPushButton("Add")
        self.button_save.clicked.connect(self.update_card_settings)
        layout.addWidget(self.button_save)
           
    def update_card_settings(self):
        step_params = {}
        for row in range(self.layout_step_settings.rowCount()):
            key = self.layout_step_settings.itemAt(row,0).widget().text()
            widget = self.layout_step_settings.itemAt(row,1).widget()
            if key == 'after_step':
                value = widget.currentText()
            else:
                value = int(widget.text())
            step_params[key] = value
        self.mainWindow.step_add(step_params)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()