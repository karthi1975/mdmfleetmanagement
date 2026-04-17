#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "esphome/core/helpers.h"
#include "esphome/core/preferences.h"
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/components/wifi/wifi_component.h"

#include <cstring>
#include <string>

namespace esphome {
namespace provision_portal {

static const char *const TAG = "provision_portal";

// Stable NVS hash. ESPHome keys most preferences by
// App.get_config_version_hash(), which rotates on every YAML/version
// change and orphans prior saves. Using a fixed constant keeps home_id
// and device label readable across OTAs — mirrors the wifi fix in
// common/base.yaml (see wifi_component.cpp:627, where has_sta()==false
// also routes to a stable hash).
static constexpr uint32_t PREF_HASH = 0x484F4D45UL;  // "HOME"

struct ProvisionSettings {
  char home_id[65];
  char device_label[65];
} PACKED;

class ProvisionPortal : public AsyncWebHandler, public Component {
 public:
  explicit ProvisionPortal(web_server_base::WebServerBase *base) : base_(base) {}

  float get_setup_priority() const override {
    // After WiFi setup so wifi::global_wifi_component is valid.
    return setup_priority::WIFI - 1.0f;
  }

  void setup() override {
    this->pref_ = global_preferences->make_preference<ProvisionSettings>(PREF_HASH, true);
    ProvisionSettings s{};
    if (this->pref_.load(&s)) {
      this->home_id_ = s.home_id;
      this->device_label_ = s.device_label;
      ESP_LOGI(TAG, "Loaded: home_id='%s' label='%s'",
               this->home_id_.c_str(), this->device_label_.c_str());
    } else {
      ESP_LOGI(TAG, "No stored provisioning settings yet");
    }
    this->base_->init();
    this->base_->add_handler_without_auth(this);
  }

  void dump_config() override {
    ESP_LOGCONFIG(TAG, "Provision Portal:");
    ESP_LOGCONFIG(TAG, "  home_id='%s'", this->home_id_.c_str());
    ESP_LOGCONFIG(TAG, "  device_label='%s'", this->device_label_.c_str());
  }

  const std::string &get_home_id() const { return this->home_id_; }
  const std::string &get_device_label() const { return this->device_label_; }

  // Active only while the AP is up. During normal STA operation the shared
  // web_server_base is used by other components (e.g. OTA), so we must
  // not intercept their requests.
  bool canHandle(AsyncWebServerRequest *request) const override {
    return wifi::global_wifi_component != nullptr &&
           wifi::global_wifi_component->is_ap_active();
  }

  void handleRequest(AsyncWebServerRequest *req) override {
    const char *url = req->url().c_str();
    if (std::strcmp(url, "/scan.json") == 0) {
      this->handle_scan_(req);
      return;
    }
    if (std::strcmp(url, "/save") == 0 && req->method() == HTTP_POST) {
      this->handle_save_(req);
      return;
    }
    this->serve_form_(req);
  }

 protected:
  void handle_scan_(AsyncWebServerRequest *req) {
    AsyncResponseStream *stream = req->beginResponseStream("application/json");
    stream->print("[");
    bool first = true;
    for (auto &scan : wifi::global_wifi_component->get_scan_result()) {
      if (scan.get_is_hidden()) continue;
      if (!first) stream->print(",");
      first = false;
      stream->printf("{\"ssid\":\"%s\",\"rssi\":%d,\"lock\":%d}",
                     scan.get_ssid().c_str(), scan.get_rssi(), scan.get_with_auth());
    }
    stream->print("]");
    req->send(stream);
  }

  void handle_save_(AsyncWebServerRequest *req) {
    std::string ssid = req->arg("ssid").c_str();
    std::string psk = req->arg("psk").c_str();
    std::string home_id = req->arg("home_id").c_str();
    std::string label = req->arg("label").c_str();

    ESP_LOGI(TAG, "Saving ssid='%s' home_id='%s' label='%s'",
             ssid.c_str(), home_id.c_str(), label.c_str());

    ProvisionSettings s{};
    std::strncpy(s.home_id, home_id.c_str(), sizeof(s.home_id) - 1);
    std::strncpy(s.device_label, label.c_str(), sizeof(s.device_label) - 1);
    this->pref_.save(&s);
    global_preferences->sync();

    this->home_id_ = home_id;
    this->device_label_ = label;

    // Defer wifi save so NVS writes happen on the main loop thread.
    this->defer([ssid, psk]() {
      wifi::global_wifi_component->save_wifi_sta(ssid.c_str(), psk.c_str());
    });

    req->send(200, "text/html",
              "<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
              "<h2>Saved</h2><p>Device is rebooting and connecting to WiFi.</p>"
              "<p>You can close this page.</p></body></html>");
  }

  void serve_form_(AsyncWebServerRequest *req) {
    std::string html;
    html.reserve(2048);
    html += "<!DOCTYPE html><html><head>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Provision ";
    html += App.get_name();
    html += "</title><style>"
            "body{font-family:-apple-system,system-ui,sans-serif;max-width:440px;margin:12px auto;padding:0 14px;color:#222}"
            "h2{margin-bottom:2px}"
            ".mac{color:#666;font-size:12px;margin-bottom:16px}"
            "label{display:block;font-weight:600;font-size:14px;margin-top:12px}"
            "input{width:100%;padding:10px;margin:4px 0 2px;box-sizing:border-box;font-size:16px;"
            "border:1px solid #bbb;border-radius:4px}"
            ".hint{color:#666;font-size:12px;margin-top:2px}"
            "button{width:100%;padding:14px;margin-top:22px;background:#1976d2;color:#fff;border:0;"
            "font-size:16px;border-radius:4px;font-weight:600}"
            "</style></head><body>";
    html += "<h2>" + App.get_name() + "</h2>";
    html += "<div class=mac>MAC " + get_mac_address_pretty() + "</div>";
    html += "<form method=POST action=/save>"
            "<label>WiFi SSID</label>"
            "<input name=ssid required placeholder='Home WiFi name'>"
            "<label>WiFi password</label>"
            "<input name=psk type=password placeholder='WiFi password'>"
            "<label>Home ID</label>"
            "<input name=home_id required placeholder='e.g. home-001' value='";
    html += this->home_id_;
    html += "'><div class=hint>Same value for every device in this home.</div>"
            "<label>Device name</label>"
            "<input name=label required placeholder='e.g. Kitchen Sensor' value='";
    html += this->device_label_;
    html += "'><div class=hint>Friendly name shown in the fleet console.</div>"
            "<button type=submit>Save and connect</button>"
            "</form></body></html>";
    req->send(200, "text/html", html.c_str());
  }

  web_server_base::WebServerBase *base_;
  ESPPreferenceObject pref_;
  std::string home_id_;
  std::string device_label_;
};

}  // namespace provision_portal
}  // namespace esphome
