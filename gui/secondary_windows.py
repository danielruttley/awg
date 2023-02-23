import logging
import inspect
from copy import copy

from qtpy.QtWidgets import (QVBoxLayout,QWidget,QFormLayout,QComboBox,
                            QLineEdit,QPushButton,QLabel,QGridLayout,
                            QCheckBox,QFileDialog)
from qtpy.QtGui import QIntValidator,QDoubleValidator

from .helpers import convert_str_to_list, QHLine

from actions import ActionContainer

freq_functions = [x[5:] for x in dir(ActionContainer) if x[:5] == 'freq_']
amp_functions = [x[4:] for x in dir(ActionContainer) if x[:4] == 'amp_']
max_num_segments = 10 # actual value is 2**(max_num_segments)

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
            elif key == 'number_of_segments':
                widget = QComboBox()
                widget.addItems([str(2**x) for x in list(range(max_num_segments+1))])
                widget.setCurrentText(str(self.card_settings[key]))
            else:
                widget = QLineEdit()
                widget.setText(str(self.card_settings[key]))
                widget.setValidator(QDoubleValidator())
            if key in ['segment_min_samples','segment_step_samples']:
                widget.setReadOnly(True)
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
            if key in ['active_channels','number_of_segments']:
                value = int(widget.currentText())
            elif key in ['sample_rate_Hz','segment_min_samples','segment_step_samples']:
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
            self.box_duration.setText(str(self.main_window.segments[self.editing_segment][0].duration_ms))
        else:
            self.box_duration.setText(str(1))
        layout_duration.addRow('duration_ms', self.box_duration)
        
        self.box_phase_behaviour = QComboBox()
        self.box_phase_behaviour.addItems(['optimise','continue','manual'])
        if self.editing_segment is not None:
            self.box_phase_behaviour.setCurrentText(self.main_window.segments[self.editing_segment][0].phase_behaviour)
        else:
            self.box_phase_behaviour.setCurrentText('continue')
        layout_duration.addRow('phase_behaviour', self.box_phase_behaviour) 
        
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
        segment_params['phase_behaviour'] = self.box_phase_behaviour.currentText()
        
        success = True
        for channel_widget in self.channel_widgets:
            index = channel_widget.channel_index

            channel_params = {}
            channel_success, channel_params['freq'], channel_params['amp'], channel_params['amp_comp_filename'] = channel_widget.get_params()

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
            self.segment = self.main_window.segments[self.editing][self.channel_index]
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

        layout_amp_comp = QGridLayout()
        layout_amp_comp.addWidget(QLabel('Amp compensation file:'),0,0,1,1)
        self.label_amp_comp_filename = QLabel('None')
        layout_amp_comp.addWidget(self.label_amp_comp_filename,0,1,1,4)
        amp_comp_browse_button = QPushButton('Browse')
        amp_comp_browse_button.clicked.connect(self.open_amp_comp_browse_window)
        layout_amp_comp.addWidget(amp_comp_browse_button,0,5,1,1)
        layout.addLayout(layout_amp_comp)

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
                value = convert_str_to_list(value)
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
                value = convert_str_to_list(value)
            except Exception:
                logging.error('Failed to evaluate {} for amplitude parameter {}'.format(value,key))
                widget.setStyleSheet('background-color: red')
                success = False
            else:
                widget.setStyleSheet('')
                amp_params[key] = value

        amp_comp_filename = self.label_amp_comp_filename.text()

        return success, freq_params, amp_params, amp_comp_filename

    def open_amp_comp_browse_window(self):
        filename = QFileDialog.getOpenFileName(self, 'Load amplitude compensation file','.',"Text documents (*.txt)")[0]
        if filename != '':
            self.label_amp_comp_filename.setText(filename)

