"""Probe /record/multi-get parameter encoding with a few known record ids."""

import requests

BASE = "https://api.phira.cn"
IDS = [116635776, 113915225, 99057577]

variants = [
    ("repeat", [("ids", str(i)) for i in IDS]),
    ("comma", [("ids", ",".join(map(str, IDS)))]),
    ("single", [("ids", str(IDS[0]))]),
    ("single_list", [("ids", [str(IDS[0])])]),
]

for name, params in variants:
    try:
        r = requests.get(f"{BASE}/record/multi-get", params=params, timeout=30)
        print(f"{name:12s} -> {r.status_code}  {r.text[:160]}")
    except Exception as exc:  # noqa: BLE001
        print(f"{name:12s} -> ERR {type(exc).__name__}")
