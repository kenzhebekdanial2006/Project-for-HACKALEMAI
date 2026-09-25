from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from catboost import CatBoostRegressor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# CONFIG
# ============================================================

API_URL = "https://single-runs-api.open-meteo.com/v1/forecast"

MODEL_NAME = "ecmwf_ifs"

LOCAL_TIMEZONE = "Asia/Almaty"

HORIZON_HOURS = 48

API_FORECAST_HOURS = 120

MODEL_DELAY_HOURS = 6
SAFETY_BUFFER_MINUTES = 10


# ============================================================
# FILES
# ============================================================

MODEL_PATH = BASE_DIR / "models" / "catboost_weather.cbm"

OUTPUT_DIR = BASE_DIR / "predictions" / "live"

CSV_PATH = (
    OUTPUT_DIR / "forecast_live.csv"
)

JSON_PATH = (
    OUTPUT_DIR / "forecast_live.json"
)


# ============================================================
# TURBINES
# ============================================================

TURBINES = {

    "WT_1": {
        "latitude": 43.645139,
        "longitude": 78.535611,
    },

    "WT_2": {
        "latitude": 43.643194,
        "longitude": 78.538833,
    },
}


# ============================================================
# WEATHER VARIABLES
# ============================================================

HOURLY = [

    "temperature_2m",

    "relative_humidity_2m",

    "surface_pressure",

    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",

    "wind_direction_10m",
    "wind_direction_80m",
    "wind_direction_120m",

    "wind_gusts_10m",
]


# ============================================================
# MODEL FEATURES
# MUST MATCH train_model_v2.py
# ============================================================

FEATURES = [

    "turbine",

    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",

    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",

    "wind_gusts_10m",

    "wind_direction_10m_sin",
    "wind_direction_10m_cos",

    "wind_direction_80m_sin",
    "wind_direction_80m_cos",

    "wind_direction_120m_sin",
    "wind_direction_120m_cos",

    "wind_shear_80_10",
    "wind_shear_120_80",
    "wind_shear_120_10",

    "wind_speed_80m_cubed",
    "wind_speed_120m_cubed",

    "forecast_horizon_hour",
    "lead_from_run_hours",

    "hour_sin",
    "hour_cos",

    "day_sin",
    "day_cos",
]


# ============================================================
# HTTP
# ============================================================

def create_session() -> requests.Session:

    retry = Retry(

        total=4,

        connect=4,

        read=4,

        backoff_factor=1,

        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],

        allowed_methods=frozenset(
            ["GET"]
        ),

        respect_retry_after_header=True,

        raise_on_status=False,
    )

    session = requests.Session()

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        ),
    )

    return session


# ============================================================
# TIME
# ============================================================

def now_utc() -> pd.Timestamp:

    return pd.Timestamp.now(
        tz="UTC"
    )


def get_target_window(
    retrieved_at: pd.Timestamp,
) -> pd.DatetimeIndex:

    """
    Следующие 48 полных часов.

    Например:
        сейчас 14:37 UTC

    первый forecast:
        15:00 UTC
    """

    first_hour = (

        retrieved_at
        .floor("h")

        + pd.Timedelta(
            hours=1
        )
    )

    return pd.date_range(

        start=first_hour,

        periods=HORIZON_HOURS,

        freq="h",
    )


# ============================================================
# ECMWF RUN SELECTION
# ============================================================

def get_run_candidates(
    retrieved_at: pd.Timestamp,
) -> list[pd.Timestamp]:

    """
    Не используем слишком свежий run.

    safe cutoff:

        current UTC
        - 6 hours
        - 10 minute safety buffer

    Затем округляем к циклу:
        00 / 06 / 12 / 18 UTC.
    """

    safe_cutoff = (

        retrieved_at

        - pd.Timedelta(
            hours=MODEL_DELAY_HOURS
        )

        - pd.Timedelta(
            minutes=SAFETY_BUFFER_MINUTES
        )
    )

    latest_run = (
        safe_cutoff.floor("6h")
    )

    return [

        latest_run
        - pd.Timedelta(
            hours=6 * i
        )

        for i in range(6)
    ]


# ============================================================
# REQUEST ONE RUN
# ============================================================

