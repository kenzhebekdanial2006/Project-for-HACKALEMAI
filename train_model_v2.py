from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from catboost import CatBoostRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


# ============================================================
# PATHS
# ============================================================

DATA_PATH = Path(
    "data/processed/training_v2.csv"
)

MODEL_DIR = Path("models")

VALIDATION_MODEL_PATH = (
    MODEL_DIR / "catboost_weather_validation.cbm"
)

FINAL_MODEL_PATH = (
    MODEL_DIR / "catboost_weather.cbm"
)

METADATA_PATH = (
    MODEL_DIR / "catboost_weather_metadata.json"
)

VALIDATION_RESULTS_PATH = (
    MODEL_DIR / "weather_validation_predictions.csv"
)


# ============================================================
# TARGET
# ============================================================

TARGET = "power"


# ============================================================
# MODEL FEATURES
# ============================================================

FEATURES = [

    # turbine
    "turbine",

    # weather
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",

    # wind speed
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",

    "wind_gusts_10m",

    # direction encoded as sin/cos
    "wind_direction_10m_sin",
    "wind_direction_10m_cos",

    "wind_direction_80m_sin",
    "wind_direction_80m_cos",

    "wind_direction_120m_sin",
    "wind_direction_120m_cos",

    # wind shear
    "wind_shear_80_10",
    "wind_shear_120_80",
    "wind_shear_120_10",

    # physical wind features
    "wind_speed_80m_cubed",
    "wind_speed_120m_cubed",

    # forecast horizon
    "forecast_horizon_hour",
    "lead_from_run_hours",

    # calendar
    "hour_sin",
    "hour_cos",

    "day_sin",
    "day_cos",
]


CAT_FEATURES = [
    "turbine",
]


# ============================================================
# IMPORTANT
# ============================================================

# Эти признаки существуют в training_v2.csv,
# но мы специально НЕ используем их:
#
# actual_wind_speed
# actual_temperature
#
# Потому что в реальном прогнозе будущего
# они неизвестны.


# ============================================================
# LOAD
# ============================================================

def load_data() -> pd.DataFrame:

    if not DATA_PATH.exists():

        raise FileNotFoundError(
            f"Не найден:\n{DATA_PATH.resolve()}"
        )

    print("Загружаем training_v2...")

    df = pd.read_csv(
        DATA_PATH
    )

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="raise",
    )

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

    # --------------------------------------------------------
    # REQUIRED
    # --------------------------------------------------------

    required = set(
        FEATURES
        + [
            TARGET,
            "timestamp",
            "decision_time_utc",
        ]
    )

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        raise ValueError(
            f"Не хватает колонок: "
            f"{sorted(missing)}"
        )

    # --------------------------------------------------------
    # NULL CHECK
    # --------------------------------------------------------

    nulls = df[
        FEATURES + [TARGET]
    ].isna().sum()

    nulls = nulls[
        nulls > 0
    ]

    if not nulls.empty:

        raise ValueError(
            f"NaN в dataset:\n"
            f"{nulls}"
        )

    df = df.sort_values(
        [
            "decision_time_utc",
            "timestamp",
            "turbine",
        ]
    ).reset_index(
        drop=True
    )

    print(
        f"Строк: {len(df)}"
    )

    print(
        f"Decision runs: "
        f"{df['decision_time_utc'].nunique()}"
    )

    print(
        f"Target period: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    return df


# ============================================================
# PURGED TIME SPLIT
# ============================================================

def split_data(
    df: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:

    """
    Из-за 48h forecast windows target-часы перекрываются.

    Поэтому:

    TRAIN:
        decision date <= 2026-01-18

    PURGE:
        2026-01-19

    VALIDATION:
        decision date >= 2026-01-20

    Это предотвращает попадание одинаковых target timestamp
    в train и validation.
    """

    decision_date = (
        df["decision_time_utc"]
        .dt
        .tz_convert("Asia/Almaty")
        .dt
        .date
    )

    decision_date = pd.to_datetime(
        decision_date
    )

    train = df[
        decision_date
        <= pd.Timestamp("2026-01-18")
    ].copy()

    purge = df[
        decision_date
        == pd.Timestamp("2026-01-19")
    ].copy()

    validation = df[
        decision_date
        >= pd.Timestamp("2026-01-20")
    ].copy()

    if train.empty:
        raise ValueError(
            "Train пуст."
        )

    if validation.empty:
        raise ValueError(
            "Validation пуст."
        )

    # --------------------------------------------------------
    # LEAKAGE CHECK
    # --------------------------------------------------------

    train_targets = set(
        zip(
            train["timestamp"],
            train["turbine"],
        )
    )

    validation_targets = set(
        zip(
            validation["timestamp"],
            validation["turbine"],
        )
    )

    overlap = (
        train_targets
        &
        validation_targets
    )

    if overlap:

        raise ValueError(
            f"DATA LEAKAGE: "
            f"{len(overlap)} target timestamps "
            f"есть и в train, и validation."
        )

    print()
    print(
        "======================================"
    )
    print(
        " PURGED TIME SPLIT"
    )
    print(
        "======================================"
    )

    print(
        f"TRAIN rows: {len(train)}"
    )

    print(
        f"TRAIN decisions: "
        f"{train['decision_time_utc'].nunique()}"
    )

    print(
        f"TRAIN targets: "
        f"{train['timestamp'].min()} "
        f"-> "
        f"{train['timestamp'].max()}"
    )

    print()

    print(
        f"PURGE rows: {len(purge)}"
    )

    print()

    print(
        f"VALIDATION rows: "
        f"{len(validation)}"
    )

    print(
        f"VALIDATION decisions: "
        f"{validation['decision_time_utc'].nunique()}"
    )

    print(
        f"VALIDATION targets: "
        f"{validation['timestamp'].min()} "
        f"-> "
        f"{validation['timestamp'].max()}"
    )

    print()

    print(
        "Train/validation target overlap: 0 ✓"
    )

    return (
        train,
        purge,
        validation,
    )


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    y_true,
    y_pred,
) -> dict:

    predictions = np.clip(
        np.asarray(y_pred),
        0.0,
        1.0,
    )

    y_true = np.asarray(
        y_true
    )

    mae = mean_absolute_error(
        y_true,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            predictions,
        )
    )

    r2 = r2_score(
        y_true,
        predictions,
    )

    # Normalized target 0..1,
    # поэтому MAE можно также показать как
    # процент nominal power.
    mae_percent = (
        mae * 100
    )

    rmse_percent = (
        rmse * 100
    )

    return {

        "MAE": float(mae),

        "MAE_percent_nominal": float(
            mae_percent
        ),

        "RMSE": float(rmse),

        "RMSE_percent_nominal": float(
            rmse_percent
        ),

        "R2": float(r2),
    }


