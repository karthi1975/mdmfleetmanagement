                                                                                                                                 
  ✅ Done so far                                                                                                                        
                                              
  ┌─────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬────────┐  
  │  #  │                                                     Milestone                                                     │ Status │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 1   │ DigitalOcean droplet provisioned (fleetmanagement, 146.190.152.168, Ubuntu 24.04)                                 │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 2   │ Basic hardening: non-root deploy user with sudo + SSH key, system nginx disabled, UFW active                      │ ✓      │
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤
  │ 3   │ Docker + docker-compose-v2 installed; deploy in docker group                                                      │ ✓      │
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 4   │ Private GitHub repo karthi1975/mdmfleetmanagement created; code pushed (.claude/, .env, .playwright-mcp/ ignored) │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 5   │ Droplet cloned repo via read-only GitHub deploy key (~/.ssh/github_mdm)                                           │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤
  │ 6   │ Full stack up via docker compose: postgres, mosquitto, nginx, fleet-api (FastAPI), esphome, grafana, loki,        │ ✓      │  
  │     │ rsyslog                                                                                                           │        │
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 7   │ Firmware HTTP serving at http://146.190.152.168/firmware/…/firmware.bin (200 OK)                                  │ ✓      │
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 8   │ MQTT reachable from public internet (droplet :1883)                                                               │ ✓      │
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤  
  │ 9   │ ESP32 flashed via USB on Mac, joined home WiFi (Bahubali), registered to droplet MQTT                             │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤
  │ 10  │ Root-caused mqtt_ota task-WDT reset bug (no WDT feeds during download → silent rollback)                          │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤
  │ 11  │ Patched mqtt_ota.h with WDT feeds + MQTT keepalive pumping + progress logs; committed and pushed                  │ ✓      │  
  ├─────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────┤
  │ 12  │ Validated end-to-end remote OTA: Mac → public MQTT → droplet HTTP firmware → home-WiFi ESP32 flash → reboot →     │ ✓      │  
  │     │ re-register with new version                                                                                      │        │
  └─────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴────────┘  
                                                                                                                                      
  ---                                                                                                                                   
  🔒 Next: harden for mdmfleetmanagment.homeadapt.us                                                                                   
                                                                                                                                        
  ⚠️  Current state has three serious exposures: MQTT 1883 anonymous, fleet-api on 8000 with no auth/TLS, firmware served over plain   
  HTTP. Fix in this order.                    
                                                                                                                                        
  1. DNS
                                                                                                                                        
  At your DNS provider for homeadapt.us:                                                                                               
  A   mdmfleetmanagment   146.190.152.168   TTL 300                                                                                     
  Verify:                                                                                                                             
  dig +short mdmfleetmanagment.homeadapt.us   # should return 146.190.152.168                                                            
                                                                            
  2. TLS for HTTPS and MQTTS (one cert covers both)                                                                                     
                                                                                                                                        
  On the droplet:                                                                                                                       
  sudo apt install -y certbot                                                                                                           
  # Stop docker nginx briefly so certbot can bind :80                                                                                   
  cd ~/MDM_ESP32 && docker compose stop nginx                                                                                           
  sudo certbot certonly --standalone -d mdmfleetmanagment.homeadapt.us -m karthi.jeyabalan@gmail.com --agree-tos --non-interactive       
  sudo ls /etc/letsencrypt/live/mdmfleetmanagment.homeadapt.us/                                                                        
  docker compose start nginx                                                                                                            
  Then mount /etc/letsencrypt into both nginx and mosquitto (docker-compose.yml edit + nginx.conf + mosquitto.conf updates). Also set up
   certbot renew cron.                                                                                                                  
                                                                                                                                        
  3. Lock down MQTT (port 8883 TLS + user/password)                                                                                     
                                                                                                                                        
  - Create password file: mosquitto_passwd -c /mosquitto/config/passwd fleet                                                            
  - Edit mosquitto/mosquitto.conf: allow_anonymous false, password_file /mosquitto/config/passwd, add TLS listener on 8883 with the   
  Let's Encrypt cert.                                                                                                                   
  - Update esphome/secrets.yaml: mqtt_broker: "mdmfleetmanagment.homeadapt.us", mqtt_port: 8883, add mqtt_username/mqtt_password, set    
  broker CA.                                                                                                                            
  - Close port 1883: sudo ufw delete allow 1883/tcp && sudo ufw allow 8883/tcp                                                          
                                                                                                                                      
  4. Put fleet-api behind nginx at HTTPS only                                                                                           
                                                                                                                                      
  - nginx.conf: add TLS server block on 443 proxying /api/ → http://fleet-api:8000, redirect 80 → 443.                                  
  - Close port 8000: sudo ufw delete allow 8000/tcp.                                                                                    
  - Require API auth token (fleet_server/api/auth.py already exists — wire it up).                                                      
                                                                                                                                        
  5. Flash ESP32 once over USB with the new secrets, then every future update flows via the hardened OTA pipeline.                    
                                                                                                                                        
  6. Observability + ops                                                                                                                
                                                                                                                                        
  - certbot auto-renewal hook that restarts nginx + mosquitto                                                                           
  - Grafana admin password changed from default (.env → GF_SECURITY_ADMIN_PASSWORD)                                                     
  - Postgres password rotated                                                                                                         
  - Backup pgdata volume nightly (cron → pg_dump → data/backups/)                                                                       
                                                                                                                                      
  ---                                                                                                                                   
  Want to do steps 1–2 (DNS + certbot) now?           