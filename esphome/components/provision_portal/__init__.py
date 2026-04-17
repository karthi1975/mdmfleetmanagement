"""ESPHome external component: provisioning portal.

Replaces the built-in captive_portal with a form that collects WiFi SSID,
WiFi password, home_id, and a device label. Values are persisted to NVS
under a stable hash (independent of App.get_config_version_hash()) so
they survive OTAs and YAML edits — same rationale as the wifi fix in
common/base.yaml.
"""

import esphome.codegen as cg
from esphome.components import web_server_base
from esphome.components.web_server_base import CONF_WEB_SERVER_BASE_ID
import esphome.config_validation as cv
from esphome.const import CONF_ID

DEPENDENCIES = ["wifi"]
AUTO_LOAD = ["web_server_base"]

provision_portal_ns = cg.esphome_ns.namespace("provision_portal")
ProvisionPortal = provision_portal_ns.class_("ProvisionPortal", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(ProvisionPortal),
        cv.GenerateID(CONF_WEB_SERVER_BASE_ID): cv.use_id(
            web_server_base.WebServerBase
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    paren = await cg.get_variable(config[CONF_WEB_SERVER_BASE_ID])
    var = cg.new_Pvariable(config[CONF_ID], paren)
    await cg.register_component(var, config)
