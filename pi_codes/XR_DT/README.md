# XR Home Automation — Mock HA Server

## Setup

```bash
pip install -r requirements.txt
python server.py
```

Server starts on `http://0.0.0.0:8123`

---

## 1. Set your token

In `server.py`, change:
```python
VALID_TOKEN = "YOUR_TOKEN_HERE"
```
Then update the same token in your Unity scripts (`access_token` field in FanController, LightController, DeviceController).

Point each Unity script's `home_assistant_url` to `<your-pc-ip>:8123`.

---

## 2. Create Entity IDs

Before the XR app can control a device it must be registered:

```bash
curl -X POST http://localhost:8123/api/entities \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"switch.fan_living_room","friendly_name":"Living Room Fan","device_type":"fan","initial_state":"off"}'
```

**device_type** values: `fan` | `lamp` | `tubelight`

### Other entity endpoints
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/entities` | List all entity IDs |
| POST | `/api/entities` | Create entity (body above) |
| DELETE | `/api/entities/{entity_id}` | Remove entity |

---

## 3. API endpoints (used automatically by Unity scripts)

| Method | URL | Used by |
|--------|-----|---------|
| GET | `/api/states/{entity_id}` | All controllers (initial state fetch) |
| POST | `/api/services/switch/turn_on` | ChangeState() |
| POST | `/api/services/switch/turn_off` | ChangeState() |
| WS | `/api/websocket` | Real-time state_changed events |

---

## 4. View logs

All actions are written to `device_log.txt` in the same folder.

```bash
# Tail live
tail -f device_log.txt

# Or via API (last 200 lines)
curl http://localhost:8123/api/logs?lines=200 \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 5. Swagger UI

Visit `http://localhost:8123/docs` to explore and test all endpoints interactively.
