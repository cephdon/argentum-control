#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
    Argentum Control GUI

    Copyright (C) 2013 Isabella Stevens
    Copyright (C) 2014 Michael Shiel
    Copyright (C) 2015 Trent Waddington

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from PyQt4 import QtGui, QtCore

class OptionsDialog(QtGui.QDialog):
    '''
    Argentum Options Dialog
    '''

    optionsToAdd = [('horizontal_offset', 'Distance between cartridges'),
                    ('vertical_offset', 'Misalignment of print heads on cartridges'),
                    ('print_overlap', 'Distance to move between lines'),
                    ('dilate_count', 'Extra thickness of asorbic'),
                    ('x_speed', 'Print speed (x axis)'),
                    ('y_speed', 'Print speed (y axis)'),
                    ('x_acc', 'Acceleration enabled (x axis)'),
                    ('y_acc', 'Acceleration enabled (y axis)')
                   ]
    created = {}

    def __init__(self, parent=None, options=None):

        QtGui.QWidget.__init__(self, parent)

        self.parent = parent
        self.options = options

        #--Layout Stuff---------------------------#
        mainLayout = QtGui.QVBoxLayout()

        if self.options:
            self.addOptions(mainLayout, self.options)

        #--The Button------------------------------#
        layout = QtGui.QHBoxLayout()
        button = QtGui.QPushButton("Save") #string or icon
        #self.connect(button, QtCore.SIGNAL("clicked()"), self.close)
        button.clicked.connect(self.gatherValues)
        layout.addWidget(button)

        mainLayout.addLayout(layout)
        self.setLayout(mainLayout)

        self.resize(400, 60)
        self.setWindowTitle('Printer Options')

    def createOptionWidget(self, parentLayout, optionName, labelText, defaultValue):
        self.addLabel(parentLayout, labelText)

        if type(defaultValue) == type(True):
            checkbox = QtGui.QCheckBox()
            if defaultValue:
                checkbox.setCheckState(QtCore.Qt.Checked)
            else:
                checkbox.setCheckState(QtCore.Qt.Unchecked)
            parentLayout.addWidget(checkbox)
            return checkbox

        optionLineEdit = QtGui.QLineEdit(str(defaultValue))
        parentLayout.addWidget(optionLineEdit)
        return optionLineEdit

    def addOptions(self, parentLayout, options):
        for option in self.optionsToAdd:
            optionName, labelText = option
            if optionName in self.options and self.options[optionName] != "":
                defaultValue = self.options[optionName]
            elif optionName == "x_speed" or optionName == "y_speed":
                defaultValue = 1500
            elif optionName == "x_acc" or optionName == "y_acc":
                defaultValue = True
            else:
                defaultValue = 0

            layout = QtGui.QHBoxLayout()

            widget = self.createOptionWidget(layout, optionName, labelText, defaultValue)

            self.created[optionName] = widget

            parentLayout.addLayout(layout)

    def addLabel(self, layout, labelText):
        label = QtGui.QLabel()
        label.setText(labelText)
        layout.addWidget(label)

    def gatherValues(self):
        options = self.options

        for name, widget in self.created.items():
            if type(widget) == QtGui.QCheckBox:
                options[name] = (widget.checkState() == QtCore.Qt.Checked)
            else:
                options[name] = str(widget.text())

        self.parent.updatePrinterOptions(options)

        self.close()


class InputDialog(QtGui.QDialog):
   '''
   this is for when you need to get some user input text
   '''

   def __init__(self, parent=None, title='user input', label='comment', text=''):

       QtGui.QWidget.__init__(self, parent)

       #--Layout Stuff---------------------------#
       mainLayout = QtGui.QVBoxLayout()

       layout = QtGui.QHBoxLayout()
       self.label = QtGui.QLabel()
       self.label.setText(label)
       layout.addWidget(self.label)

       self.text = QtGui.QLineEdit(text)
       layout.addWidget(self.text)

       mainLayout.addLayout(layout)

       #--The Button------------------------------#
       layout = QtGui.QHBoxLayout()
       button = QtGui.QPushButton("okay") #string or icon
       #self.connect(button, QtCore.SIGNAL("clicked()"), self.close)
       button.clicked.connect(self.close)
       layout.addWidget(button)

       mainLayout.addLayout(layout)
       self.setLayout(mainLayout)

       self.resize(400, 60)
       self.setWindowTitle(title)


