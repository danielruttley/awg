from qtpy.QtWidgets import QFrame

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
        
def convert_str_to_list(string):
    string = str(string)
    string = string.replace('[','')
    string = string.replace(']','')
    if string == '':
        raise Exception
    string = '['+string+']'
    return eval(string)