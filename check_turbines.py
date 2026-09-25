import pandas as pd

df = pd.read_csv(
    "weather_backtest/weather_backtest_all.csv"
)

features = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",
    "wind_direction_120m",
    "surface_pressure",
]

wt1 = (
    df[df["turbine"] == "WT_1"]
    .sort_values(["forecast_date", "time"])
    .reset_index(drop=True)
)

wt2 = (
    df[df["turbine"] == "WT_2"]
    .sort_values(["forecast_date", "time"])
    .reset_index(drop=True)
)

print("Количество строк:")
print("WT_1:", len(wt1))
print("WT_2:", len(wt2))

print("\nРазличия погодных признаков:")

for feature in features:

    different = (
        wt1[feature].round(6)
        != wt2[feature].round(6)
    ).sum()

    print(
        f"{feature}: "
        f"{different} различающихся строк "
        f"из {len(wt1)}"
    )

print("\nGrid:")
print(
    df[
        [
            "turbine",
            "grid_latitude",
            "grid_longitude",
            "grid_elevation",
        ]
    ]
    .drop_duplicates()
    .to_string(index=False)
)