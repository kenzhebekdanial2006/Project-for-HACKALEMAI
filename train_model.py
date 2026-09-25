from pathlib import Path
import json

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

DATA_PATH = Path("data/processed/hourly_training.csv")
MODEL_DIR = Path("models")

VALIDATION_MODEL_PATH = MODEL_DIR / "catboost_validation.cbm"
FINAL_MODEL_PATH = MODEL_DIR / "catboost_power.cbm"
METADATA_PATH = MODEL_DIR / "model_metadata.json"
VALIDATION_RESULTS_PATH = MODEL_DIR / "validation_predictions.csv"


# ============================================================
# FEATURES
# ============================================================

FEATURES = [
    "wind_speed",
    "temperature",
    "turbine",
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
]

TARGET = "power"

CAT_FEATURES = [
    "turbine",
]


# ============================================================
# LOAD DATA
# ============================================================

def load_data() -> pd.DataFrame:

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n{DATA_PATH.resolve()}"
        )

    df = pd.read_csv(DATA_PATH)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="raise"
    )

    df = df.sort_values(
        ["timestamp", "turbine"]
    ).reset_index(drop=True)

    print("Данные загружены:")
    print(f"Строк: {len(df)}")
    print(
        f"Период: "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    return df


# ============================================================
# TIME SPLIT
# ============================================================

def split_data(df: pd.DataFrame):

    """
    Train:
        до 31 декабря 2025 включительно

    Validation:
        январь 2026

    Временной split важен:
    мы НЕ перемешиваем будущее с прошлым.
    """

    validation_start = pd.Timestamp(
        "2026-01-01 00:00:00"
    )

    train = df[
        df["timestamp"] < validation_start
    ].copy()

    validation = df[
        df["timestamp"] >= validation_start
    ].copy()

    if train.empty:
        raise ValueError("Train dataset пуст.")

    if validation.empty:
        raise ValueError("Validation dataset пуст.")

    print()
    print("===================================")
    print(" TIME SPLIT")
    print("===================================")

    print(
        f"TRAIN: "
        f"{train['timestamp'].min()} -> "
        f"{train['timestamp'].max()}"
    )

    print(
        f"TRAIN rows: {len(train)}"
    )

    print()

    print(
        f"VALIDATION: "
        f"{validation['timestamp'].min()} -> "
        f"{validation['timestamp'].max()}"
    )

    print(
        f"VALIDATION rows: {len(validation)}"
    )

    return train, validation


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    y_true,
    y_pred,
) -> dict:

    y_pred = np.clip(
        y_pred,
        0.0,
        1.0
    )

    mae = mean_absolute_error(
        y_true,
        y_pred
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            y_pred
        )
    )

    r2 = r2_score(
        y_true,
        y_pred
    )

    return {
        "MAE": float(mae),
        "RMSE": float(rmse),
        "R2": float(r2),
    }


# ============================================================
# TRAIN VALIDATION MODEL
# ============================================================

