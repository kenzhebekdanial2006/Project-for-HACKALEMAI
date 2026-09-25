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


DATA_PATH = Path("data/processed/training_v2.csv")
OUTPUT_PATH = Path("models/turbine_model_comparison.json")


# ============================================================
# FEATURES
# ============================================================

BASE_FEATURES = [
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

JOINT_FEATURES = [
    "turbine",
    *BASE_FEATURES,
]

TARGET = "power"


# ============================================================
# METRICS
# ============================================================

def metrics(y_true, y_pred):

    pred = np.clip(
        np.asarray(y_pred),
        0.0,
        1.0,
    )

    true = np.asarray(y_true)

    return {
        "MAE": float(
            mean_absolute_error(
                true,
                pred
            )
        ),

        "RMSE": float(
            np.sqrt(
                mean_squared_error(
                    true,
                    pred
                )
            )
        ),

        "R2": float(
            r2_score(
                true,
                pred
            )
        ),
    }


def print_metrics(name, values):

    print(name)

    print(
        f"  MAE:  "
        f"{values['MAE']:.6f}"
    )

    print(
        f"  RMSE: "
        f"{values['RMSE']:.6f}"
    )

    print(
        f"  R2:   "
        f"{values['R2']:.6f}"
    )


# ============================================================
# MODEL
# ============================================================

def make_model():

    return CatBoostRegressor(
        loss_function="RMSE",
        eval_metric="MAE",

        iterations=2000,
        learning_rate=0.025,
        depth=8,

        l2_leaf_reg=7,
        random_strength=0.5,

        random_seed=42,

        verbose=False,

        allow_writing_files=False,
    )


# ============================================================
# LOAD
# ============================================================

def load_data():

    df = pd.read_csv(
        DATA_PATH
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df["decision_time_utc"] = pd.to_datetime(
        df["decision_time_utc"],
        utc=True,
    )

    df["decision_date"] = (
        df["decision_time_utc"]
        .dt
        .tz_convert(
            "Asia/Almaty"
        )
        .dt
        .tz_localize(None)
        .dt
        .normalize()
    )

    return df


# ============================================================
# STRICT SPLIT
# ============================================================

def split_data(df):

    """
    TRAIN:
        до 10 января

    PURGE:
        11 января

    TUNE:
        12-17 января

    PURGE:
        18 января

    TEST:
        19-29 января

    Благодаря purge 48h forecast windows
    не пересекаются между группами.
    """

    train = df[
        df["decision_date"]
        <= pd.Timestamp("2026-01-10")
    ].copy()

    tune = df[
        df["decision_date"].between(
            pd.Timestamp("2026-01-12"),
            pd.Timestamp("2026-01-17"),
        )
    ].copy()

    test = df[
        df["decision_date"]
        >= pd.Timestamp("2026-01-19")
    ].copy()

    print("======================================")
    print(" SPLIT")
    print("======================================")

    print("Train:", len(train))
    print("Tune: ", len(tune))
    print("Test: ", len(test))

    # Проверка target leakage
    def targets(frame):
        return set(
            zip(
                frame["timestamp"],
                frame["turbine"],
            )
        )

    train_targets = targets(train)
    tune_targets = targets(tune)
    test_targets = targets(test)

    print(
        "Train/Tune overlap:",
        len(
            train_targets
            & tune_targets
        )
    )

    print(
        "Train/Test overlap:",
        len(
            train_targets
            & test_targets
        )
    )

    print(
        "Tune/Test overlap:",
        len(
            tune_targets
            & test_targets
        )
    )

    return train, tune, test


# ============================================================
# JOINT MODEL
# ============================================================

def evaluate_joint(
    train,
    tune,
    test,
):

    print()
    print("======================================")
    print(" JOINT MODEL")
    print("======================================")

    model = make_model()

    model.fit(
        train[JOINT_FEATURES],
        train[TARGET],

        cat_features=["turbine"],

        eval_set=(
            tune[JOINT_FEATURES],
            tune[TARGET],
        ),

        early_stopping_rounds=150,

        use_best_model=True,
    )

    pred = np.clip(
        model.predict(
            test[JOINT_FEATURES]
        ),
        0,
        1,
    )

    result = test[
        [
            "decision_time_utc",
            "timestamp",
            "turbine",
            "power",
        ]
    ].copy()

    result["prediction"] = pred

    all_metrics = metrics(
        result["power"],
        result["prediction"],
    )

    print_metrics(
        "ALL",
        all_metrics
    )

    per_turbine = {}

    for turbine in [
        "WT_1",
        "WT_2",
    ]:

        part = result[
            result["turbine"]
            == turbine
        ]

        values = metrics(
            part["power"],
            part["prediction"],
        )

        per_turbine[turbine] = values

        print_metrics(
            turbine,
            values
        )

    # Проверяем, создаёт ли joint model
    # вообще разные прогнозы для WT_1 и WT_2.

    pivot = result.pivot_table(
        index=[
            "decision_time_utc",
            "timestamp",
        ],
        columns="turbine",
        values="prediction",
        aggfunc="first",
    ).dropna()

    if (
        "WT_1" in pivot.columns
        and
        "WT_2" in pivot.columns
    ):

        difference = (
            pivot["WT_1"]
            -
            pivot["WT_2"]
        ).abs()

        print()
        print(
            "Среднее |prediction WT_1 - WT_2|:"
        )

        print(
            f"{difference.mean():.8f}"
        )

        print(
            "Максимальное различие:"
        )

        print(
            f"{difference.max():.8f}"
        )

    return (
        all_metrics,
        per_turbine,
        model.get_best_iteration() + 1,
    )


# ============================================================
# SEPARATE MODELS
# ============================================================

def evaluate_separate(
    train,
    tune,
    test,
):

    print()
    print("======================================")
    print(" SEPARATE MODELS")
    print("======================================")

    all_predictions = []

    per_turbine = {}

    iterations = {}

    for turbine in [
        "WT_1",
        "WT_2",
    ]:

        print()
        print(
            f"Training {turbine}..."
        )

        train_t = train[
            train["turbine"]
            == turbine
        ]

        tune_t = tune[
            tune["turbine"]
            == turbine
        ]

        test_t = test[
            test["turbine"]
            == turbine
        ].copy()

        model = make_model()

        model.fit(
            train_t[BASE_FEATURES],
            train_t[TARGET],

            eval_set=(
                tune_t[BASE_FEATURES],
                tune_t[TARGET],
            ),

            early_stopping_rounds=150,

            use_best_model=True,
        )

        prediction = np.clip(
            model.predict(
                test_t[
                    BASE_FEATURES
                ]
            ),
            0,
            1,
        )

        test_t[
            "prediction"
        ] = prediction

        values = metrics(
            test_t["power"],
            prediction,
        )

        per_turbine[
            turbine
        ] = values

        iterations[
            turbine
        ] = (
            model.get_best_iteration()
            + 1
        )

        print_metrics(
            turbine,
            values
        )

        all_predictions.append(
            test_t
        )

    result = pd.concat(
        all_predictions,
        ignore_index=True,
    )

    all_metrics = metrics(
        result["power"],
        result["prediction"],
    )

    print()
    print_metrics(
        "SEPARATE — ALL",
        all_metrics
    )

    return (
        all_metrics,
        per_turbine,
        iterations,
    )


# ============================================================
# ACTUAL TURBINE DIFFERENCE
# ============================================================

def actual_turbine_difference(df):

    # Один actual target оставляем один раз,
    # несмотря на overlapping forecasts.

    actual = (
        df[
            [
                "timestamp",
                "turbine",
                "power",
            ]
        ]

        .drop_duplicates(
            [
                "timestamp",
                "turbine",
            ]
        )
    )

    pivot = actual.pivot(
        index="timestamp",
        columns="turbine",
        values="power",
    ).dropna()

    difference = (
        pivot["WT_1"]
        -
        pivot["WT_2"]
    ).abs()

    print()
    print("======================================")
    print(" REAL TURBINE DIFFERENCE")
    print("======================================")

    print(
        "Среднее |power WT_1 - WT_2|:"
    )

    print(
        f"{difference.mean():.6f}"
    )

    print(
        "Максимальное различие:"
    )

    print(
        f"{difference.max():.6f}"
    )

    print(
        "Корреляция WT_1 / WT_2:"
    )

    print(
        f"{pivot['WT_1'].corr(pivot['WT_2']):.6f}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    df = load_data()

    actual_turbine_difference(
        df
    )

    train, tune, test = (
        split_data(df)
    )

    (
        joint_all,
        joint_turbines,
        joint_iterations,
    ) = evaluate_joint(
        train,
        tune,
        test,
    )

    (
        separate_all,
        separate_turbines,
        separate_iterations,
    ) = evaluate_separate(
        train,
        tune,
        test,
    )

    report = {
        "joint": {
            "overall": joint_all,
            "per_turbine": joint_turbines,
            "best_iterations": (
                joint_iterations
            ),
        },

        "separate": {
            "overall": separate_all,
            "per_turbine": (
                separate_turbines
            ),
            "best_iterations": (
                separate_iterations
            ),
        },
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("======================================")
    print(" COMPARISON")
    print("======================================")

    print(
        "Joint MAE:",
        f"{joint_all['MAE']:.6f}"
    )

    print(
        "Separate MAE:",
        f"{separate_all['MAE']:.6f}"
    )

    improvement = (
        joint_all["MAE"]
        -
        separate_all["MAE"]
    )

    relative = (
        improvement
        /
        joint_all["MAE"]
        * 100
    )

    print(
        "MAE difference:",
        f"{improvement:.6f}"
    )

    print(
        "Separate relative improvement:",
        f"{relative:.2f}%"
    )

    print()
    print(
        f"Report:\n"
        f"{OUTPUT_PATH.resolve()}"
    )


if __name__ == "__main__":
    main()