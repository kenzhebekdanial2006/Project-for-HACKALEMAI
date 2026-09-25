"""Текущий прогноз Open-Meteo для двух турбин; НЕ исторический backtest.

Установка: python -m pip install requests pandas tzdata
Запуск из корня: python -m backend.windops.weather.client

В storage/weather/<время_получения>/ сохраняются response.json и
wind_forecast.csv. Исходный ответ сохраняется до проверки данных.
Время получения ответа НЕ является временем выпуска погодной модели.
Документация: https://open-meteo.com/en/docs
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.paths import WEATHER_DIR

API_URL = "https://api.open-meteo.com/v1/forecast"
LOCAL_TIMEZONE = "Asia/Almaty"
HORIZON_HOURS = 48
TURBINES = {
    "WT_1": {"latitude": 43.645139, "longitude": 78.535611},
    "WT_2": {"latitude": 43.643194, "longitude": 78.538833},
}
HOURLY = [
    "temperature_2m", "relative_humidity_2m", "surface_pressure",
    "wind_speed_10m", "wind_speed_80m", "wind_speed_120m",
    "wind_direction_10m", "wind_direction_80m", "wind_direction_120m",
    "wind_gusts_10m",
]


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def parse_weather(payload: Any, expected: pd.DatetimeIndex,
                  retrieved_at: pd.Timestamp) -> pd.DataFrame:
    """Проверить обе точки; не публиковать частичный или неполный прогноз."""
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(f"Open-Meteo: {payload.get('reason', 'ошибка API')}")
    if not isinstance(payload, list) or len(payload) != len(TURBINES):
        raise ValueError("Ожидался список ответов для двух координат.")
    if expected[0] <= retrieved_at:
        raise ValueError("Во время загрузки начался целевой час. Повторите запуск.")

    frames = []
    for index, ((name, coordinates), item) in enumerate(zip(TURBINES.items(), payload)):
        if not isinstance(item, dict) or item.get("error"):
            raise ValueError(f"{name}: некорректный ответ API: {item!r}")
        if "location_id" in item and item["location_id"] != index:
            raise ValueError(f"{name}: неожиданный порядок location_id.")
        if not isinstance(item.get("hourly"), dict):
            raise ValueError(f"{name}: отсутствуют почасовые данные.")

        df = pd.DataFrame(item["hourly"])
        missing = set(["time", *HOURLY]) - set(df.columns)
        if missing:
            raise ValueError(f"{name}: отсутствуют поля {sorted(missing)}")
        df = df[["time", *HOURLY]].copy()
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True, errors="raise")
        df = df.sort_values("time").reset_index(drop=True)
        if not pd.DatetimeIndex(df["time"]).equals(expected):
            raise ValueError(f"{name}: нужны ровно 48 целевых часов без пропусков и повторов.")

        values = df[HOURLY].apply(pd.to_numeric, errors="raise")
        invalid = values.isna() | values.isin([float("inf"), float("-inf")])
        if invalid.any().any():
            bad = invalid.columns[invalid.any()].tolist()
            raise ValueError(f"{name}: пропуски или бесконечные значения в {bad}")
        df[HOURLY] = values
        units = item.get("hourly_units", {})
        for variable in HOURLY:
            if variable.startswith(("wind_speed_", "wind_gusts_")):
                if units.get(variable) != "m/s":
                    raise ValueError(f"{name}: неожиданные единицы {variable}: {units.get(variable)}")
                if (df[variable] < 0).any():
                    raise ValueError(f"{name}: отрицательная скорость ветра в {variable}")
        if units.get("temperature_2m") != "°C" or units.get("surface_pressure") != "hPa":
            raise ValueError(f"{name}: неожиданные единицы температуры или давления.")

        df.insert(0, "turbine", name)
        df.insert(1, "latitude", coordinates["latitude"])
        df.insert(2, "longitude", coordinates["longitude"])
        df["time_local"] = df["time"].dt.tz_convert(LOCAL_TIMEZONE)
        df["grid_latitude"] = item.get("latitude")
        df["grid_longitude"] = item.get("longitude")
        df["retrieved_at_utc"] = retrieved_at.isoformat()
        df["source"] = "open-meteo/forecast"
        # Автовыбор сохраняется как в исходном коде. Это НЕ имя конкретной модели.
        df["model_selection"] = "auto"
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def get_all_weather(output_dir: Path | str = WEATHER_DIR) -> tuple[pd.DataFrame, Path]:
    started_at = utc_now()
    # Явное окно: 48 часовых отметок с начала следующего часа.
    first_hour = started_at.floor("h") + pd.Timedelta(hours=1)
    expected = pd.date_range(first_hour, periods=HORIZON_HOURS, freq="h")
    params = {
        "latitude": ",".join(str(c["latitude"]) for c in TURBINES.values()),
        "longitude": ",".join(str(c["longitude"]) for c in TURBINES.values()),
        "hourly": ",".join(HOURLY),
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
        "timezone": "UTC",
        "timeformat": "unixtime",
        "start_hour": expected[0].strftime("%Y-%m-%dT%H:%M"),
        "end_hour": expected[-1].strftime("%Y-%m-%dT%H:%M"),
    }
    retry = Retry(
        total=3, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(API_URL, params=params, timeout=(10, 30))
        if not response.ok:
            raise requests.HTTPError(
                f"Open-Meteo HTTP {response.status_code}: {response.text[:500]}",
                response=response,
            )
        payload = response.json()
    retrieved_at = utc_now()

    # Новый каталог на каждый запуск: предыдущие прогнозы не перезаписываются.
    run_dir = Path(output_dir) / retrieved_at.strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot = {
        "mode": "live",
        "endpoint": API_URL,
        "params": params,
        "request_started_at_utc": started_at.isoformat(),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "model_selection": "auto",
        "model_initialization_time_utc": None,
        "model_available_at_utc": None,
        "note": "Время выпуска модели неизвестно; этот снимок не доказывает доступность в феврале 2026.",
        "response": payload,
    }
    (run_dir / "response.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    weather = parse_weather(payload, expected, retrieved_at)
    csv_path = run_dir / "wind_forecast.csv"
    weather.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return weather, csv_path


def main() -> None:
    weather, csv_path = get_all_weather()
    print(weather[["turbine", "time_local", "wind_speed_80m",
                   "wind_speed_120m", "wind_direction_120m"]].to_string(index=False))
    print(f"\nСохранено {len(weather)} строк: {csv_path.resolve()}")
    print("Это текущая погода для модели выработки, не исторический тест и не прогноз мощности.")


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ValueError, TypeError, OSError) as error:
        raise SystemExit(f"ОШИБКА: {error}") from error
