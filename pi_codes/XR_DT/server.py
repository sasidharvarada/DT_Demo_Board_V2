"""
XR Home Automation Server
- Accepts HA-format REST + WebSocket from Meta Quest XR
- Translates entity state changes → ESP32 cmd array at POST /data
- All config read from .env
"""

import json, logging, asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Annotated
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
import os

from fastapi import (FastAPI, WebSocket, WebSocketDisconnect,
                     HTTPException, Request, Depends, Security)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

# ══════════════════════════════════════════════════════════════
#  ENV
# ══════════════════════════════════════════════════════════════
load_dotenv()

PORT        = int(os.getenv("HA_PORT",    "8123"))
VALID_TOKEN =     os.getenv("HA_TOKEN",   "change-me")
ESP32_IP    =     os.getenv("ESP32_IP",   "10.2.135.210")
ESP32_PORT  = int(os.getenv("ESP32_PORT", "8100"))
ESP32_URL   = f"http://{ESP32_IP}:{ESP32_PORT}/data"

# ══════════════════════════════════════════════════════════════
#  ANSI colours
# ══════════════════════════════════════════════════════════════
R   = "\033[0m";  B   = "\033[1m";  DIM = "\033[2m"
CY  = "\033[96m"; GR  = "\033[92m"; YE  = "\033[93m"
RE  = "\033[91m"; MA  = "\033[95m"; BL  = "\033[94m"
WH  = "\033[97m"; OR  = "\033[33m"

def _now(): return datetime.now().strftime("%H:%M:%S")
def _line(colour, icon, label, detail=""):
    print(f"  {DIM}{_now()}{R}  {colour}{B}{icon} {label}{R}"
          + (f"  {DIM}{detail}{R}" if detail else ""), flush=True)

# ══════════════════════════════════════════════════════════════
#  FILE LOG
# ══════════════════════════════════════════════════════════════
LOG_FILE = Path("device_log.txt")
_flog = logging.getLogger("xr_file")
_flog.setLevel(logging.DEBUG)
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
_flog.addHandler(_fh)
_flog.propagate = False
def flog(level, msg): getattr(_flog, level)(msg)

# ══════════════════════════════════════════════════════════════
#  ESP32 CMD BUILDER
#  cmd = [strip1, strip2, strip3, strip4, buzzer, tube, [R,G,B], fan_speed]
# ══════════════════════════════════════════════════════════════
DEFAULT_CMD = [0, 0, 0, 0, 0, 0, [0, 0, 0], 0]

# Entity ID → function that returns a cmd array given (current_state_dict, new_state "on"/"off")
# Each builder reads the current full state so we never clobber other devices
def _cmd(state: dict) -> list:
    """Build cmd array from full entity state dict."""
    return [
        state.get("strip1", 0),
        state.get("strip2", 0),
        state.get("strip3", 0),
        state.get("strip4", 0),
        state.get("buzzer", 0),
        state.get("tube",   0),
        state.get("rgb",    [255, 255, 255]),
        state.get("fan_speed", 0),
    ]

# ══════════════════════════════════════════════════════════════
#  DEFAULT ENTITIES  (pre-seeded at startup)
#  entity_id → {
#      state: "on"/"off",
#      friendly_name: str,
#      device_type: str,
#      esp_key: str,          ← which key in board_state to flip
#      on_value: int/list,    ← value when "on"
#      off_value: int/list,   ← value when "off"
#  }
# ══════════════════════════════════════════════════════════════
DEFAULT_ENTITIES = {
    "switch.fan":     {"friendly_name": "Fan",       "device_type": "fan",
                       "esp_key": "fan_speed", "on_value": 255,         "off_value": 0},
    "switch.tube":    {"friendly_name": "Tube Light", "device_type": "tubelight",
                       "esp_key": "tube",      "on_value": 1,           "off_value": 0},
    "switch.buzzer":  {"friendly_name": "Buzzer",     "device_type": "buzzer",
                       "esp_key": "buzzer",    "on_value": 1,           "off_value": 0},
    "switch.strip1":  {"friendly_name": "LED Strip 1","device_type": "lamp",
                       "esp_key": "strip1",    "on_value": 1,           "off_value": 0},
    "switch.strip2":  {"friendly_name": "LED Strip 2","device_type": "lamp",
                       "esp_key": "strip2",    "on_value": 1,           "off_value": 0},
    "switch.strip3":  {"friendly_name": "LED Strip 3","device_type": "lamp",
                       "esp_key": "strip3",    "on_value": 1,           "off_value": 0},
    "switch.strip4":  {"friendly_name": "LED Strip 4","device_type": "lamp",
                       "esp_key": "strip4",    "on_value": 1,           "off_value": 0},
    # RGB colour presets — toggling sets rgb; tube must already be on
    "switch.rgb_white": {"friendly_name": "RGB White", "device_type": "lamp",
                         "esp_key": "rgb",     "on_value": [255,255,255],"off_value": [0,0,0]},
    "switch.rgb_red":   {"friendly_name": "RGB Red",   "device_type": "lamp",
                         "esp_key": "rgb",     "on_value": [255,0,0],    "off_value": [0,0,0]},
    "switch.rgb_green": {"friendly_name": "RGB Green", "device_type": "lamp",
                         "esp_key": "rgb",     "on_value": [0,255,0],    "off_value": [0,0,0]},
    "switch.rgb_blue":  {"friendly_name": "RGB Blue",  "device_type": "lamp",
                         "esp_key": "rgb",     "on_value": [0,0,255],    "off_value": [0,0,0]},
}

