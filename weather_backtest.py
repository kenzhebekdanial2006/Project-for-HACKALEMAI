"""
weather_backtest.py

Архивные прогнозы ECMWF для честного backtest двух ВЭС.

Мы НЕ используем фактическую историческую погоду.
Мы запрашиваем конкретный архивный запуск ECMWF IFS через:

    https://single-runs-api.open-meteo.com/v1/forecast

Open-Meteo Single Runs API:
    https://open-meteo.com/en/docs/single-runs-api

Пример тестового запуска:

    python weather_backtest.py --start 2026-01-31 --end 2026-02-02

Полный февраль:

    python weather_backtest.py --start 2026-01-31 --end 2026-02-28

Повторно скачать уже существующие даты:

    python weather_backtest.py --start 2026-01-31 --end 2026-02-02 --force
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://single-runs-api.open-meteo.com/v1/forecast"

# ECMWF IFS HRES
MODEL = "ecmwf_ifs"

LOCAL_TIMEZONE = "Asia/Almaty"

# Прогноз мощности нужен на 48 часов
HORIZON_HOURS = 48

# Сколько часов самого weather forecast запросить от ECMWF run.
# Потом из этих 96 часов мы вырежем нужные 48 часов.
API_FORECAST_HOURS = 96


# ============================================================
# МОМЕНТ ФОРМИРОВАНИЯ ПРОГНОЗА
# ============================================================

# Для backtest принимаем правило:
#
# 31 января 23:50 Asia/Almaty
#        ↓
# прогноз с 1 февраля 00:00
#
# 1 февраля 23:50
#        ↓
# прогноз с 2 февраля 00:00
#
# и т.д.

DECISION_HOUR_LOCAL = 23
DECISION_MINUTE_LOCAL = 50


# ============================================================
# ПОЛИТИКА ДОСТУПНОСТИ ECMWF RUN
# ============================================================

# run — это время инициализации модели, а не время,
# когда прогноз уже появился у пользователя.
#
# Для global weather model применяем консервативное правило:
#
#       run + 6 часов + 10 минут
#
# только после этого считаем run доступным.

MODEL_DELAY_HOURS = 6
SAFETY_BUFFER_MINUTES = 10


# ============================================================
# OUTPUT
# ============================================================

OUTPUT_DIR = Path("weather_backtest")


# ============================================================
# КООРДИНАТЫ ТУРБИН
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
# ПОГОДНЫЕ ПРИЗНАКИ
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
# HTTP SESSION
# ============================================================

def create_session() -> requests.Session:
    """
    Создаёт HTTP session с автоматическими retry.
    """

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

        allowed_methods=frozenset(["GET"]),

        respect_retry_after_header=True,

        raise_on_status=False,
    )

    session = requests.Session()

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        )
    )

    return session


# ============================================================
# DECISION TIME
# ============================================================

def get_decision_time(
    forecast_date: pd.Timestamp,
) -> pd.Timestamp:
    """
    Возвращает момент формирования прогноза.

    Например:

        forecast_date = 2026-01-31

    получаем:

        2026-01-31 23:50 Asia/Almaty
    """

    timestamp = pd.Timestamp(
        forecast_date.date()
    )

    timestamp = timestamp.tz_localize(
        LOCAL_TIMEZONE
    )

    timestamp += pd.Timedelta(
        hours=DECISION_HOUR_LOCAL,
        minutes=DECISION_MINUTE_LOCAL,
    )

    return timestamp


# ============================================================
# ЦЕЛЕВЫЕ 48 ЧАСОВ
# ============================================================

def get_target_window(
    decision_time_local: pd.Timestamp,
) -> pd.DatetimeIndex:
    """
    Например:

    Decision:
        31 января 23:50 Алматы

    Forecast starts:
        1 февраля 00:00 Алматы

    Возвращаем 48 часовых точек.
    """

    start_local = decision_time_local.ceil("h")

    start_utc = start_local.tz_convert("UTC")

    expected = pd.date_range(

        start=start_utc,

        periods=HORIZON_HOURS,

        freq="h",
    )

    return expected


# ============================================================
# ECMWF RUN CANDIDATES
# ============================================================

def get_run_candidates(
    decision_time_local: pd.Timestamp,
) -> list[pd.Timestamp]:
    """
    ECMWF IFS запускается примерно:

        00 UTC
        06 UTC
        12 UTC
        18 UTC

    Выбираем самый свежий запуск, который по нашей
    консервативной политике уже мог быть доступен.

    Если он отсутствует в API — пробуем предыдущие.
    """

    decision_utc = decision_time_local.tz_convert(
        "UTC"
    )

    safe_cutoff = (

        decision_utc

        - pd.Timedelta(
            hours=MODEL_DELAY_HOURS
        )

        - pd.Timedelta(
            minutes=SAFETY_BUFFER_MINUTES
        )
    )

    # Округляем вниз:
    #
    # 17:30 -> 12:00
    # 18:20 -> 18:00
    #
    # для циклов 00 / 06 / 12 / 18.
    latest_run = safe_cutoff.floor("6h")

    candidates = [

        latest_run
        - pd.Timedelta(
            hours=6 * i
        )

        for i in range(5)
    ]

    return candidates


# ============================================================
# API REQUEST
# ============================================================

def request_run(
    session: requests.Session,
    run_time: pd.Timestamp,
) -> tuple[Any, str]:
    """
    Загружает полный кусок прогноза конкретного ECMWF run.

    ВАЖНО:
    start_hour / end_hour здесь НЕ используем.

    Получаем 96 forecast hours, после чего нужные 48 часов
    фильтруются функцией parse_weather().
    """

    params = {

        "latitude": ",".join(

            str(
                coordinates["latitude"]
            )

            for coordinates
            in TURBINES.values()
        ),

        "longitude": ",".join(

            str(
                coordinates["longitude"]
            )

            for coordinates
            in TURBINES.values()
        ),

        "models": MODEL,

        "run": run_time.strftime(
            "%Y-%m-%dT%H:%M"
        ),

        "hourly": ",".join(
            HOURLY
        ),

        "wind_speed_unit": "ms",

        "temperature_unit": "celsius",

        "timezone": "UTC",

        "timeformat": "unixtime",

        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ
        #
        # Single Runs API отдаёт прогноз,
        # начинающийся от самого model run.
        #
        # Берём с запасом 96 часов,
        # нужные 48 выберем потом.
        "forecast_hours": API_FORECAST_HOURS,
    }

    response = session.get(

        API_URL,

        params=params,

        timeout=(15, 90),
    )

    if not response.ok:

        raise requests.HTTPError(

            (
                f"HTTP "
                f"{response.status_code}: "
                f"{response.text[:1000]}"
            ),

            response=response,
        )

    try:

        payload = response.json()

    except requests.JSONDecodeError as error:

        raise ValueError(
            "API вернул не JSON."
        ) from error

    if (
        isinstance(payload, dict)
        and payload.get("error")
    ):

        raise ValueError(

            payload.get(
                "reason",
                "Open-Meteo API error",
            )
        )

    return (
        payload,
        response.url,
    )


# ============================================================
# ПОИСК ДОСТУПНОГО RUN
# ============================================================

class NoValidRunError(RuntimeError):
    """Все кандидаты прогноза недоступны или не прошли проверку."""


def fetch_available_run(
    session: requests.Session,
    decision_time_local: pd.Timestamp,
    expected: pd.DatetimeIndex,
    forecast_date: pd.Timestamp,
):
    """
    Пробует несколько ECMWF runs.

    HTTP 200 недостаточно:
    дополнительно проверяем, что run реально содержит
    все необходимые погодные значения на целевые 48 часов.

    Если run содержит NaN / пропуски —
    автоматически пробуем предыдущий run.
    """

    candidates = get_run_candidates(
        decision_time_local
    )

    errors = []

    for run_time in candidates:

        print(
            f"    пробуем ECMWF run "
            f"{run_time.isoformat()}"
        )

        try:

            # 1. Получаем run
            payload, request_url = request_run(
                session=session,
                run_time=run_time,
            )

            # 2. Сразу проверяем содержимое
            weather = parse_weather(
                payload=payload,
                expected=expected,
                forecast_date=forecast_date,
                decision_time_local=decision_time_local,
                run_time=run_time,
            )

            print(
                f"      ✓ run валиден"
            )

            return (
                run_time,
                payload,
                request_url,
                weather,
            )

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as error:

            error_text = str(error)

            errors.append(
                (
                    run_time.isoformat(),
                    error_text,
                )
            )

            print(
                f"      ✗ run непригоден: "
                f"{error_text}"
            )

            print(
                "      пробуем предыдущий..."
            )

    raise NoValidRunError(
        "Не удалось найти валидный ECMWF run. "
        f"Проверено {len(candidates)} runs. "
        f"Ошибки: {errors}"
    )

def parse_weather(
    payload: Any,
    expected: pd.DatetimeIndex,
    forecast_date: pd.Timestamp,
    decision_time_local: pd.Timestamp,
    run_time: pd.Timestamp,
) -> pd.DataFrame:
    """
    Проверяет API response и выбирает ровно наши 48 часов.
    """

    # При нескольких координатах Open-Meteo
    # должен вернуть list.
    if (
        not isinstance(payload, list)
        or len(payload) != len(TURBINES)
    ):

        raise ValueError(
            "Ожидался список ответов "
            "для двух координат."
        )

    frames = []

    decision_utc = decision_time_local.tz_convert(
        "UTC"
    )

    estimated_available_at = (

        run_time

        + pd.Timedelta(
            hours=MODEL_DELAY_HOURS
        )

        + pd.Timedelta(
            minutes=SAFETY_BUFFER_MINUTES
        )
    )

    # Защита от look-ahead
    if estimated_available_at > decision_utc:

        raise ValueError(

            "Выбран ECMWF run, который "
            "по нашей availability policy "
            "ещё не должен был быть доступен."
        )

    for index, (
        (name, coordinates),
        item,
    ) in enumerate(
        zip(
            TURBINES.items(),
            payload,
        )
    ):

        # ----------------------------------------------------
        # BASIC RESPONSE CHECK
        # ----------------------------------------------------

        if not isinstance(
            item,
            dict,
        ):

            raise ValueError(
                f"{name}: "
                "ответ не является объектом."
            )

        if item.get("error"):

            raise ValueError(
                f"{name}: "
                f"{item}"
            )

        if (
            "location_id" in item
            and item["location_id"] != index
        ):

            raise ValueError(
                f"{name}: "
                "неожиданный location_id."
            )

        hourly = item.get(
            "hourly"
        )

        if not isinstance(
            hourly,
            dict,
        ):

            raise ValueError(
                f"{name}: "
                "отсутствует hourly."
            )

        # ----------------------------------------------------
        # DATAFRAME
        # ----------------------------------------------------

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
                f"отсутствуют поля "
                f"{sorted(missing)}"
            )

        df = df[
            [
                "time",
                *HOURLY,
            ]
        ].copy()

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        df["time"] = pd.to_datetime(

            df["time"],

            unit="s",

            utc=True,

            errors="raise",
        )

        df = (

            df
            .sort_values("time")
            .drop_duplicates(
                subset=["time"]
            )
            .reset_index(drop=True)
        )

        # ====================================================
        # ГЛАВНОЕ ИСПРАВЛЕНИЕ
        #
        # API вернул прогноз начиная от MODEL RUN.
        #
        # Теперь вырезаем только наши целевые 48 часов.
        # ====================================================

        df = df[

            (df["time"] >= expected[0])

            &

            (df["time"] <= expected[-1])

        ].copy()

        df = df.reset_index(
            drop=True
        )

        actual_index = (
            pd.DatetimeIndex(
                df["time"]
            )
        )

        if not actual_index.equals(
            expected
        ):

            actual_start = (
                actual_index.min()
                if len(actual_index)
                else None
            )

            actual_end = (
                actual_index.max()
                if len(actual_index)
                else None
            )

            raise ValueError(

                f"{name}: после фильтрации "
                f"ожидалось "
                f"{HORIZON_HOURS} часов, "
                f"получено {len(df)}. "

                f"Ожидалось: "
                f"{expected[0]} -> "
                f"{expected[-1]}. "

                f"Получено: "
                f"{actual_start} -> "
                f"{actual_end}."
            )

        # ----------------------------------------------------
        # NUMERIC VALIDATION
        # ----------------------------------------------------

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
                    float("inf"),
                    float("-inf"),
                ]
            )
        )

        if invalid.any().any():

            bad_columns = (

                invalid.columns[
                    invalid.any()
                ]
                .tolist()
            )

            raise ValueError(

                f"{name}: "
                "NaN/Inf в погодных данных: "
                f"{bad_columns}"
            )

        df[HOURLY] = values

        # ----------------------------------------------------
        # UNITS
        # ----------------------------------------------------

        units = item.get(
            "hourly_units",
            {}
        )

        for variable in HOURLY:

            if variable.startswith(
                (
                    "wind_speed_",
                    "wind_gusts_",
                )
            ):

                unit = units.get(
                    variable
                )

                if unit != "m/s":

                    raise ValueError(

                        f"{name}: "
                        f"неожиданная единица "
                        f"{variable}: "
                        f"{unit}"
                    )

                if (
                    df[variable] < 0
                ).any():

                    raise ValueError(

                        f"{name}: "
                        f"обнаружена "
                        f"отрицательная скорость "
                        f"в {variable}"
                    )

        if (
            units.get("temperature_2m")
            != "°C"
        ):

            raise ValueError(

                f"{name}: "
                "temperature_2m имеет "
                f"единицу "
                f"{units.get('temperature_2m')}"
            )

        if (
            units.get("surface_pressure")
            != "hPa"
        ):

            raise ValueError(

                f"{name}: "
                "surface_pressure имеет "
                f"единицу "
                f"{units.get('surface_pressure')}"
            )

        # ----------------------------------------------------
        # TURBINE
        # ----------------------------------------------------

        df.insert(
            0,
            "turbine",
            name,
        )

        df.insert(
            1,
            "latitude",
            coordinates["latitude"],
        )

        df.insert(
            2,
            "longitude",
            coordinates["longitude"],
        )

        # ----------------------------------------------------
        # LOCAL TIME
        # ----------------------------------------------------

        df["time_local"] = (

            df["time"]
            .dt
            .tz_convert(
                LOCAL_TIMEZONE
            )
        )

        # ----------------------------------------------------
        # BACKTEST METADATA
        # ----------------------------------------------------

        df["forecast_date"] = (
            forecast_date.strftime(
                "%Y-%m-%d"
            )
        )

        df[
            "decision_time_local"
        ] = (
            decision_time_local
            .isoformat()
        )

        df[
            "decision_time_utc"
        ] = (
            decision_utc.isoformat()
        )

        df[
            "run_initialization_utc"
        ] = (
            run_time.isoformat()
        )

        df[
            "estimated_run_available_at_utc"
        ] = (
            estimated_available_at
            .isoformat()
        )

        # ----------------------------------------------------
        # FORECAST LEAD
        # ----------------------------------------------------

        df[
            "lead_from_decision_hours"
        ] = (

            (
                df["time"]
                - decision_utc
            )

            .dt
            .total_seconds()

            / 3600
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

        # Номер часа внутри нашего 48h forecast
        df[
            "forecast_horizon_hour"
        ] = range(
            1,
            len(df) + 1,
        )

        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        df["weather_model"] = MODEL

        df["source"] = (
            "open-meteo/single-runs"
        )

        # ----------------------------------------------------
        # GRID INFORMATION
        # ----------------------------------------------------

        df["grid_latitude"] = (
            item.get("latitude")
        )

        df["grid_longitude"] = (
            item.get("longitude")
        )

        df["grid_elevation"] = (
            item.get("elevation")
        )

        frames.append(
            df
        )

    result = pd.concat(

        frames,

        ignore_index=True,
    )

    # 48 часов × 2 турбины = 96 строк
    expected_rows = (
        HORIZON_HOURS
        * len(TURBINES)
    )

    if len(result) != expected_rows:

        raise ValueError(

            f"Ожидалось "
            f"{expected_rows} строк, "
            f"получено {len(result)}."
        )

    return result


# ============================================================
# ОБРАБОТКА ОДНОГО ДНЯ
# ============================================================

def process_date(
    session: requests.Session,
    forecast_date: pd.Timestamp,
    force: bool = False,
) -> pd.DataFrame:

    date_string = (
        forecast_date.strftime(
            "%Y-%m-%d"
        )
    )

    run_dir = (

        OUTPUT_DIR

        / forecast_date.strftime(
            "%Y%m%d"
        )
    )

    csv_path = (
        run_dir
        / "forecast.csv"
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if (
        csv_path.exists()
        and not force
    ):

        print()
        print(
            f"{date_string}: "
            "уже скачано — используем cache."
        )

        return pd.read_csv(
            csv_path
        )

    run_dir.mkdir(

        parents=True,

        exist_ok=True,
    )

    # --------------------------------------------------------
    # DECISION TIME
    # --------------------------------------------------------

    decision_time_local = (
        get_decision_time(
            forecast_date
        )
    )

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    expected = get_target_window(
        decision_time_local
    )

    print()
    print(
        "======================================"
    )

    print(
        f"FORECAST DATE: "
        f"{date_string}"
    )

    print(
        f"Decision local: "
        f"{decision_time_local}"
    )

    print(
        f"Decision UTC:   "
        f"{decision_time_local.tz_convert('UTC')}"
    )

    print(
        f"Target UTC: "
        f"{expected[0]} "
        f"-> "
        f"{expected[-1]}"
    )

    print(
        f"Target local: "
        f"{expected[0].tz_convert(LOCAL_TIMEZONE)} "
        f"-> "
        f"{expected[-1].tz_convert(LOCAL_TIMEZONE)}"
    )

    # --------------------------------------------------------
    # FIND RUN
    # --------------------------------------------------------

    (
        run_time,
        payload,
        request_url,
        weather,
    ) = fetch_available_run(

        session=session,

        decision_time_local=decision_time_local,

        expected=expected,

        forecast_date=forecast_date,
    )

    print(
        f"Используем run: "
        f"{run_time}"
    )

    estimated_available_at = (

        run_time

        + pd.Timedelta(
            hours=MODEL_DELAY_HOURS
        )

        + pd.Timedelta(
            minutes=(
                SAFETY_BUFFER_MINUTES
            )
        )
    )

    print(
        "Estimated available: "
        f"{estimated_available_at}"
    )

    # --------------------------------------------------------
    # RAW RESPONSE
    # --------------------------------------------------------

    snapshot = {

        "mode": "backtest",

        "forecast_date": (
            date_string
        ),

        "decision_time_local": (
            decision_time_local
            .isoformat()
        ),

        "decision_time_utc": (
            decision_time_local
            .tz_convert("UTC")
            .isoformat()
        ),

        "weather_model": MODEL,

        "run_initialization_utc": (
            run_time.isoformat()
        ),

        "availability_policy": {

            "model_delay_hours": (
                MODEL_DELAY_HOURS
            ),

            "safety_buffer_minutes": (
                SAFETY_BUFFER_MINUTES
            ),

            "estimated_available_at_utc": (
                estimated_available_at
                .isoformat()
            ),

            "exact_historical_api_availability_known": False,
        },

        "endpoint": API_URL,

        "request_url": request_url,

        "api_forecast_hours": (
            API_FORECAST_HOURS
        ),

        "target_start_utc": (
            expected[0]
            .isoformat()
        ),

        "target_end_utc": (
            expected[-1]
            .isoformat()
        ),

        "response": payload,
    }

    json_path = (
        run_dir
        / "response.json"
    )

    json_path.write_text(

        json.dumps(

            snapshot,

            ensure_ascii=False,

            indent=2,

            allow_nan=False,
        ),

        encoding="utf-8",
    )

    # --------------------------------------------------------
    # SAVE CSV
    # --------------------------------------------------------

    weather.to_csv(

        csv_path,

        index=False,

        encoding="utf-8-sig",
    )

    print(
        f"Сохранено "
        f"{len(weather)} строк:"
    )

    print(
        csv_path.resolve()
    )

    return weather


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    start_date: str,
    end_date: str,
    force: bool = False,
    skip_unavailable: bool = False,
) -> pd.DataFrame:

    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True,
    )

    dates = pd.date_range(

        start=start_date,

        end=end_date,

        freq="D",
    )

    frames = []
    skipped_dates = []
    skipped_path = OUTPUT_DIR / "skipped_dates.json"

    def save_skipped_dates():
        skipped_path.write_text(
            json.dumps(
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "skipped_dates": skipped_dates,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if skip_unavailable:
        save_skipped_dates()

    with create_session() as session:

        for forecast_date in dates:

            try:

                frame = process_date(

                    session=session,

                    forecast_date=(
                        forecast_date
                    ),

                    force=force,
                )

                frames.append(
                    frame
                )

            except NoValidRunError as error:
                if not skip_unavailable:
                    raise
                skipped_dates.append({
                    "forecast_date": str(forecast_date.date()),
                    "reason": str(error),
                })
                save_skipped_dates()
                print(f"ПРОПУСК {forecast_date.date()}: {error}")
                print(f"Причина записана в {skipped_path}")

            except Exception as error:

                print()
                print(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                print(
                    f"ОШИБКА "
                    f"{forecast_date.date()}:"
                )

                print(
                    error
                )

                print(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                raise

            # Не бомбим API запросами
            time.sleep(0.3)

    if not frames:

        raise RuntimeError(
            "Backtest не содержит данных."
        )

    # --------------------------------------------------------
    # COMBINED DATASET
    # --------------------------------------------------------

    combined = pd.concat(

        frames,

        ignore_index=True,
    )

    output_path = (

        OUTPUT_DIR

        / "weather_backtest_all.csv"
    )

    combined.to_csv(

        output_path,

        index=False,

        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        " BACKTEST ГОТОВ"
    )

    print(
        "======================================"
    )

    print(
        f"Forecast dates: "
        f"{start_date} "
        f"-> "
        f"{end_date}"
    )

    print(
        f"Количество успешных дат: "
        f"{len(frames)} из {len(dates)}"
    )

    if skip_unavailable:
        print(f"Пропущено дат: {len(skipped_dates)}; отчёт: {skipped_path}")

    print(
        f"Всего строк: "
        f"{len(combined)}"
    )

    print(
        f"Турбины: "
        f"{sorted(combined['turbine'].unique())}"
    )

    print(
        f"\nСохранено:\n"
        f"{output_path.resolve()}"
    )

    return combined


# ============================================================
# COMMAND LINE
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(

        description=(
            "ECMWF Single Runs "
            "historical weather backtest"
        )
    )

    parser.add_argument(

        "--start",

        default="2026-01-31",

        help=(
            "Первая дата decision point, "
            "формат YYYY-MM-DD"
        ),
    )

    parser.add_argument(

        "--end",

        default="2026-02-28",

        help=(
            "Последняя дата decision point, "
            "формат YYYY-MM-DD"
        ),
    )

    parser.add_argument(

        "--force",

        action="store_true",

        help=(
            "Повторно загрузить данные, "
            "даже если forecast.csv "
            "уже существует."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_args()

    run_backtest(

        start_date=args.start,

        end_date=args.end,

        force=args.force,
    )


if __name__ == "__main__":

    try:

        main()

    except (
        requests.RequestException,
        ValueError,
        RuntimeError,
        TypeError,
        OSError,
    ) as error:

        raise SystemExit(
            f"\nОШИБКА: {error}"
        ) from error
