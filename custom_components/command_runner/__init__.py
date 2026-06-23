"""Command Runner Integration for Home Assistant."""

import logging
from datetime import timedelta
from urllib.parse import quote, urlencode
from uuid import uuid4

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    Platform,
    __version__ as HA_VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

CONF_AUTO_SENSOR_REFRESH = "automatic_sensor_refresh"
CONF_SENSOR_REFRESH_INTERVAL = "sensor_refresh_interval"
CONF_DEVICE_ID = "device_id"

INTEGRATION_VERSION = "1.2.0"

DEFAULT_AUTO_SENSOR_REFRESH = True
DEFAULT_SENSOR_REFRESH_INTERVAL = 120
SCAN_INTERVAL = timedelta(seconds=30)


def _header_safe(value: str) -> str:
    """Return an ASCII-safe HTTP header value understood by Command Runner."""
    return quote(str(value), safe="-._~")


def device_headers(
    hass: HomeAssistant,
    api_key: str,
    device_id: str,
    *,
    approval_request: bool = False,
) -> dict[str, str]:
    """Build API-key and stable trusted-device headers."""
    location_name = hass.config.location_name or "Home Assistant"
    headers = {
        "X-API-Key": api_key,
        "X-Device-ID": _header_safe(device_id),
        "X-Device-Name": _header_safe(f"Home Assistant - {location_name}"),
        "X-Device-Model": _header_safe("Home Assistant Integration"),
        "X-Device-System": _header_safe("Home Assistant"),
        "X-Device-System-Version": _header_safe(HA_VERSION),
        "X-App-Version": _header_safe(INTEGRATION_VERSION),
    }
    if approval_request:
        headers["X-Device-Approval-Request"] = "true"
    return headers


def command_id(command: dict) -> str | None:
    """Return the stable command UUID supplied by the Mac app."""
    value = command.get("id")
    if value is None:
        return None
    return str(value)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Command Runner from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    api_key = entry.data.get(CONF_API_KEY, "")
    device_id = entry.data[CONF_DEVICE_ID]
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
        device_id,
        auto_sensor_refresh,
        sensor_refresh_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add one persistent trusted-device ID to existing config entries."""
    if entry.version < 2:
        data = dict(entry.data)
        data.setdefault(CONF_DEVICE_ID, str(uuid4()))
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.info("Migrated Command Runner entry to trusted-device authentication")

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
        device_id: str,
        auto_sensor_refresh: bool,
        sensor_refresh_interval: int,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self.host = host
        self.port = port
        self.api_key = api_key
        self.device_id = device_id
        self.base_url = f"http://{host}:{port}"
        self.status_data: dict = {}
        self.last_execution: dict = {
            "command_id": None,
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
        """Get API-key and stable trusted-device headers."""
        return device_headers(self.hass, self.api_key, self.device_id)

    async def _async_check_in(self) -> None:
        """Confirm this Home Assistant instance is approved by the host."""
        session = async_get_clientsession(self.hass)
        async with async_timeout.timeout(10):
            async with session.get(
                f"{self.base_url}/api/device/check-in",
                headers=self._get_headers(),
            ) as response:
                try:
                    result = await response.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise UpdateFailed("Invalid device check-in response") from err

                status = result.get("status")
                message = result.get("message") or "Device authorization failed"
                if status == "approved":
                    return
                if status == "invalid_api_key" or response.status == 401:
                    raise UpdateFailed(f"Invalid API key: {message}")
                if status == "pending_approval":
                    raise UpdateFailed(
                        "Waiting for device approval in Command Runner on the Mac"
                    )
                if status == "rejected":
                    raise UpdateFailed(
                        "Home Assistant was rejected by the Command Runner host"
                    )
                if status == "removed":
                    raise UpdateFailed(
                        "Home Assistant was removed from the Command Runner host"
                    )

                raise UpdateFailed(message)

    async def _async_update_data(self):
        """Fetch command list and status data from API."""
        session = async_get_clientsession(self.hass)

        commands: list[dict] = []

        try:
            await self._async_check_in()
            async with async_timeout.timeout(10):
                async with session.get(
                    f"{self.base_url}/commands",
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 401:
                        raise UpdateFailed("Unauthorized: Invalid or missing API key")
                    if response.status == 403:
                        result = await response.json()
                        raise UpdateFailed(
                            result.get("message", "Device is not approved by the host")
                        )

                    response.raise_for_status()
                    data = await response.json()

                    if data.get("success"):
                        raw_commands = data.get("commands", [])
                        commands = [cmd for cmd in raw_commands if command_id(cmd)]
                        skipped = len(raw_commands) - len(commands)
                        if skipped:
                            _LOGGER.warning(
                                "Skipped %d Command Runner command(s) without stable id",
                                skipped,
                            )
                    else:
                        raise UpdateFailed("Failed to fetch commands")

        except UpdateFailed:
            raise
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

    async def execute_command(
        self,
        command_id_value: str,
        command_name: str | None = None,
        parameters: str | None = None,
    ):
        """Execute a command on the Mac by stable command UUID."""
        session = async_get_clientsession(self.hass)

        try:
            url = f"{self.base_url}/run/{quote(command_id_value, safe='')}"
            if parameters:
                url += f"?{urlencode({'params': parameters})}"

            async with async_timeout.timeout(30):
                async with session.get(
                    url,
                    headers=self._get_headers(),
                ) as response:
                    if response.status == 401:
                        _LOGGER.error("Unauthorized: Invalid or missing API key")
                        result = {"success": False, "error": "Unauthorized"}
                    elif response.status == 403:
                        result = await response.json()
                        result.setdefault(
                            "error", result.get("message", "Device is not approved")
                        )
                    else:
                        response.raise_for_status()
                        result = await response.json()

            self.last_execution = {
                "command_id": command_id_value,
                "command_name": command_name or result.get("command") or command_id_value,
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
                "command_id": command_id_value,
                "command_name": command_name or command_id_value,
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
                "command_id": command_id_value,
                "command_name": command_name or command_id_value,
                "status": "Failed",
                "output": None,
                "error": str(err),
                "exit_code": None,
            }
            self.async_set_updated_data(self.data)
            return {"success": False, "error": str(err)}

    async def async_get_sensor_output(self, command_id_value: str) -> dict:
        """Get output for a sensor-type command from the Mac by stable UUID."""
        session = async_get_clientsession(self.hass)

        try:
            url = f"{self.base_url}/sensor/{quote(command_id_value, safe='')}"

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
                        result = await response.json()
                        return {
                            "success": False,
                            "error": result.get(
                                "message", "Device is not approved by the host"
                            ),
                        }

                    response.raise_for_status()
                    result = await response.json()
                    return result

        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching sensor output: %s", err)
            return {"success": False, "error": str(err)}
        except Exception as err:
            _LOGGER.error("Unexpected error fetching sensor output: %s", err)
            return {"success": False, "error": str(err)}
