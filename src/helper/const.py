"""Constants for Pyhiveapi."""

from typing import Any

from .hivedataclasses import EntityConfig

SYNC_PACKAGE_NAME = "pyhiveapi"
SYNC_PACKAGE_DIR = "/pyhiveapi/"
ASYNC_PACKAGE_NAME = "apyhiveapi"
ASYNC_PACKAGE_DIR = "/apyhiveapi/"
SMS_REQUIRED = "SMS_MFA"


# HTTP return codes.
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_MOVED_PERMANENTLY = 301
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503

EXPECTED_DEVICE_DATA_LENGTH = 3


HIVETOHA: dict[str, Any] = {
    "Attribute": {True: "Online", False: "Offline"},
    "Boost": {None: "OFF", False: "OFF"},
    "Heating": {False: "OFF", "ENABLED": True, "DISABLED": False},
    "Hotwater": {"MANUAL": "ON", None: "OFF", False: "OFF"},
    "Hub": {
        "Status": {True: 1, False: 0},
        "Smoke": {True: 1, False: 0},
        "Dog": {True: 1, False: 0},
        "Glass": {True: 1, False: 0},
    },
    "Light": {"ON": True, "OFF": False},
    "Sensor": {
        "OPEN": True,
        "CLOSED": False,
        True: "Online",
        False: "Offline",
    },
    "Switch": {"ON": True, "OFF": False},
}

HIVE_TYPES = {
    "Hub": ["hub", "sense"],
    "Thermo": ["thermostatui", "trv"],
    "Heating": ["heating", "trvcontrol"],
    "Hotwater": ["hotwater"],
    "Light": ["warmwhitelight", "tuneablelight", "colourtuneablelight"],
    "Sensor": ["motionsensor", "contactsensor"],
    "Switch": ["activeplug"],
}

PRODUCTS = {
    "sense": [
        EntityConfig(
            entity_type="binary_sensor",
            ha_name="Glass Detection",
            hive_type="GLASS_BREAK",
        ),
        EntityConfig(
            entity_type="binary_sensor", ha_name="Smoke Detection", hive_type="SMOKE_CO"
        ),
        EntityConfig(
            entity_type="binary_sensor",
            ha_name="Dog Bark Detection",
            hive_type="DOG_BARK",
        ),
    ],
    "heating": [
        EntityConfig(entity_type="climate"),
        EntityConfig(
            entity_type="switch",
            ha_name=" Heat on Demand",
            hive_type="Heating_Heat_On_Demand",
            category="config",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Current Temperature",
            hive_type="Heating_Current_Temperature",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Target Temperature",
            hive_type="Heating_Target_Temperature",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" State",
            hive_type="Heating_State",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Heating_Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Boost",
            hive_type="Heating_Boost",
            category="diagnostic",
        ),
    ],
    "trvcontrol": [
        EntityConfig(entity_type="climate"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Current Temperature",
            hive_type="Heating_Current_Temperature",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Target Temperature",
            hive_type="Heating_Target_Temperature",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" State",
            hive_type="Heating_State",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Heating_Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Boost",
            hive_type="Heating_Boost",
            category="diagnostic",
        ),
    ],
    "hotwater": [
        EntityConfig(entity_type="water_heater"),
        EntityConfig(
            entity_type="sensor",
            ha_name="Hotwater State",
            hive_type="Hotwater_State",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name="Hotwater Mode",
            hive_type="Hotwater_Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name="Hotwater Boost",
            hive_type="Hotwater_Boost",
            category="diagnostic",
        ),
    ],
    "activeplug": [
        EntityConfig(entity_type="switch"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Power",
            hive_type="Power",
            category="diagnostic",
        ),
    ],
    "warmwhitelight": [
        EntityConfig(entity_type="light"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "tuneablelight": [
        EntityConfig(entity_type="light"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "colourtuneablelight": [
        EntityConfig(entity_type="light"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Mode",
            hive_type="Mode",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "motionsensor": [
        EntityConfig(entity_type="binary_sensor"),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Current Temperature",
            hive_type="Current_Temperature",
            category="diagnostic",
        ),
    ],
    "contactsensor": [
        EntityConfig(entity_type="binary_sensor"),
    ],
}

DEVICES = {
    "contactsensor": [
        EntityConfig(
            entity_type="sensor",
            ha_name=" Battery Level",
            hive_type="Battery",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "hub": [
        EntityConfig(
            entity_type="binary_sensor",
            ha_name="Hive Hub Status",
            hive_type="Connectivity",
            category="diagnostic",
        ),
    ],
    "motionsensor": [
        EntityConfig(
            entity_type="sensor",
            ha_name=" Battery Level",
            hive_type="Battery",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "sense": [
        EntityConfig(
            entity_type="binary_sensor",
            ha_name="Hive Hub Status",
            hive_type="Connectivity",
        ),
    ],
    "thermostatui": [
        EntityConfig(
            entity_type="sensor",
            ha_name=" Battery Level",
            hive_type="Battery",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
    "trv": [
        EntityConfig(
            entity_type="sensor",
            ha_name=" Battery Level",
            hive_type="Battery",
            category="diagnostic",
        ),
        EntityConfig(
            entity_type="sensor",
            ha_name=" Availability",
            hive_type="Availability",
            category="diagnostic",
        ),
    ],
}
