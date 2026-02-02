"""Button platform for Command Runner."""
import logging
from homeassistant.components.button import ButtonEntity
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
    """Set up Command Runner buttons."""
    coordinator: CommandRunnerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for command in coordinator.data:
        entities.append(CommandRunnerButton(coordinator, command, entry))

    async_add_entities(entities)


class CommandRunnerButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Command Runner button."""

    def __init__(self, coordinator: CommandRunnerCoordinator, command: dict, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._command = command
        self._attr_name = command["name"]
        self._attr_unique_id = f"{entry.entry_id}_{command['name']}"
        self._attr_icon = "mdi:play-circle"

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
            "command": self._command.get("command"),
            "allow_parameters": self._command.get("allowParameters", False),
            "voice_trigger": self._command.get("voice", ""),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info(f"Executing command: {self._command['name']}")
        result = await self.coordinator.execute_command(self._command["name"])

        if result.get("success"):
            _LOGGER.info(f"Command executed successfully: {self._command['name']}")
        else:
            _LOGGER.error(f"Command failed: {result.get('error', 'Unknown error')}")