# ============================================================
# PRINT METRICS
# ============================================================

def print_metrics(
    title: str,
    metrics: dict,
) -> None:

    print()
    print(title)

    print(
        f"  MAE:  "
        f"{metrics['MAE']:.6f}"
        f" "
        f"({metrics['MAE_percent_nominal']:.2f}%)"
    )

    print(
        f"  RMSE: "
        f"{metrics['RMSE']:.6f}"
        f" "
        f"({metrics['RMSE_percent_nominal']:.2f}%)"
    )

    print(
        f"  R2:   "
        f"{metrics['R2']:.6f}"
    )


# ============================================================
# MODEL
# ============================================================

def create_model(
    iterations: int = 2500,
) -> CatBoostRegressor:

    return CatBoostRegressor(

        loss_function="RMSE",

        eval_metric="MAE",

        iterations=iterations,

        learning_rate=0.025,

        depth=8,

        l2_leaf_reg=7,

        random_strength=0.5,

        random_seed=42,

        verbose=100,

        allow_writing_files=False,
    )


# ============================================================
# VALIDATION MODEL
# ============================================================

def train_validation_model(
    train: pd.DataFrame,
    validation: pd.DataFrame,
):

    X_train = train[
        FEATURES
    ]

    y_train = train[
        TARGET
    ]

    X_val = validation[
        FEATURES
    ]

    y_val = validation[
        TARGET
    ]

    model = create_model(
        iterations=2500
    )

    print()
    print(
        "======================================"
    )
    print(
        " ОБУЧЕНИЕ CATBOOST WEATHER V2"
    )
    print(
        "======================================"
    )

    model.fit(

        X_train,

        y_train,

        cat_features=CAT_FEATURES,

        eval_set=(
            X_val,
            y_val,
        ),

        early_stopping_rounds=200,

        use_best_model=True,
    )

    predictions = model.predict(
        X_val
    )

    predictions = np.clip(
        predictions,
        0.0,
        1.0,
    )

    metrics = calculate_metrics(
        y_val,
        predictions,
    )

    print()
    print(
        "======================================"
    )
    print(
        " VALIDATION"
    )
    print(
        "======================================"
    )

    print_metrics(
        "ALL",
        metrics,
    )

    # ========================================================
    # VALIDATION OUTPUT
    # ========================================================

    result = validation[
        [
            "decision_time_utc",
            "run_initialization_utc",
            "timestamp",
            "turbine",
            "forecast_horizon_hour",
            "wind_speed_120m",
            "actual_wind_speed",
            "power",
        ]
    ].copy()

    result[
        "prediction"
    ] = predictions

    result[
        "absolute_error"
    ] = (

        result["power"]
        -
        result["prediction"]

    ).abs()

    # ========================================================
    # PER TURBINE
    # ========================================================

    turbine_metrics = {}

    for turbine in sorted(
        result["turbine"].unique()
    ):

        part = result[
            result["turbine"]
            == turbine
        ]

        values = calculate_metrics(

            part["power"],

            part["prediction"],
        )

        turbine_metrics[
            turbine
        ] = values

        print_metrics(
            turbine,
            values,
        )

    # ========================================================
    # BY HORIZON
    # ========================================================

    horizon_metrics = {}

    horizon_groups = {

        "H01_12": (
            1,
            12,
        ),

        "H13_24": (
            13,
            24,
        ),

        "H25_36": (
            25,
            36,
        ),

        "H37_48": (
            37,
            48,
        ),
    }

    print()
    print(
        "======================================"
    )
    print(
        " METRICS BY FORECAST HORIZON"
    )
    print(
        "======================================"
    )

    for name, (
        start,
        end,
    ) in horizon_groups.items():

        part = result[

            result[
                "forecast_horizon_hour"
            ].between(
                start,
                end,
            )

        ]

        values = calculate_metrics(

            part["power"],

            part["prediction"],
        )

        horizon_metrics[
            name
        ] = values

        print_metrics(
            f"{name} ({start}-{end}h)",
            values,
        )

    # ========================================================
    # SAVE
    # ========================================================

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    model.save_model(
        VALIDATION_MODEL_PATH
    )

    result.to_csv(

        VALIDATION_RESULTS_PATH,

        index=False,

        encoding="utf-8-sig",
    )

    best_iteration = (
        model.get_best_iteration()
    )

    if best_iteration < 0:

        best_iterations = 500

    else:

        # CatBoost index начинается с 0.
        best_iterations = (
            best_iteration + 1
        )

    return (
        model,
        metrics,
        turbine_metrics,
        horizon_metrics,
        best_iterations,
    )


