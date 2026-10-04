"""
CEEW smart-meter data: about 100 households in Mathura and Bareilly (Uttar
Pradesh), one reading every 3 minutes, May 2019 to early 2021.

Agrawal, Mani, Jain and Ganesan (2021), "High frequency smart meter data from
two districts in India (Mathura and Bareilly)", Harvard Dataverse,
doi:10.7910/DVN/GOCHJH, CC0 1.0.

``python -m aethergrid.realdata.ceew --out data/ceew`` downloads the original
CSV files through the Dataverse access API.
"""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

DATAVERSE = "https://dataverse.harvard.edu/api/access/datafile/{id}?format=original"
FILES = {
    5425325: "CEEW - Smart meter data Bareilly 2019.csv",
    5425310: "CEEW - Smart meter data Bareilly 2020.csv",
    5425314: "CEEW - Smart meter data Bareilly 2021.csv",
    5425311: "CEEW - Smart meter data Mathura 2019.csv",
    5425313: "CEEW - Smart meter data Mathura 2020.csv",
    5425312: "CEEW - Smart meter data Mathura 2021.csv",
}
MIN_READINGS_PER_HOUR = 15  # of 20 three-minute readings
MIN_SUPPLY_VOLTAGE = 100.0  # below this the household had no grid supply


def download(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for file_id, name in FILES.items():
        dest = out / name
        if not dest.exists():
            print(f"downloading {name}")
            urllib.request.urlretrieve(DATAVERSE.format(id=file_id), dest)


def load_hourly(data_dir: Path) -> pd.DataFrame:
    """Hourly kWh per meter, with the share of 3-minute readings that had grid supply."""
    frames = []
    for name in FILES.values():
        raw = pd.read_csv(
            Path(data_dir) / name,
            usecols=["x_Timestamp", "t_kWh", "z_Avg Voltage (Volt)", "meter"],
        )
        raw["x_Timestamp"] = pd.to_datetime(raw["x_Timestamp"], errors="coerce", format="mixed")
        raw["t_kWh"] = pd.to_numeric(raw["t_kWh"], errors="coerce")
        raw["z_Avg Voltage (Volt)"] = pd.to_numeric(raw["z_Avg Voltage (Volt)"], errors="coerce")
        raw = raw.dropna(subset=["x_Timestamp", "t_kWh", "meter"])
        raw["hour"] = raw["x_Timestamp"].dt.floor("h")
        raw["supplied"] = raw["z_Avg Voltage (Volt)"] >= MIN_SUPPLY_VOLTAGE
        hourly = raw.groupby(["meter", "hour"]).agg(
            kwh=("t_kWh", "sum"), readings=("t_kWh", "size"), supplied=("supplied", "sum")
        )
        frames.append(hourly.reset_index())
    df = pd.concat(frames, ignore_index=True)
    df = df.groupby(["meter", "hour"], as_index=False).sum()  # meters that span two yearly files
    df["city"] = np.where(df["meter"].str.startswith("BR"), "Bareilly", "Mathura")
    df["complete"] = df["readings"] >= MIN_READINGS_PER_HOUR
    df["outage"] = df["complete"] & (df["supplied"] < df["readings"] * 0.5)
    return df.sort_values(["meter", "hour"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the CEEW smart-meter files")
    parser.add_argument("--out", type=Path, default=Path("data/ceew"))
    download(parser.parse_args().out)


if __name__ == "__main__":
    main()