def request_run(
    session: requests.Session,
    run_time: pd.Timestamp,
):

    params = {

        "latitude": ",".join(

            str(
                item["latitude"]
            )

            for item
            in TURBINES.values()
        ),

        "longitude": ",".join(

            str(
                item["longitude"]
            )

            for item
            in TURBINES.values()
        ),

        "models": MODEL_NAME,

        "run": (
            run_time
            .strftime(
                "%Y-%m-%dT%H:%M"
            )
        ),

        "hourly": ",".join(
            HOURLY
        ),

        "wind_speed_unit": "ms",

        "temperature_unit": "celsius",

        "timezone": "UTC",

        "timeformat": "unixtime",

        "forecast_hours": (
            API_FORECAST_HOURS
        ),
    }

    response = session.get(

        API_URL,

        params=params,

        timeout=(15, 90),
    )

    if not response.ok:

        raise requests.HTTPError(

            f"HTTP "
            f"{response.status_code}: "
            f"{response.text[:1000]}"
        )

    payload = response.json()

    if (
        isinstance(payload, dict)
        and payload.get("error")
    ):

        raise ValueError(
            payload.get(
                "reason",
                "Open-Meteo error",
            )
        )

    return (
        payload,
        response.url,
    )


# ============================================================
# PARSE RUN
# ============================================================

