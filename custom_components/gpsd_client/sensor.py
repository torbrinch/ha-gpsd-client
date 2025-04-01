"""Support for GPSD."""
from __future__ import annotations, unicode_literals

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from gpsdclient import GPSDClient
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_MODE,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from slugify import slugify

_LOGGER = logging.getLogger(__name__)

ATTR_CLIMB = "climb"
ATTR_ELEVATION = "elevation"
ATTR_UTC_TIME = "utc_time"
ATTR_SPEED = "speed"

DEFAULT_HOST = "localhost"
DEFAULT_NAME = "GPSD Client"
DEFAULT_PORT = 2947

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the GPSD Client platform."""
    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    unique_id = config.get(CONF_UNIQUE_ID)

    try:
        gpsd_client = GPSDClient(host=host, port=port)
        result = gpsd_client.json_stream()
        for gps_data in gpsd_client.dict_stream(convert_datetime=True):
            if gps_data["class"] == "DEVICES":
                path = gps_data["devices"][0].get("path")
                driver = gps_data["devices"][0].get("driver")
                subtype = gps_data["devices"][0].get("subtype")
                if not unique_id:
                    unique_id = slugify(f"{path}_{driver}_{subtype}")
                break

        _LOGGER.info("GPSD Client initialized for host %s:%s", host, port)

    except (ConnectionError, EnvironmentError) as e:
        _LOGGER.warning("Could not connect to GPSD at %s:%s: %s", host, port, e)
        return False

    async_add_entities([GpsdClient(hass, name, host, port, unique_id)])


class GpsdClient(SensorEntity):
    """Representation of a GPS receiver available via GPSD."""

    def __init__(self, hass, name, host, port, unique_id):
        """Initialize the GPSD Client sensor."""
        self.hass = hass
        self._name = name
        self._host = host
        self._port = port
        self._uid = unique_id
        self.lat = None
        self.lon = None
        self.alt = None
        self.time = None
        self.speed = None
        self.climb = None
        self.mode = 0

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def native_value(self) -> int:
        """Return the state of the sensor (mode as a numeric value)."""
        return self.mode

    @property
    def state_class(self) -> str:
        """This sensor returns instant measurements."""
        return "measurement"

    @property
    def icon(self) -> str:
        """Icon for the GPSD Client."""
        return "mdi:map-marker-check-outline"

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return self._uid

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes returned by GPSD."""
        return {
            ATTR_LATITUDE: self.lat,
            ATTR_LONGITUDE: self.lon,
            ATTR_ELEVATION: self.alt,
            ATTR_UTC_TIME: self.time,
            ATTR_SPEED: self.speed,
            ATTR_CLIMB: self.climb,
            ATTR_MODE: self.mode_str(),
        }

    async def async_update(self) -> None:
        """Grab the latest GPSD data."""

        def get_tpv():
            try:
                client = GPSDClient(host=self._host, port=self._port)
                for gps_data in client.dict_stream(convert_datetime=True):
                    if gps_data["class"] == "TPV":
                        return gps_data
            except Exception as e:
                _LOGGER.warning("Failed to fetch GPSD data: %s", e)
            return {}

        _LOGGER.debug("Calling async_update() for GPSD sensor...")
        gps_data = await self.hass.async_add_executor_job(get_tpv)

        if gps_data:
            _LOGGER.debug("Received GPSD data: %s", gps_data)
            self.lat = gps_data.get("lat")
            self.lon = gps_data.get("lon")
            self.alt = gps_data.get("alt")
            self.time = gps_data.get("time")
            self.speed = gps_data.get("speed")
            self.climb = gps_data.get("climb")
            self.mode = gps_data.get("mode", 0)

    def mode_str(self) -> str:
        """Return the string for the current GPS mode."""
        if self.mode == 3:
            return "3D Fix"
        if self.mode == 2:
            return "2D Fix"
        if self.mode == 1:
            return "No Fix"
        return "Unknown"