# ── in-memory store ───────────────────────────────────────────
# entities[entity_id] = merged dict with "state" + all DEFAULT_ENTITIES fields
entities: dict[str, dict] = {}

# board_state mirrors what we last sent to ESP32
# keys: strip1,strip2,strip3,strip4,buzzer,tube,rgb,fan_speed
board_state: dict = {
    "strip1": 0, "strip2": 0, "strip3": 0, "strip4": 0,
    "buzzer": 0, "tube": 0, "rgb": [0,0,0], "fan_speed": 0,
}

subscribers: list[WebSocket] = []

# ══════════════════════════════════════════════════════════════
#  ESP32 FORWARD
# ══════════════════════════════════════════════════════════════
async def send_to_esp32(entity_id: str, new_state: str):
    """Update board_state for the entity and POST full cmd to ESP32."""
    meta = entities.get(entity_id)
    if not meta or "esp_key" not in meta:
        return  # custom entity without ESP mapping — skip

    key = meta["esp_key"]
    board_state[key] = meta["on_value"] if new_state == "on" else meta["off_value"]

    cmd = _cmd(board_state)
    payload = {"cmd": cmd}

    _line(OR, "→", f"ESP32  POST {ESP32_URL}", f"cmd={cmd}")
    flog("info", f"ESP32 CMD  entity={entity_id}  key={key}  cmd={cmd}")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(ESP32_URL, json=payload)
            _line(GR if resp.status_code < 300 else RE,
                  "✓" if resp.status_code < 300 else "✗",
                  f"ESP32  {resp.status_code}", resp.text[:80])
            flog("info", f"ESP32 RESP  {resp.status_code}  {resp.text[:80]}")
    except Exception as e:
        _line(RE, "✗", f"ESP32 ERROR", str(e))
        flog("error", f"ESP32 ERROR  {e}")

# ══════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════
bearer_scheme = HTTPBearer(auto_error=False)

def verify_token(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials],
                            Security(bearer_scheme)] = None):
    if credentials is None:
        raise HTTPException(401, "Missing Authorization header")
    if credentials.credentials != VALID_TOKEN:
        raise HTTPException(403, "Invalid token")
    return credentials.credentials

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def entity_response(eid: str) -> dict:
    e = entities[eid]
    return {
        "entity_id": eid,
        "state": e["state"],
        "attributes": {
            "friendly_name": e.get("friendly_name", eid),
            "device_type":   e.get("device_type", "unknown"),
        },
        "last_changed": datetime.utcnow().isoformat(),
        "last_updated": datetime.utcnow().isoformat(),
    }

async def broadcast(eid: str, old: str, new: str):
    msg = json.dumps({
        "type": "event",
        "event": {
            "event_type": "state_changed",
            "data": {
                "entity_id": eid,
                "old_state": {"state": old, "entity_id": eid},
                "new_state": {"state": new, "entity_id": eid},
            },
        },
    })
    dead = []
    for ws in subscribers:
        try:    await ws.send_text(msg)
        except: dead.append(ws)
    for ws in dead: subscribers.remove(ws)
    if subscribers:
        _line(MA, "⇢", f"BROADCAST  {eid}", f"{old}→{new}  ({len(subscribers)} sub)")

