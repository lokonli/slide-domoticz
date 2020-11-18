# Dashticz plugin for Innovation in Motion Slide
#
# Author: lokonli
#
"""
<plugin key="iim-slide" name="Slide by Innovation in Motion" author="lokonli" version="0.1.10" wikilink="https://github.com/lokonli/slide-domoticz" externallink="https://slide.store/">
    <description>
        <h2>Slide by Innovation in Motion</h2><br/>
        Plugin for Slide by Innovation in Motion.<br/>
        <br/>
        It uses the Innovation in Motion open API.<br/>
        <br/>
        This is beta release 0.1.10. <br/>
        <br/>
        <h3>Configuration</h3>
        First you have to register via the Slide app.
        Fill in your email-address and password you used during registration below.<br/>
        <br/>
        Slides will be discovered and added to Domoticz automatically.<br/>
        <br/>        

    </description>
    <params>
           <param field="Mode1" label="Email address" width="200px" required="true" default="name@gmail.com"/>
           <param field="Mode2" label="Password" width="200px" required="true" default="" password="true"/>
            <param field="Mode6" label="Debug" width="150px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Python" value="18"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
# pylint:disable=undefined-variable
import Domoticz
import json
from datetime import datetime, timezone
import time
import _strptime


class iimSlide:
    enabled = False

    def __init__(self):
        #self.var = 123
        self.access_token = ''
        self.messageQueue = {}
        self._expiretoken = None
        # 0: Date including timezone info; 1: No timezone info. Workaround for strptime bug
        self._dateType = 0
        self._checkMovement = 0

        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        Domoticz.Debug("Length {}".format(len(self.messageQueue)))
        self._tick = 0
        self._dateType = 0
        self._checkMovement = 0
        self.access_token = ''

        self.myConn = Domoticz.Connection(
            Name="IIM Connection", Transport="TCP/IP", Protocol="HTTPS", Address="api.goslide.io", Port="443")
        self.myConn.Connect()

    def onStop(self):
        Domoticz.Debug("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")
        if (Status == 0):
            Domoticz.Debug("IIM connected successfully.")
            if (self.access_token == ''):
                self.authorize()
            elif len(self.messageQueue) > 0:
                self.slideRequest(self.messageQueue)
                self.messageQueue = {}
                # self.getOverview(1)
        else:
            Domoticz.Error("Failed to connect ("+str(Status)+") to: " +
                           Parameters["Address"]+" with error: "+Description)

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")
        DumpHTTPResponseToLog(Data)

        strData = Data["Data"].decode("utf-8", "ignore")
        Status = int(Data["Status"])
        try:
            Response = json.loads(strData)
        except:
            Domoticz.Debug("Invalid response data")
            return
        if ("access_token" in Response):
            self.access_token = Response["access_token"]
            if "expires_at" in Response:
                from datetime import datetime
                expires_at = Response["expires_at"]
                try:  # Python bug? strptime doesn't work the second time ...
                    self._expiretoken = datetime.strptime(
                        expires_at + ' +0000', "%Y-%m-%d %H:%M:%S %z"
                    )
                    self._dateType = 0
                except TypeError:
                    self._expiretoken = datetime(*(time.strptime(
                        expires_at + ' +0000', "%Y-%m-%d %H:%M:%S %z"
                    )[0:7]))
                    self._dateType = 1
                self.getOverview()
            else:
                self._expiretoken = None
                Domoticz.Error(
                    "Auth login JSON is missing the 'expires_at' field "
                )
        elif ("slides" in Response):
            updated = False
            for slide in Response["slides"]:
                Domoticz.Debug('Slide id: {}'.format(slide["id"]))
                for device in Devices:
                    if (Devices[device].DeviceID == str(slide["id"])):
                        Domoticz.Debug('Device exists')
                        # in case device is offline then no pos info
                        if "device_info" in slide:
                            if "pos" in slide["device_info"]:
                                if self.setStatus(Devices[device], slide["device_info"]["pos"]):
                                    updated = True
                            else:
                                Domoticz.Log('Device offline: ' +
                                             str(slide["id"]))
                            break
                        else:
                            Domoticz.Log('Device offline: ' + str(slide["id"]))
                        break
                else:
                    Domoticz.Log('New slide found')
                    Domoticz.Log(json.dumps(slide))
                    # During installation of Slide the name is null
                    if slide["device_name"] != None:
                        # Try to find the first free id
                        units = list(range(1, len(Devices)+2))
                        for device in Devices:
                            units.remove(device)
                        unit = min(units)
                        myDev = Domoticz.Device(Name=slide["device_name"], Unit=unit, DeviceID=str(
                            slide["id"]), Type=244, Subtype=73, Switchtype=13, Used=1)
                        myDev.Create()
                        # in case device is offline then no pos info
                        if "pos" in slide["device_info"]:
                            self.setStatus(myDev, slide["device_info"]["pos"])
                    else:
                        Domoticz.Debug(
                            'Unnamed slide. Waiting for slide name.')
            self._checkMovement = max(self._checkMovement-1, 0)
            if updated | (self._checkMovement > 0):
                self.getOverview(2)
        else:
            Domoticz.Debug("Unhandled response")
            Domoticz.Debug(json.dumps(Response))

        if (Status == 200):
            Domoticz.Debug("Good Response received from IIM")

        elif (Status == 302):
            Domoticz.Debug("IIM returned a Page Moved Error.")
            sendData = {'Verb': 'POST',
                        'URL': Data["Headers"]["Location"],
                        'Headers': {'Content-Type': 'Content-Type: application/json',
                                    #                                    'Connection': 'keep-alive',
                                    'Accept': 'Content-Type: application/json',
                                    'Host': Parameters["Address"],
                                    'User-Agent': 'Domoticz/1.0'},
                        'Data': ''
                        }
            Connection.Send(sendData)
        elif (Status == 400):
            Domoticz.Error("IIM returned a Bad Request Error.")
        elif (Status == 500):
            Domoticz.Error("IIM returned a Server Error.")
        elif (Status == 424):
            Domoticz.Debug('Status 424: At least one slide is offline')
        else:
            Domoticz.Debug("IIM returned a status: "+str(Status))

        if len(self.messageQueue) > 0:
            self.slideRequest(self.messageQueue)
            self.messageQueue = {}

    def setStatus(self, device, pos):
        Domoticz.Debug("setStatus called")
        sValue = str(int(pos*100))
        nValue = 2
        if pos < 0.13:
            nValue = 0
            sValue = '0'
        if pos > 0.87:
            nValue = 1
            sValue = '100'
        if(device.sValue != sValue):
            device.Update(nValue=nValue, sValue=sValue)
            return True
        else:
            return False

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) +
                       ": Parameter '" + str(Command) + "', Level: " + str(Level))
        if (Command == 'Off'):
            self.setPosition(Devices[Unit].DeviceID, 0)
        if (Command == 'On'):
            self.setPosition(Devices[Unit].DeviceID, 1)
        if (Command == 'Set Level'):
            self.setPosition(Devices[Unit].DeviceID, Level/100)
        if (Command == 'Stop'):
            self.slideStop(Devices[Unit].DeviceID, Level/100)

    def slideRequest(self, sendData, delay=0):
        Domoticz.Debug("slideRequest called")
        if self.myConn.Connected() and (self.access_token != ''):
            sendData['Headers'] = {'Content-Type': 'application/json',
                                   'Host': 'api.goslide.io',
                                   'Accept': 'application/json',
                                   'X-Requested-With': 'XMLHttpRequest',
                                   'Authorization': 'Bearer ' + self.access_token
                                   }
            self.myConn.Send(sendData, delay)
            # only start checking if we are not checking yet
            if (sendData['Verb'] == 'POST'):
                self._checkMovement = min(self._checkMovement+1, 2)
                if self._checkMovement == 1:
                    self.getOverview(2)
        else:
            self.messageQueue = sendData
            if (not self.myConn.Connecting() and not self.myConn.Connected()):
                self.myConn.Connect()

    def setPosition(self, id, level):
        Domoticz.Debug("setPosition called")
        sendData = {'Verb': 'POST',
                    'URL': '/api/slide/{}/position'.format(id),
                    'Data': json.dumps({"pos": str(level)})
                    }
        self.slideRequest(sendData)

    def slideStop(self, id, level):
        Domoticz.Debug("slideStop called")
        sendData = {'Verb': 'POST',
                    'URL': '/api/slide/{}/stop'.format(id)
                    }
        self.slideRequest(sendData)

    def authorize(self):
        Domoticz.Debug("authorize called")
        postdata = {
            'email': Parameters["Mode1"],
            'password': Parameters['Mode2']
        }

        sendData = {'Verb': 'POST',
                    'URL': '/api/auth/login',
                    'Headers': {'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'Host': 'api.goslide.io',
                                'User-Agent': 'Domoticz/1.0'},
                    'Data': json.dumps(postdata)
                    }
        self.myConn.Send(sendData)

    def getOverview(self, delay=0):
        Domoticz.Debug("getOverview called")
        sendData = {'Verb': 'GET',
                    'URL': '/api/slides/overview'
                    }
        self.slideRequest(sendData, delay)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text +
                       "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")
        if (not self.myConn.Connecting() and not self.myConn.Connected()):
            self.myConn.Connect()
        self._checkMovement = 0

    def onHeartbeat(self):
        self._tick = self._tick + 1
        if self._tick > 1:
            self._tick = 0
            self.getOverview()

        if self._expiretoken is not None:
            from datetime import datetime, timezone

            diffdays = 30  # In case of errors no token refresh
            try:
                if self._dateType == 0:
                    diff = self._expiretoken - datetime.now(timezone.utc)
                else:
                    diff = self._expiretoken - datetime.now()
                diffdays = diff.days
            except:
                Domoticz.Error('Error in computing date difference')
            # Reauthenticate if token is less then 7 days valid
            if diffdays <= 7:
                Domoticz.Debug(
                    "Authentication token will expire in {} days, renewing it".format(
                        int(diffdays))
                )
                self.authorize()


global _plugin
_plugin = iimSlide()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)


def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)


def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)


def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status,
                           Priority, Sound, ImageFile)


def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions


def LogMessage(Message):
    Domoticz.Debug(Message)


def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return


def DumpHTTPResponseToLog(httpResp, level=0):
    if (level == 0):
        Domoticz.Debug("HTTP Details ("+str(len(httpResp))+"):")
    indentStr = ""
    for x in range(level):
        indentStr += "----"
    if isinstance(httpResp, dict):
        for x in httpResp:
            if not isinstance(httpResp[x], dict) and not isinstance(httpResp[x], list):
                Domoticz.Debug(indentStr + ">'" + x +
                               "':'" + str(httpResp[x]) + "'")
            else:
                Domoticz.Debug(indentStr + ">'" + x + "':")
                DumpHTTPResponseToLog(httpResp[x], level+1)
    elif isinstance(httpResp, list):
        for x in httpResp:
            Domoticz.Debug(indentStr + "['" + x + "']")
    else:
        Domoticz.Debug(indentStr + ">'" + x + "':'" + str(httpResp[x]) + "'")
