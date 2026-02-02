"""Config flow for Command Runner integration."""
import logging
from typing import Any
import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.1.100"): str,
        vol.Required(CONF_PORT, default=8080): int,
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    api_key = data.get(CONF_API_KEY, "")

    session = async_get_clientsession(hass)
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with async_timeout.timeout(10):
            async with session.get(
                f"http://{host}:{port}/commands",
                headers=headers
            ) as response:
                if response.status == 401:
                    raise InvalidAuth("Invalid API key")

                if response.status == 403:
                    raise NoAPIKeys("Server has no API keys configured")

                response.raise_for_status()
                result = await response.json()

                if not result.get("success"):
                    raise CannotConnect("Server responded but returned error")

                return {"title": f"Command Runner ({host})"}

    except aiohttp.ClientError:
        raise CannotConnect("Cannot connect to Command Runner")
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect(f"Unknown error: {err}")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Command Runner."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoAPIKeys:
                errors["base"] = "no_api_keys"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""


class NoAPIKeys(Exception):
    """Error to indicate server has no API keys configured."""
