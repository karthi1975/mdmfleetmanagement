#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "esphome/components/mqtt/mqtt_client.h"

#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_ota_ops.h"

#include <string>

namespace esphome {
namespace mqtt_ota {

static const char *const TAG = "mqtt_ota";

// Cloudflare Origin CA root — used to validate origin certs served by
// the fleet broker / firmware host when the OTA URL is https://.
// PEM is embedded so the firmware needs no filesystem access at runtime.
static const char *const CF_ORIGIN_CA_PEM = R"(-----BEGIN CERTIFICATE-----
MIIEADCCAuigAwIBAgIID+rOSdTGfGcwDQYJKoZIhvcNAQELBQAwgYsxCzAJBgNV
BAYTAlVTMRkwFwYDVQQKExBDbG91ZEZsYXJlLCBJbmMuMTQwMgYDVQQLEytDbG91
ZEZsYXJlIE9yaWdpbiBTU0wgQ2VydGlmaWNhdGUgQXV0aG9yaXR5MRYwFAYDVQQH
Ew1TYW4gRnJhbmNpc2NvMRMwEQYDVQQIEwpDYWxpZm9ybmlhMB4XDTE5MDgyMzIx
MDgwMFoXDTI5MDgxNTE3MDAwMFowgYsxCzAJBgNVBAYTAlVTMRkwFwYDVQQKExBD
bG91ZEZsYXJlLCBJbmMuMTQwMgYDVQQLEytDbG91ZEZsYXJlIE9yaWdpbiBTU0wg
Q2VydGlmaWNhdGUgQXV0aG9yaXR5MRYwFAYDVQQHEw1TYW4gRnJhbmNpc2NvMRMw
EQYDVQQIEwpDYWxpZm9ybmlhMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEAwEiVZ/UoQpHmFsHvk5isBxRehukP8DG9JhFev3WZtG76WoTthvLJFRKFCHXm
V6Z5/66Z4S09mgsUuFwvJzMnE6Ej6yIsYNCb9r9QORa8BdhrkNn6kdTly3mdnykb
OomnwbUfLlExVgNdlP0XoRoeMwbQ4598foiHblO2B/LKuNfJzAMfS7oZe34b+vLB
yrP/1bgCSLdc1AxQc1AC0EsQQhgcyTJNgnG4va1c7ogPlwKyhbDyZ4e59N5lbYPJ
SmXI/cAe3jXj1FBLJZkwnoDKe0v13xeF+nF32smSH0qB7aJX2tBMW4TWtFPmzs5I
lwrFSySWAdwYdgxw180yKU0dvwIDAQABo2YwZDAOBgNVHQ8BAf8EBAMCAQYwEgYD
VR0TAQH/BAgwBgEB/wIBAjAdBgNVHQ4EFgQUJOhTV118NECHqeuU27rhFnj8KaQw
HwYDVR0jBBgwFoAUJOhTV118NECHqeuU27rhFnj8KaQwDQYJKoZIhvcNAQELBQAD
ggEBAHwOf9Ur1l0Ar5vFE6PNrZWrDfQIMyEfdgSKofCdTckbqXNTiXdgbHs+TWoQ
wAB0pfJDAHJDXOTCWRyTeXOseeOi5Btj5CnEuw3P0oXqdqevM1/+uWp0CM35zgZ8
VD4aITxity0djzE6Qnx3Syzz+ZkoBgTnNum7d9A66/V636x4vTeqbZFBr9erJzgz
hhurjcoacvRNhnjtDRM0dPeiCJ50CP3wEYuvUzDHUaowOsnLCjQIkWbR7Ni6KEIk
MOz2U0OBSif3FTkhCgZWQKOOLo1P42jHC3ssUZAtVNXrCk3fw9/E15k8NPkBazZ6
0iykLhH1trywrKRMVw67F44IE8Y=
-----END CERTIFICATE-----
)";

class MqttOtaComponent : public Component {
 public:
  float get_setup_priority() const override {
    return setup_priority::AFTER_CONNECTION;
  }

  void setup() override {
    std::string topic = "fleet/" + App.get_name() + "/ota/cmd";
    mqtt::global_mqtt_client->subscribe(
        topic,
        [this](const std::string &topic, const std::string &payload) {
          this->handle_ota_command_(payload);
        },
        0);
    ESP_LOGI(TAG, "Subscribed to %s", topic.c_str());
  }

