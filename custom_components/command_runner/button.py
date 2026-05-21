"""Button platform for Command Runner."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from . import CommandRunnerCoordinator, command_id

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

CONF_SHOW_NOTIFICATIONS = "show_notifications"

FIXED_BUTTON_UNIQUE_ID_SUFFIXES = {"refresh"}


def _button_unique_id(entry: ConfigEntry, command: dict) -> str:
    """Return the unique ID for a command button."""
    return f"{entry.entry_id}_command_{command_id(command)}"



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Command Runner buttons."""
    coordinator: CommandRunnerCoordinator = hass.data[DOMAIN][entry.entry_id]

    manager = CommandRunnerButtonManager(hass, entry, coordinator, async_add_entities)
    manager.async_setup()
    entry.async_on_unload(coordinator.async_add_listener(manager.async_reconcile))


class CommandRunnerButtonManager:
    """Keep command button entities in sync with the Mac command list."""

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
        self.entities: dict[str, CommandRunnerButton] = {}
        self._refresh_added = False

    def async_setup(self) -> None:
        """Create initial entities."""
        entities: list[ButtonEntity] = []

        if not self._refresh_added:
            entities.append(CommandRunnerRefreshButton(self.coordinator, self.entry))
            self._refresh_added = True

        entities.extend(self._new_command_entities())
        self._remove_orphaned_registry_entries()
        self.async_add_entities(entities)

    @callback
    def async_reconcile(self) -> None:
        """Add, update, and remove entities after each coordinator refresh."""
        entities = self._new_command_entities()
        self._remove_orphaned_registry_entries()

        if entities:
            _LOGGER.debug("Adding %d new Command Runner button entities", len(entities))
            self.async_add_entities(entities)

    def _command_buttons(self) -> list[dict]:
        return [
            command
            for command in (self.coordinator.data or [])
            if command.get("kind", "command") == "command"
        ]

    def _new_command_entities(self) -> list[CommandRunnerButton]:
        entities: list[CommandRunnerButton] = []

        for command in self._command_buttons():
            unique_id = _button_unique_id(self.entry, command)
            if unique_id in self.entities:
                self.entities[unique_id].update_command(command)
                continue

            entity = CommandRunnerButton(self.coordinator, command, self.entry)
            self.entities[unique_id] = entity
            entities.append(entity)

        return entities

    def _remove_orphaned_registry_entries(self) -> None:
        registry = er.async_get(self.hass)
        valid_unique_ids = {f"{self.entry.entry_id}_refresh"}
        valid_unique_ids.update(
            _button_unique_id(self.entry, command) for command in self._command_buttons()
        )

        for entity in er.async_entries_for_config_entry(registry, self.entry.entry_id):
            if entity.domain != "button" or entity.unique_id is None:
                continue
            if entity.unique_id in valid_unique_ids:
                continue

            # All button entities for this config entry are either the fixed
            # refresh button or command buttons, so anything else is stale.
            _LOGGER.info("Removing orphaned Command Runner button entity: %s", entity.entity_id)
            registry.async_remove(entity.entity_id)


class CommandRunnerRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to refresh Command Runner statistics."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Command Runner Refresh Statistics"
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_icon = "mdi:refresh"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    async def async_press(self) -> None:
        """Handle the button press to refresh statistics."""
        _LOGGER.info("Refreshing Command Runner statistics")
        await self.coordinator.async_request_refresh()

        all_ids = self.hass.states.async_entity_ids("sensor")
        command_runner_sensor_ids = [
            eid for eid in all_ids
            if eid.startswith("sensor.command_runner")
            and "_sensor" not in eid.lower()
        ]

        _LOGGER.debug(
            "Found %d command_runner sensor IDs: %s",
            len(command_runner_sensor_ids),
            command_runner_sensor_ids,
        )

        for entity_id in command_runner_sensor_ids:
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_id},
                    blocking=True,
                )
                _LOGGER.debug("Refreshed %s", entity_id)
            except Exception as err:  # noqa: BLE001 - HA service failures should be logged only.
                _LOGGER.error("Failed to refresh %s: %s", entity_id, err)

        show_notifications = self._entry.options.get(CONF_SHOW_NOTIFICATIONS, True)
        if show_notifications:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Command Runner",
                    "message": "Statistics and sensors refreshed successfully",
                    "notification_id": f"{DOMAIN}_refresh_{self.coordinator.host}",
                },
            )


class CommandRunnerButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Command Runner button."""

    def __init__(
        self,
        coordinator: CommandRunnerCoordinator,
        command: dict,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self.update_command(command, write_state=False)
        self._attr_unique_id = _button_unique_id(entry, command)
        self._attr_icon = "mdi:play-circle"

    def update_command(self, command: dict, write_state: bool = True) -> None:
        """Update command metadata when it changes on the Mac."""
        self._command = command
        self._attr_name = command["name"]
        if write_state and self.hass is not None:
            self.async_write_ha_state()

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "command_id": command_id(self._command),
            "command": self._command.get("command"),
            "allow_parameters": self._command.get("allowParameters", False),
            "voice_trigger": self._command.get("voice", ""),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        command_id_value = command_id(self._command)
        command_name = self._command["name"]
        if command_id_value is None:
            _LOGGER.error("Cannot execute command without stable id: %s", command_name)
            return

        _LOGGER.info("Executing command %s (%s)", command_name, command_id_value)

        result = await self.coordinator.execute_command(command_id_value, command_name)

        show_notifications = self._entry.options.get(CONF_SHOW_NOTIFICATIONS, True)

        if result.get("success"):
            _LOGGER.info("Command executed successfully: %s", command_name)

            if show_notifications:
                output = result.get("output", "").strip()
                exit_code = result.get("exitCode", 0)

                if output:
                    message = (
                        f"**Command:** {command_name}\n\n"
                        f"**Output:**\n```\\n{output}\\n```\n\n"
                        f"**Exit Code:** {exit_code}"
                    )
                else:
                    message = (
                        f"Command '{command_name}' executed successfully "
                        f"with exit code {exit_code}"
                    )

                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"✅ Command Success: {command_name}",
                        "message": message,
                        "notification_id": f"{DOMAIN}_{self.unique_id}",
                    },
                )

        else:
            error_message = result.get("error", "Unknown error")
            _LOGGER.error("Command failed: %s", error_message)

            if show_notifications:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"❌ Command Failed: {command_name}",
                        "message": (
                            f"**Error:** {error_message}\n\n"
                            f"**Command:** {command_name}"
                        ),
                        "notification_id": f"{DOMAIN}_{self.unique_id}",
                    },
                )

        await self.coordinator.async_request_refresh()
