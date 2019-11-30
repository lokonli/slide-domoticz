# Dashticz plugin for Innovation in Motion Slide
#
# Author: lokonli
#
"""
<plugin key="iim-slide" name="Slide by Innovation in Motion" author="lokonli" version="0.0.1" wikilink="https://github.com/lokonli/slide-domoticz" externallink="https://github.com/lokonli/slide-domoticz">
    <description>
        <h2>Slide by Innovation in Motion</h2><br/>
        Plugin for Slide by Innovation in Motion.

        It uses the Innovation in Motion open API. You must have registered your slide device.

        This is an alpha release.
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Feature one...</li>
            <li>Feature two...</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Curtain - Device to control the curtain position</li>
        </ul>
        <h3>Configuration</h3>
        First you have to register via the Slide app.
        
        <h3>External links</h3>
        <ul style="list-style-type:square">
            <li><a href="https://slide.store/">Slide store</a></li>
            <li><a href="https://slide.store/">Slide Open Cloud API</a></li>
        </ul>

    </description>
    <params>
           <param field="Mode1" label="Email address used for IIM registration" width="200px" required="true" default="name@gmail.com"/>
           <param field="Mode2" label="Password used for IIM registraion" width="200px" required="true" default="" password="true"/>
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
import Domoticz
import json
from datetime import datetime, timezone
import time
import _strptime

#import asyncio
#from goslideapi import GoSlideCloud
# Parameters = Parameters  # pylint:disable=invalid-name,used-before-assignment, undefined-variable
# Devices = Devices  # pylint:disable=invalid-name,used-before-assignment, undefined-variable


class iimSlide:
    enabled = False

    def __init__(self):
        #self.var = 123
        self.authorized = False
        self.messageQueue = {}
        self._expiretoken = None

        return

    def onStart(self):
        Domoticz.Log("onStart called")
        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        Domoticz.Log("Length {}".format(len(self.messageQueue)))

        self.myConn = Domoticz.Connection(
            Name="IIM Connection", Transport="TCP/IP", Protocol="HTTPS", Address="api.goslide.io", Port="443")
        self.myConn.Connect()
        self._tick = 0

    def onStop(self):
        Domoticz.Log("onStop called")

    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Debug("IIM connected successfully.")
            if (not self.authorized):
                self.authorize()
            elif len(self.messageQueue) > 0:
                Connection.Send(self.messageQueue)
                self.messageQueue = {}
                self.getOverview(1)
        else:
            Domoticz.Log("Failed to connect ("+str(Status)+") to: " +
                         Parameters["Address"]+" with error: "+Description)

    def onMessage(self, Connection, Data):
        Domoticz.Log("onMessage called")
        DumpHTTPResponseToLog(Data)

        strData = Data["Data"].decode("utf-8", "ignore")
        Status = int(Data["Status"])
        Response = json.loads(strData)
        if ("access_token" in Response):
            self.access_token = Response["access_token"]
            self.authorized = True
            if "expires_at" in Response:
                from datetime import datetime
                expires_at = Response["expires_at"]
                try:  # Python bug? strptime doesn't work the second time ...
                    self._expiretoken = datetime.strptime(
                        expires_at + ' +0000', "%Y-%m-%d %H:%M:%S %z"
                    )
                except TypeError:
                    self._expiretoken = datetime(*(time.strptime(
                        expires_at + ' +0000', "%Y-%m-%d %H:%M:%S %z"
                    )[0:7]))
                self.getOverview()
            else:
                self._expiretoken = None
                Domoticz.Error(
                    "Auth login JSON is missing the 'expires_at' field "
                )
        elif ("slides" in Response):
            updated = False
            for slide in Response["slides"]:
                Domoticz.Log('Slide id: {}'.format(slide["id"]))
                for device in Devices:
                    if (Devices[device].DeviceID == str(slide["id"])):
                        Domoticz.Log('Device exists')
                        # in case device is offline then no pos info
                        if "pos" in slide["device_info"]:
                            if self.setStatus(Devices[device], slide["device_info"]["pos"]):
                                updated = True
                        else:
                            Domoticz.Log('Device offline')
                        break
                else:
                    Domoticz.Log('Creating new device ')
                    Domoticz.Log(json.dumps(slide))
                    myDev = Domoticz.Device(Name=slide["device_name"], Unit=len(
                        Devices)+1, DeviceID=str(slide["id"]), Type=244, Subtype=73, Switchtype=13, Used=1)
                    myDev.Create()
                    # in case device is offline then no pos info
                    if "pos" in slide["device_info"]:
                        self.setStatus(myDev, slide["device_info"]["pos"])
            if updated:
                self.getOverview(1)
        else:
            Domoticz.Log("Unhandled response")
            Domoticz.Log(json.dumps(Response))

        if (Status == 200):
            Domoticz.Log("Good Response received from IIM")

        elif (Status == 302):
            Domoticz.Log("IIM returned a Page Moved Error.")
            sendData = {'Verb': 'POST',
                        'URL': Data["Headers"]["Location"],
                        'Headers': {'Content-Type': 'Content-Type: application/json',
                                    'Connection': 'keep-alive',
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
        else:
            Domoticz.Error("IIM returned a status: "+str(Status))

        if len(self.messageQueue) > 0:
            Connection.Send(self.messageQueue)
            self.messageQueu = {}

    def setStatus(self, device, pos):
        sValue = str(int(pos*100))
        nValue = 2
        if pos < 0.08:
            nValue = 0
            sValue = '0'
        if pos > 0.92:
            nValue = 1
            sValue = '100'
        if(device.sValue != sValue):
            device.Update(nValue=nValue, sValue=sValue)
            return True
        else:
            return False

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) +
                     ": Parameter '" + str(Command) + "', Level: " + str(Level))
        if (Command == 'Off'):
            self.setPosition(Devices[Unit].DeviceID, 0)
        if (Command == 'On'):
            self.setPosition(Devices[Unit].DeviceID, 1)
        if (Command == 'Set Level'):
            self.setPosition(Devices[Unit].DeviceID, Level/100)
        if (Command == 'Stop'):
            self.slideStop(Devices[Unit].DeviceID, Level/100)

    def setPosition(self, id, level):
        sendData = {'Verb': 'POST',
                    'URL': '/api/slide/{}/position'.format(id),
                    'Headers': {'Content-Type': 'application/json',
                                'Host': 'api.goslide.io',
                                'Connection': 'keep-alive',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Authorization': 'Bearer ' + self.access_token},
                    'Data': json.dumps({"pos": str(level)})
                    }
        if (not self.myConn.Connected()):
            self.messageQueue = sendData
            self.myConn.Connect()
        else:
            self.myConn.Send(sendData)
            self.getOverview(1)

    def getPosition(self, id, delay=0):
        sendData = {'Verb': 'GET',
                    'URL': '/api/slide/{}/info'.format(id),
                    'Headers': {'Content-Type': 'application/json',
                                'Host': 'api.goslide.io',
                                'Connection': 'keep-alive',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Authorization': 'Bearer ' + self.access_token}
                    }
        if (not self.myConn.Connected()):
            self.messageQueue = sendData
            self.myConn.Connect()
        else:
            self.myConn.Send(sendData, delay)

    def slideStop(self, id, level):
        sendData = {'Verb': 'POST',
                    'URL': '/api/slide/{}/stop'.format(id),
                    'Headers': {'Content-Type': 'application/json',
                                'Host': 'api.goslide.io',
                                'Connection': 'keep-alive',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Authorization': 'Bearer ' + self.access_token}
                    }
        if (not self.myConn.Connected()):
            self.messageQueue = sendData
            self.myConn.Connect()
        else:
            self.myConn.Send(sendData)
            self.getOverview(1)

    def authorize(self):
        postdata = {
            'email': Parameters["Mode1"],
            'password': Parameters['Mode2']
        }

        sendData = {'Verb': 'POST',
                    'URL': '/api/auth/login',
                    'Headers': {'Content-Type': 'application/json',
                                'Connection': 'keep-alive',
                                'Accept': 'application/json',
                                'Host': 'api.goslide.io',
                                'User-Agent': 'Domoticz/1.0'},
                    'Data': json.dumps(postdata)
                    }
        self.myConn.Send(sendData)

    def getOverview(self, delay=0):
        #                Domoticz.Log(self.access_token)
        sendData = {'Verb': 'GET',
                    'URL': '/api/slides/overview',
                    'Headers': {'Content-Type': 'application/json',
                                'Connection': 'keep-alive',
                                'Host': 'api.goslide.io',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Authorization': 'Bearer ' + self.access_token},
                    #                            'Data' : ''
                    }
        if (not self.myConn.Connected()):
            self.messageQueue = sendData
            self.myConn.Connect()
        else:
            self.myConn.Send(sendData, delay)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text +
                     "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called")
        self.connected = False

    def onHeartbeat(self):
        self._tick = self._tick + 1
        if self._tick > 4:
            self._tick = 0
            self.getOverview(1)

        if self._expiretoken is not None:
            from datetime import datetime, timezone
            diff = self._expiretoken - datetime.now()

            # Reauthenticate if token is less then 7 days valid
            if diff.days <= 7:
                Domoticz.Log(
                    "Authentication token will expire in {} days, renewing it".format(
                        int(diff.days))
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
    Domoticz.Log(Message)


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
