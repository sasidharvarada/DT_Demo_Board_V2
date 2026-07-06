# ESP32 Device Control Scripts

## Payload Format

The ESP32 expects a JSON payload in the following format:

```json
{
  "cmd": [
    strip1,
    strip2,
    strip3,
    strip4,
    buzzer,
    tube,
    [R, G, B],
    fan_speed
  ]
}
```

| Index | Device     | Values  |
| ----- | ---------- | ------- |
| 0     | Strip 1    | 0/1     |
| 1     | Strip 2    | 0/1     |
| 2     | Strip 3    | 0/1     |
| 3     | Strip 4    | 0/1     |
| 4     | Buzzer     | 0/1     |
| 5     | Tube Light | 0/1     |
| 6     | RGB Color  | [R,G,B] |
| 7     | Fan Speed  | 0-255   |

---

## Common Configuration

```python
import requests

ESP_IP = "Esp_IP"
PORT = 8100

url = f"http://{ESP_IP}:{PORT}/data"
```

---

# Fan Control

## Fan ON

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,0,[255,255,255],255]
}

requests.post(url, json=payload)
print("Fan ON")
```

## Fan OFF

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Fan OFF")
```

---

# Buzzer Control

## Buzzer ON

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,1,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Buzzer ON")
```

## Buzzer OFF

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Buzzer OFF")
```

---

# Tube Light Control

## Tube Light ON (White)

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,1,[255,255,255],0]
}

requests.post(url, json=payload)
print("Tube Light ON")
```

## Tube Light OFF

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,0,[0,0,0],0]
}

requests.post(url, json=payload)
print("Tube Light OFF")
```

## Tube Light RED

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,1,[255,0,0],0]
}

requests.post(url, json=payload)
print("Tube RED")
```

## Tube Light GREEN

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,1,[0,255,0],0]
}

requests.post(url, json=payload)
print("Tube GREEN")
```

## Tube Light BLUE

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,1,[0,0,255],0]
}

requests.post(url, json=payload)
print("Tube BLUE")
```

---

# LED Strip Control

## Trigger Strip 1

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [1,0,0,0,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Strip 1 Triggered")
```

## Trigger Strip 2

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,1,0,0,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Strip 2 Triggered")
```

## Trigger Strip 3

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,1,0,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Strip 3 Triggered")
```

## Trigger Strip 4

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,1,0,0,[255,255,255],0]
}

requests.post(url, json=payload)
print("Strip 4 Triggered")
```

---

# Global Controls

## Turn Everything ON

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [1,1,1,1,1,1,[255,255,255],255]
}

requests.post(url, json=payload)
print("All Devices ON")
```

## Turn Everything OFF

```python
import requests

url = "http://Esp_IP:8100/data"

payload = {
    "cmd": [0,0,0,0,0,0,[0,0,0],0]
}

requests.post(url, json=payload)
print("All Devices OFF")
```