def parse_run(
    payload,
    run_time: pd.Timestamp,
    expected: pd.DatetimeIndex,
) -> pd.DataFrame:

    if (
        not isinstance(payload, list)
        or len(payload) != len(TURBINES)
    ):

        raise ValueError(
            "API должен вернуть "
            "две координаты."
        )

    frames = []

    for index, (
        (name, coordinates),
        item,
    ) in enumerate(
        zip(
            TURBINES.items(),
            payload,
        )
    ):

        if (
            not isinstance(item, dict)
            or item.get("error")
        ):

            raise ValueError(
                f"{name}: "
                "некорректный API response."
            )

        hourly = item.get(
            "hourly"
        )

        if not isinstance(
            hourly,
            dict,
        ):

            raise ValueError(
                f"{name}: нет hourly."
            )

        df = pd.DataFrame(
            hourly
        )

        required = {
            "time",
            *HOURLY,
        }

        missing = (
            required
            - set(df.columns)
        )

        if missing:

            raise ValueError(
                f"{name}: "
                f"нет колонок "
                f"{sorted(missing)}"
            )

        df = df[
            [
                "time",
                *HOURLY,
            ]
        ].copy()

        # ------------------------------------
        # TIME
        # ------------------------------------

        df["time"] = pd.to_datetime(

            df["time"],

            unit="s",

            utc=True,

            errors="raise",
        )

        df = (

            df.sort_values("time")

            .drop_duplicates(
                subset=["time"]
            )

            .reset_index(
                drop=True
            )
        )

        # Только следующие нужные 48 часов
        df = df[

            (df["time"] >= expected[0])

            &

            (df["time"] <= expected[-1])

        ].copy()

        df = df.reset_index(
            drop=True
        )

        actual = pd.DatetimeIndex(
            df["time"]
        )

        if not actual.equals(
            expected
        ):

            raise ValueError(

                f"{name}: "
                f"ожидалось "
                f"{HORIZON_HOURS} часов, "
                f"получено {len(df)}."
            )

        # ------------------------------------
        # NUMERIC
        # ------------------------------------

        values = df[
            HOURLY
        ].apply(

            pd.to_numeric,

            errors="coerce",
        )

        invalid = (

            values.isna()

            |

            values.isin(
                [
                    np.inf,
                    -np.inf,
                ]
            )
        )

        if invalid.any().any():

            columns = (
                invalid.columns[
                    invalid.any()
                ]
                .tolist()
            )

            raise ValueError(

                f"{name}: "
                f"NaN/Inf: "
                f"{columns}"
            )

        df[HOURLY] = values

        # ------------------------------------
        # METADATA
        # ------------------------------------

        df.insert(
            0,
            "turbine",
            name,
        )

        df.insert(
            1,
            "latitude",
            coordinates[
                "latitude"
            ],
        )

        df.insert(
            2,
            "longitude",
            coordinates[
                "longitude"
            ],
        )

        df[
            "run_initialization_utc"
        ] = run_time

        df[
            "forecast_horizon_hour"
        ] = np.arange(
            1,
            len(df) + 1,
        )

        df[
            "lead_from_run_hours"
        ] = (

            (
                df["time"]
                - run_time
            )

            .dt
            .total_seconds()

            / 3600
        )

        df[
            "grid_latitude"
        ] = item.get(
            "latitude"
        )

        df[
            "grid_longitude"
        ] = item.get(
            "longitude"
        )

        df[
            "grid_elevation"
        ] = item.get(
            "elevation"
        )

        frames.append(
            df
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    if len(result) != (
        HORIZON_HOURS
        * len(TURBINES)
    ):

        raise ValueError(
            "Некорректное количество "
            "forecast rows."
        )

    return result


# ============================================================
# FIND LIVE RUN
# ============================================================

def fetch_live_weather():

    retrieved_at = now_utc()

    expected = get_target_window(
        retrieved_at
    )

    candidates = get_run_candidates(
        retrieved_at
    )

    errors = []

    with create_session() as session:

        for run_time in candidates:

            print(
                f"Пробуем ECMWF run: "
                f"{run_time}"
            )

            try:

                payload, request_url = (
                    request_run(
                        session=session,
                        run_time=run_time,
                    )
                )

                weather = parse_run(

                    payload=payload,

                    run_time=run_time,

                    expected=expected,
                )

                print(
                    "✓ Run валиден"
                )

                return (
                    weather,
                    retrieved_at,
                    run_time,
                    request_url,
                )

            except (
                requests.RequestException,
                ValueError,
            ) as error:

                print(
                    f"✗ {error}"
                )

                errors.append(
                    {
                        "run": (
                            run_time
                            .isoformat()
                        ),
                        "error": str(error),
                    }
                )

    raise RuntimeError(
        "Нет валидного ECMWF run: "
        f"{errors}"
    )


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def add_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Local target time
    df["timestamp"] = (

        df["time"]

        .dt
        .tz_convert(
            LOCAL_TIMEZONE
        )

        .dt
        .tz_localize(None)
    )

    # ------------------------------------
    # Calendar
    # ------------------------------------

    df["hour"] = (
        df["timestamp"].dt.hour
    )

    df["day_of_year"] = (
        df["timestamp"]
        .dt
        .dayofyear
    )

    df["hour_sin"] = np.sin(

        2
        * np.pi
        * df["hour"]
        / 24
    )

    df["hour_cos"] = np.cos(

        2
        * np.pi
        * df["hour"]
        / 24
    )

    df["day_sin"] = np.sin(

        2
        * np.pi
        * df["day_of_year"]
        / 365.25
    )

    df["day_cos"] = np.cos(

        2
        * np.pi
        * df["day_of_year"]
        / 365.25
    )

    # ------------------------------------
    # Wind direction
    # ------------------------------------

    for height in [
        "10m",
        "80m",
        "120m",
    ]:

        column = (
            f"wind_direction_{height}"
        )

        radians = np.deg2rad(
            df[column]
        )

        df[
            f"wind_direction_{height}_sin"
        ] = np.sin(
            radians
        )

        df[
            f"wind_direction_{height}_cos"
        ] = np.cos(
            radians
        )

    # ------------------------------------
    # Wind shear
    # ------------------------------------

    df["wind_shear_80_10"] = (

        df["wind_speed_80m"]
        -
        df["wind_speed_10m"]
    )

    df["wind_shear_120_80"] = (

        df["wind_speed_120m"]
        -
        df["wind_speed_80m"]
    )

    df["wind_shear_120_10"] = (

        df["wind_speed_120m"]
        -
        df["wind_speed_10m"]
    )

    # ------------------------------------
    # Wind cubed
    # ------------------------------------

    df["wind_speed_80m_cubed"] = (
        df["wind_speed_80m"] ** 3
    )

    df[
        "wind_speed_120m_cubed"
    ] = (
        df["wind_speed_120m"] ** 3
    )

    return df


# ============================================================
# PREDICTION
# ============================================================

def predict_power(
    weather: pd.DataFrame,
) -> pd.DataFrame:

    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            f"Модель не найдена:\n"
            f"{MODEL_PATH.resolve()}"
        )

    weather = add_features(
        weather
    )

    missing = (
        set(FEATURES)
        -
        set(weather.columns)
    )

    if missing:

        raise ValueError(
            f"Нет features: "
            f"{sorted(missing)}"
        )

    if weather[
        FEATURES
    ].isna().any().any():

        raise ValueError(
            "Features содержат NaN."
        )

    model = CatBoostRegressor()

    model.load_model(
        MODEL_PATH
    )

    prediction = model.predict(
        weather[FEATURES]
    )

    weather[
        "predicted_power"
    ] = np.clip(
        prediction,
        0.0,
        1.0,
    )

    return weather


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(
    df: pd.DataFrame,
    retrieved_at: pd.Timestamp,
    run_time: pd.Timestamp,
    request_url: str,
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    columns = [

        "timestamp",

        "turbine",

        "forecast_horizon_hour",

        "wind_speed_10m",
        "wind_speed_80m",
        "wind_speed_120m",

        "wind_direction_120m",

        "wind_gusts_10m",

        "temperature_2m",

        "relative_humidity_2m",

        "surface_pressure",

        "predicted_power",
    ]

    result = (

        df[columns]

        .sort_values(
            [
                "timestamp",
                "turbine",
            ]
        )

        .reset_index(
            drop=True
        )
    )

    result.to_csv(

        CSV_PATH,

        index=False,

        encoding="utf-8-sig",
    )

    # ------------------------------------
    # JSON for React / FastAPI
    # ------------------------------------

    forecasts = []

    for row in result.to_dict(
        orient="records"
    ):

        forecasts.append(
            {
                "turbine": row[
                    "turbine"
                ],

                "time": (
                    pd.Timestamp(
                        row["timestamp"]
                    )
                    .tz_localize(
                        LOCAL_TIMEZONE
                    )
                    .isoformat()
                ),

                "forecast_horizon_hour": int(
                    row[
                        "forecast_horizon_hour"
                    ]
                ),

                "weather": {

                    "wind_speed_10m": float(
                        row[
                            "wind_speed_10m"
                        ]
                    ),

                    "wind_speed_80m": float(
                        row[
                            "wind_speed_80m"
                        ]
                    ),

                    "wind_speed_120m": float(
                        row[
                            "wind_speed_120m"
                        ]
                    ),

                    "wind_direction_120m": float(
                        row[
                            "wind_direction_120m"
                        ]
                    ),

                    "wind_gusts_10m": float(
                        row[
                            "wind_gusts_10m"
                        ]
                    ),

                    "temperature_2m": float(
                        row[
                            "temperature_2m"
                        ]
                    ),

                    "relative_humidity_2m": float(
                        row[
                            "relative_humidity_2m"
                        ]
                    ),

                    "surface_pressure": float(
                        row[
                            "surface_pressure"
                        ]
                    ),
                },

                "predicted_power": float(
                    row[
                        "predicted_power"
                    ]
                ),
            }
        )

    document = {

        "status": "ok",

        "generated_at_utc": (
            retrieved_at.isoformat()
        ),

        "weather_model": (
            "ECMWF IFS HRES"
        ),

        "weather_run_utc": (
            run_time.isoformat()
        ),

        "power_model": (
            "catboost_weather_v2"
        ),

        "horizon_hours": (
            HORIZON_HOURS
        ),

        "turbines": list(
            TURBINES.keys()
        ),

        "forecast_count": len(
            forecasts
        ),

        "request_url": request_url,

        "forecasts": forecasts,
    }

    JSON_PATH.write_text(

        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),

        encoding="utf-8",
    )

    return result