# ============================================================
# FINAL MODEL
# ============================================================

def train_final_model(
    df: pd.DataFrame,
    iterations: int,
):

    """
    После честной validation
    обучаем итоговую модель на всех 60 runs.

    Здесь февраль 2026 отсутствует,
    поэтому test leakage нет.
    """

    X = df[
        FEATURES
    ]

    y = df[
        TARGET
    ]

    model = CatBoostRegressor(

        loss_function="RMSE",

        iterations=iterations,

        learning_rate=0.025,

        depth=8,

        l2_leaf_reg=7,

        random_strength=0.5,

        random_seed=42,

        verbose=100,

        allow_writing_files=False,
    )

    print()
    print(
        "======================================"
    )
    print(
        " FINAL CATBOOST WEATHER"
    )
    print(
        "======================================"
    )

    print(
        f"Rows: {len(df)}"
    )

    print(
        f"Iterations: {iterations}"
    )

    model.fit(

        X,

        y,

        cat_features=CAT_FEATURES,
    )

    model.save_model(
        FINAL_MODEL_PATH
    )

    return model


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data()

    (
        train,
        purge,
        validation,
    ) = split_data(
        df
    )

    (
        validation_model,
        validation_metrics,
        turbine_metrics,
        horizon_metrics,
        best_iterations,
    ) = train_validation_model(

        train=train,

        validation=validation,
    )

    train_final_model(

        df=df,

        iterations=best_iterations,
    )

    # ========================================================
    # METADATA
    # ========================================================

    metadata = {

        "model": (
            "CatBoostRegressor"
        ),

        "version": (
            "weather_v2"
        ),

        "target": TARGET,

        "features": FEATURES,

        "categorical_features": (
            CAT_FEATURES
        ),

        "forbidden_features": [
            "actual_wind_speed",
            "actual_temperature",
        ],

        "weather_source": (
            "ECMWF IFS via "
            "Open-Meteo Single Runs API"
        ),

        "training_rows": int(
            len(df)
        ),

        "decision_runs": int(
            df[
                "decision_time_utc"
            ].nunique()
        ),

        "training_target_period": {

            "start": (
                df["timestamp"]
                .min()
                .isoformat()
            ),

            "end": (
                df["timestamp"]
                .max()
                .isoformat()
            ),
        },

        "split": {

            "type": (
                "purged_time_split"
            ),

            "train_decision_end": (
                "2026-01-18"
            ),

            "purged_decision_date": (
                "2026-01-19"
            ),

            "validation_decision_start": (
                "2026-01-20"
            ),
        },

        "validation_metrics": (
            validation_metrics
        ),

        "turbine_metrics": (
            turbine_metrics
        ),

        "horizon_metrics": (
            horizon_metrics
        ),

        "iterations": int(
            best_iterations
        ),

        "prediction_range": [
            0.0,
            1.0,
        ],
    }

    METADATA_PATH.write_text(

        json.dumps(

            metadata,

            ensure_ascii=False,

            indent=2,
        ),

        encoding="utf-8",
    )

    print()
    print(
        "======================================"
    )
    print(
        " WEATHER MODEL V2 ГОТОВА"
    )
    print(
        "======================================"
    )

    print(
        f"Final model:\n"
        f"{FINAL_MODEL_PATH.resolve()}"
    )

    print()
    print(
        f"Metadata:\n"
        f"{METADATA_PATH.resolve()}"
    )

    print()
    print(
        f"Validation predictions:\n"
        f"{VALIDATION_RESULTS_PATH.resolve()}"
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