 private:
  static std::string extract_json_(const std::string &json, const std::string &key) {
    std::string search = "\"" + key + "\"";
    size_t key_pos = json.find(search);
    if (key_pos == std::string::npos) return "";
    size_t colon_pos = json.find(":", key_pos + search.length());
    if (colon_pos == std::string::npos) return "";
    size_t quote_start = json.find("\"", colon_pos + 1);
    if (quote_start == std::string::npos) return "";
    size_t quote_end = json.find("\"", quote_start + 1);
    if (quote_end == std::string::npos) return "";
    return json.substr(quote_start + 1, quote_end - quote_start - 1);
  }

  void publish_status_(const char *status, const std::string &version) {
    std::string topic = "fleet/" + App.get_name() + "/ota/status";
    char buf[128];
    snprintf(buf, sizeof(buf), "{\"status\":\"%s\",\"version\":\"%s\"}", status, version.c_str());
    mqtt::global_mqtt_client->publish(topic, buf, 0, 0, false);
    ESP_LOGI(TAG, "Status: %s (v%s)", status, version.c_str());
  }

  void handle_ota_command_(const std::string &payload) {
    ESP_LOGI(TAG, "OTA command: %s", payload.c_str());

    std::string version = extract_json_(payload, "version");
    std::string url = extract_json_(payload, "url");
    if (url.empty()) {
      ESP_LOGE(TAG, "No URL in OTA command");
      return;
    }

    bool is_https = url.rfind("https://", 0) == 0;
    ESP_LOGI(TAG, "OTA: version=%s url=%s (%s)",
             version.c_str(), url.c_str(), is_https ? "https" : "http");
    publish_status_("downloading", version);

    // Configure HTTP client. For https:// pin to the CF Origin CA so
    // we trust only origin certs issued under that root; for http://
    // leave cert_pem null.
    esp_http_client_config_t http_cfg = {};
    http_cfg.url = url.c_str();
    http_cfg.timeout_ms = 30000;
    http_cfg.keep_alive_enable = true;
    if (is_https) {
      http_cfg.cert_pem = CF_ORIGIN_CA_PEM;
    }

    esp_https_ota_config_t ota_cfg = {};
    ota_cfg.http_config = &http_cfg;

    esp_https_ota_handle_t handle = nullptr;
    esp_err_t err = esp_https_ota_begin(&ota_cfg, &handle);
    if (err != ESP_OK || handle == nullptr) {
      ESP_LOGE(TAG, "esp_https_ota_begin failed: %s", esp_err_to_name(err));
      publish_status_("failed", version);
      return;
    }

    int total_size = esp_https_ota_get_image_size(handle);
    ESP_LOGI(TAG, "Firmware size: %d bytes", total_size);
    publish_status_("flashing", version);

    // Stream loop. Long downloads on the main task starve IDLE and trip
    // the task WDT — feed it every iteration and pump the MQTT loop
    // every ~32 KB so keepalive survives.
    int last_pump = 0;
    while (true) {
      err = esp_https_ota_perform(handle);
      if (err != ESP_ERR_HTTPS_OTA_IN_PROGRESS) break;

      int read = esp_https_ota_get_image_len_read(handle);
      App.feed_wdt();
      if (read - last_pump >= 32 * 1024) {
        mqtt::global_mqtt_client->loop();
        last_pump = read;
        ESP_LOGI(TAG, "OTA progress: %d/%d", read, total_size);
      }
      delay(1);
    }

    if (err != ESP_OK) {
      ESP_LOGE(TAG, "esp_https_ota_perform failed: %s", esp_err_to_name(err));
      esp_https_ota_abort(handle);
      publish_status_("failed", version);
      return;
    }

    if (!esp_https_ota_is_complete_data_received(handle)) {
      ESP_LOGE(TAG, "OTA: incomplete data");
      esp_https_ota_abort(handle);
      publish_status_("failed", version);
      return;
    }

    err = esp_https_ota_finish(handle);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "esp_https_ota_finish failed: %s", esp_err_to_name(err));
      publish_status_("failed", version);
      return;
    }

    int total_read = esp_https_ota_get_image_len_read(handle);
    ESP_LOGI(TAG, "OTA success! Wrote %d bytes. Rebooting...", total_read);
    publish_status_("success", version);

    // Pump the MQTT client loop so the success publish actually flushes
    // before we reboot (delay() alone leaves it queued).
    for (int i = 0; i < 60; i++) {
      mqtt::global_mqtt_client->loop();
      delay(50);
    }
    App.safe_reboot();
  }
};

}  // namespace mqtt_ota
}  // namespace esphome
