"""Coordinator module for managing Growatt data fetching."""

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import growattServer
from growattServer import DeviceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BATT_MODE_BATTERY_FIRST,
    BATT_MODE_GRID_FIRST,
    BATT_MODE_LOAD_FIRST,
    DEFAULT_URL,
    DOMAIN,
)
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
            msg = f"Unknown API version: {self.api_version}"
            raise ValueError(msg)

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
                        _LOGGER.debug(
                            "Could not convert %s to float: %s", pv_key, data[pv_key]
                        )

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
                # The V1 Plant APIs do not provide the same information as the classic plant_info() API
                # More specifically:
                # 1. There is no monetary information to be found, so today and lifetime money is not available
                # 2. There is no nominal power, this is provided by inverter min_energy()
                # This means, for the total coordinator we can only fetch and map the following:
                # todayEnergy -> today_energy
                # totalEnergy -> total_energy
                # invTodayPpv -> current_power
                # Ensure plant_energy_overview is only called on OpenApiV1
                if hasattr(self.api, "plant_energy_overview"):
                    total_info = self.api.plant_energy_overview(self.plant_id)
                    total_info["todayEnergy"] = total_info.get("today_energy")
                    total_info["totalEnergy"] = total_info.get("total_energy")
                    total_info["invTodayPpv"] = total_info.get("current_power")
                else:
                    msg = "plant_energy_overview is not available for this API class"
                    raise AttributeError(msg)
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
                _LOGGER.exception(
                    "Error fetching min device data for %s", self.device_id
                )
                msg = f"Error fetching min device data: {err}"
                raise UpdateFailed(msg) from err
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
                    mix_details = self.api.device_details(
                        self.device_id, DeviceType.SPH_MIX
                    )
                    mix_energy = self.api.device_energy(
                        self.device_id, DeviceType.SPH_MIX
                    )

                    date_str = mix_energy.get("time")
                    date_format = "%Y-%m-%d %H:%M:%S"
                    tz = dt_util.get_default_time_zone()
                    if date_str is not None:
                        naive_dt = datetime.datetime.strptime(date_str, date_format)
                        aware_dt = naive_dt.replace(tzinfo=tz)
                        mix_details["lastdataupdate"] = aware_dt
                    else:
                        mix_details["lastdataupdate"] = None

                    mix_energy["ppv1"] = mix_energy.get("ppv1", 0) / 1000  # W to kW
                    mix_energy["ppv2"] = mix_energy.get("ppv2", 0) / 1000  # W to kW
                    mix_energy["ppv"] = mix_energy.get("ppv", 0) / 1000  # W to kW
                    mix_energy["accdischargePowerKW"] = (
                        mix_energy.get("accdischargePower", 0) / 1000
                    )  # W to kW

                    mix_info = {**mix_details, **mix_energy}
                    self.data = mix_info
                    _LOGGER.debug(
                        "mix_info for device %s: %r", self.device_id, mix_info
                    )
                except growattServer.GrowattV1ApiError as err:
                    _LOGGER.exception(
                        "Error fetching mix device data for %s", self.device_id
                    )
                    msg = f"Error fetching {self.device_type} device data: {err}"
                    raise UpdateFailed(msg) from err
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
                    "etouser_combined": float(
                        dashboard_data["etouser"].replace("kWh", "")
                    )
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

    def _get_time_segment_params(
        self,
        segment_id: int,
        batt_mode: int,
        start_time: datetime.time,
        end_time: datetime.time,
        enabled: bool,
        charge_power: int,
        charge_stop_soc: int,
        mains_enabled: bool,
    ) -> tuple[DeviceType, Any, str]:
        """
        Determine device type and create appropriate params for time segment update.

        Args:
            segment_id: Time segment ID (1-9)
            batt_mode: Battery mode (0=load first, 1=battery first, 2=grid first)
            start_time: Start time (datetime.time object)
            end_time: End time (datetime.time object)
            enabled: Whether the segment is enabled
            charge_power: Charge power percentage (0-100, SPH_MIX only)
            charge_stop_soc: Charge stop SOC percentage (0-100, SPH_MIX only)
            mains_enabled: Enable mains charging (SPH_MIX only)

        Returns:
            Tuple of (device_type, params, command)

        Raises:
            HomeAssistantError: If device type is unsupported or battery mode is invalid
        """
        if self.device_type == "tlx":
            # MIN_TLX device - use TimeSegmentParams
            device_type = growattServer.DeviceType.MIN_TLX
            params = self.api.TimeSegmentParams(
                segment_id=segment_id,
                batt_mode=batt_mode,
                start_time=start_time,
                end_time=end_time,
                enabled=enabled,
            )
            command = f"time_segment_{segment_id}"
            return device_type, params, command

        elif self.device_type == "mix":
            # SPH_MIX device - different commands based on battery mode
            device_type = growattServer.DeviceType.SPH_MIX

            if batt_mode == BATT_MODE_BATTERY_FIRST:
                # Battery first mode - AC charge time period
                params = self.api.MixAcChargeTimeParams(
                    charge_power=charge_power,
                    charge_stop_soc=charge_stop_soc,
                    mains_enabled=mains_enabled,
                    start_hour=start_time.hour,
                    start_minute=start_time.minute,
                    end_hour=end_time.hour,
                    end_minute=end_time.minute,
                    enabled=enabled,
                    segment_id=segment_id,
                )
                command = "mix_ac_charge_time_period"
                return device_type, params, command

            elif batt_mode == BATT_MODE_GRID_FIRST:
                # Grid first mode - AC discharge time period
                params = self.api.MixAcDischargeTimeParams(
                    discharge_power=charge_power,  # discharge power
                    discharge_stop_soc=charge_stop_soc,  # Stop at % SOC
                    start_hour=start_time.hour,
                    start_minute=start_time.minute,
                    end_hour=end_time.hour,
                    end_minute=end_time.minute,
                    enabled=enabled,
                    segment_id=segment_id,
                )
                command = "mix_ac_discharge_time_period"
                return device_type, params, command

            elif batt_mode == BATT_MODE_LOAD_FIRST:
                # Load first mode - single export
                params = self.api.ChargeDischargeParams(
                    discharge_stop_soc=charge_stop_soc,
                )
                command = "mix_single_export"
                return device_type, params, command

            else:
                msg = f"Invalid battery mode {batt_mode} for MIX device"
                _LOGGER.error(msg)
                raise HomeAssistantError(msg)

        else:
            msg = f"Time segment updates not supported for device type: {self.device_type}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

    async def update_time_segment(
        self,
        segment_id: int,
        batt_mode: int,
        start_time: datetime.time,
        end_time: datetime.time,
        enabled: bool,
        charge_power: int = 80,
        charge_stop_soc: int = 95,
        mains_enabled: bool = True,
    ) -> None:
        """
        Update a time segment.

        Args:
            segment_id: Time segment ID (1-9)
            batt_mode: Battery mode (0=load first, 1=battery first, 2=grid first)
            start_time: Start time (datetime.time object)
            end_time: End time (datetime.time object)
            enabled: Whether the segment is enabled
            charge_power: Charge power percentage (0-100, SPH_MIX only)
            charge_stop_soc: Charge stop SOC percentage (0-100, SPH_MIX only)
            mains_enabled: Enable mains charging (SPH_MIX only)

        """
        _LOGGER.debug(
            "Updating time segment %s for device %s (%s)",
            segment_id,
            self.device_id,
            self.device_type,
        )

        if self.api_version != "v1":
            msg = "Time segment updates require V1 API (token authentication)"
            _LOGGER.warning(msg)
            raise HomeAssistantError(msg)

        # Get device type, params, and command for this update
        device_type, params, command = self._get_time_segment_params(
            segment_id=segment_id,
            batt_mode=batt_mode,
            start_time=start_time,
            end_time=end_time,
            enabled=enabled,
            charge_power=charge_power,
            charge_stop_soc=charge_stop_soc,
            mains_enabled=mains_enabled,
        )

        _LOGGER.debug(
            "Running Command %s with params %s",
            command,
            params,
        )

        try:
            # Use V1 API write_time_segment method
            response = self.hass.async_add_executor_job(
                self.api.write_time_segment,
                self.device_id,
                device_type,
                command,
                params,
            )

            _LOGGER.debug(
                "Write time segment response: type=%s, response=%s",
                type(response).__name__,
                response,
            )

            # Handle dict response (most common)
            if isinstance(response, dict):
                error_code = response.get("error_code", 1)
                error_msg = response.get("error_msg", "Unknown error")

                if error_code == 0:
                    _LOGGER.info(
                        "Successfully updated time segment %s for device %s: %s (Full response: %s)",
                        segment_id,
                        self.device_id,
                        error_msg,
                        response,
                    )
                    # Trigger a refresh to update the data
                    await self.async_refresh()
                else:
                    _LOGGER.error(
                        "Failed to update time segment %s for device %s: error_code=%s, %s",
                        segment_id,
                        self.device_id,
                        error_code,
                        error_msg,
                    )
                    msg = f"Failed to update time segment: {error_msg} (code: {error_code})"
                    raise HomeAssistantError(msg)
            else:
                _LOGGER.warning(
                    "Unexpected response format for time segment update: %s - %s",
                    type(response).__name__,
                    response,
                )
        except HomeAssistantError:
            # Re-raise HomeAssistantError as-is
            raise
        except Exception as err:
            _LOGGER.exception(
                "Error updating time segment %s for device %s",
                segment_id,
                self.device_id,
            )
            msg = f"Error updating time segment: {err}"
            raise HomeAssistantError(msg) from err

    async def read_time_segments(self) -> list[dict[str, Any]]:
        """
        Read time segments from the device.

        For MIN/TLX devices: Uses the API's read_time_segments method.
        For SPH/MIX devices: Parses the forced charge/discharge fields.

        Returns:
            List of time segment dictionaries with keys:
            - segment_id: int
            - batt_mode: int (0=load first, 1=battery first/charge, 2=grid first/discharge)
            - mode_name: str
            - start_time: str (HH:MM format)
            - end_time: str (HH:MM format)
            - enabled: bool

        """
        if self.api_version != "v1":
            msg = "Time segment reading requires V1 API"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

        if self.device_type == "tlx":
            return await self._read_tlx_time_segments()
        elif self.device_type == "mix":
            return await self._read_mix_time_segments()
        else:
            msg = f"Time segment reading not supported for device type: {self.device_type}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

    async def _read_tlx_time_segments(self) -> list[dict[str, Any]]:
        """Read time segments for MIN/TLX devices using the API."""
        _LOGGER.debug(
            "Reading TLX time segments for device %s",
            self.device_id,
        )

        try:
            response = await self.hass.async_add_executor_job(
                self.api.read_time_segments,
                self.device_id,
                growattServer.DeviceType.MIN_TLX,
            )

            _LOGGER.debug(
                "TLX read_time_segments response type: %s, content: %s",
                type(response).__name__,
                response,
            )

            # Handle different response formats
            if isinstance(response, list):
                time_segments = response
            elif isinstance(response, dict):
                error_code = response.get("error_code", 1)
                if error_code == 0:
                    time_segments = response.get("data", [])
                else:
                    error_msg = response.get("error_msg", "Unknown error")
                    msg = f"API error reading time segments: {error_msg} (code: {error_code})"
                    raise HomeAssistantError(msg)
            else:
                _LOGGER.warning(
                    "Unexpected response format: %s", type(response).__name__
                )
                time_segments = []

            _LOGGER.info(
                "Successfully read %d time segments for TLX device %s",
                len(time_segments),
                self.device_id,
            )

            return time_segments

        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Error reading TLX time segments: %s", err)
            msg = f"Error reading TLX time segments: {err}"
            raise HomeAssistantError(msg) from err

    async def _read_mix_time_segments(self) -> list[dict[str, Any]]:
        """
        Read time segments for SPH/MIX devices by parsing device settings.

        SPH/MIX devices store charge/discharge periods in numbered fields:
        - forcedChargeStopSwitch1-6: Enable flags for charge periods
        - forcedChargeTimeStart1-6: Start times for charge periods
        - forcedChargeTimeStop1-6: End times for charge periods
        - forcedDischargeStopSwitch1-6: Enable flags for discharge periods
        - forcedDischargeTimeStart1-6: Start times for discharge periods
        - forcedDischargeTimeStop1-6: End times for discharge periods

        """
        _LOGGER.debug(
            "Reading MIX time segments for device %s",
            self.device_id,
        )

        try:
            # Get current device data which includes all settings
            if not self.data:
                await self.async_refresh()

            time_segments = []

            # Parse charge periods (Battery First mode - batt_mode=1)
            for i in range(1, 7):  # 6 charge periods
                enabled = bool(self.data.get(f"forcedChargeStopSwitch{i}", 0))
                start_time = self.data.get(f"forcedChargeTimeStart{i}", "0:0")
                end_time = self.data.get(f"forcedChargeTimeStop{i}", "0:0")

                # Normalize time format from "H:M" to "HH:MM"
                start_time = self._normalize_time_format(start_time)
                end_time = self._normalize_time_format(end_time)

                time_segments.append(
                    {
                        "segment_id": i,
                        "batt_mode": BATT_MODE_BATTERY_FIRST,
                        "mode_name": "Battery First (Charge)",
                        "start_time": start_time,
                        "end_time": end_time,
                        "enabled": enabled,
                    }
                )

            # Parse discharge periods (Grid First mode - batt_mode=2)
            for i in range(1, 7):  # 6 discharge periods
                enabled = bool(self.data.get(f"forcedDischargeStopSwitch{i}", 0))
                start_time = self.data.get(f"forcedDischargeTimeStart{i}", "0:0")
                end_time = self.data.get(f"forcedDischargeTimeStop{i}", "0:0")

                # Normalize time format
                start_time = self._normalize_time_format(start_time)
                end_time = self._normalize_time_format(end_time)

                time_segments.append(
                    {
                        "segment_id": i + 6,  # Offset by 6 to avoid conflicts
                        "batt_mode": BATT_MODE_GRID_FIRST,
                        "mode_name": "Grid First (Discharge)",
                        "start_time": start_time,
                        "end_time": end_time,
                        "enabled": enabled,
                    }
                )

            _LOGGER.info(
                "Successfully read %d time segments for MIX device %s",
                len(time_segments),
                self.device_id,
            )

            return time_segments

        except Exception as err:
            _LOGGER.exception("Error reading MIX time segments: %s", err)
            msg = f"Error reading MIX time segments: {err}"
            raise HomeAssistantError(msg) from err

    @staticmethod
    def _normalize_time_format(time_str: str) -> str:
        """
        Normalize time string from "H:M" format to "HH:MM" format.

        Examples:
            "14:0" -> "14:00"
            "0:0" -> "00:00"
            "9:30" -> "09:30"

        """
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return "00:00"

            hours = int(parts[0])
            minutes = int(parts[1])

            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, AttributeError):
            return "00:00"
