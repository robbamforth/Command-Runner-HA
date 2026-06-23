"""Config flow for Command Runner integration."""

import asyncio
import logging
from typing import Any
from uuid import uuid4

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import (
    CONF_AUTO_SENSOR_REFRESH,
    CONF_DEVICE_ID,
    CONF_SENSOR_REFRESH_INTERVAL,
    DEFAULT_AUTO_SENSOR_REFRESH,
    DEFAULT_SENSOR_REFRESH_INTERVAL,
    device_headers,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

CONF_SHOW_NOTIFICATIONS = "show_notifications"


def _build_config_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build config schema with conditional refresh interval field."""
    auto_refresh = defaults.get(
        CONF_AUTO_SENSOR_REFRESH, DEFAULT_AUTO_SENSOR_REFRESH
    )

    schema: dict[Any, Any] = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "192.168.1.100")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, 8080)): int,
        vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
        vol.Required(CONF_AUTO_SENSOR_REFRESH, default=auto_refresh): bool,
    }

    if auto_refresh:
        schema[
            vol.Required(
                CONF_SENSOR_REFRESH_INTERVAL,
                default=defaults.get(
                    CONF_SENSOR_REFRESH_INTERVAL,
                    DEFAULT_SENSOR_REFRESH_INTERVAL,
                ),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=1))

    return vol.Schema(schema)


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
    device_id: str,
    *,
    approval_request: bool = False,
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    api_key = data.get(CONF_API_KEY, "")

    session = async_get_clientsession(hass)
    headers = device_headers(
        hass,
        api_key,
        device_id,
        approval_request=approval_request,
    )

    try:
        async with async_timeout.timeout(10):
            async with session.get(
                f"http://{host}:{port}/api/device/check-in",
                headers=headers,
            ) as response:
                result = await response.json()
                status = result.get("status")
                message = result.get("message", "Device authorization failed")
                if status == "invalid_api_key" or response.status == 401:
                    if "no api keys" in message.lower():
                        raise NoAPIKeys(message)
                    raise InvalidAuth(message)
                if status not in {
                    "approved",
                    "pending_approval",
                    "rejected",
                    "removed",
                }:
                    response.raise_for_status()
                    raise CannotConnect(message)

                return {
                    "title": f"Command Runner ({host})",
                    "device_status": status,
                }

    except aiohttp.ClientError as err:
        raise CannotConnect("Cannot connect to Command Runner") from err
    except asyncio.TimeoutError as err:
        raise CannotConnect("Connection timed out") from err
    except asyncio.CancelledError as err:
        raise CannotConnect("Connection timed out") from err
    except (InvalidAuth, NoAPIKeys, CannotConnect):
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect(f"Unknown error: {err}") from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Command Runner."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the flow with one stable candidate device ID."""
        super().__init__()
        self._device_id = str(uuid4())

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        defaults = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 8080,
            CONF_API_KEY: "",
            CONF_AUTO_SENSOR_REFRESH: DEFAULT_AUTO_SENSOR_REFRESH,
            CONF_SENSOR_REFRESH_INTERVAL: DEFAULT_SENSOR_REFRESH_INTERVAL,
        }

        if user_input is not None:
            defaults.update(user_input)
            try:
                info = await validate_input(
                    self.hass,
                    user_input,
                    self._device_id,
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoAPIKeys:
                errors["base"] = "no_api_keys"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if not user_input.get(
                    CONF_AUTO_SENSOR_REFRESH, DEFAULT_AUTO_SENSOR_REFRESH
                ):
                    user_input.pop(CONF_SENSOR_REFRESH_INTERVAL, None)
                elif CONF_SENSOR_REFRESH_INTERVAL not in user_input:
                    user_input[CONF_SENSOR_REFRESH_INTERVAL] = (
                        DEFAULT_SENSOR_REFRESH_INTERVAL
                    )

                user_input[CONF_DEVICE_ID] = self._device_id

                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_config_schema(defaults),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        defaults = {
            CONF_HOST: entry.data.get(CONF_HOST, ""),
            CONF_PORT: entry.data.get(CONF_PORT, 8080),
            CONF_API_KEY: entry.data.get(CONF_API_KEY, ""),
            CONF_AUTO_SENSOR_REFRESH: entry.data.get(
                CONF_AUTO_SENSOR_REFRESH, DEFAULT_AUTO_SENSOR_REFRESH
            ),
            CONF_SENSOR_REFRESH_INTERVAL: entry.data.get(
                CONF_SENSOR_REFRESH_INTERVAL,
                DEFAULT_SENSOR_REFRESH_INTERVAL,
            ),
        }

        if user_input is not None:
            defaults.update(user_input)
            try:
                device_id = entry.data.get(CONF_DEVICE_ID) or str(uuid4())
                await validate_input(
                    self.hass,
                    user_input,
                    device_id,
                    approval_request=True,
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoAPIKeys:
                errors["base"] = "no_api_keys"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if not user_input.get(
                    CONF_AUTO_SENSOR_REFRESH, DEFAULT_AUTO_SENSOR_REFRESH
                ):
                    user_input.pop(CONF_SENSOR_REFRESH_INTERVAL, None)
                elif CONF_SENSOR_REFRESH_INTERVAL not in user_input:
                    user_input[CONF_SENSOR_REFRESH_INTERVAL] = (
                        DEFAULT_SENSOR_REFRESH_INTERVAL
                    )

                user_input[CONF_DEVICE_ID] = device_id

                new_unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                if new_unique_id != entry.unique_id:
                    await self.async_set_unique_id(new_unique_id)
                    self._abort_if_unique_id_configured()

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                    title=f"Command Runner ({user_input[CONF_HOST]})",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_config_schema(defaults),
            errors=errors,
            description_placeholders={
                "host": entry.data.get(CONF_HOST, ""),
            },
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Command Runner."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SHOW_NOTIFICATIONS,
                    default=self.config_entry.options.get(
                        CONF_SHOW_NOTIFICATIONS, False
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""


class NoAPIKeys(Exception):
    """Error to indicate server has no API keys configured."""