# ============================================================
# MAIN PIPELINE
# ============================================================

def generate_live_forecast():

    (
        weather,
        retrieved_at,
        run_time,
        request_url,
    ) = fetch_live_weather()

    prediction = predict_power(
        weather
    )

    result = save_outputs(

        prediction,

        retrieved_at=retrieved_at,

        run_time=run_time,

        request_url=request_url,
    )

    return result


# ============================================================
# CLI
# ============================================================

def main():

    result = generate_live_forecast()

    print()
    print(
        "======================================"
    )
    print(
        " LIVE POWER FORECAST ГОТОВ"
    )
    print(
        "======================================"
    )

    print(
        f"Rows: {len(result)}"
    )

    print(
        f"Period: "
        f"{result['timestamp'].min()} "
        f"-> "
        f"{result['timestamp'].max()}"
    )

    print()
    print(
        "Средняя мощность:"
    )

    print(
        result
        .groupby("turbine")
        ["predicted_power"]
        .mean()
        .to_string()
    )

    print()
    print(
        "Первые прогнозы:"
    )

    print(

        result[
            [
                "timestamp",
                "turbine",
                "wind_speed_120m",
                "predicted_power",
            ]
        ]

        .head(10)

        .to_string(
            index=False
        )
    )

    print()
    print(
        f"CSV:\n"
        f"{CSV_PATH.resolve()}"
    )

    print()
    print(
        f"JSON:\n"
        f"{JSON_PATH.resolve()}"
    )


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        raise SystemExit(
            f"\nОШИБКА: {error}"
        ) from error
