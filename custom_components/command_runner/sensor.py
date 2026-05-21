"""Sensor platform for Command Runner."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CommandRunnerCoordinator, command_id

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

FIXED_SENSOR_SUFFIXES = {
    "status",
    "version",
    "port",
    "uptime",
    "total_requests",
    "requests_processing",
    "api_keys_configured",
    "last_request",
    "last_command_name",
    "last_command_status",
    "last_command_output",
}


def _command_sensor_unique_id(entry: ConfigEntry, command: dict) -> str:
    """Return the unique ID for a command-backed sensor."""
    return f"{entry.entry_id}_sensor_{command_id(command)}"



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Command Runner sensors."""
    coordinator: CommandRunnerCoordinator = hass.data[DOMAIN][entry.entry_id]

    manager = CommandRunnerSensorManager(hass, entry, coordinator, async_add_entities)
    manager.async_setup()
    entry.async_on_unload(coordinator.async_add_listener(manager.async_reconcile))


class CommandRunnerSensorManager:
    """Keep command sensor entities in sync with the Mac command list."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: CommandRunnerCoordinator,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.entities: dict[str, CommandRunnerCommandSensor] = {}
        self._fixed_added = False

    def async_setup(self) -> None:
        """Create initial entities."""
        entities: list[SensorEntity] = []

        if not self._fixed_added:
            entities.extend(
                [
                    CommandRunnerStatusSensor(self.coordinator, self.entry),
                    CommandRunnerVersionSensor(self.coordinator, self.entry),
                    CommandRunnerPortSensor(self.coordinator, self.entry),
                    CommandRunnerUptimeSensor(self.coordinator, self.entry),
                    CommandRunnerTotalRequestsSensor(self.coordinator, self.entry),
                    CommandRunnerProcessingSensor(self.coordinator, self.entry),
                    CommandRunnerAPIKeysSensor(self.coordinator, self.entry),
                    CommandRunnerLastRequestSensor(self.coordinator, self.entry),
                    CommandRunnerLastCommandNameSensor(self.coordinator, self.entry),
                    CommandRunnerLastCommandStatusSensor(self.coordinator, self.entry),
                    CommandRunnerLastCommandOutputSensor(self.coordinator, self.entry),
                ]
            )
            self._fixed_added = True

        entities.extend(self._new_command_entities())
        self._remove_orphaned_registry_entries()
        _LOGGER.debug(
            "Creating %d sensor entities (%d command sensors)",
            len(entities),
            sum(isinstance(e, CommandRunnerCommandSensor) for e in entities),
        )
        self.async_add_entities(entities, update_before_add=True)

    @callback
    def async_reconcile(self) -> None:
        """Add, update, and remove entities after each coordinator refresh."""
        entities = self._new_command_entities()
        self._remove_orphaned_registry_entries()

        if entities:
            _LOGGER.debug("Adding %d new Command Runner sensor entities", len(entities))
            self.async_add_entities(entities, update_before_add=True)

    def _command_sensors(self) -> list[dict]:
        return [
            command
            for command in (self.coordinator.data or [])
            if command.get("kind") == "sensor"
        ]

    def _new_command_entities(self) -> list["CommandRunnerCommandSensor"]:
        entities: list[CommandRunnerCommandSensor] = []

        for command in self._command_sensors():
            unique_id = _command_sensor_unique_id(self.entry, command)
            if unique_id in self.entities:
                self.entities[unique_id].update_command(command)
                continue

            entity = CommandRunnerCommandSensor(self.coordinator, command, self.entry)
            self.entities[unique_id] = entity
            entities.append(entity)

        return entities

    def _remove_orphaned_registry_entries(self) -> None:
        registry = er.async_get(self.hass)
        valid_unique_ids = {
            f"{self.entry.entry_id}_{suffix}" for suffix in FIXED_SENSOR_SUFFIXES
        }
        valid_unique_ids.update(
            _command_sensor_unique_id(self.entry, command)
            for command in self._command_sensors()
        )

        for entity in er.async_entries_for_config_entry(registry, self.entry.entry_id):
            if entity.domain != "sensor" or entity.unique_id is None:
                continue
            if entity.unique_id in valid_unique_ids:
                continue
            if entity.unique_id.startswith(f"{self.entry.entry_id}_sensor_") and entity.unique_id not in valid_unique_ids:
                _LOGGER.info("Removing orphaned Command Runner sensor entity: %s", entity.entity_id)
                registry.async_remove(entity.entity_id)


class CommandRunnerStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner status sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "Command Runner Status"
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
        self._attr_name = "Command Runner Version"
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
        self._attr_name = "Command Runner Port"
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
        self._attr_name = "Command Runner Uptime"
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
        self._attr_name = "Command Runner Total Requests"
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
        self._attr_name = "Command Runner Requests Processing"
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
        self._attr_name = "Command Runner API Keys Configured"
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
        self._attr_name = "Command Runner Last Request"
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


class CommandRunnerLastCommandNameSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner last command name sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "Command Runner Last Command Name"
        self._attr_unique_id = f"{entry.entry_id}_last_command_name"
        self._attr_icon = "mdi:text"

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
        return self.coordinator.last_execution.get("command_name") or "None"


class CommandRunnerLastCommandStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner last command status sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "Command Runner Last Command Status"
        self._attr_unique_id = f"{entry.entry_id}_last_command_status"
        self._attr_icon = "mdi:check-circle"

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
        status = self.coordinator.last_execution.get("status")
        return status if status else "Unknown"

    @property
    def icon(self):
        status = self.coordinator.last_execution.get("status")
        if status == "Success":
            return "mdi:check-circle"
        if status == "Failed":
            return "mdi:close-circle"
        return "mdi:help-circle"


class CommandRunnerLastCommandOutputSensor(CoordinatorEntity, SensorEntity):
    """Representation of Command Runner last command output sensor."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "Command Runner Last Command Output"
        self._attr_unique_id = f"{entry.entry_id}_last_command_output"
        self._attr_icon = "mdi:text-box"

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
        last_exec = self.coordinator.last_execution

        if last_exec.get("status") == "Success":
            output = last_exec.get("output")
            if output:
                return output[:255] if len(output) > 255 else output
            return "No output"

        if last_exec.get("status") == "Failed":
            error = last_exec.get("error")
            if error:
                return error[:255] if len(error) > 255 else error
            return "Unknown error"

        return "None"

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        last_exec = self.coordinator.last_execution
        attrs: dict = {}

        if last_exec.get("exit_code") is not None:
            attrs["exit_code"] = last_exec.get("exit_code")

        if last_exec.get("status") == "Success":
            full_output = last_exec.get("output")
            if full_output and len(full_output) > 255:
                attrs["full_output"] = full_output
        elif last_exec.get("status") == "Failed":
            full_error = last_exec.get("error")
            if full_error and len(full_error) > 255:
                attrs["full_error"] = full_error

        return attrs if attrs else None


