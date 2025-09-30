"""Coordinator module for managing Growatt data fetching."""

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from . import growattServer
from .growattServer import DeviceType

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_URL, DOMAIN
from .models import GrowattRuntimeData

if TYPE_CHECKING:
    from .sensor.sensor_entity_description import GrowattSensorEntityDescription

type GrowattConfigEntry = ConfigEntry[GrowattRuntimeData]

SCAN_INTERVAL = datetime.timedelta(minutes=5)

_LOGGER = logging.getLogger(__name__)

class GrowattCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage Growatt data fetching."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GrowattConfigEntry,
        device_id: str,
        device_type: str,
        plant_id: str,
    ) -> None:
        """Initialize the coordinator."""
        self.api_version = (
            "v1" if config_entry.data.get("auth_type") == "api_token" else "classic"
        )
        self.device_id = device_id
        self.device_type = device_type
        self.plant_id = plant_id
        self.previous_values: dict[str, Any] = {}

        if self.api_version == "v1":
            self.username = None
            self.password = None
            self.url = config_entry.data.get(CONF_URL, DEFAULT_URL)
            self.token = config_entry.data["token"]
            self.api = growattServer.OpenApiV1(token=self.token)
        elif self.api_version == "classic":
            self.username = config_entry.data.get(CONF_USERNAME)
            self.password = config_entry.data[CONF_PASSWORD]
            self.url = config_entry.data.get(CONF_URL, DEFAULT_URL)
            self.api = growattServer.GrowattApi(
                add_random_user_id=True, agent_identifier=self.username
            )
            self.api.server_url = self.url
        else:
            raise ValueError(f"Unknown API version: {self.api_version}")

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({device_id})",
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )

    def _calculate_epv_today(self, data: dict) -> dict:
        """Calculate total solar generation today from individual PV inputs.

        Args:
            data: Device data dictionary

        Returns:
            Updated data dictionary with epvToday calculated if needed
        """
        if "epvToday" not in data and any(
            key in data for key in ("epv1Today", "epv2Today", "epv3Today", "epv4Today")
        ):
            total_pv_today = 0.0
            for i in range(1, 5):
                pv_key = f"epv{i}Today"
                if pv_key in data and data[pv_key] not in (None, ""):
                    try:
                        total_pv_today += float(data[pv_key])
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not convert %s to float: %s", pv_key, data[pv_key])

            data["epvToday"] = total_pv_today
            _LOGGER.debug(
                "Calculated epvToday = %s from sum of individual PV inputs for device %s",
                total_pv_today,
                self.device_id,
            )

        return data

    def _sync_update_data(self) -> dict[str, Any]:
        """Update data via library synchronously."""
        _LOGGER.debug("Updating data for %s (%s)", self.device_id, self.device_type)

        # login only required for classic API
        if self.api_version == "classic":
            self.api.login(self.username, self.password)

        if self.device_type == "total":
            if self.api_version == "v1":
                # # Plant info
                # plants = self.api.plant_list()
                # _LOGGER.debug("Plants: Found %s plants", plants['count'])
                # plant_id = plants['plants'][0]['plant_id']
                # _LOGGER.debug("Plant: id %s plants", plant_id)
                # The V1 Plant APIs do not provide the same information as the classic plant_info() API
                # More specifically:
                # 1. There is no monetary information to be found, so today and lifetime money is not available
                # 2. There is no nominal power, this is provided by inverter min_energy()
                # This means, for the total coordinator we can only fetch and map the following:
                # todayEnergy -> today_energy
                # totalEnergy -> total_energy
                # invTodayPpv -> current_power
                total_info = self.api.plant_energy_overview(self.plant_id)
                total_info["todayEnergy"] = total_info["today_energy"]
                total_info["totalEnergy"] = total_info["total_energy"]
                total_info["invTodayPpv"] = total_info["current_power"]
            else:
                # Classic API: use plant_info as before
                total_info = self.api.plant_info(self.device_id)
                del total_info["deviceList"]
                plant_money_text, currency = total_info["plantMoneyText"].split("/")
                total_info["plantMoneyText"] = plant_money_text
                total_info["currency"] = currency
            _LOGGER.debug("Total info for plant %s: %r", self.plant_id, total_info)
            self.data = total_info
        elif self.device_type == "inverter":
            self.data = self.api.inverter_detail(self.device_id)
        elif self.device_type == "min":
            # Open API V1: min device
            try:
                min_details = self.api.min_detail(self.device_id)
                min_settings = self.api.min_settings(self.device_id)
                min_energy = self.api.min_energy(self.device_id)
                min_info = {**min_details, **min_settings, **min_energy}

                # Calculate epvToday if not present
                min_info = self._calculate_epv_today(min_info)

                self.data = min_info
                _LOGGER.debug("min_info for device %s: %r", self.device_id, min_info)
            except growattServer.GrowattV1ApiError as err:
                _LOGGER.error(
                    "Error fetching min device data for %s: %s", self.device_id, err
                )
                raise UpdateFailed(f"Error fetching min device data: {err}") from err
        elif self.device_type == "tlx":
            tlx_info = self.api.tlx_detail(self.device_id)
            self.data = tlx_info["data"]

            # Calculate epvToday if not present
            self.data = self._calculate_epv_today(self.data)

            _LOGGER.debug("tlx_info for device %s: %r", self.device_id, tlx_info)
        elif self.device_type == "storage":
            storage_info_detail = self.api.storage_params(self.device_id)
            storage_energy_overview = self.api.storage_energy_overview(
                self.plant_id, self.device_id
            )
            self.data = {
                **storage_info_detail["storageDetailBean"],
                **storage_energy_overview,
            }
        elif self.device_type == "mix":
            if self.api_version == "v1":
                # Open API V1: min device
                try:
                    mix_details = self.api.device_details(self.device_id , DeviceType.MIX_SPH)
                    mix_energy = self.api.device_energy(self.device_id, DeviceType.MIX_SPH)

                    date_str = mix_energy.get("time")
                    date_format = '%Y-%m-%d %H:%M:%S'
                    naive_dt = datetime.datetime.strptime(date_str, date_format)
                    tz = dt_util.get_default_time_zone()
                    aware_dt = naive_dt.replace(tzinfo=tz)
                    mix_details["lastdataupdate"] = aware_dt
                    _LOGGER.error(
                        "MIX DETAILS for %s -> %s", mix_details, last_updated_time
                    )

                    mix_info = {**mix_details, **mix_energy}
                    self.data = mix_info
                    _LOGGER.debug("mix_info for device %s: %r", self.device_id, mix_info)
                except growattServer.GrowattV1ApiError as err:
                    _LOGGER.error(
                        "Error fetching mix device data for %s: %s", self.device_id, err
                    )
                    raise UpdateFailed(f"Error fetching {self.device_type} device data: {err}") from err
            else:
                mix_info = self.api.mix_info(self.device_id)
                mix_totals = self.api.mix_totals(self.device_id, self.plant_id)
                mix_system_status = self.api.mix_system_status(
                    self.device_id, self.plant_id
                )
                mix_detail = self.api.mix_detail(self.device_id, self.plant_id)

                # Get the chart data and work out the time of the last entry
                mix_chart_entries = mix_detail["chartData"]
                sorted_keys = sorted(mix_chart_entries)

                # Create datetime from the latest entry
                date_now = dt_util.now().date()
                last_updated_time = dt_util.parse_time(str(sorted_keys[-1]))
                mix_detail["lastdataupdate"] = datetime.datetime.combine(
                    date_now,
                    last_updated_time,  # type: ignore[arg-type]
                    dt_util.get_default_time_zone(),
                )

                # Dashboard data for mix system
                dashboard_data = self.api.dashboard_data(self.plant_id)
                dashboard_values_for_mix = {
                    "etouser_combined": float(dashboard_data["etouser"].replace("kWh", ""))
                }
                self.data = {
                    **mix_info,
                    **mix_totals,
                    **mix_system_status,
                    **mix_detail,
                    **dashboard_values_for_mix,
                }
            _LOGGER.debug(
                "Finished updating data for %s (%s)",
                self.device_id,
                self.device_type,
            )


        return self.data

    async def _async_update_data(self) -> dict[str, Any]:
        """Asynchronously update data via library."""
        try:
            return await self.hass.async_add_executor_job(self._sync_update_data)
        except json.decoder.JSONDecodeError as err:
            _LOGGER.error("Unable to fetch data from Growatt server: %s", err)
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def get_currency(self):
        """Get the currency."""
        return self.data.get("currency")

    def _get_matching_api_key(
        self, variable: str | list[str] | tuple[str], key_list: dict[str, Any]
    ) -> str | None:
        """Get the matching api_key from the data."""
        if isinstance(variable, str):
            api_value = key_list.get(variable)
            return variable
        elif isinstance(variable, (list, tuple)):
            # Try each key in the array until we find a match
            for key in variable:
                value = key_list.get(key)
                if value is not None:
                    api_value = value
                    return key
                    break

    def get_data(
        self, entity_description: "GrowattSensorEntityDescription"
    ) -> str | int | float | None:
        """Get the data."""
        # Support entity_description.api_key being either str or list/tuple of str
        variable = self._get_matching_api_key(entity_description.api_key, self.data)
        api_value = self.data.get(variable)

        previous_value = self.previous_values.get(variable)
        return_value = api_value

        # If we have a 'drop threshold' specified, then check it and correct if needed
        if (
            entity_description.previous_value_drop_threshold is not None
            and previous_value is not None
            and api_value is not None
        ):
            _LOGGER.debug(
                (
                    "%s - Drop threshold specified (%s), checking for drop... API"
                    " Value: %s, Previous Value: %s"
                ),
                entity_description.name,
                entity_description.previous_value_drop_threshold,
                api_value,
                previous_value,
            )
            diff = float(api_value) - float(previous_value)

            # Check if the value has dropped (negative value i.e. < 0) and it has only
            # dropped by a small amount, if so, use the previous value.
            # Note - The energy dashboard takes care of drops within 10%
            # of the current value, however if the value is low e.g. 0.2
            # and drops by 0.1 it classes as a reset.
            if -(entity_description.previous_value_drop_threshold) <= diff < 0:
                _LOGGER.debug(
                    (
                        "Diff is negative, but only by a small amount therefore not a"
                        " nightly reset, using previous value (%s) instead of api value"
                        " (%s)"
                    ),
                    previous_value,
                    api_value,
                )
                return_value = previous_value
            else:
                _LOGGER.debug(
                    "%s - No drop detected, using API value", entity_description.name
                )

        # Lifetime total values should always be increasing, they will never reset,
        # however the API sometimes returns 0 values when the clock turns to 00:00
        # local time in that scenario we should just return the previous value
        if entity_description.never_resets and api_value == 0 and previous_value:
            _LOGGER.debug(
                (
                    "API value is 0, but this value should never reset, returning"
                    " previous value (%s) instead"
                ),
                previous_value,
            )
            return_value = previous_value

        self.previous_values[variable] = return_value

        return return_value

    def get_value(self, entity_description) -> str | int | None:
        """Get a value from coordinator data for number/switch entities."""
        return self.data.get(entity_description.api_key)

    def set_value(self, entity_description, value: str | int) -> None:
        """Update a value in coordinator data after successful write."""
        self.data[entity_description.api_key] = value

    async def update_time_segment(
        self, segment_id: int, batt_mode: int, start_time, end_time, enabled: bool
    ) -> None:
        """Update a time segment.

        Args:
            segment_id: Time segment ID (1-9)
            batt_mode: Battery mode (0=load first, 1=battery first, 2=grid first)
            start_time: Start time (datetime.time object)
            end_time: End time (datetime.time object)
            enabled: Whether the segment is enabled
        """

        _LOGGER.debug(
            "Updating MIN/TLX time segment %s for device %s",
            segment_id,
            self.device_id,
        )

        if self.api_version == "v1":
            # Use V1 API for token authentication
            response = await self.hass.async_add_executor_job(
                self.api.min_write_time_segment,
                self.device_id,
                segment_id,
                batt_mode,
                start_time,
                end_time,
                enabled,
            )

            if hasattr(response, 'get'):
                if response.get("error_code", 1) == 0:
                    _LOGGER.info(
                        "Successfully updated MIN/TLX time segment %s for device %s",
                        segment_id,
                        self.device_id,
                    )
                    # Trigger a refresh to update the data
                    await self.async_refresh()
                else:
                    error_msg = response.get("error_msg", "Unknown error")
                    _LOGGER.error(
                        "Failed to update MIN/TLX time segment %s for device %s: %s",
                        segment_id,
                        self.device_id,
                        error_msg,
                    )
                    raise HomeAssistantError(f"Failed to update time segment: {error_msg}")
        else:
            _LOGGER.warning(
                "Time segment updates are only supported with V1 API (token authentication)"
            )
            raise HomeAssistantError(
                "Time segment updates require token authentication"
            )

    async def read_time_segments(self) -> list[dict]:
        """Read time segments from an inverter.

        Returns:
            List of dictionaries containing segment information
        """
        _LOGGER.debug(
            "Reading MIN/TLX time segments for device %s",
            self.device_id,
        )

        if self.api_version != "v1":
            _LOGGER.warning(
                "Reading time segments is only supported with V1 API (token authentication)"
            )
            raise HomeAssistantError(
                "Reading time segments requires token authentication"
            )

        # Ensure we have current data
        if not self.data:
            _LOGGER.debug("Triggering refresh to get time segments")
            await self.async_refresh()

        time_segments = []
        mode_names = {0: "Load First", 1: "Battery First", 2: "Grid First"}

        try:
            # Extract time segments from coordinator data
            for i in range(1, 10):  # Segments 1-9
                # Get raw time values
                start_time_raw = self.data.get(f"forcedTimeStart{i}", "0:0")
                end_time_raw = self.data.get(f"forcedTimeStop{i}", "0:0")

                # Handle 'null' or empty values
                if start_time_raw in ("null", None, ""):
                    start_time_raw = "0:0"
                if end_time_raw in ("null", None, ""):
                    end_time_raw = "0:0"

                # Format times with leading zeros (HH:MM)
                try:
                    start_parts = str(start_time_raw).split(":")
                    start_hour = int(start_parts[0])
                    start_min = int(start_parts[1])
                    start_time = f"{start_hour:02d}:{start_min:02d}"
                except (ValueError, IndexError):
                    start_time = "00:00"

                try:
                    end_parts = str(end_time_raw).split(":")
                    end_hour = int(end_parts[0])
                    end_min = int(end_parts[1])
                    end_time = f"{end_hour:02d}:{end_min:02d}"
                except (ValueError, IndexError):
                    end_time = "00:00"

                # Get the mode value
                mode_raw = self.data.get(f"time{i}Mode")
                if mode_raw in ("null", None):
                    batt_mode = None
                else:
                    try:
                        batt_mode = int(mode_raw)
                    except (ValueError, TypeError):
                        batt_mode = None

                # Get the enabled status
                enabled_raw = self.data.get(f"forcedStopSwitch{i}", 0)
                if enabled_raw in ("null", None):
                    enabled = False
                else:
                    try:
                        enabled = int(enabled_raw) == 1
                    except (ValueError, TypeError):
                        enabled = False

                segment = {
                    "segment_id": i,
                    "batt_mode": batt_mode,
                    "mode_name": mode_names.get(batt_mode, "Unknown"),
                    "start_time": start_time,
                    "end_time": end_time,
                    "enabled": enabled,
                }

                time_segments.append(segment)
                _LOGGER.debug("MIN/TLX time segment %s: %s", i, segment)

        except Exception as err:
            _LOGGER.error("Error reading MIN/TLX time segments: %s", err)
            raise HomeAssistantError(
                f"Error reading MIN/TLX time segments: {err}"
            ) from err

        return time_segments