class CommandLineEdit(QtGui.QLineEdit):
    submit_keys = [QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return]

    # Order must be up, down
    arrow_keys = [QtCore.Qt.Key_Up, QtCore.Qt.Key_Down]

    command_history = []
    history_index = -1
    last_content = ''

    def __init__(self, *args):
        QtGui.QLineEdit.__init__(self, *args)

    def event(self, event):
        if (event.type() == QtCore.QEvent.KeyPress):
            key = event.key()

            if key in self.submit_keys:
                self.emit(QtCore.SIGNAL("enterPressed"))

                # We leave the signal catcher to call self.submit_command()

                return True

            if key in self.arrow_keys:
                if len(self.command_history) < 1:
                    return True

                if self.history_index < 0:
                    self.last_content = str(self.text())

                if key == self.arrow_keys[0]:
                    self.history_index = min(self.history_index + 1, len(self.command_history) - 1)
                else:
                    self.history_index = max(self.history_index - 1, -1)

                if self.history_index < 0:
                    command = self.last_content
                else:
                    command = self.command_history[self.history_index]

                self.setText(command)

                return True

        return QtGui.QLineEdit.event(self, event)

    def submit_command(self):
        command = str(self.text())

        self.history_index = -1
        self.command_history.insert(0,command)

        self.setText("")

class RollerCalibrationDialog(QtGui.QDialog):
    '''
    Roller Calibration Dialog
    '''

    def __init__(self, controller, parent=None):

        QtGui.QWidget.__init__(self, parent)

        self.controller = controller
        self.parent = parent

        #--Layout Stuff---------------------------#
        mainLayout = QtGui.QVBoxLayout()

        # Controls Here
        row = QtGui.QHBoxLayout()
        self.addButton(row, "Disable Rollers", self.disableRollers)
        self.addButton(row, "Enable Rollers", self.enableRollers)
        mainLayout.addLayout(row)

        row = QtGui.QHBoxLayout()
        self.addButton(row, "Up ^", self.rollerUp)
        self.addButton(row, "Retract", self.rollerRetract)
        mainLayout.addLayout(row)

        row = QtGui.QHBoxLayout()
        self.addButton(row, "Down v", self.rollerDown)
        self.addButton(row, "Deploy", self.rollerDeploy)
        mainLayout.addLayout(row)

        row = QtGui.QHBoxLayout()
        self.addButton(row, "Set Retract Position", self.setRetractPosition)
        self.addButton(row, "Set Deploy Position", self.setDeployPosition)
        mainLayout.addLayout(row)

        #--The Button------------------------------#
        layout = QtGui.QHBoxLayout()
        button = QtGui.QPushButton("Close")
        self.connect(button, QtCore.SIGNAL("clicked()"), self.close)
        layout.addWidget(button)
        saveButton = self.addButton(layout, "Save", self.save)
        mainLayout.addLayout(layout)

        self.setLayout(mainLayout)

        self.resize(200, 60)
        self.setWindowTitle('Roller Calibration')

        saveButton.setDefault(True)
        saveButton.setFocus()
        self.enableRollers()

    def disableRollers(self):
        if self.controller:
            self.controller.rollerCommand('e')

    def enableRollers(self):
        if self.controller:
            self.controller.rollerCommand('E')

    def rollerUp(self):
        if self.controller:
            self.controller.rollerCommand('+')

    def rollerDown(self):
        if self.controller:
            self.controller.rollerCommand('-')

    def rollerRetract(self):
        if self.controller:
            self.controller.rollerCommand('r')

    def rollerDeploy(self):
        if self.controller:
            self.controller.rollerCommand('d')

    def setRetractPosition(self):
        if self.controller:
            self.controller.rollerCommand('R')

    def setDeployPosition(self):
        if self.controller:
            self.controller.rollerCommand('D')

    def save(self):
        if self.controller:
            self.controller.printer.command("!write")
        self.close()

    def addButton(self, parent, label, function):
        button = QtGui.QPushButton(label) #string or icon
        self.connect(button, QtCore.SIGNAL("clicked()"), function)
        parent.addWidget(button)
        return button

    def createOptionWidget(self, parentLayout, optionName, defaultValue):
        optionLineEdit = QtGui.QLineEdit(str(defaultValue))
        parentLayout.addWidget(optionLineEdit)
        return optionLineEdit

    def addOptions(self, parentLayout, options):
        for optionName, defaultValue in options.items():
            layout = QtGui.QHBoxLayout()

            widget = self.createOptionWidget(layout, optionName, defaultValue)

            self.created[optionName] = widget

            parentLayout.addLayout(layout)
