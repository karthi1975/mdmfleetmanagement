#pragma once
#ifdef USE_ESP32

#include "esphome/core/helpers.h"
#include "esphome/components/network/ip_address.h"
#include "esphome/components/socket/socket.h"

namespace esphome {
namespace provision_portal {

// Minimal UDP DNS server — points every A query at our AP IP so phones
// hit our HTTP server for their OS captive-portal probe and auto-pop the
// sign-in browser. Ported from esphome/components/captive_portal.
class DNSServer {
 public:
  void start(const network::IPAddress &ip);
  void stop();
  void process_next_request();

 protected:
  inline void destroy_socket_() {
    delete this->socket_;
    this->socket_ = nullptr;
  }
  static constexpr size_t DNS_BUFFER_SIZE = 192;

  socket::ListenSocket *socket_{nullptr};
  network::IPAddress server_ip_;
  uint8_t buffer_[DNS_BUFFER_SIZE];
};

}  // namespace provision_portal
}  // namespace esphome

#endif  // USE_ESP32
