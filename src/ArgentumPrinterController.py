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

from PrinterController import PrinterController
import serial
import hashlib
import os
import time
import sys
from imageproc import calcDJB2

order = ['8', '4', 'C', '2', 'A', '6', 'E', '1', '9', '5', 'D', '3', 'B'];
MAX_FIRING_LINE_LEN = 13*4+12
NO_RESPONSE = "Printer didn't respond. Please ensure no other programs have the port open and try again."

class ArgentumPrinterController(PrinterController):
    serialDevice = None
    port = None
    connected = False
    delimiter = '\n'
    lastError = None
    version = None
    printerNumber = None
    lightsOn = True
    leftFanOn = False
    rightFanOn = False
    printing = False
    sendingFile = False
    logSerial = False
    serialLog = None

    def __init__(self, port=None):
        self.port = port
        self.lastCommandTime = None

    def clearPrinterNumber(self):
        self.printerNumber = None

    def clearVersion(self):
        self.version = None
        self.majorVersion = None
        self.minorVersion = None
        self.patchVersion = None
        self.buildVersion = None
        self.tagVersion   = None

    def serialWriteString(self, strval):
        data = strval.encode('utf-8')
        self.serialWriteRaw(data)

    def serialWriteRaw(self, data):
        self.logData("write:", data)
        self.serialDevice.write(data)

    def debug(self, msg):
        msg = str(msg)
        print(msg)
        if self.logSerial:
            if self.serialLog == None:
                self.serialLog = open("serial.log", "wb")
            self.serialLog.write(msg + "\n")
            self.serialLog.flush()

    def logData(self, msg, data):
        if self.logSerial:
            if self.serialLog == None:
                self.serialLog = open("serial.log", "wb")
            str = msg
            for d in data:
                if (d >= 'a' and d <= 'z' or
                    d >= 'A' and d <= 'Z' or
                    d >= '0' and d <= '9' or
                    d == '+' or d == '-' or d == ' ' or d == '#' or
                    d == '[' or d == ']' or d == '.' or d == ',' or
                    d == '?' or d == '!' or d == ':' or d == '_' or
                    d == "'"):
                    str = str + d
                elif d == '\r':
                    str = str + "\\r"
                elif d == '\n':
                    str = str + "\\n"
                else:
                    str = str + "\\x{:02}".format(ord(d))
            self.serialLog.write(str + "\n")
            self.serialLog.flush()

    def serialSetTimeout(self, timeout, serialDevice=None):
        if serialDevice == None:
            serialDevice = self.serialDevice
        if sys.platform == "win32":
            from serial import win32, ctypes
            if timeout == None:
                timeouts = (0, 0, 0, 0, 0)
            elif timeout == 0:
                timeouts = (win32.MAXDWORD, 0, 0, 0, 0)
            else:
                timeouts = (0, 0, int(timeout*1000), 0, 0)
            win32.SetCommTimeouts(serialDevice.hComPort, ctypes.byref(win32.COMMTIMEOUTS(*timeouts)))
            serialDevice._timeout = timeout
        else:
            serialDevice.timeout = timeout

    def serialRead(self, n, serialDevice=None):
        data = None
        if serialDevice:
            data = serialDevice.read(n)
        else:
            data = self.serialDevice.read(n)
        self.logData("read:", data)
        return data

    def parseVersion(self, version):
        if version.find('.') == -1:
            return
        major = version[:version.find('.')]
        version = version[version.find('.')+1:]
        if version.find('.') == -1:
            return
        minor = version[:version.find('.')]
        version = version[version.find('.')+1:]
        if version.find('+') == -1:
            return
        patch = version[:version.find('+')]
        build = version[version.find('+')+1:].rstrip()
        if len(build) != 8:
            return

        tag = None
        if patch.find('-') != -1:
            tag = patch[patch.find('-')+1:]
            patch = patch[:patch.find('-')]

        try:
            major = int(major)
            minor = int(minor)
            patch = int(patch)
        except ValueError:
            return

        self.version = "{}.{}.{}".format(major, minor, patch)
        if tag:
            self.version = self.version + "-" + tag
        self.version = self.version + "+" + build

        self.majorVersion = major
        self.minorVersion = minor
        self.patchVersion = patch
        self.buildVersion = build
        self.tagVersion   = tag

        self.debug("Printer is running version: " + self.version)

    def resetPort(self, serialDevice):
        try:
            import termios
            self.debug("Attempting low level port reset.")
            attrs = termios.tcgetattr(serialDevice.fd)
            termios.tcsetattr(serialDevice.fd, termios.TCSANOW, attrs)
            return True
        except:
            pass
        return False

    def connect(self, port=None):
        if port:
            self.port = port

        try:
            self.serialDevice = None
            serialDevice = serial.Serial(self.port, 115200, timeout=0)
            serialDevice.flushInput()
            serialDevice.flush()
            serialDevice.close()
            serialDevice = serial.Serial(self.port, 115200, timeout=1)
            self.connected = False
            self.lightsOn = True
            self.leftFanOn = False
            self.rightFanOn = False

            self.clearPrinterNumber()
            self.clearVersion()
            self.junkBeforeVersion = []

            self.debug("Waiting for printer response.")
            allResponse = ''
            firstChar = self.serialRead(1, serialDevice)
            if firstChar == None:
                self.debug("No first char.")
                self.serialSetTimeout(10, serialDevice)
                firstChar = self.serialRead(1, serialDevice)
            if firstChar == None or len(firstChar) == 0:
                self.debug("No response.")
                self.lastError = NO_RESPONSE
                return False
            firstCharOrd = ord(firstChar)
            if firstCharOrd < 9 or firstCharOrd > 126:
                self.debug("Trying port reset.")
                if not self.resetPort(serialDevice):
                    self.debug("Reset port not possible.")
                    self.lastError = "Port needs reset."
                    serialDevice.close()
                    return False
                serialDevice.close()
                serialDevice = serial.Serial(self.port, 115200, timeout=1)
                firstChar = self.serialRead(1, serialDevice)
                firstCharOrd = ord(firstChar)
                if firstCharOrd < 9 or firstCharOrd > 126:
                    self.debug("Reset port failed.")
                    self.lastError = "Port needs reset."
                    serialDevice.close()
                    return False
                self.debug("Reset port okay!")

            self.debug("Reading rest of response.")
            allResponse = ''
            try:
                while len(allResponse) < 80:
                    allResponse = allResponse + firstChar
                    n = serialDevice.inWaiting()
                    if n != 0:
                        allResponse = allResponse + self.serialRead(n, serialDevice)
                    firstChar = self.serialRead(1, serialDevice)
                    if firstChar == None or len(firstChar) == 0:
                        break
            except:
                pass

            if len(allResponse) < 8:
                self.debug("Response is too short.")
                self.lastError = NO_RESPONSE
                return False

            printerNumber = None
            version = None
            pm = '+Printer Number ['
            if allResponse.find(pm) != -1:
                if allResponse.find(pm) != 0:
                    self.junkBeforeVersion = allResponse[:allResponse.find(pm)].split('\n')
                tmp = allResponse[allResponse.find(pm) + len(pm):]
                if tmp.find(']') != -1:
                    printerNumber = tmp[:tmp.find(']')]
            vm = '+Version ['
            if allResponse.find(vm) != -1:
                tmp = allResponse[allResponse.find(vm) + len(vm):]
                if tmp.find(']') != -1:
                    version = tmp[:tmp.find(']')]

            if printerNumber:
                self.printerNumber = printerNumber
                self.debug("Printer number: " + printerNumber)
            if version:
                self.parseVersion(version)
            else:
                self.legacyFirmware(allResponse)

            self.debug("Response looks okay.")
            self.connected = True
            self.serialDevice = serialDevice
            self.serialSetTimeout(0)
            self.debug("Printer looks okay.")
            return True

        except serial.SerialException as e:
            self.lastError = str(e)
        except Exception as e:
            self.lastError = "Unknown Error: {}".format(e)
            return False

    def legacyFirmware(self, response):
        self.debug("legacy firmware response: " + response)
        oYear = response.find("+2014")
        if oYear == -1:
            oYear = response.find("+2015")
        if oYear != -1:
            sVer = oYear
            while sVer > 0:
                sVer = sVer - 1
                if not (response[sVer] == '.' or
                        response[sVer] >= '0' and response[sVer] <= '9'):
                    sVer = sVer + 1
                    break
            eVer = oYear
            while eVer < len(response) - 1:
                eVer = eVer + 1
                if not (response[eVer] == '.' or
                        response[eVer] >= '0' and response[eVer] <= '9'):
                    break
            self.parseVersion(response[sVer:eVer])

    def disconnect(self):
        if self.serialDevice:
            self.serialDevice.close()
        self.serialDevice = None
        self.connected = False
        self.version = None

    def getTimeSinceLastCommand(self):
        if self.lastCommandTime == None:
            return None
        return time.time() - self.lastCommandTime

    def command(self, command, timeout=None, expect=None, wait=False):
        self.lastCommandTime = time.time()
        if self.serialDevice and self.connected:
            self.serialWriteString(command + self.delimiter)
            if wait != False:
                if timeout == None:
                    timeout = 30
                if expect == None:
                    expect = command
            if timeout:
                return self.waitForResponse(timeout, expect)
            return True
        return None

    def move(self, x, y, wait=False):
        if x is not None:
            self.command('M X {}'.format(x), wait=wait)

        if y is not None:
            self.command('M Y {}'.format(y), wait=wait)

    def home(self, wait=False):
        if wait:
            self.command('home', timeout=30, expect='+Homed')
        else:
            self.command('home')

    def calibrate(self):
        self.command('c')

    def Print(self, filename, path=None, progressFunc=None):
        if progressFunc == None:
            self.command('p ' + filename)
            return

        self.printing = True

        lines = 100
        if path:
            file = open(path, "r")
            contents = file.read()
            file.close()
            lines = 0
            for line in contents.split('\n'):
                if len(line) > 3 and line[0] == 'M' and line[2] == 'X':
                    lines = lines + 1
            if lines == 0:
                self.debug("couldn't get number of lines in {}".format(path))
                self.printing = False
                return
            self.debug("{} has {} lines.".format(filename, lines))

        try:
            self.serialSetTimeout(2*60)
            self.command('p ' + filename)

            pos = 0
            Done = False
            while not Done:
                response = self.waitForResponse(timeout=2*60, expect='\n')
                if response == None:
                    break
                for line in response:
                    if line == ".":
                        pos = pos + 1
                        if not progressFunc(pos, lines):
                            Done = True
                            break
                    if line.find("Print complete") != -1:
                        Done = True
                        break
                    if line.find("Stopping") != -1:
                        Done = True
                        break
        finally:
            self.serialSetTimeout(0)
            self.printing = False


    def isHomed(self):
        response = self.command('lim', 1)
        for resp in response:
            if resp == "+Limits: X- Y- ":
                return True
        return False

    def fire(self, address, primitive):
        self.debug('[APC] Firing Command - {} - {}'.format(address, primitive))

        self.command('\x01{}{}\x00'.format(address, primitive))

    def pause(self):
        self.command('P')

    def resume(self):
        self.command('R')

    def start(self):
        self.command('p')

    def stop(self):
        self.command('S')

    def emergencyStop(self):
        self.disconnect()
        self.connect(self.port)

    monitorEnabled = True
    def monitor(self):
        if not self.monitorEnabled:
            return None

        try:
            if self.connected and self.serialDevice.timeout == 0:
                data = None
                n = self.serialDevice.inWaiting()
                if n > 0:
                    data = self.serialRead(n)

                if data:
                    return data
        except Exception as e:
            self.debug("monitor exception: {}".format(e))
        return None

    def waitForResponse(self, timeout=0.5, expect=None):
        if not self.connected:
            return None

        self.serialSetTimeout(timeout)
        response = ""
        try:
            while True:
                data = self.serialRead(1)
                n = self.serialDevice.inWaiting()
                if n > 0:
                    data = data + self.serialRead(n)
                else:
                    break
                if data:
                    response = response + data.decode('utf-8', 'ignore')

                if expect:
                    if response.find(expect) != -1:
                        break
        except:
            pass
        finally:
            self.serialSetTimeout(0)

        if response == "":
            return None

        response = response.split('\n')
        resp_list = []
        for resp in response:
            if resp.find('\r') != -1:
                resp = resp[:resp.find('\r')]
            resp_list.append(resp)
        return resp_list

    def missingFiles(self, files):
        response = self.command("ls", timeout=2)
        missing = []
        for filename in files:
            found = False
            for resp in response:
                if resp.lower() == ("+" + filename).lower():
                    found = True
                    break
            if not found:
                missing.append(filename)
        return missing

    def checkMd5(self, filename):
        file = open(filename, 'r')
        contents = file.read()
        file.close()
        m = hashlib.md5()
        m.update(contents)
        md5 = m.hexdigest()
        response = self.command("md5 {}".format(os.path.basename(filename)), timeout=10, expect='\n')
        for line in response:
            if line == md5:
                return True
        return False

    def checkDJB2(self, path):
        file = open(path, 'r')
        contents = file.read()
        file.close()

        if contents[0] == '#' and contents[1] == ' ' and contents[10] == '\n':
            djb2 = contents[2:10]
        else:
            hash = calcDJB2(contents)
            djb2 = "{:08x}".format(hash)

        filename = os.path.basename(path)
        self.debug("asking printer for {} with djb2 {}.".format(filename, djb2))

        response = self.command("djb2 {}".format(filename), timeout=30, expect='\n')
        for line in response:
            if len(line) == 8:
                self.debug("printer has " + line)
            if line == djb2:
                return True
        return False

    def send(self, path, progressFunc=None, printOnline=False):
        self.sendingFile = True
        file = open(path, 'r')
        contents = file.read()
        file.close()

        filename = os.path.basename(path)

        start = time.time()

        size = len(contents)
        compressed = self.compress(contents)
        if printOnline:
            cmd = "recv {} o {}"
        else:
            cmd = "recv {} {}"
        if compressed and (printOnline or len(compressed) * 3 < size):
            self.debug("compression rate {} to 1".format(float(size) / len(compressed)))
            size = len(compressed)
            contents = compressed
            if printOnline:
                cmd = "recv {} bo {}"
            else:
                cmd = "recv {} b {}"
        self.serialDevice.flushInput()
        self.serialDevice.flush()
        response = self.command(cmd.format(size, filename), timeout=10, expect='\n')
        if response == None:
            self.debug("no response to recv")
            self.sendingFile = False
            return
        gotReady = False
        for line in response:
            if line == "Ready":
                gotReady = True
        if not gotReady:
            self.debug("Didn't get Ready, got: ")
            self.debug(response)
            self.sendingFile = False
            return

        self.debug("sending {} bytes.".format(size))

        canceled = False
        paused = False

        try:
            hash = 5381
            fails = 0
            pos = 0
            while (pos < size):
                if paused:
                    pres = progressFunc(pos, size)
                    if pres == False:
                        self.serialWriteRaw('C')
                        self.debug("canceled!")
                        canceled = True
                        break
                    if pres == "Pause":
                        self.serialWriteRaw('P')
                        self.serialSetTimeout(10)
                        cmd = self.serialRead(1)
                        if cmd != 'p':
                            self.debug("printer didn't ping pause.")
                            self.serialSetTimeout(1)
                            rest = cmd + self.serialRead(79)
                            rest = rest.strip()
                            if len(rest) > 0:
                                self.debug("'" + rest + "'")
                            canceled = True
                            break
                        continue
                nleft = size - pos
                blocksize = nleft if nleft < 1024 else 1024
                block = contents[pos:pos+blocksize]
                encblock = ""
                oldhash = hash
                for c in block:
                    encblock = encblock + c
                    cval = ord(c)
                    if cval >= 128:
                        cval = -(256 - cval)
                    hash = hash * 33 + cval
                    hash = hash & 0xffffffff
                encblock = encblock + chr( hash        & 0x7f)
                encblock = encblock + chr((hash >>  7) & 0x7f)
                encblock = encblock + chr((hash >> 14) & 0x7f)
                encblock = encblock + chr((hash >> 21) & 0x7f)
                encblock = encblock + chr((hash >> 28) & 0x0f)
                self.serialWriteRaw(encblock)

                done = False
                cmd = None
                while not done and not canceled:
                    if cmd == None:
                        self.serialSetTimeout(1)
                        cmd = self.serialRead(1)
                        if cmd == "":
                            cmd = None
                            continue

                    if cmd == "B":
                        hash = oldhash
                        fails = fails + 1
                        if fails > 12:
                            self.debug("Too many failures.")
                            self.serialSetTimeout(0)
                            self.sendingFile = False
                            return
                        self.debug("block is bad at {}/{}".format(pos, size))
                        done = True
                        cmd = None
                    elif cmd == "G":
                        pos = pos + blocksize
                        if progressFunc:
                            pres = progressFunc(pos, size)
                            if pres == False:
                                self.serialWriteRaw('C')
                                self.debug("canceled!")
                                canceled = True
                            elif pres == "Pause":
                                self.debug("paused!")
                                paused = True
                        else:
                            self.debug("block is good at {}/{}".format(pos, size))
                        done = True
                        cmd = None
                    else:
                        self.serialSetTimeout(1)
                        rest = cmd + self.serialRead(79)
                        rest = rest.strip()
                        if len(rest) > 0:
                            self.debug("'" + rest + "'")
                        cmd = None
                        if len(rest) > 2 and rest[len(rest)-2:] == '\nG':
                            cmd = 'G'
                        if rest.find('Errorecv') != -1:
                            done = True
                            canceled = True

                if canceled:
                    break

            if canceled:
                return False

            self.serialSetTimeout(0)
            if progressFunc:
                progressFunc(size, size)
            else:
                self.debug("sent.")

            end = time.time()

            self.debug("Sent in {} seconds.".format(end - start))
        finally:
            self.sendingFile = False

        return True

    def compress(self, contents):
        compressed = []
        lastFiringLine = None
        lastFiring = None
        lastParts = []
        firings = []
        for line in contents.split('\n'):
            if len(line) == 0:
                continue
            if line[0] == '#':
                compressed.append(line)
                continue

            if line[0] == 'M':
                if len(firings) > 0:

                    if len(firings) != len(order):
                        self.debug("firing order changed!")
                        return None
                    firingLine = None
                    for i in range(len(firings)):
                        if firings[i][0] != order[i]:
                            self.debug("firing order changed!")
                            return None
                        if firingLine:
                            if firingLine == ".":
                                firingLine = "," + firings[i][1:]
                            else:
                                firingLine = firingLine + "," + firings[i][1:]
                        else:
                            firingLine = firings[i][1:]
                            if firingLine == None or firingLine == "":
                                firingLine = "."
                    if lastFiringLine and firingLine == lastFiringLine:
                        compressed.append('d')
                    else:
                        compressed.append(firingLine)
                    lastFiringLine = firingLine
                    if len(firingLine) > MAX_FIRING_LINE_LEN:
                        self.debug("firing line too long.")
                        return None
                    firings = []
                if line[2:3] == 'X':
                    compressed.append(line[2:3] + line[4:])
                else:
                    compressed.append(line[4:])
            elif line[0] == 'F':
                firing = line[2:]
                if lastFiring and firing[1:] == lastFiring[1:]:
                    firing = firing[0:1]
                else:
                    lastFiring = firing
                    part = None
                    if firing[1:] == "0000":
                        firing = firing[0:1] + 'z'
                    elif firing[1:3] == "00":
                        part = firing[3:5]
                        firing = firing[0:1] + 'z'
                    elif firing[3:5] == "00":
                        part = firing[1:3]
                        firing = firing[0:1]
                    if part:
                        if part in lastParts:
                            firing = firing + chr(ord('a') + lastParts.index(part))
                        else:
                            lastParts.append(part)
                            if len(lastParts) > 25:
                                lastParts.pop(0)
                            firing = firing + part
                firings.append(firing)
            else:
                self.debug("what's this? {}".format(line))
                return None

        return '\n'.join(compressed) + "\n"

    def volt(self):
        response = self.command("volt", expect='\n', timeout=1)
        if response:
            for line in response:
                if line.find(':') != -1 and line.find('volts.') != -1:
                    return float(line[line.find(': ') + 2:line.find(' volts')])
        return 0

    def getOptions(self):
        response = self.command("?eeprom", expect=']', timeout=1)
        if response == None:
            return None
        response = ''.join(response)
        if response.find('horizontal_offset:') == -1:
            return None
        if response.find('vertical_offset:') == -1:
            return None
        if response.find('print_overlap:') == -1:
            return None
        if response.find('CRC:') == -1:
            return None
        value1 = response[response.find('horizontal_offset:') + 19:]
        value1 = value1[:value1.find('vertical_offset:')]
        value2 = response[response.find('vertical_offset:') + 17:]
        value2 = value2[:value2.find('print_overlap:')]
        value3 = response[response.find('print_overlap:') + 15:]
        ePos = 0
        while value3[ePos] >= '0' and value3[ePos] <= '9':
            ePos = ePos + 1
        value3 = value3[:ePos]
        return {'horizontal_offset': int(value1),
                'vertical_offset': int(value2),
                'print_overlap': int(value3)}

    def updateOptions(self, options):
        horizontal_offset = options['horizontal_offset']
        vertical_offset = options['vertical_offset']
        print_overlap = options['print_overlap']
        self.command("!write po {} {} {}".format(horizontal_offset, vertical_offset, print_overlap))

    def getPosition(self):
        if not self.connected:
            return None
        if not self.monitorEnabled:
            return None
        if self.serialDevice.timeout != 0:
            return None
        if self.printing or self.sendingFile:
            return None
        response = self.command("pos", timeout=0.1)
        if response == None:
            return None
        response = ''.join(response)

        if response.find('+X:') == -1:
            return None
        response = response[response.find('+X: ') + 4:]
        if response.find(' mm') == -1:
            return None
        xmm = float(response[:response.find(' mm')])
        if response.find(', Y:') == -1:
            return None
        response = response[response.find(', Y: ') + 5:]
        if response.find(' mm') == -1:
            return None
        ymm = float(response[:response.find(' mm')])

        if response.find('+X:') == -1:
            return None
        response = response[response.find('+X: ') + 4:]
        if response.find(' steps') == -1:
            return None
        xsteps = int(response[:response.find(' steps')])
        if response.find(', Y:') == -1:
            return None
        response = response[response.find(', Y: ') + 5:]
        if response.find(' steps') == -1:
            return None
        ysteps = int(response[:response.find(' steps')])

        return (xmm, ymm, xsteps, ysteps)

    def turnLightsOn(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 8 255")
        self.lightsOn = True

    def turnLightsOff(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 8 0")
        self.lightsOn = False

    def turnLeftFanOn(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 7 255")
        self.leftFanOn = True

    def turnLeftFanOff(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 7 0")
        self.leftFanOn = False

    def turnRightFanOn(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 9 255")
        self.rightFanOn = True

    def turnRightFanOff(self):
        if self.printing or self.sendingFile:
            return
        self.command("pwm 9 0")
        self.rightFanOn = False

    def getPrinterNumber(self):
        response = self.command("pnum", expect=']', timeout=1)
        if response == None:
            return None
        allResponse = ''.join(response)
        pm = '+Printer Number ['
        if allResponse.find(pm) == -1:
            return None
        pnum = allResponse[allResponse.find(pm) + len(pm):]
        pnum = pnum[:pnum.find(']')]
        return pnum

    def setPrinterNumber(self, pnum):
        self.printerNumber = pnum
        self.command("pnum {}".format(pnum))

    def moveTo(self, x, y, withOk=False):
        if withOk:
            self.command("M {} {} k".format(int(x), int(y)))
        else:
            self.command("M {} {}".format(int(x), int(y)))

    def turnMotorsOn(self):
        self.command('+')

    def turnMotorsOff(self):
        self.command('-')
