"""Sensor platform for Command Runner."""

import logging
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CommandRunnerCoordinator

_LOGGER = logging.getLogger(__name__)
DOMAIN = "command_runner"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Command Runner sensors."""
    coordinator: CommandRunnerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CommandRunnerStatusSensor(coordinator, entry),
        CommandRunnerVersionSensor(coordinator, entry),
        CommandRunnerPortSensor(coordinator, entry),
        CommandRunnerUptimeSensor(coordinator, entry),
        CommandRunnerTotalRequestsSensor(coordinator, entry),
        CommandRunnerProcessingSensor(coordinator, entry),
        CommandRunnerAPIKeysSensor(coordinator, entry),
        CommandRunnerLastRequestSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CommandRunnerStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner status sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Status"
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_icon = "mdi:server"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("status", "unknown")
        return "unavailable"


class CommandRunnerVersionSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner version sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Version"
        self._attr_unique_id = f"{entry.entry_id}_version"
        self._attr_icon = "mdi:information"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("version", "unknown")
        return None


class CommandRunnerPortSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner port sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Port"
        self._attr_unique_id = f"{entry.entry_id}_port"
        self._attr_icon = "mdi:ethernet"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("port")
        return None


class CommandRunnerUptimeSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner uptime sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Uptime"
        self._attr_unique_id = f"{entry.entry_id}_uptime"
        self._attr_icon = "mdi:clock-outline"
        self._attr_native_unit_of_measurement = "s"
        self._attr_device_class = SensorDeviceClass.DURATION

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("uptime")
        return None

    @property
    def extra_state_attributes(self):
        status_data = self.coordinator.status_data
        if status_data and status_data.get("uptime"):
            uptime_seconds = status_data.get("uptime", 0)
            days = uptime_seconds // 86400
            hours = (uptime_seconds % 86400) // 3600
            minutes = (uptime_seconds % 3600) // 60
            return {"uptime_formatted": f"{days}d {hours}h {minutes}m"}
        return {}


class CommandRunnerTotalRequestsSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner total requests sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Total Requests"
        self._attr_unique_id = f"{entry.entry_id}_total_requests"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = "total_increasing"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("totalRequests", 0)
        return 0


class CommandRunnerProcessingSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner requests processing sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Requests Processing"
        self._attr_unique_id = f"{entry.entry_id}_requests_processing"
        self._attr_icon = "mdi:cog"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return status_data.get("requestsProcessing", 0)
        return 0


class CommandRunnerAPIKeysSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner API keys configured sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner API Keys Configured"
        self._attr_unique_id = f"{entry.entry_id}_api_keys_configured"
        self._attr_icon = "mdi:key"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            return "Yes" if status_data.get("apiKeysConfigured") else "No"
        return "Unknown"


class CommandRunnerLastRequestSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner last request time sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Command Runner Last Request"
        self._attr_unique_id = f"{entry.entry_id}_last_request"
        self._attr_icon = "mdi:clock-check"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def native_value(self):
        status_data = self.coordinator.status_data
        if status_data:
            last_request = status_data.get("lastRequestTime", 0)
            if last_request > 0:
                return datetime.fromtimestamp(last_request, tz=timezone.utc)
        return None