class StepCreationWindow(QWidget):
    def __init__(self,main_window,editing=None):
        """Widget for defining the parameters of a step.
        
        Parameters
        ----------
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
        self.main_window = main_window
        self.editing = editing
        self.setWindowTitle('New step')
        
        if self.editing != None:
            self.setWindowTitle('Editing step {}'.format(editing))

        layout = QVBoxLayout()
        self.setLayout(layout)

        step_settings = ['segment','number_of_loops','after_step','rearr']
        after_step_options = ['continue','loop_until_trigger']
        rearr_options = ['False','True']

        self.layout_step_settings = QFormLayout()

        for key in step_settings:
            if key == 'after_step':
                widget = QComboBox()
                widget.addItems(after_step_options)
                widget.setCurrentText(after_step_options[0])
                if self.editing != None:
                    widget.setCurrentText(self.main_window.steps[editing][key])
            elif key == 'rearr':
                widget = QComboBox()
                widget.addItems(rearr_options)
                widget.setCurrentText(after_step_options[0])
                if self.editing != None:
                    widget.setCurrentText(str(self.main_window.steps[editing][key]))
            else:
                widget = QLineEdit()
                if key == 'number_of_loops':
                    widget.setText(str(1))
                else:
                    widget.setText(str(0))
                if self.editing != None:
                    widget.setText(str(self.main_window.steps[editing][key]))
                widget.setValidator(QIntValidator())
            self.layout_step_settings.addRow(key, widget)
        layout.addLayout(self.layout_step_settings)

        if self.editing != None:
            self.button_save = QPushButton("Edit")
        else:
            self.button_save = QPushButton("Add")
            
        self.button_save.clicked.connect(self.update_step_settings)
        layout.addWidget(self.button_save)
           
    def update_step_settings(self):
        step_params = {}
        for row in range(self.layout_step_settings.rowCount()):
            key = self.layout_step_settings.itemAt(row,0).widget().text()
            widget = self.layout_step_settings.itemAt(row,1).widget()
            if key == 'after_step':
                value = widget.currentText()
            elif key == 'rearr':
                value = eval(widget.currentText())
            else:
                value = int(widget.text())
            step_params[key] = value
        
        self.main_window.step_add(step_params,self.editing)

class RearrSettingsWindow(QWidget):
    def __init__(self,mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
        self.setWindowTitle("rearrangement settings")

        layout = QVBoxLayout()
        self.setLayout(layout)

        settings = ['start_freq_MHz','target_freq_MHz','channel','segment','mode']

        self.layout_rearr_settings = QFormLayout()
        for key in settings:
            value = getattr(self.mainWindow.rr,key)
            if key == 'channel':
                widget = QComboBox()
                widget.addItems([str(x) for x in list(range(self.mainWindow.card_settings['active_channels']))])
                widget.setCurrentText(str(value))
            elif key == 'mode':
                widget = QComboBox()
                widget.addItems(['simultaneous','sequential'])
                widget.setCurrentText(str(value))
            else:
                widget = QLineEdit()
                widget.setText(str(value))
                if not 'freq' in key:
                    widget.setValidator(QDoubleValidator())
            self.layout_rearr_settings.addRow(key, widget)
        layout.addLayout(self.layout_rearr_settings)

        self.button_save = QPushButton("Save")
        self.button_save.clicked.connect(self.update_rearr_settings)
        layout.addWidget(self.button_save)
           
    def update_rearr_settings(self):
        new_rearr_settings = {}
        for row in range(self.layout_rearr_settings.rowCount()):
            key = self.layout_rearr_settings.itemAt(row,0).widget().text()
            widget = self.layout_rearr_settings.itemAt(row,1).widget()
            if key == 'channel':
                value = int(widget.currentText())
            elif key == 'mode':
                value = widget.currentText()
            elif 'freq' in key:
                try:
                    value = convert_str_to_list(widget.text())
                except:
                    logging.error('Could not evaluate {} for rearrangement setting {}'.format(widget.text(),key))
                    return
            else:
                value = int(widget.text())
            new_rearr_settings[key] = value
        self.mainWindow.update_rearr_settings(new_rearr_settings)
        
class AmpAdjusterSettingsWindow(QWidget):
    def __init__(self,mainWindow,amp_adjuster_settings):
        """The container window for the AmpAdjuster settings. This window 
        handles communication with the main window. Actual parameters are set
        in the sub-widgets for each channel.
        
        Parameters
        ----------
        mainWindow : `MainWindow`
            The main gui controller which opens this window. Passing this 
            through allows this window to resubmit the new parameters 
            directly to the mainWindow.
        amp_adjuster_settings : list of dicts
            The amp_adjuster_settings to modify in this window. A copy is made 
            and then resubmitted when the user is finished editing. This allows 
            the MainWindow to reject changes and keep the old settings if it 
            encounters an error in the new values.
            
            This should be a list of dicts where each entry is the dict for a 
            given channel.
        
        """
        
        super().__init__()
        self.mainWindow = mainWindow
        self.aa_settings = amp_adjuster_settings.copy()
        self.setWindowTitle("AmpAdjuster settings")
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        self.channel_widgets = []
        
        for channel,settings in enumerate(self.aa_settings):
            channel_widget = AmpAdjusterSettingsChannelWidget(channel,settings)
            layout.addWidget(channel_widget)
            self.channel_widgets.append(channel_widget)

        self.button_save = QPushButton("Save")
        self.button_save.clicked.connect(self.update_aa_settings)
        layout.addWidget(self.button_save)
           
    def update_aa_settings(self):
        aa_settings = []
        overall_success = True
        for channel, widget in enumerate(self.channel_widgets):
            success, settings = widget.get_settings()
            aa_settings.append(settings)
            if not success:
                overall_success = False
        if overall_success:
            self.mainWindow.set_amp_adjuster_settings(new_amp_adjuster_settings=aa_settings)
    
class AmpAdjusterSettingsChannelWidget(QWidget):
    def __init__(self,channel,settings):
        """Widget to edit the amp adjuster settings for a single channel.
        
        Parameters
        ----------
        channel : {0,1}
            The channel index to use.
        settings_window : AmpAdjusterSettingsWindow
            The AmpAdjuster window which is the parent of this widget. Passing 
            this object through allows for the exisiting dictionary parameters 
            to be displayed.
            
        """
        super().__init__()
        self.channel = channel
        self.settings = settings
        
        layout = QGridLayout()
        self.setLayout(layout)
        
        layout.addWidget(QLabel('<h2>Channel {}</h2>'.format(self.channel)),0,0,1,4)
        
        self.button_enabled = QCheckBox('Enable AmpAdjuster')
        self.button_enabled.setChecked(settings['enabled'])
        
        layout.addWidget(self.button_enabled,0,4,1,2)
        
        layout.addWidget(QLabel('Calibration file:'),1,0,1,1)
        
        self.label_filename = QLabel(settings['filename'])
        
        layout.addWidget(self.label_filename,1,1,1,4)
        
        browse_button = QPushButton('Browse')
        browse_button.clicked.connect(self.open_calibration_browse_window)
        layout.addWidget(browse_button,1,5,1,1)
        
        self.form_layout = QFormLayout()
        
        for key in ['non_adjusted_amp_mV']:
            widget = QLineEdit()
            widget.setText(str(self.settings[key]))
            widget.setValidator(QDoubleValidator())
            self.form_layout.addRow(key, widget)

        self.form_layout.addRow('Legacy parameters (not used with .awgde files):',None)

        for key in ['freq_limit_1_MHz','freq_limit_2_MHz','amp_limit_1','amp_limit_2']:
            widget = QLineEdit()
            widget.setText(str(self.settings[key]))
            widget.setValidator(QDoubleValidator())
            self.form_layout.addRow(key, widget)
        layout.addLayout(self.form_layout,2,0,1,6)
    
    def open_calibration_browse_window(self):
        filename = QFileDialog.getOpenFileName(self, 'Load channel {} AmpAdjust calibration'.format(self.channel),'.',"AWG DE calibration (*.awgde);;Text documents (*.txt)")[0]
        if filename != '':
            self.label_filename.setText(filename)
    
    def get_settings(self):
        """Returns the settings of the AmpAdjuster channel as a dictionary to 
        be collated by the parent `AmpAdjusterSettingsWindow` class before 
        being passed back to the `MainWindow class.
        
        """
        success = True
        settings = {}
        
        settings['enabled'] = self.button_enabled.isChecked()
        settings['filename'] = self.label_filename.text()
        
        for row in range(self.form_layout.rowCount()):
            key = self.form_layout.itemAt(row,0).widget().text()
            widget = self.form_layout.itemAt(row,1).widget()
            value = widget.text()
            try:
                value = float(value)
            except Exception:
                logging.error('Failed to evaluate {} for channel {} AmpAdjuster parameter {}'.format(value,self.channel,key))
                widget.setStyleSheet('background-color: red')
                success = False
            else:
                widget.setStyleSheet('')
                settings[key] = value

        return success, settings        
