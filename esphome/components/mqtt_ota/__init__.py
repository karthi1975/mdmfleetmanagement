"""ESPHome external component: MQTT-triggered HTTP OTA for fleet management."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

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

    # Ensure esp_http_client and esp_https_ota IDF components are included
    cg.add_platformio_option(
        "build_flags", ["-DUSE_MQTT_OTA"]
    )
