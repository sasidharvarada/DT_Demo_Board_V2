import requests

url = "http://10.2.130.18:8100/data"

payload = {
    "cmd": [1,1,1,1,0,1,[255,255,255],0]
}

requests.post(url, json=payload)
print("test")
