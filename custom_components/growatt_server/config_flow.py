"""Config flow for growatt server integration."""

from typing import Any

import growattServer
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    AUTH_API_TOKEN,
    AUTH_PASSWORD,
    CONF_API_KEY,
    CONF_AUTH_TYPE,
    CONF_PLANT_ID,
    DEFAULT_AUTH_TYPE,
    DEFAULT_URL,
    DOMAIN,
    LOGIN_INVALID_AUTH_CODE,
    SERVER_URLS,
)


class GrowattServerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow class."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise growatt server flow."""
        self.user_id = None
        self.data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the start of the config flow - show authentication method selection."""
        if user_input is not None:
            self.data[CONF_AUTH_TYPE] = user_input[CONF_AUTH_TYPE]
            if user_input[CONF_AUTH_TYPE] == AUTH_PASSWORD:
                return await self.async_step_password_auth()
            return await self.async_step_token_auth()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_AUTH_TYPE, default=DEFAULT_AUTH_TYPE): vol.In(
                    {
                        AUTH_PASSWORD: "Username/Password (Classic API)",
                        AUTH_API_TOKEN: "API Token (Official V1 API - MIN devices only)",
                    }
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_password_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle password authentication."""
        errors = {}
        
        if user_input is not None:
            try:
                # Initialise the library with the username & a random id each time it is started
                api = growattServer.GrowattApi(
                    add_random_user_id=True, agent_identifier=user_input[CONF_USERNAME]
                )
                api.server_url = user_input[CONF_URL]
                login_response = await self.hass.async_add_executor_job(
                    api.login, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )

                if not login_response.get("success"):
                    if login_response.get("msg") == LOGIN_INVALID_AUTH_CODE:
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                else:
                    self.user_id = login_response["user"]["id"]
                    self.data.update(user_input)
                    self.data["api"] = api
                    return await self.async_step_plant()

            except Exception:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_URL, default=DEFAULT_URL): vol.In(SERVER_URLS),
            }
        )

        return self.async_show_form(
            step_id="password_auth", data_schema=data_schema, errors=errors
        )

    async def async_step_token_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle token authentication."""
        errors = {}

        if user_input is not None:
            try:
                # Initialize V1 API with token
                api = growattServer.OpenApiV1(token=user_input[CONF_API_KEY])
                
                # Test the token by getting plant list
                plants_response = await self.hass.async_add_executor_job(api.plant_list)
                
                if not plants_response.get("plants"):
                    errors["base"] = "no_plants"
                else:
                    self.data.update(user_input)
                    self.data["api"] = api
                    self.data["plants_data"] = plants_response["plants"]
                    return await self.async_step_plant()

            except growattServer.GrowattV1ApiError as e:
                if "401" in str(e) or "unauthorized" in str(e).lower():
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="token_auth", data_schema=data_schema, errors=errors
        )

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a "plant" to Home Assistant."""
        # Get plant data based on auth type
        if self.data[CONF_AUTH_TYPE] == AUTH_PASSWORD:
            plant_info = await self.hass.async_add_executor_job(
                self.data["api"].plant_list, self.user_id
            )
            if not plant_info["data"]:
                return self.async_abort(reason="no_plants")
            plants_data = plant_info["data"]
            plants = {plant["plantId"]: plant["plantName"] for plant in plants_data}
        else:  # API token
            plants_data = self.data["plants_data"]
            plants = {plant["plant_id"]: plant["plant_name"] for plant in plants_data}

        if user_input is None and len(plants_data) > 1:
            data_schema = vol.Schema({vol.Required(CONF_PLANT_ID): vol.In(plants)})
            return self.async_show_form(step_id="plant", data_schema=data_schema)

        if user_input is None:
            # Single plant => mark it as selected
            if self.data[CONF_AUTH_TYPE] == AUTH_PASSWORD:
                user_input = {CONF_PLANT_ID: plants_data[0]["plantId"]}
            else:
                user_input = {CONF_PLANT_ID: plants_data[0]["plant_id"]}

        user_input[CONF_NAME] = plants[user_input[CONF_PLANT_ID]]
        await self.async_set_unique_id(user_input[CONF_PLANT_ID])
        self._abort_if_unique_id_configured()
        
        # Clean up temporary data and prepare final config
        final_data = {
            CONF_AUTH_TYPE: self.data[CONF_AUTH_TYPE],
            CONF_PLANT_ID: user_input[CONF_PLANT_ID],
            CONF_NAME: user_input[CONF_NAME],
        }
        
        if self.data[CONF_AUTH_TYPE] == AUTH_PASSWORD:
            final_data.update({
                CONF_USERNAME: self.data[CONF_USERNAME],
                CONF_PASSWORD: self.data[CONF_PASSWORD],
                CONF_URL: self.data[CONF_URL],
            })
        else:
            final_data[CONF_API_KEY] = self.data[CONF_API_KEY]

        return self.async_create_entry(title=final_data[CONF_NAME], data=final_data)
