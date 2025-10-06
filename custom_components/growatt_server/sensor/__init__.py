"""Read status of growatt inverters."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..coordinator import GrowattConfigEntry, GrowattCoordinator
from .inverter import INVERTER_SENSOR_TYPES
from .mix import MIX_SENSOR_TYPES
from .sensor_entity_description import GrowattSensorEntityDescription
from .storage import STORAGE_SENSOR_TYPES
from .tlx import TLX_SENSOR_TYPES
from .total import TOTAL_SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)
_TRANSLATIONS_CACHE: dict[str, Any] | None = None


async def _load_translations_cache(hass: HomeAssistant) -> None:
    """Load translations for custom component (async, non-blocking)."""
    global _TRANSLATIONS_CACHE
    
    if _TRANSLATIONS_CACHE is not None:
        return  # Already loaded
    
    try:
        import json
        from pathlib import Path
        
        # Get the path to our strings.json file
        component_dir = Path(__file__).parent.parent
        strings_path = component_dir / "strings.json"
        
        if strings_path.exists():
            # Use executor to avoid blocking the event loop
            content = await hass.async_add_executor_job(
                strings_path.read_text, "utf-8"
            )
            raw_translations = json.loads(content)
            
            # Resolve key references like [%key:component::growatt_server::entity::sensor::inverter_amperage_input_1::name%]
            _TRANSLATIONS_CACHE = _resolve_translation_keys(raw_translations)
            _LOGGER.debug("Loaded custom component translations from strings.json")
        else:
            _TRANSLATIONS_CACHE = {}
            _LOGGER.warning("strings.json not found, using empty translation cache")
    except (FileNotFoundError, json.JSONDecodeError) as ex:
        _LOGGER.error("Failed to load translations: %s", ex)
        _TRANSLATIONS_CACHE = {}


def _resolve_translation_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve [%key:...%] references in translation strings."""
    import re
    
    def resolve_value(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("[%key:") and value.endswith("%]"):
            # Parse key reference: [%key:component::growatt_server::entity::sensor::inverter_amperage_input_1::name%]
            key_match = re.match(r'\[%key:component::growatt_server::entity::sensor::([^:]+)::name%\]', value)
            if key_match:
                referenced_key = key_match.group(1)
                # Look up the referenced translation
                sensor_data = data.get("entity", {}).get("sensor", {})
                referenced_translation = sensor_data.get(referenced_key, {})
                if isinstance(referenced_translation, dict) and "name" in referenced_translation:
                    resolved = referenced_translation["name"]
                    # Recursively resolve in case the referenced key also has a reference
                    return resolve_value(resolved)
            # If we can't resolve, return original value
            return value
        elif isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(item) for item in value]
        else:
            return value
    
    return resolve_value(data)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GrowattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Growatt sensor."""
    # Load translations for custom component (async, non-blocking)
    await _load_translations_cache(hass)
    
    # Use runtime_data instead of hass.data
    data = config_entry.runtime_data

    entities: list[GrowattSensor] = []

    # Add total sensors
    total_coordinator = data.total_coordinator
    entities.extend(
        GrowattSensor(
            total_coordinator,
            name=f"{config_entry.data['name']} Total",
            serial_id=config_entry.data["plant_id"],
            unique_id=f"{config_entry.data['plant_id']}-{description.key}",
            description=description,
        )
        for description in TOTAL_SENSOR_TYPES
    )

    # Add sensors for each device
    for device_sn, device_coordinator in data.devices.items():
        sensor_descriptions: list = []
        if device_coordinator.device_type == "inverter":
            sensor_descriptions = list(INVERTER_SENSOR_TYPES)
        elif device_coordinator.device_type in ("tlx", "min"):
            sensor_descriptions = list(TLX_SENSOR_TYPES)
        elif device_coordinator.device_type == "storage":
            sensor_descriptions = list(STORAGE_SENSOR_TYPES)
        elif device_coordinator.device_type == "mix":
            sensor_descriptions = list(MIX_SENSOR_TYPES)
        else:
            _LOGGER.debug(
                "Device type %s was found but is not supported right now",
                device_coordinator.device_type,
            )

        entities.extend(
            GrowattSensor(
                device_coordinator,
                name=device_sn,
                serial_id=device_sn,
                unique_id=f"{device_sn}-{description.key}",
                description=description,
            )
            for description in sensor_descriptions
        )

    async_add_entities(entities)


class GrowattSensor(CoordinatorEntity[GrowattCoordinator], SensorEntity):
    """Representation of a Growatt Sensor."""

    _attr_has_entity_name = False
    entity_description: GrowattSensorEntityDescription

    def __init__(
        self,
        coordinator: GrowattCoordinator,
        name: str,
        serial_id: str,
        unique_id: str,
        description: GrowattSensorEntityDescription,
    ) -> None:
        """Initialize a PVOutput sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:solar-power"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_id)},
            manufacturer="Growatt",
            name=name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        # If entity description has an explicit name, use it
        if (hasattr(self.entity_description, 'name') and
            self.entity_description.name and
            str(self.entity_description.name) != "UndefinedType._singleton"):
            return self.entity_description.name

        # Try to get translation from custom component's strings.json (cached)
        if self.entity_description.translation_key and _TRANSLATIONS_CACHE is not None:
            try:
                # Navigate to entity.sensor translations
                sensor_translations = _TRANSLATIONS_CACHE.get("entity", {}).get("sensor", {})
                translation_data = sensor_translations.get(self.entity_description.translation_key, {})
                
                if isinstance(translation_data, dict) and "name" in translation_data:
                    return translation_data["name"]
                elif isinstance(translation_data, str):
                    return translation_data

            except (KeyError, AttributeError, TypeError):
                pass

            # Fallback: convert translation_key to readable format
            return self.entity_description.translation_key.replace('_', ' ').title()

        # Final fallback to device class name (current behavior)
        return None


    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        result = self.coordinator.get_data(self.entity_description)
        if (
            isinstance(result, (int, float))
            and self.entity_description.precision is not None
        ):
            result = round(result, self.entity_description.precision)
        return result

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        if self.entity_description.currency:
            return self.coordinator.get_currency()
        return super().native_unit_of_measurement

