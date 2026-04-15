/**
 * MQTT-triggered HTTP OTA component for ESPHome.
 *
 * Subscribes to fleet/{device}/ota/cmd MQTT topic.
 * On command: downloads firmware .bin from URL, flashes, reports status back.
 * Status reports go to fleet/{device}/ota/status.
 *
 * Expected MQTT command payload:
 *   {"version":"2.0.0","url":"http://192.168.1.231:8000/firmware/2.0.0/firmware.bin","checksum":"sha256hex"}
 */

#pragma once

#include "esphome.h"
#include <HTTPUpdate.h>
#include <ArduinoJson.h>
#include <WiFiClient.h>

class MqttOtaComponent : public Component {
 public:
  void setup() override {
    // Subscribe to OTA command topic via ESPHome's MQTT client
    std::string topic = "fleet/" + App.get_name() + "/ota/cmd";

    mqtt::global_mqtt_client->subscribe(
        topic,
        [this](const std::string &topic, const std::string &payload) {
          this->handle_ota_command(payload);
        },
        0  // QoS 0
    );
    ESP_LOGI("mqtt_ota", "Subscribed to %s", topic.c_str());
  }

  float get_setup_priority() const override {
    // Run after MQTT is connected
    return setup_priority::AFTER_CONNECTION;
  }

 private:
  void publish_status(const char *status, const char *version) {
    std::string topic = "fleet/" + App.get_name() + "/ota/status";
    char buf[128];
    snprintf(buf, sizeof(buf), "{\"status\":\"%s\",\"version\":\"%s\"}", status, version);
    mqtt::global_mqtt_client->publish(topic, buf, 0, false);
    ESP_LOGI("mqtt_ota", "Status: %s (version %s)", status, version);
  }

  void handle_ota_command(const std::string &payload) {
    ESP_LOGI("mqtt_ota", "OTA command received: %s", payload.c_str());

    // Parse JSON
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
      ESP_LOGE("mqtt_ota", "JSON parse error: %s", err.c_str());
      return;
    }

    const char *version = doc["version"] | "";
    const char *url = doc["url"] | "";

    if (strlen(url) == 0) {
      ESP_LOGE("mqtt_ota", "No URL in OTA command");
      return;
    }

    ESP_LOGI("mqtt_ota", "Starting OTA: version=%s url=%s", version, url);

    // Report downloading status
    publish_status("downloading", version);

    // Use ESP32 HTTPUpdate to download and flash
    WiFiClient wifi_client;
    httpUpdate.setLedPin(GPIO_NUM_2, LOW);  // Blink LED during update
    httpUpdate.rebootOnUpdate(false);       // We'll reboot manually after reporting

    t_httpUpdate_return result = httpUpdate.update(wifi_client, url);

    switch (result) {
      case HTTP_UPDATE_FAILED:
        ESP_LOGE("mqtt_ota", "OTA failed: %s", httpUpdate.getLastErrorString().c_str());
        publish_status("failed", version);
        break;

      case HTTP_UPDATE_NO_UPDATES:
        ESP_LOGW("mqtt_ota", "OTA: no update available");
        publish_status("failed", version);
        break;

      case HTTP_UPDATE_OK:
        ESP_LOGI("mqtt_ota", "OTA success! Rebooting...");
        publish_status("success", version);
        // Give MQTT time to send the status message before reboot
        delay(1000);
        App.safe_reboot();
        break;
    }
  }
};
