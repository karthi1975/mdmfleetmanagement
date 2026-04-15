#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "esphome/components/mqtt/mqtt_client.h"

#include "esp_ota_ops.h"
#include "esp_partition.h"

#include <cstring>
#include <string>
#include "lwip/sockets.h"
#include "lwip/netdb.h"

namespace esphome {
namespace mqtt_ota {

static const char *const TAG = "mqtt_ota";

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
    // Find "key": or "key" : (handles optional whitespace after colon)
    std::string search = "\"" + key + "\"";
    size_t key_pos = json.find(search);
    if (key_pos == std::string::npos) return "";
    size_t colon_pos = json.find(":", key_pos + search.length());
    if (colon_pos == std::string::npos) return "";
    // Skip whitespace after colon
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

  // Parse URL into host, port, path
  struct UrlParts {
    std::string host;
    int port;
    std::string path;
  };

  static bool parse_url_(const std::string &url, UrlParts &parts) {
    // http://host:port/path
    if (url.substr(0, 7) != "http://") return false;
    std::string rest = url.substr(7);
    size_t slash = rest.find('/');
    std::string host_port = (slash != std::string::npos) ? rest.substr(0, slash) : rest;
    parts.path = (slash != std::string::npos) ? rest.substr(slash) : "/";

    size_t colon = host_port.find(':');
    if (colon != std::string::npos) {
      parts.host = host_port.substr(0, colon);
      parts.port = atoi(host_port.substr(colon + 1).c_str());
    } else {
      parts.host = host_port;
      parts.port = 80;
    }
    return !parts.host.empty();
  }

  void handle_ota_command_(const std::string &payload) {
    ESP_LOGI(TAG, "OTA command: %s", payload.c_str());

    std::string version = extract_json_(payload, "version");
    std::string url = extract_json_(payload, "url");
    if (url.empty()) {
      ESP_LOGE(TAG, "No URL in OTA command");
      return;
    }

    UrlParts parts;
    if (!parse_url_(url, parts)) {
      ESP_LOGE(TAG, "Invalid URL: %s", url.c_str());
      return;
    }

    ESP_LOGI(TAG, "OTA: version=%s host=%s port=%d path=%s",
             version.c_str(), parts.host.c_str(), parts.port, parts.path.c_str());
    publish_status_("downloading", version);

    // Resolve host
    struct addrinfo hints = {}, *res = nullptr;
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    char port_str[8];
    snprintf(port_str, sizeof(port_str), "%d", parts.port);

    if (getaddrinfo(parts.host.c_str(), port_str, &hints, &res) != 0 || !res) {
      ESP_LOGE(TAG, "DNS resolve failed for %s", parts.host.c_str());
      publish_status_("failed", version);
      return;
    }

    int sock = lwip_socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0 || lwip_connect(sock, res->ai_addr, res->ai_addrlen) != 0) {
      ESP_LOGE(TAG, "Connection failed");
      freeaddrinfo(res);
      if (sock >= 0) lwip_close(sock);
      publish_status_("failed", version);
      return;
    }
    freeaddrinfo(res);

    // Recv timeout: fail loudly instead of hanging if the stream stalls.
    struct timeval tv = {};
    tv.tv_sec = 15;
    lwip_setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    // Send HTTP GET request — Connection: close so server FINs after body.
    char request[512];
    snprintf(request, sizeof(request),
             "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n",
             parts.path.c_str(), parts.host.c_str());
    lwip_send(sock, request, strlen(request), 0);

    // Read HTTP response header
    char header_buf[1024];
    int header_len = 0;
    bool header_done = false;
    int content_length = -1;

    while (!header_done && header_len < (int)sizeof(header_buf) - 1) {
      int n = lwip_recv(sock, header_buf + header_len, 1, 0);
      if (n <= 0) break;
      header_len += n;
      header_buf[header_len] = 0;
      if (header_len >= 4 && strcmp(header_buf + header_len - 4, "\r\n\r\n") == 0) {
        header_done = true;
      }
    }

    if (!header_done) {
      ESP_LOGE(TAG, "Failed to read HTTP header");
      lwip_close(sock);
      publish_status_("failed", version);
      return;
    }

    // Check HTTP 200
    if (strstr(header_buf, "200") == nullptr) {
      ESP_LOGE(TAG, "HTTP error: %.*s", 32, header_buf);
      lwip_close(sock);
      publish_status_("failed", version);
      return;
    }

    // Extract content length
    char *cl = strcasestr(header_buf, "content-length:");
    if (cl) {
      content_length = atoi(cl + 15);
    }
    ESP_LOGI(TAG, "Firmware size: %d bytes", content_length);

    // Begin OTA flash
    publish_status_("flashing", version);

    const esp_partition_t *update_partition = esp_ota_get_next_update_partition(nullptr);
    if (!update_partition) {
      ESP_LOGE(TAG, "No OTA partition found");
      lwip_close(sock);
      publish_status_("failed", version);
      return;
    }

    esp_ota_handle_t ota_handle;
    esp_err_t err = esp_ota_begin(update_partition, content_length > 0 ? content_length : OTA_SIZE_UNKNOWN, &ota_handle);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "OTA begin failed: %s", esp_err_to_name(err));
      lwip_close(sock);
      publish_status_("failed", version);
      return;
    }

    // Stream firmware data to OTA partition
    uint8_t buf[1024];
    int total = 0;
    while (content_length < 0 || total < content_length) {
      int n = lwip_recv(sock, buf, sizeof(buf), 0);
      if (n < 0) {
        ESP_LOGE(TAG, "recv failed/timeout after %d bytes", total);
        esp_ota_abort(ota_handle);
        lwip_close(sock);
        publish_status_("failed", version);
        return;
      }
      if (n == 0) break;  // FIN
      err = esp_ota_write(ota_handle, buf, n);
      if (err != ESP_OK) {
        ESP_LOGE(TAG, "OTA write failed: %s", esp_err_to_name(err));
        esp_ota_abort(ota_handle);
        lwip_close(sock);
        publish_status_("failed", version);
        return;
      }
      total += n;
    }
    lwip_close(sock);

    if (content_length > 0 && total != content_length) {
      ESP_LOGE(TAG, "Short read: %d/%d", total, content_length);
      esp_ota_abort(ota_handle);
      publish_status_("failed", version);
      return;
    }

    ESP_LOGI(TAG, "Wrote %d bytes", total);

    err = esp_ota_end(ota_handle);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "OTA end failed: %s", esp_err_to_name(err));
      publish_status_("failed", version);
      return;
    }

    err = esp_ota_set_boot_partition(update_partition);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Set boot partition failed: %s", esp_err_to_name(err));
      publish_status_("failed", version);
      return;
    }

    ESP_LOGI(TAG, "OTA success! Rebooting...");
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
