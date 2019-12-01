# slide-domoticz
Domoticz plugin for Slide by Innovation in Motion

This is an alpha release.
It's tested for a single slide only, but might work for multiple slides as well.

# Installation

Create a folder name slide-domoticz in the domoticz/plugins folder:

    cd <Domoticz>/plugins
    mkdir slide-domoticz

Copy plugin.py to this folder

or, in domoticz/plugins:

    git clone https://github.com/lokonli/slide-domoticz

Then restart Domoticz.

    sudo systemctl restart domoticz.service

Add the Slide hardware to Domoticz. Slide can be found in Domoticz under Domoticz->Hardware

In the configuration page fill in your email address and password as used for registration in the Slide app.

Slide devices will be created automatically.

# Links
https://slide.store/
https://github.com/ualex73/goslide-api/blob/master/goslideapi/goslideapi.py
https://documenter.getpostman.com/view/6223391/S1Lu2pSf?version=latest
https://www.domoticz.com/wiki/Developing_a_Python_plugin

# Documentation
See the Wiki:
https://github.com/lokonli/slide-domoticz/wiki
