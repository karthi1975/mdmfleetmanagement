"""ESPHome external component: MQTT-triggered HTTP/HTTPS OTA for fleet management."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.components.esp32 import include_builtin_idf_component

DEPENDENCIES = ["mqtt"]

mqtt_ota_ns = cg.esphome_ns.namespace("mqtt_ota")
MqttOtaComponent = mqtt_ota_ns.class_("MqttOtaComponent", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(MqttOtaComponent),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add_platformio_option("build_flags", ["-DUSE_MQTT_OTA"])
    # ESP-IDF built-in components used by mqtt_ota.h — both excluded by
    # default in DEFAULT_EXCLUDED_IDF_COMPONENTS, so re-enable.
    include_builtin_idf_component("esp_http_client")
    include_builtin_idf_component("esp_https_ota")
