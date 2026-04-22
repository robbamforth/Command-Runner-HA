"""Command Runner Integration for Home Assistant."""

import logging
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

CONF_AUTO_SENSOR_REFRESH = "automatic_sensor_refresh"
CONF_SENSOR_REFRESH_INTERVAL = "sensor_refresh_interval"

DEFAULT_AUTO_SENSOR_REFRESH = True
DEFAULT_SENSOR_REFRESH_INTERVAL = 30
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Command Runner from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    api_key = entry.data.get(CONF_API_KEY, "")
    auto_sensor_refresh = entry.data.get(
        CONF_AUTO_SENSOR_REFRESH, DEFAULT_AUTO_SENSOR_REFRESH
    )
    sensor_refresh_interval = entry.data.get(
        CONF_SENSOR_REFRESH_INTERVAL, DEFAULT_SENSOR_REFRESH_INTERVAL
    )

    coordinator = CommandRunnerCoordinator(
        hass,
        host,
        port,
        api_key,
        auto_sensor_refresh,
        sensor_refresh_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class CommandRunnerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Command Runner data."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_key: str,
        auto_sensor_refresh: bool,
        sensor_refresh_interval: int,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self.host = host
        self.port = port
        self.api_key = api_key
        self.base_url = f"http://{host}:{port}"
        self.status_data: dict = {}
        self.last_execution: dict = {
            "command_name": None,
            "status": None,
            "output": None,
            "error": None,
            "exit_code": None,
        }

        update_interval = None
        if auto_sensor_refresh:
            update_interval = timedelta(seconds=max(1, int(sensor_refresh_interval)))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    def _get_headers(self) -> dict:
        """Get headers with API key if configured."""
        if self.api_key:
            return {"X-API-Key": self.api_key}
        return {}

    async def _async_update_data(self):
        """Fetch command list and status data from API."""
        session = async_get_clientsession(self.hass)

        commands: list[dict] = []

        try:
            async with async_timeout.timeout(10):
                async with session.get(
                    f"{self.base_url}/commands",
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 401:
                        raise UpdateFailed("Unauthorized: Invalid or missing API key")
                    if response.status == 403:
                        raise UpdateFailed(
                            "Forbidden: Server has no API keys configured"
                        )

                    response.raise_for_status()
                    data = await response.json()

                    if data.get("success"):
                        commands = data.get("commands", [])
                    else:
                        raise UpdateFailed("Failed to fetch commands")

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        try:
            async with async_timeout.timeout(10):
                async with session.get(
                    f"{self.base_url}/status",
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        if status_data.get("success"):
                            self.status_data = status_data
                        else:
                            _LOGGER.warning("Failed to fetch status data")
                    else:
                        _LOGGER.warning(
                            "Status endpoint returned %s", response.status
                        )

        except Exception as err:
            _LOGGER.warning("Error fetching status data: %s", err)

        return commands

    async def execute_command(self, command_name: str, parameters: str | None = None):
        """Execute a command on the Mac."""
        session = async_get_clientsession(self.hass)

        try:
            url = f"{self.base_url}/run/{command_name}"
            if parameters:
                url += f"?params={parameters}"

            async with async_timeout.timeout(30):
                async with session.get(
                    url,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 401:
                        _LOGGER.error("Unauthorized: Invalid or missing API key")
                        result = {"success": False, "error": "Unauthorized"}
                    elif response.status == 403:
                        _LOGGER.error(
                            "Forbidden: Server has no API keys configured"
                        )
                        result = {"success": False, "error": "Forbidden"}
                    else:
                        response.raise_for_status()
                        result = await response.json()

            self.last_execution = {
                "command_name": command_name,
                "status": "Success" if result.get("success") else "Failed",
                "output": result.get("output", "").strip()
                if result.get("success")
                else None,
                "error": result.get("error") if not result.get("success") else None,
                "exit_code": result.get("exitCode") if result.get("success") else None,
            }

            self.async_set_updated_data(self.data)

            return result

        except aiohttp.ClientError as err:
            _LOGGER.error("Error executing command: %s", err)
            self.last_execution = {
                "command_name": command_name,
                "status": "Failed",
                "output": None,
                "error": str(err),
                "exit_code": None,
            }
            self.async_set_updated_data(self.data)
            return {"success": False, "error": str(err)}

        except Exception as err:
            _LOGGER.error("Unexpected error executing command: %s", err)
            self.last_execution = {
                "command_name": command_name,
                "status": "Failed",
                "output": None,
                "error": str(err),
                "exit_code": None,
            }
            self.async_set_updated_data(self.data)
            return {"success": False, "error": str(err)}

    async def async_get_sensor_output(self, command_name: str) -> dict:
        """Get output for a sensor-type command from the Mac."""
        session = async_get_clientsession(self.hass)

        try:
            url = f"{self.base_url}/sensor/{command_name}"

            async with async_timeout.timeout(30):
                async with session.get(
                    url,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 401:
                        _LOGGER.error(
                            "Unauthorized: Invalid or missing API key for sensor"
                        )
                        return {"success": False, "error": "Unauthorized"}
                    if response.status == 403:
                        _LOGGER.error(
                            "Forbidden: Server has no API keys configured for sensor"
                        )
                        return {"success": False, "error": "Forbidden"}

                    response.raise_for_status()
                    result = await response.json()
                    return result

        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching sensor output: %s", err)
            return {"success": False, "error": str(err)}
        except Exception as err:
            _LOGGER.error("Unexpected error fetching sensor output: %s", err)
            return {"success": False, "error": str(err)}
