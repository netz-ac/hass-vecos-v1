from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    DEFAULT_LOCK_COUNT,
    DEFAULT_OPEN_DURATION,
    DEFAULT_PORT,
    DOMAIN,
    NUMBER_OF_LOCKS,
    OPEN_DURATION,
)

class VecosV1HubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(NUMBER_OF_LOCKS, default=DEFAULT_LOCK_COUNT): vol.All(int, vol.Range(min=1, max=16)),
                vol.Required(OPEN_DURATION, default=DEFAULT_OPEN_DURATION): vol.All(int, vol.Range(min=1, max=3600)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
