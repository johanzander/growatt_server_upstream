"""Growatt Sensor definitions for the SPH type (Open API V1).

Entity keys deliberately reuse mix_* names where a Classic API equivalent exists,
so that users migrating from Classic API (where SPH appeared as "mix") to V1 API
retain their Energy Dashboard history (the unique_id includes the key name).

Sensors with no Classic API equivalent use sph_* keys.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

from .sensor_entity_description import GrowattSensorEntityDescription

SPH_SENSOR_TYPES: tuple[GrowattSensorEntityDescription, ...] = (
    # ------------------------------------------------------------------- #
    # Sensors using mix_* keys for backward-compat with Classic API users #
    # ------------------------------------------------------------------- #
    # Values from 'sph_detail' API call (device/mix/mix_data_info)
    # NOTE: The key is intentionally "mix_statement_of_charge" (not "state_of_charge")
    # to preserve backward-compatibility with users migrating from the Classic API,
    # where SPH appeared as "mix" and used this exact key.
    GrowattSensorEntityDescription(
        key="mix_statement_of_charge",
        translation_key="mix_statement_of_charge",
        api_key="bmsSOC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_voltage",
        translation_key="mix_battery_voltage",
        api_key="vbat",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    GrowattSensorEntityDescription(
        key="mix_pv1_voltage",
        translation_key="mix_pv1_voltage",
        api_key="vpv1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    GrowattSensorEntityDescription(
        key="mix_pv2_voltage",
        translation_key="mix_pv2_voltage",
        api_key="vpv2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    GrowattSensorEntityDescription(
        key="mix_grid_voltage",
        translation_key="mix_grid_voltage",
        api_key="vac1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_charge",
        translation_key="mix_battery_charge",
        api_key="pcharge1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_discharge_w",
        translation_key="mix_battery_discharge_w",
        api_key="pdischarge1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # TODO: remove coordinator W→kW conversion once growattServer normalises
    # SPH discharge power units (no native kW field in V1 API).
    GrowattSensorEntityDescription(
        key="mix_battery_discharge_kw",
        translation_key="mix_battery_discharge_kw",
        api_key="pdischarge1KW",  # synthetic kW field created in coordinator
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_export_to_grid",
        translation_key="mix_export_to_grid",
        api_key="pacToGridTotal",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_import_from_grid",
        translation_key="mix_import_from_grid",
        api_key="pacToUserR",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Values from 'sph_energy' API call (device/mix/mix_last_data)
    # Note: ppv1/ppv2/ppv are returned in W by the API but converted to kW
    # in the coordinator to match the units Classic API mix sensors used.
    GrowattSensorEntityDescription(
        key="mix_wattage_pv_1",
        translation_key="mix_wattage_pv_1",
        api_key="ppv1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_wattage_pv_2",
        translation_key="mix_wattage_pv_2",
        api_key="ppv2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_wattage_pv_all",
        translation_key="mix_wattage_pv_all",
        api_key="ppv",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_charge_today",
        translation_key="mix_battery_charge_today",
        api_key="echarge1Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_charge_lifetime",
        translation_key="mix_battery_charge_lifetime",
        api_key="echarge1Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_discharge_today",
        translation_key="mix_battery_discharge_today",
        api_key="edischarge1Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_battery_discharge_lifetime",
        translation_key="mix_battery_discharge_lifetime",
        api_key="edischarge1Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="mix_solar_generation_today",
        translation_key="mix_solar_generation_today",
        api_key="epvtoday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_solar_generation_lifetime",
        translation_key="mix_solar_generation_lifetime",
        api_key="epvTotal",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="mix_system_production_today",
        translation_key="mix_system_production_today",
        api_key="esystemtoday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_self_consumption_today",
        translation_key="mix_self_consumption_today",
        api_key="eselfToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_import_from_grid_today",
        translation_key="mix_import_from_grid_today",
        api_key="etoUserToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_export_to_grid_today",
        translation_key="mix_export_to_grid_today",
        api_key="etoGridToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_export_to_grid_lifetime",
        translation_key="mix_export_to_grid_lifetime",
        api_key="etogridTotal",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="mix_load_consumption_today",
        translation_key="mix_load_consumption_today",
        api_key="elocalLoadToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_load_consumption_lifetime",
        translation_key="mix_load_consumption_lifetime",
        api_key="elocalLoadTotal",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="mix_load_consumption_battery_today",
        translation_key="mix_load_consumption_battery_today",
        api_key="echarge1",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_load_consumption_solar_today",
        translation_key="mix_load_consumption_solar_today",
        api_key="eChargeToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GrowattSensorEntityDescription(
        key="mix_last_update",
        translation_key="mix_last_update",
        api_key="lastdataupdate",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    # ------------------------------------------------------------------ #
    # Sensors available in Classic API but NOT in V1 API:                #
    #   mix_import_from_grid_today_combined  (synthetic, no V1 field)    #
    #   mix_load_consumption                 (real-time power, no V1 field)
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # SPH-specific sensors with sph_* keys (no Classic API equivalent)   #
    # ------------------------------------------------------------------ #
    GrowattSensorEntityDescription(
        key="sph_grid_frequency",
        translation_key="sph_grid_frequency",
        api_key="fac",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="sph_temperature_1",
        translation_key="sph_temperature_1",
        api_key="temp1",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="sph_temperature_2",
        translation_key="sph_temperature_2",
        api_key="temp2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="sph_temperature_3",
        translation_key="sph_temperature_3",
        api_key="temp3",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="sph_temperature_4",
        translation_key="sph_temperature_4",
        api_key="temp4",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GrowattSensorEntityDescription(
        key="sph_temperature_5",
        translation_key="sph_temperature_5",
        api_key="temp5",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)