# ══════════════════════════════════════════════════════════════
#  LIFESPAN — seed default entities
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app):
    # seed entities
    for eid, meta in DEFAULT_ENTITIES.items():
        entities[eid] = {**meta, "state": "off"}

    w = 58
    print(f"\n{BL}{'═'*w}{R}")
    print(f"{BL}  XR HOME AUTOMATION SERVER{R}   {DIM}http://0.0.0.0:{PORT}{R}")
    print(f"{BL}{'═'*w}{R}\n")
    _line(WH, "i", "Swagger UI",   f"http://localhost:{PORT}/docs")
    _line(WH, "i", "Token tail",   f"...{VALID_TOKEN[-20:]}")
    _line(WH, "i", "ESP32 target", f"{ESP32_URL}")
    _line(WH, "i", "Log file",     str(LOG_FILE.resolve()))
    print()
    _line(GR, "✓", "Default entities seeded:")
    for eid in DEFAULT_ENTITIES:
        _line(DIM, " ", eid)
    print()
    yield

# ══════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════
app = FastAPI(title="XR Home Automation Server",
              version="2.0.0", lifespan=lifespan)

# ── middleware: log + detect token mismatch early ─────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    path   = request.url.path
    client = request.client.host if request.client else "?"
    token_hdr = request.headers.get("authorization", "")
    if token_hdr:
        token_val = token_hdr.removeprefix("Bearer ").strip()
        if token_val != VALID_TOKEN and path.startswith("/api/"):
            _line(RE, "✗", f"{request.method} {path}",
                  f"[{client}]  403 — sent: ...{token_val[-20:]}"
                  f"  expected: ...{VALID_TOKEN[-20:]}")
            flog("warning",
                 f"403 TOKEN MISMATCH  {request.method} {path}"
                 f"  client={client}  got=...{token_val[-20:]}")
    return await call_next(request)

# ══════════════════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════════════════
class EntityCreate(BaseModel):
    entity_id:     str
    friendly_name: str
    device_type:   str
    initial_state: str = "off"

class ServicePayload(BaseModel):
    entity_id: str

# ══════════════════════════════════════════════════════════════
#  REST — HA API  (XR sends these)
# ══════════════════════════════════════════════════════════════

@app.get("/api/states/{entity_id}")
async def get_state(entity_id: str, request: Request,
                    token: str = Depends(verify_token)):
    client = request.client.host if request.client else "?"
    if entity_id not in entities:
        _line(RE, "✗", f"GET STATE  {entity_id}", f"[{client}]  404")
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    s = entities[entity_id]["state"]
    _line(CY, "↓", f"GET STATE  {entity_id}", f"[{client}]  → {B}{s}{R}")
    flog("info", f"GET STATE  {entity_id}={s}  client={client}")
    return JSONResponse(entity_response(entity_id))


@app.post("/api/services/switch/{action}")
async def service_call(action: str, payload: ServicePayload,
                       request: Request, token: str = Depends(verify_token)):
    client    = request.client.host if request.client else "?"
    entity_id = payload.entity_id

    if action not in ("turn_on", "turn_off"):
        raise HTTPException(400, f"Unknown action '{action}'")
    if entity_id not in entities:
        _line(RE, "✗", f"switch/{action}  {entity_id}", f"[{client}]  404")
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    old = entities[entity_id]["state"]
    new = "on" if action == "turn_on" else "off"
    entities[entity_id]["state"] = new

    colour = GR if new == "on" else YE
    icon   = "▶" if new == "on" else "■"
    label  = "TURN ON " if new == "on" else "TURN OFF"
    _line(colour, icon, f"{label}  {entity_id}", f"[{client}]  {old}→{B}{new}{R}")
    flog("info", f"{action.upper()}  {entity_id}  {old}->{new}  client={client}")

    # Forward to ESP32
    await send_to_esp32(entity_id, new)
    # Notify WS subscribers
    await broadcast(entity_id, old, new)

    return JSONResponse([entity_response(entity_id)])


# ══════════════════════════════════════════════════════════════
#  ENTITY MANAGEMENT
# ══════════════════════════════════════════════════════════════