class CommandRunnerCommandSensor(SensorEntity):
    """Standalone sensor for command output."""

    _attr_icon = "mdi:console"
    _attr_should_poll = True

    def __init__(
        self,
        coordinator: CommandRunnerCoordinator,
        command: dict,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the command sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self.update_command(command, write_state=False)
        self._attr_unique_id = _command_sensor_unique_id(entry, command)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.host)},
            "name": f"Command Runner ({self._coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    def update_command(self, command: dict, write_state: bool = True) -> None:
        """Update command metadata when it changes on the Mac."""
        self._command = command
        self._command_id: str | None = command_id(command)
        self._command_name: str = command["name"]
        self._attr_name = f"Command Runner {self._command_name}"
        if write_state and self.hass is not None:
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {
            "command_id": command_id(self._command),
            "command": self._command.get("name"),
            "raw_command": self._command.get("command"),
            "voice_trigger": self._command.get("voice", ""),
        }

    async def async_update(self) -> None:
        """Fetch latest value from Command Runner."""
        _LOGGER.debug("Polling sensor %s", self._command_name)
        if self._command_id is None:
            _LOGGER.error("Cannot poll sensor without stable id: %s", self._command_name)
            return

        result = await self._coordinator.async_get_sensor_output(self._command_id)

        _LOGGER.debug("Command sensor %s got result: %s", self._command_name, result)

        if not result.get("success"):
            _LOGGER.warning(
                "Failed to update sensor '%s': %s",
                self._command_name,
                result.get("error", "Unknown error"),
            )
            return

        output = (result.get("output") or "").strip()
        self._attr_native_value = output[:255] if len(output) > 255 else output
        _LOGGER.debug("Sensor %s updated to: %s", self._command_name, self._attr_native_value)
