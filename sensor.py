"""
Support for monitoring the Transmission BitTorrent client API.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.transmission/
"""
import logging
from datetime import timedelta

import voluptuous as vol
import requests
import json

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_HOST, CONF_TOKEN, CONF_NAME, CONF_PORT,
    CONF_MONITORED_VARIABLES, STATE_IDLE)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)
_THROTTLED_REFRESH = None

DEFAULT_NAME = 'Aria2c'
DEFAULT_PORT = 6800

SENSOR_TYPES = {
    'active': ['Active', Tasks],
    'download_speed': ['Down Speed', 'MB/s'],
    'upload_speed': ['Up Speed', 'MB/s'],
    'unfinished_tasks': ['Unfinished Tasks', Tasks]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_MONITORED_VARIABLES, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TOKEN): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
})


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Aria2c sensors."""

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    token = config.get(CONF_TOKEN)
   

    try:
        aria2c_api = Aria2cHomeassistant(
            host, port=port, token=token)
        aria2c_api.getVer()
    except ConnectionError as error:
        _LOGGER.error(
            "Connection to Aria2c API failed on %s:%s with message %s",
            host, port, error.original
        )
        return False

    # pylint: disable=global-statement
    global _THROTTLED_REFRESH
    _THROTTLED_REFRESH = Throttle(timedelta(seconds=1))(
        aria2c_api.getVer)

    dev = []
    for variable in config[CONF_MONITORED_VARIABLES]:
        dev.append(Aria2cSensor(variable, aria2c_api, name))

    add_devices(dev)


class Aria2cSensor(Entity):
    """Representation of a Aria2c sensor."""

    def __init__(self, sensor_type, aria2c_client, client_name):
        """Initialize the sensor."""
        self._name = SENSOR_TYPES[sensor_type][0]
        self.aria2c_client = aria2c_client
        self.type = sensor_type
        self.client_name = client_name
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    # pylint: disable=no-self-use
    def refresh_aria2c_data(self):
        """Call the throttled Aria2c refresh method."""

        if _THROTTLED_REFRESH is not None:
            try:
                _THROTTLED_REFRESH()
            except ConnectionError:
                _LOGGER.error("Connection to Aria2c API failed")

    def update(self):
        """Get the latest data from Aria2c and updates the state."""
        self.refresh_aria2c_data()
        
        if self.aria2c_client:
            if self.type == 'download_speed':
                mb_spd = float(self.aria2c_client.getDownloadSpeed())
                mb_spd = mb_spd / 1024 / 1024
                self._state = round(mb_spd, 2 if mb_spd < 0.1 else 1)
            elif self.type == 'upload_speed':
                mb_spd = float(self.aria2c_client.getUpSpeed())
                mb_spd = mb_spd / 1024 / 1024
                self._state = round(mb_spd, 2 if mb_spd < 0.1 else 1)
            elif self.type == 'active':
                self._state = int(self.aria2c_client.getActive())
            elif self.type == 'unfinished_tasks':
                self._state = int(self.aria2c_client.getUnfinishedTasks())

class Aria2cHomeassistant:
    def __init__(self, host, port, token=None):
        self.host = host
        self.port = port
        self.token = token
        self.serverUrl = "http://{host}:{port}/jsonrpc".format(**locals())
        self.IDPREFIX = "pyaria2c"
        self.GET_VER = 'aria2.getVersion'
        self.GET_STATUS = 'aria2.getGlobalStat'

    def _genPayload(self, method, uris=None, options=None, cid=None):
        cid = self.IDPREFIX + cid if cid else self.IDPREFIX
        p = {
            'jsonrpc': '2.0', 
            'id': cid,
            'method': method,
            'params': ["token:" + self.token]
            }
        if uris:
            p['params'].append(uris)
        if options:
            p['params'].append(options)
        return p

    @staticmethod
    def _defaultErrorHandler(code, message):
        print("ERROR: {}, {}".format(code, message))
        return None
    
    def _post(self, action, params, onSuc, onFail=None):
        if onFail is None:
            onFail = self._defaultErrorHandler
        payloads = self._genPayload(action, *params)
        resp = requests.post(self.serverUrl, data=json.dumps(payloads))
        result = resp.json()
        if "error" in result:
            return onFail(result["error"]["code"], result["error"]["message"])
        else:
            return onSuc(resp)

    def getVer(self):
        def success(response):
            return response.json()['result']['version']
        return self._post(self.GET_VER, [], success)
    def getDownloadSpeed(self):
        def success(response):
            return response.json()['result']['downloadSpeed']
        return self._post(self.GET_STATUS, [], success)
    def getUpSpeed(self):
        def success(response):
            return response.json()['result']['uploadSpeed']
        return self._post(self.GET_STATUS, [], success)
    def getActive(self):
        def success(response):
            return response.json()['result']['numActive']
        return self._post(self.GET_STATUS, [], success)
    def getUnfinishedTasks(self):
        def success(response):
            return int(response.json()['result']['numActive']) + int(response.json()['result']['numWaiting'])
        return self._post(self.GET_STATUS, [], success)

