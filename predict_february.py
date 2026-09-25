from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor


# ============================================================
# PATHS
# ============================================================

WEATHER_PATH = Path(
    "weather_backtest/weather_backtest_all.csv"
)

MODEL_PATH = Path(
    "models/catboost_weather.cbm"
)

OUTPUT_DIR = Path(
    "predictions"
)

OUTPUT_PATH = (
    OUTPUT_DIR / "forecast_february.csv"
)

LATEST_OUTPUT_PATH = (
    OUTPUT_DIR / "forecast_february_latest.csv"
)


# ============================================================
# FEATURES
# ДОЛЖНЫ СОВПАДАТЬ С train_model_v2.py
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
# LOAD WEATHER
# ============================================================

def load_weather() -> pd.DataFrame:

    if not WEATHER_PATH.exists():

        raise FileNotFoundError(
            f"Не найден:\n{WEATHER_PATH.resolve()}"
        )

    print("Загружаем февральский ECMWF backtest...")

    df = pd.read_csv(
        WEATHER_PATH
    )

    print(
        f"Исходных строк: {len(df)}"
    )

    # UTC target time
    df["time"] = pd.to_datetime(
        df["time"],
        utc=True,
        errors="raise",
    )

    # Decision time
    df["decision_time_utc"] = pd.to_datetime(
        df["decision_time_utc"],
        utc=True,
        errors="raise",
    )

    df["run_initialization_utc"] = pd.to_datetime(
        df["run_initialization_utc"],
        utc=True,
        errors="raise",
    )

    # ========================================================
    # LOCAL TARGET TIME
    # ========================================================

    df["timestamp"] = (

        df["time"]

        .dt
        .tz_convert(
            "Asia/Almaty"
        )

        .dt
        .tz_localize(None)
    )

    return df


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def add_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # ========================================================
    # TIME
    # ========================================================

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

    # ========================================================
    # WIND DIRECTION
    # ========================================================

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

    # ========================================================
    # WIND SHEAR
    # ========================================================

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

    # ========================================================
    # WIND POWER PHYSICS
    # ========================================================

    df["wind_speed_80m_cubed"] = (
        df["wind_speed_80m"] ** 3
    )

    df["wind_speed_120m_cubed"] = (
        df["wind_speed_120m"] ** 3
    )

    return df


# ============================================================
# VALIDATE
# ============================================================

def validate_features(
    df: pd.DataFrame,
) -> None:

    missing = (
        set(FEATURES)
        -
        set(df.columns)
    )

    if missing:

        raise ValueError(
            f"Не хватает признаков: "
            f"{sorted(missing)}"
        )

    nulls = (
        df[FEATURES]
        .isna()
        .sum()
    )

    nulls = nulls[
        nulls > 0
    ]

    if not nulls.empty:

        raise ValueError(
            "Есть NaN в признаках:\n"
            f"{nulls}"
        )


# ============================================================
# PREDICT
# ============================================================

def predict_power(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            f"Не найдена модель:\n"
            f"{MODEL_PATH.resolve()}"
        )

    print()
    print("Загружаем CatBoost weather model...")

    model = CatBoostRegressor()

    model.load_model(
        MODEL_PATH
    )

    X = df[
        FEATURES
    ]

    print(
        f"Прогнозируем {len(X)} строк..."
    )

    predictions = model.predict(
        X
    )

    # normalized power ограничиваем
    # физически допустимым диапазоном
    predictions = np.clip(
        predictions,
        0.0,
        1.0,
    )

    result = df.copy()

    result[
        "predicted_power"
    ] = predictions

    return result


# ============================================================
# OUTPUT
# ============================================================

def prepare_output(
    df: pd.DataFrame,
) -> pd.DataFrame:

    columns = [

        "decision_time_utc",

        "run_initialization_utc",

        "timestamp",

        "turbine",

        "forecast_horizon_hour",

        "lead_from_decision_hours",

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

    result = df[
        columns
    ].copy()

    result = result.sort_values(
        [
            "decision_time_utc",
            "timestamp",
            "turbine",
        ]
    )

    return result


# ============================================================
# LATEST FORECAST FOR EACH TARGET
# ============================================================

def make_latest_forecast(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Один target hour может прогнозироваться дважды:

    например:
        вчера как +36h
        сегодня как +12h

    Для dashboard обычно нужен самый свежий forecast,
    поэтому выбираем последний decision_time.
    """

    latest = (

        df.sort_values(
            "decision_time_utc"
        )

        .drop_duplicates(
            subset=[
                "timestamp",
                "turbine",
            ],
            keep="last",
        )

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

    return latest


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    result: pd.DataFrame,
    latest: pd.DataFrame,
) -> None:

    print()
    print(
        "======================================"
    )
    print(
        " FEBRUARY POWER FORECAST ГОТОВ"
    )
    print(
        "======================================"
    )

    print(
        f"Все forecast rows: "
        f"{len(result)}"
    )

    print(
        f"Уникальные target rows: "
        f"{len(latest)}"
    )

    print(
        f"Target period: "
        f"{result['timestamp'].min()} "
        f"-> "
        f"{result['timestamp'].max()}"
    )

    print()
    print(
        "Средняя predicted power:"
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
        "Максимальная predicted power:"
    )

    print(
        result
        .groupby("turbine")
        ["predicted_power"]
        .max()
        .to_string()
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    weather = load_weather()

    weather = add_features(
        weather
    )

    validate_features(
        weather
    )

    predictions = predict_power(
        weather
    )

    result = prepare_output(
        predictions
    )

    # Сохраняем ВСЕ daily forecast runs
    result.to_csv(

        OUTPUT_PATH,

        index=False,

        encoding="utf-8-sig",
    )

    # Отдельно latest forecast на каждый target hour
    latest = make_latest_forecast(
        result
    )

    latest.to_csv(

        LATEST_OUTPUT_PATH,

        index=False,

        encoding="utf-8-sig",
    )

    # ============================================================
    # OFFICIAL FEBRUARY TEST PERIOD
    # ============================================================
    test_start = pd.Timestamp("2026-02-01 00:00:00")
    test_end = pd.Timestamp("2026-02-28 23:00:00")
    february_only = latest[
        (latest["timestamp"] >= test_start)
        & (latest["timestamp"] <= test_end)
    ].copy()

    FEBRUARY_TEST_PATH = OUTPUT_DIR / "forecast_february_test_period.csv"
    february_only.to_csv(
        FEBRUARY_TEST_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(f"Official February rows: {len(february_only)}")
    print(f"Official test file:\n{FEBRUARY_TEST_PATH.resolve()}")

    print_summary(
        result,
        latest,
    )

    print()
    print(
        f"Все forecasts:\n"
        f"{OUTPUT_PATH.resolve()}"
    )

    print()
    print(
        f"Latest per target:\n"
        f"{LATEST_OUTPUT_PATH.resolve()}"
    )


if __name__ == "__main__":

    try:

        main()

    except (
        ValueError,
        TypeError,
        OSError,
    ) as error:

        raise SystemExit(
            f"\nОШИБКА: {error}"
        ) from error