def train_validation_model(
    train: pd.DataFrame,
    validation: pd.DataFrame,
):

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_val = validation[FEATURES]
    y_val = validation[TARGET]

    model = CatBoostRegressor(

        loss_function="RMSE",

        eval_metric="MAE",

        iterations=2000,

        learning_rate=0.03,

        depth=8,

        l2_leaf_reg=5,

        random_strength=0.5,

        random_seed=42,

        verbose=100,

        allow_writing_files=False,
    )

    print()
    print("===================================")
    print(" ОБУЧЕНИЕ CATBOOST")
    print("===================================")

    model.fit(

        X_train,
        y_train,

        cat_features=CAT_FEATURES,

        eval_set=(
            X_val,
            y_val
        ),

        early_stopping_rounds=150,

        use_best_model=True,
    )

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    model.save_model(
        VALIDATION_MODEL_PATH
    )

    predictions = model.predict(
        X_val
    )

    predictions = np.clip(
        predictions,
        0.0,
        1.0
    )

    metrics = calculate_metrics(
        y_val,
        predictions
    )

    print()
    print("===================================")
    print(" VALIDATION RESULTS")
    print("===================================")

    for metric, value in metrics.items():

        print(
            f"{metric}: "
            f"{value:.6f}"
        )

    # --------------------------------------
    # METRICS PER TURBINE
    # --------------------------------------

    result = validation[
        [
            "timestamp",
            "turbine",
            "wind_speed",
            "temperature",
            "power",
        ]
    ].copy()

    result["prediction"] = predictions

    result["error"] = (
        result["power"]
        -
        result["prediction"]
    ).abs()

    print()
    print("===================================")
    print(" RESULTS BY TURBINE")
    print("===================================")

    turbine_metrics = {}

    for turbine in sorted(
        result["turbine"].unique()
    ):

        turbine_df = result[
            result["turbine"] == turbine
        ]

        metrics_turbine = calculate_metrics(
            turbine_df["power"],
            turbine_df["prediction"]
        )

        turbine_metrics[turbine] = (
            metrics_turbine
        )

        print()
        print(turbine)

        for metric, value in (
            metrics_turbine.items()
        ):

            print(
                f"  {metric}: "
                f"{value:.6f}"
            )

    result.to_csv(
        VALIDATION_RESULTS_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    best_iteration = (
        model.get_best_iteration()
    )

    if best_iteration < 0:
        best_iteration = 1000
    else:
        best_iteration += 1

    return (
        model,
        metrics,
        turbine_metrics,
        best_iteration,
    )


# ============================================================
# FINAL MODEL
# ============================================================

def train_final_model(
    df: pd.DataFrame,
    iterations: int,
):

    """
    После проверки на январе 2026
    обучаем итоговую модель уже
    на ВСЕХ доступных данных
    до 31 января 2026.
    """

    X = df[FEATURES]

    y = df[TARGET]

    print()
    print("===================================")
    print(" FINAL MODEL")
    print("===================================")

    print(
        f"Обучение на всех "
        f"{len(df)} строках"
    )

    print(
        f"Iterations: {iterations}"
    )

    model = CatBoostRegressor(

        loss_function="RMSE",

        iterations=iterations,

        learning_rate=0.03,

        depth=8,

        l2_leaf_reg=5,

        random_strength=0.5,

        random_seed=42,

        verbose=100,

        allow_writing_files=False,
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

def main():

    df = load_data()

    train, validation = split_data(
        df
    )

    (
        validation_model,
        metrics,
        turbine_metrics,
        best_iterations,
    ) = train_validation_model(
        train,
        validation
    )

    final_model = train_final_model(
        df,
        iterations=best_iterations
    )

    metadata = {

        "model": "CatBoostRegressor",

        "target": TARGET,

        "features": FEATURES,

        "categorical_features": (
            CAT_FEATURES
        ),

        "training_period": {
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

        "validation_period": {
            "start": (
                validation["timestamp"]
                .min()
                .isoformat()
            ),
            "end": (
                validation["timestamp"]
                .max()
                .isoformat()
            ),
        },

        "validation_metrics": metrics,

        "turbine_metrics": (
            turbine_metrics
        ),

        "iterations": int(
            best_iterations
        ),

        "power_range": [
            0.0,
            1.0
        ],
    }

    METADATA_PATH.write_text(

        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8"
    )

    print()
    print("===================================")
    print(" ГОТОВО")
    print("===================================")

    print(
        f"Модель:"
        f"\n{FINAL_MODEL_PATH.resolve()}"
    )

    print(
        f"\nМетаданные:"
        f"\n{METADATA_PATH.resolve()}"
    )

    print(
        f"\nValidation predictions:"
        f"\n{VALIDATION_RESULTS_PATH.resolve()}"
    )


if __name__ == "__main__":
    main()