@app.get("/api/entities")
async def list_entities(token: str = Depends(verify_token)):
    rows = [{"entity_id": eid,
             "state": entities[eid]["state"],
             "friendly_name": entities[eid].get("friendly_name",""),
             "device_type": entities[eid].get("device_type","")}
            for eid in entities]
    _line(WH, "≡", "LIST ENTITIES", f"{len(entities)} total")
    return JSONResponse(rows)


@app.post("/api/entities")
async def create_entity(data: EntityCreate,
                        token: str = Depends(verify_token)):
    if data.entity_id in entities:
        raise HTTPException(409, f"'{data.entity_id}' already exists")
    entities[data.entity_id] = {
        "state":         data.initial_state,
        "friendly_name": data.friendly_name,
        "device_type":   data.device_type,
    }
    _line(GR, "+", f"ENTITY CREATED  {data.entity_id}",
          f"type={data.device_type}  state={data.initial_state}")
    flog("info",
         f"CREATED  {data.entity_id}  type={data.device_type}")
    return JSONResponse({"message": "Entity created",
                         "entity_id": data.entity_id})


@app.delete("/api/entities/{entity_id}")
async def delete_entity(entity_id: str,
                        token: str = Depends(verify_token)):
    if entity_id not in entities:
        raise HTTPException(404, f"'{entity_id}' not found")
    del entities[entity_id]
    _line(YE, "−", f"ENTITY DELETED  {entity_id}")
    flog("info", f"DELETED  {entity_id}")
    return JSONResponse({"message": "Entity deleted"})


@app.get("/api/logs")
async def get_logs(lines: int = 100,
                   token: str = Depends(verify_token)):
    if not LOG_FILE.exists():
        return JSONResponse([])
    all_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return JSONResponse(all_lines[-lines:])


# ══════════════════════════════════════════════════════════════
#  WEBSOCKET — HA protocol
# ══════════════════════════════════════════════════════════════

@app.websocket("/api/websocket")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = (f"{websocket.client.host}:{websocket.client.port}"
              if websocket.client else "?")
    _line(BL, "⌁", "WS CONNECT", f"[{client}]")
    flog("info", f"WS CONNECT  {client}")
    authenticated = False

    try:
        await websocket.send_text(json.dumps(
            {"type": "auth_required", "ha_version": "2024.1.0"}))

        while True:
            raw      = await websocket.receive_text()
            msg      = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "auth":
                token = msg.get("access_token", "")
                if token == VALID_TOKEN:
                    authenticated = True
                    await websocket.send_text(json.dumps(
                        {"type": "auth_ok", "ha_version": "2024.1.0"}))
                    _line(GR, "✓", "WS AUTH OK", f"[{client}]")
                    flog("info", f"WS AUTH OK  {client}")
                else:
                    await websocket.send_text(json.dumps(
                        {"type": "auth_invalid", "message": "Invalid token"}))
                    _line(RE, "✗", "WS AUTH FAIL",
                          f"[{client}]  sent: ...{token[-20:]}")
                    flog("warning",
                         f"WS AUTH FAIL  {client}  token=...{token[-20:]}")
                    await websocket.close()
                    return

            elif msg_type == "subscribe_events" and authenticated:
                msg_id = msg.get("id", 1)
                if msg.get("event_type") == "state_changed":
                    if websocket not in subscribers:
                        subscribers.append(websocket)
                    await websocket.send_text(json.dumps(
                        {"id": msg_id, "type": "result",
                         "success": True, "result": None}))
                    _line(BL, "⊕", "WS SUBSCRIBED",
                          f"[{client}]  total={len(subscribers)}")
                    flog("info",
                         f"WS SUBSCRIBED  {client}  total={len(subscribers)}")

            elif not authenticated:
                await websocket.send_text(json.dumps(
                    {"type": "auth_required", "ha_version": "2024.1.0"}))

    except WebSocketDisconnect:
        _line(BL, "⌁", "WS DISCONNECT", f"[{client}]")
        flog("info", f"WS DISCONNECT  {client}")
    except json.JSONDecodeError:
        _line(RE, "✗", "WS BAD JSON", f"[{client}]")
    except Exception as e:
        _line(RE, "✗", f"WS ERROR  {e}", f"[{client}]")
        flog("error", f"WS ERROR  {client}  {e}")
    finally:
        if websocket in subscribers:
            subscribers.remove(websocket)


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT,
                reload=False, log_level="warning")