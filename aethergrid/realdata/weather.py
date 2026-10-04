"""
Hourly observed weather from the Open-Meteo historical archive
(https://open-meteo.com/en/docs/historical-weather-api, ERA5-based reanalysis,
CC BY 4.0; no API key).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
CITIES = {"Mathura": (27.4924, 77.6737), "Bareilly": (28.3670, 79.4304)}
VARIABLES = ["temperature_2m", "relative_humidity_2m", "shortwave_radiation"]


def fetch_city(city: str, start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    cache = Path(cache_dir) / f"open_meteo_{city}_{start}_{end}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        lat, lon = CITIES[city]
        query = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
            "hourly": ",".join(VARIABLES), "timezone": "Asia/Kolkata",
        })
        with urllib.request.urlopen(f"{ARCHIVE}?{query}", timeout=120) as resp:
            payload = json.loads(resp.read())
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    hourly = payload["hourly"]
    df = pd.DataFrame({"hour": pd.to_datetime(hourly["time"]), **{v: hourly[v] for v in VARIABLES}})
    df["city"] = city
    return df


def load_weather(start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    return pd.concat([fetch_city(c, start, end, cache_dir) for c in CITIES], ignore_index=True)
