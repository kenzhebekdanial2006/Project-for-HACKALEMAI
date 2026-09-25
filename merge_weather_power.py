from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

POWER_PATH = Path(
    "data/processed/hourly_training.csv"
)

WEATHER_PATH = Path(
    "weather_training/weather_backtest_all.csv"
)

OUTPUT_DIR = Path(
    "data/processed"
)

OUTPUT_PATH = (
    OUTPUT_DIR / "training_v2.csv"
)


# ============================================================
# LOAD POWER
# ============================================================

def load_power() -> pd.DataFrame:

    if not POWER_PATH.exists():
        raise FileNotFoundError(
            f"Не найден файл мощности:\n"
            f"{POWER_PATH.resolve()}"
        )

    print("Загружаем историческую мощность...")

    df = pd.read_csv(
        POWER_PATH
    )

    required = {
        "timestamp",
        "turbine",
        "wind_speed",
        "temperature",
        "power",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"В power dataset отсутствуют: "
            f"{sorted(missing)}"
        )

    # ----------------------------------------
    # TIMESTAMP
    # ----------------------------------------

    # Исторические данные ВЭС уже идут
    # в локальном времени.
    #
    # Оставляем timestamp timezone-naive,
    # чтобы потом объединить с ECMWF
    # после его перевода в Asia/Almaty.

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="raise"
    )

    # ----------------------------------------
    # ПЕРЕИМЕНОВЫВАЕМ ФАКТИЧЕСКУЮ ПОГОДУ
    # ----------------------------------------

    # Эти колонки сохраняются только
    # для анализа качества.
    #
    # В ML v2 они НЕ должны использоваться.

    df = df.rename(
        columns={
            "wind_speed": "actual_wind_speed",
            "temperature": "actual_temperature",
        }
    )

    keep = [
        "timestamp",
        "turbine",
        "actual_wind_speed",
        "actual_temperature",
        "power",
    ]

    df = df[keep].copy()

    # Проверяем уникальность
    duplicates = df.duplicated(
        subset=[
            "timestamp",
            "turbine",
        ]
    )

    if duplicates.any():

        count = int(
            duplicates.sum()
        )

        raise ValueError(
            f"В power dataset найдено "
            f"{count} дубликатов "
            f"timestamp+turbine."
        )

    print(
        f"  строк: {len(df)}"
    )

    print(
        f"  период: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    return df


# ============================================================
# LOAD ECMWF
# ============================================================

def load_weather() -> pd.DataFrame:

    if not WEATHER_PATH.exists():

        raise FileNotFoundError(
            f"Не найден ECMWF dataset:\n"
            f"{WEATHER_PATH.resolve()}"
        )

    print()
    print("Загружаем архивные ECMWF forecasts...")

    df = pd.read_csv(
        WEATHER_PATH
    )

    required = {

        "turbine",

        "time",

        "time_local",

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

        "forecast_horizon_hour",

        "lead_from_decision_hours",
        "lead_from_run_hours",

        "run_initialization_utc",
        "decision_time_utc",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        raise ValueError(
            "В ECMWF dataset отсутствуют: "
            f"{sorted(missing)}"
        )

    # ========================================================
    # TARGET TIME
    # ========================================================

    # time содержит UTC.
    #
    # Переводим его в Asia/Almaty,
    # затем убираем timezone.
    #
    # Получаем формат, совпадающий
    # с timestamp исторических данных ВЭС.

    utc_time = pd.to_datetime(
        df["time"],
        utc=True,
        errors="raise"
    )

    df["timestamp"] = (

        utc_time

        .dt
        .tz_convert(
            "Asia/Almaty"
        )

        .dt
        .tz_localize(None)
    )

    # ----------------------------------------
    # Forecast creation date
    # ----------------------------------------

    df[
        "decision_time_utc"
    ] = pd.to_datetime(

        df["decision_time_utc"],

        utc=True,

        errors="raise",
    )

    df[
        "run_initialization_utc"
    ] = pd.to_datetime(

        df["run_initialization_utc"],

        utc=True,

        errors="raise",
    )

    # ----------------------------------------
    # NUMERIC
    # ----------------------------------------

    numeric_columns = [

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

        "forecast_horizon_hour",

        "lead_from_decision_hours",
        "lead_from_run_hours",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="raise"
        )

    print(
        f"  строк: {len(df)}"
    )

    print(
        f"  target period: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    print(
        f"  forecast runs: "
        f"{df['decision_time_utc'].nunique()}"
    )

    return df


# ============================================================
# MERGE
# ============================================================

def merge_datasets(
    weather: pd.DataFrame,
    power: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print("Объединяем ECMWF + фактическую мощность...")

    before = len(weather)

    merged = weather.merge(

        power,

        on=[
            "timestamp",
            "turbine",
        ],

        how="left",

        validate="many_to_one",
    )

    # ========================================================
    # TARGET AVAILABILITY
    # ========================================================

    missing_power = (
        merged["power"]
        .isna()
        .sum()
    )

    print(
        f"  weather rows: {before}"
    )

    print(
        f"  без фактической мощности: "
        f"{missing_power}"
    )

    # Для train нужны только строки,
    # где фактическая power известна.

    merged = merged.dropna(
        subset=["power"]
    ).copy()

    print(
        f"  после merge: {len(merged)}"
    )

    return merged


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def add_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # ========================================================
    # CALENDAR FEATURES
    # ========================================================

    df["hour"] = (
        df["timestamp"].dt.hour
    )

    df["day_of_year"] = (
        df["timestamp"]
        .dt
        .dayofyear
    )

    df["month"] = (
        df["timestamp"].dt.month
    )

    df["day_of_week"] = (
        df["timestamp"]
        .dt
        .dayofweek
    )

    # --------------------------------------------------------
    # CYCLICAL HOUR
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CYCLICAL YEAR
    # --------------------------------------------------------

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

    # Направление 0° и 360° означает одно и то же.
    # Поэтому просто число градусов для модели не идеально.
    #
    # Переводим direction в sin/cos.

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

    # Разница скорости ветра между высотами.
    # Для ВЭС это полезный физический признак.

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
    # WIND CUBED
    # ========================================================

    # Теоретически энергия ветра примерно
    # пропорциональна кубу скорости.
    #
    # CatBoost способен найти зависимость сам,
    # но этот физический признак можно добавить.

    df["wind_speed_80m_cubed"] = (
        df["wind_speed_80m"] ** 3
    )

    df["wind_speed_120m_cubed"] = (
        df["wind_speed_120m"] ** 3
    )

    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    if (
        (df["power"] < 0).any()
        or
        (df["power"] > 1).any()
    ):

        print(
            "ПРЕДУПРЕЖДЕНИЕ: "
            "power содержит значения "
            "за пределами 0..1."
        )

    return df


# ============================================================
# FINAL COLUMN ORDER
# ============================================================

def select_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:

    columns = [

        # ------------------------------------
        # IDENTIFIERS
        # ------------------------------------

        "timestamp",

        "turbine",

        "decision_time_utc",

        "run_initialization_utc",

        "forecast_horizon_hour",

        "lead_from_decision_hours",

        "lead_from_run_hours",

        # ------------------------------------
        # ECMWF WEATHER
        # ------------------------------------

        "temperature_2m",

        "relative_humidity_2m",

        "surface_pressure",

        "wind_speed_10m",

        "wind_speed_80m",

        "wind_speed_120m",

        "wind_gusts_10m",

        # raw direction оставляем
        # для анализа

        "wind_direction_10m",

        "wind_direction_80m",

        "wind_direction_120m",

        # ------------------------------------
        # DIRECTION FEATURES
        # ------------------------------------

        "wind_direction_10m_sin",

        "wind_direction_10m_cos",

        "wind_direction_80m_sin",

        "wind_direction_80m_cos",

        "wind_direction_120m_sin",

        "wind_direction_120m_cos",

        # ------------------------------------
        # WIND PHYSICS
        # ------------------------------------

        "wind_shear_80_10",

        "wind_shear_120_80",

        "wind_shear_120_10",

        "wind_speed_80m_cubed",

        "wind_speed_120m_cubed",

        # ------------------------------------
        # CALENDAR
        # ------------------------------------

        "hour",

        "month",

        "day_of_week",

        "day_of_year",

        "hour_sin",

        "hour_cos",

        "day_sin",

        "day_cos",

        # ------------------------------------
        # ACTUAL VALUES
        #
        # ТОЛЬКО ДЛЯ ДИАГНОСТИКИ!
        #
        # НЕ использовать actual_* при
        # обучении production модели.
        # ------------------------------------

        "actual_wind_speed",

        "actual_temperature",

        # ------------------------------------
        # TARGET
        # ------------------------------------

        "power",
    ]

    missing = (
        set(columns)
        - set(df.columns)
    )

    if missing:

        raise ValueError(
            "После feature engineering "
            "не хватает колонок: "
            f"{sorted(missing)}"
        )

    return df[columns].copy()


# ============================================================
# VALIDATE FINAL DATASET
# ============================================================

def validate_dataset(
    df: pd.DataFrame,
) -> None:

    print()
    print("======================================")
    print(" DATASET VALIDATION")
    print("======================================")

    print(
        f"Rows: {len(df)}"
    )

    print(
        f"Target period: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    print(
        f"Turbines: "
        f"{sorted(df['turbine'].unique())}"
    )

    print(
        f"Decision runs: "
        f"{df['decision_time_utc'].nunique()}"
    )

    # --------------------------------------------------------
    # NULL
    # --------------------------------------------------------

    nulls = (
        df.isna()
        .sum()
    )

    nulls = nulls[
        nulls > 0
    ]

    if not nulls.empty:

        print()
        print(
            "Колонки с NaN:"
        )

        print(
            nulls.to_string()
        )

        raise ValueError(
            "training_v2 содержит NaN."
        )

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    # ВАЖНО:
    #
    # timestamp+turbine МОЖЕТ повторяться,
    # потому что один target hour может быть
    # спрогнозирован из двух разных decision runs.
    #
    # Поэтому уникальным ключом является:
    #
    # decision_time_utc
    # + timestamp
    # + turbine

    duplicates = df.duplicated(
        subset=[
            "decision_time_utc",
            "timestamp",
            "turbine",
        ]
    )

    if duplicates.any():

        raise ValueError(
            "Найдены настоящие дубликаты "
            "decision_time + timestamp + turbine."
        )

    overlapping_targets = (

        df.duplicated(
            subset=[
                "timestamp",
                "turbine",
            ],
            keep=False,
        )

        .sum()
    )

    print(
        f"Rows belonging to overlapping "
        f"48h forecasts: "
        f"{overlapping_targets}"
    )

    # --------------------------------------------------------
    # HORIZONS
    # --------------------------------------------------------

    print()
    print(
        "Forecast horizon range:"
    )

    print(
        f"  "
        f"{df['forecast_horizon_hour'].min()} "
        f"-> "
        f"{df['forecast_horizon_hour'].max()}"
    )

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    print()
    print(
        "Power:"
    )

    print(
        f"  min: "
        f"{df['power'].min():.6f}"
    )

    print(
        f"  mean: "
        f"{df['power'].mean():.6f}"
    )

    print(
        f"  max: "
        f"{df['power'].max():.6f}"
    )

    print()
    print(
        "Rows per turbine:"
    )

    print(
        df[
            "turbine"
        ]
        .value_counts()
        .to_string()
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    power = load_power()

    weather = load_weather()

    merged = merge_datasets(
        weather=weather,
        power=power,
    )

    merged = add_features(
        merged
    )

    final = select_columns(
        merged
    )

    # ----------------------------------------
    # SORT
    # ----------------------------------------

    final = final.sort_values(
        [
            "decision_time_utc",
            "timestamp",
            "turbine",
        ]
    ).reset_index(
        drop=True
    )

    validate_dataset(
        final
    )

    # ----------------------------------------
    # SAVE
    # ----------------------------------------

    final.to_csv(

        OUTPUT_PATH,

        index=False,

        encoding="utf-8-sig",
    )

    print()
    print(
        "======================================"
    )

    print(
        " TRAINING V2 ГОТОВ"
    )

    print(
        "======================================"
    )

    print(
        f"Сохранено:\n"
        f"{OUTPUT_PATH.resolve()}"
    )

    print()
    print(
        "ВАЖНО:"
    )

    print(
        "actual_wind_speed и "
        "actual_temperature сохранены "
        "только для диагностики."
    )

    print(
        "Production ML не должна "
        "использовать эти признаки."
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