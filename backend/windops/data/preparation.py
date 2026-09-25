from pathlib import Path

import numpy as np
import pandas as pd

from ..core.paths import RAW_DATA_DIR, PROCESSED_DIR


# ============================================================
# ПУТИ
# ============================================================

FILES = {
    "WT_1": RAW_DATA_DIR / "turbine_1.csv",
    "WT_2": RAW_DATA_DIR / "turbine_2.csv",
}


# ============================================================
# ИСХОДНЫЕ НАЗВАНИЯ СТОЛБЦОВ
# ============================================================

TIME_COL = "Статистическое время"
WIND_COL = "Средняя скорость ветра(m/s)"
POWER_COL = "Нормализованная активная мощность"
TEMP_COL = "Средняя температура окружающей среды(°C)"


def load_turbine(path: Path, turbine_name: str) -> pd.DataFrame:
    """
    Загружает данные одной турбины и переводит
    10-минутные данные в почасовые.
    """

    print(f"Загрузка {turbine_name}: {path}")

    if not path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {path.resolve()}"
        )

    df = pd.read_csv(path)

    # Проверяем наличие нужных столбцов
    required_columns = {
        TIME_COL,
        WIND_COL,
        POWER_COL,
        TEMP_COL,
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"{turbine_name}: отсутствуют столбцы: {missing}"
        )

    # Оставляем только нужные данные
    df = df[
        [
            TIME_COL,
            WIND_COL,
            POWER_COL,
            TEMP_COL,
        ]
    ].copy()

    # Переименовываем на нормальные английские названия
    df = df.rename(
        columns={
            TIME_COL: "timestamp",
            WIND_COL: "wind_speed",
            POWER_COL: "power",
            TEMP_COL: "temperature",
        }
    )

    # --------------------------------------------------------
    # ВРЕМЯ
    # --------------------------------------------------------

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # ЧИСЛОВЫЕ ЗНАЧЕНИЯ
    # --------------------------------------------------------

    for column in [
        "wind_speed",
        "power",
        "temperature",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Удаляем строки с некорректным временем
    df = df.dropna(subset=["timestamp"])

    # Сортируем
    df = df.sort_values("timestamp")

    # Удаляем дубликаты времени
    df = df.drop_duplicates(
        subset=["timestamp"],
        keep="last"
    )

    # --------------------------------------------------------
    # 10 МИНУТ -> 1 ЧАС
    # --------------------------------------------------------

    df = df.set_index("timestamp")

    hourly = df.resample("1h").agg(
        wind_speed=("wind_speed", "mean"),
        power=("power", "mean"),
        temperature=("temperature", "mean"),
        samples=("power", "count"),
    )

    hourly = hourly.reset_index()

    # ID турбины
    hourly["turbine"] = turbine_name

    # --------------------------------------------------------
    # КАЧЕСТВО ДАННЫХ
    # --------------------------------------------------------

    # В нормальном полном часу должно быть 6 измерений:
    # 00, 10, 20, 30, 40, 50 минут.
    #
    # Часы, где меньше 3 измерений, не используем для обучения.

    bad_hours = hourly["samples"] < 3

    hourly.loc[
        bad_hours,
        ["wind_speed", "power", "temperature"]
    ] = np.nan

    return hourly


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Добавляет временные признаки для ML.
    """

    df = df.copy()

    df["hour"] = df["timestamp"].dt.hour
    df["month"] = df["timestamp"].dt.month
    df["day_of_year"] = df["timestamp"].dt.dayofyear

    # Циклическое кодирование часа
    df["hour_sin"] = np.sin(
        2 * np.pi * df["hour"] / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * df["hour"] / 24
    )

    # Циклическое кодирование сезона
    df["day_sin"] = np.sin(
        2 * np.pi * df["day_of_year"] / 365.25
    )

    df["day_cos"] = np.cos(
        2 * np.pi * df["day_of_year"] / 365.25
    )

    return df


def prepare_training_data() -> pd.DataFrame:

    missing_paths = [path for path in FILES.values() if not path.is_file()]
    if missing_paths:
        missing_files = "\n".join(str(path.resolve()) for path in missing_paths)
        raise FileNotFoundError(
            "Не найдены исходные CSV-файлы турбин:\n"
            f"{missing_files}\n"
            f"Поместите turbine_1.csv и turbine_2.csv в {RAW_DATA_DIR} "
            "или настройте WINDOPS_STORAGE_DIR. "
            "Нужны исторические измерения, включая мощность; "
            "wind_forecast.csv с прогнозом погоды не подходит."
        )

    frames = []

    for turbine_name, path in FILES.items():

        df = load_turbine(
            path=path,
            turbine_name=turbine_name
        )

        frames.append(df)

    # Объединяем WT_1 + WT_2
    data = pd.concat(
        frames,
        ignore_index=True
    )

    data = add_time_features(data)

    # Сортировка
    data = data.sort_values(
        ["timestamp", "turbine"]
    )

    # --------------------------------------------------------
    # УДАЛЯЕМ НЕПОЛНЫЕ СТРОКИ ИЗ TRAIN DATA
    # --------------------------------------------------------

    training_data = data.dropna(
        subset=[
            "wind_speed",
            "temperature",
            "power"
        ]
    ).copy()

    return training_data


def main():

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    training_data = prepare_training_data()

    output = (
        PROCESSED_DIR /
        "hourly_training.csv"
    )

    training_data.to_csv(
        output,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("======================================")
    print(" ДАННЫЕ ПОДГОТОВЛЕНЫ")
    print("======================================")

    print(
        f"Количество почасовых строк: "
        f"{len(training_data)}"
    )

    print(
        f"Начало: "
        f"{training_data['timestamp'].min()}"
    )

    print(
        f"Конец: "
        f"{training_data['timestamp'].max()}"
    )

    print()

    print(
        training_data[
            [
                "timestamp",
                "turbine",
                "wind_speed",
                "temperature",
                "power",
                "samples",
            ]
        ].head(20).to_string(index=False)
    )

    print()
    print(
        f"Сохранено в:"
        f"\n{output.resolve()}"
    )


if __name__ == "__main__":
    main()
