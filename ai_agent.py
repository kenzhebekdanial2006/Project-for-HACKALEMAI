from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
load_dotenv(ROOT / "backend" / ".env")
STORAGE_DIR = Path(os.getenv("WINDOPS_STORAGE_DIR") or "storage").expanduser()
if not STORAGE_DIR.is_absolute():
    STORAGE_DIR = ROOT / STORAGE_DIR
BACKEND_FORECAST_PATH = STORAGE_DIR / "forecasts" / "latest.json"

FORECAST_PATH = (
    BASE_DIR
    / "predictions"
    / "live"
    / "forecast_live.json"
)

ANALYSIS_PATH = (
    BASE_DIR
    / "predictions"
    / "live"
    / "analysis_live.json"
)


# ============================================================
# OPENAI
# ============================================================

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip() or "gpt-5.4-mini"


# ============================================================
# LOAD FORECAST
# ============================================================

def load_forecast() -> dict:

    if not FORECAST_PATH.exists():
        if not BACKEND_FORECAST_PATH.exists():
            raise FileNotFoundError(
                "Live forecast не найден. Запустите npm run dev и дождитесь расчёта прогноза.\n"
                f"Проверены: {FORECAST_PATH} и {BACKEND_FORECAST_PATH}"
            )
        return adapt_backend_forecast(json.loads(BACKEND_FORECAST_PATH.read_text(encoding="utf-8")))

    return json.loads(
        FORECAST_PATH.read_text(
            encoding="utf-8"
        )
    )


def adapt_backend_forecast(forecast: dict) -> dict:
    """Use the published CatBoost predictions without recalculating power."""
    if forecast.get("mode") != "live":
        raise ValueError("Для live-анализа требуется текущий, а не архивный прогноз.")
    issued = pd.Timestamp(forecast["issuedAt"])
    now = pd.Timestamp.now(tz="UTC")
    refresh = max(300, int(os.getenv("WINDOPS_REFRESH_SECONDS") or 3600))
    if issued.tzinfo is None or issued > now or (now - issued).total_seconds() > refresh * 1.5:
        raise ValueError("Прогноз устарел или имеет неверное время. Обновите прогноз в приложении.")
    records = sorted(forecast["records"], key=lambda row: pd.Timestamp(row["timestamp"]))
    times = [pd.Timestamp(row["timestamp"]) for row in records]
    if len(times) != 48 or any(time.tzinfo is None for time in times):
        raise ValueError("Ожидались 48 часов прогноза с часовым поясом.")
    if any(right - left != pd.Timedelta(hours=1) for left, right in zip(times, times[1:])):
        raise ValueError("Часы прогноза должны идти подряд без пропусков и повторов.")
    rows = []
    for horizon, record in enumerate(records, start=1):
        weather = {
            "wind_speed_120m": record["windSpeed120m"],
            "wind_gusts_10m": record["gusts"],
            "temperature_2m": record["temperature"],
            "wind_direction_120m": record["windDirection"],
        }
        for turbine, key in (("WT_1", "WT01"), ("WT_2", "WT02")):
            rows.append({"turbine": turbine, "time": record["timestamp"],
                         "forecast_horizon_hour": horizon,
                         "predicted_power": record[key]["prediction"], "weather": dict(weather)})
    return {"generated_at_utc": forecast["issuedAt"], "weather_model": forecast["source"],
            "weather_run_utc": forecast["weatherRun"], "power_model": forecast["modelVersion"],
            "horizon_hours": 48, "forecast_id": forecast["id"], "forecasts": rows}


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_forecast(
    data: dict,
) -> dict:

    forecasts = data.get(
        "forecasts",
        []
    )

    warnings = []

    if len(forecasts) != 96:

        warnings.append(
            f"Ожидалось 96 прогнозов, "
            f"получено {len(forecasts)}."
        )

    turbines = sorted(
        {
            row.get("turbine")
            for row in forecasts
        }
    )

    if turbines != [
        "WT_1",
        "WT_2",
    ]:

        warnings.append(
            f"Неожиданный список турбин: "
            f"{turbines}"
        )

    bad_power = []

    for row in forecasts:

        power = row.get(
            "predicted_power"
        )

        if power is None:

            bad_power.append(
                row.get("time")
            )

            continue

        if not (
            0 <= float(power) <= 1
        ):

            bad_power.append(
                row.get("time")
            )

    if bad_power:

        warnings.append(
            "Есть predicted_power "
            "вне диапазона 0..1."
        )

    return {
        "valid": (
            len(warnings) == 0
        ),
        "warnings": warnings,
    }


# ============================================================
# BUILD COMPACT DATA FOR LLM
# ============================================================

def build_agent_context(
    data: dict,
) -> dict:

    forecasts = data[
        "forecasts"
    ]

    df = pd.DataFrame(
        [
            {
                "turbine": row[
                    "turbine"
                ],

                "time": row[
                    "time"
                ],

                "horizon": row[
                    "forecast_horizon_hour"
                ],

                "power": round(
                    float(
                        row[
                            "predicted_power"
                        ]
                    ),
                    4,
                ),

                "wind120": round(
                    float(
                        row[
                            "weather"
                        ][
                            "wind_speed_120m"
                        ]
                    ),
                    2,
                ),

                "gust10": round(
                    float(
                        row[
                            "weather"
                        ][
                            "wind_gusts_10m"
                        ]
                    ),
                    2,
                ),

                "temperature": round(
                    float(
                        row[
                            "weather"
                        ][
                            "temperature_2m"
                        ]
                    ),
                    1,
                ),

                "direction120": round(
                    float(
                        row[
                            "weather"
                        ][
                            "wind_direction_120m"
                        ]
                    ),
                    1,
                ),
            }

            for row in forecasts
        ]
    )

    # ========================================================
    # SUMMARY PER TURBINE
    # ========================================================

    turbine_summary = {}

    for turbine in sorted(
        df["turbine"].unique()
    ):

        part = (
            df[
                df["turbine"]
                == turbine
            ]
            .sort_values(
                "horizon"
            )
            .copy()
        )

        part["ramp"] = (
            part["power"]
            .diff()
        )

        max_power_row = part.loc[
            part["power"].idxmax()
        ]

        min_power_row = part.loc[
            part["power"].idxmin()
        ]

        max_ramp_up = (
            part["ramp"].max()
        )

        max_ramp_down = (
            part["ramp"].min()
        )

        turbine_summary[
            turbine
        ] = {

            "average_power": round(
                float(
                    part[
                        "power"
                    ].mean()
                ),
                4,
            ),

            "minimum_power": round(
                float(
                    part[
                        "power"
                    ].min()
                ),
                4,
            ),

            "minimum_power_time": (
                min_power_row[
                    "time"
                ]
            ),

            "maximum_power": round(
                float(
                    part[
                        "power"
                    ].max()
                ),
                4,
            ),

            "maximum_power_time": (
                max_power_row[
                    "time"
                ]
            ),

            "average_wind_120m": round(
                float(
                    part[
                        "wind120"
                    ].mean()
                ),
                2,
            ),

            "maximum_wind_120m": round(
                float(
                    part[
                        "wind120"
                    ].max()
                ),
                2,
            ),

            "maximum_gust_10m": round(
                float(
                    part[
                        "gust10"
                    ].max()
                ),
                2,
            ),

            "max_hourly_ramp_up": (
                round(
                    float(
                        max_ramp_up
                    ),
                    4,
                )
                if pd.notna(
                    max_ramp_up
                )
                else 0
            ),

            "max_hourly_ramp_down": (
                round(
                    float(
                        max_ramp_down
                    ),
                    4,
                )
                if pd.notna(
                    max_ramp_down
                )
                else 0
            ),
        }

    # ========================================================
    # HOURLY SERIES
    # ========================================================

    series = []

    for row in df.to_dict(
        orient="records"
    ):

        series.append(
            {
                "turbine": (
                    row["turbine"]
                ),
                "time": (
                    row["time"]
                ),
                "h": int(
                    row["horizon"]
                ),
                "power": float(
                    row["power"]
                ),
                "wind120": float(
                    row["wind120"]
                ),
                "gust10": float(
                    row["gust10"]
                ),
                "temperature": float(
                    row[
                        "temperature"
                    ]
                ),
            }
        )

    return {

        "forecast_metadata": {

            "generated_at_utc": (
                data.get(
                    "generated_at_utc"
                )
            ),

            "weather_model": (
                data.get(
                    "weather_model"
                )
            ),

            "weather_run_utc": (
                data.get(
                    "weather_run_utc"
                )
            ),

            "power_model": (
                data.get(
                    "power_model"
                )
            ),

            "horizon_hours": (
                data.get(
                    "horizon_hours"
                )
            ),
        },

        "turbine_summary": (
            turbine_summary
        ),

        "hourly_forecast": (
            series
        ),
    }


# ============================================================
# JSON PARSER
# ============================================================

def parse_llm_json(
    text: str,
) -> dict:

    cleaned = (
        text.strip()
    )

    if cleaned.startswith(
        "```"
    ):

        cleaned = cleaned.replace(
            "```json",
            "",
            1,
        )

        cleaned = cleaned.replace(
            "```",
            "",
        )

        cleaned = cleaned.strip()

    try:

        return json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        start = cleaned.find(
            "{"
        )

        end = cleaned.rfind(
            "}"
        )

        if (
            start == -1
            or end == -1
            or end <= start
        ):

            raise ValueError(
                "LLM не вернула "
                "валидный JSON."
            )

        return json.loads(
            cleaned[
                start:end + 1
            ]
        )


# ============================================================
# OPENAI LLM
# ============================================================

def call_openai_agent(
    context: dict,
) -> dict:

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "Переменная OPENAI_API_KEY "
            "не установлена."
        )

    client = OpenAI(
        base_url="https://api.openai.com/v1",
        api_key=api_key,
        timeout=60.0,
        max_retries=0,
    )

    system_prompt = """
Ты — аналитический AI-агент ветроэлектростанции.

Числовой прогноз мощности уже рассчитан ML-моделью CatBoost.
Ты НЕ должен изменять, пересчитывать или придумывать predicted_power.

predicted_power нормализована:
0.0 = 0% номинальной мощности,
1.0 = 100% номинальной мощности.

Не называй мощность в MW, потому что номинальная мощность
турбин не предоставлена.

Твои задачи:
1. Проанализировать прогноз на 48 часов.
2. Объяснить основные изменения мощности.
3. Найти периоды низкой и высокой выработки.
4. Найти резкие изменения (ramps).
5. Указать потенциальные риски по ветру и порывам.
6. Проверить логичность прогноза.
7. Решить, есть ли причина запросить новый пересчёт.

Используй ТОЛЬКО переданные данные.
Не придумывай отсутствующую информацию.

Для любых упоминаний времени копируй точные ISO timestamps из hourly_forecast,
включая смещение часового пояса. Для диапазона копируй обе его границы.
Не используй выражения «утром», «ночью», «сегодня» и даты без времени.
Не преобразуй часовой пояс и не называй моменты за пределами прогноза.
trend_24h относится только к forecast_horizon_hour 1–24,
trend_48h — только к forecast_horizon_hour 25–48.
Проверяй, что значения мощности относятся именно к указанному timestamp.

Если прогнозы WT_1 и WT_2 почти одинаковы,
это допустимо: турбины могут получать одинаковый прогноз
из одной погодной ячейки.

Ответ должен быть ТОЛЬКО JSON без markdown.

Формат:

{
  "status": "ok или warning",
  "summary": "краткий итог",
  "trend_24h": "анализ первых 24 часов",
  "trend_48h": "анализ часов 25-48",
  "risks": [
    {
      "severity": "low или medium или high",
      "type": "тип риска",
      "message": "описание"
    }
  ],
  "key_periods": [
    {
      "time": "ISO timestamp или диапазон",
      "description": "что происходит"
    }
  ],
  "recommendations": [
    "рекомендация"
  ],
  "recalculate": false,
  "recalculate_reason": null
}
"""

    user_prompt = json.dumps(
        context,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )

    response = (
        client
        .chat
        .completions
        .create(

            model=OPENAI_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        system_prompt
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        user_prompt
                    ),
                },
            ],

            max_completion_tokens=3000,
            response_format={"type": "json_object"},
        )
    )

    choice = response.choices[0]
    if choice.message.refusal:
        raise RuntimeError("OpenAI отказалась выполнять запрос.")
    if choice.finish_reason != "stop":
        raise RuntimeError(
            f"OpenAI не завершила ответ: {choice.finish_reason}"
        )

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:

        raise RuntimeError(
            "OpenAI вернула "
            "пустой ответ."
        )

    return parse_llm_json(
        content
    )


# ============================================================
# MAIN AGENT
# ============================================================

def analyze_live_forecast() -> dict:

    forecast = load_forecast()

    validation = validate_forecast(
        forecast
    )

    if not validation["valid"]:
        raise ValueError("Некорректный прогноз: " + " ".join(validation["warnings"]))

    context = build_agent_context(
        forecast
    )

    analysis = call_openai_agent(
        context
    )

    result = {

        "status": "ok",

        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "forecast_generated_at_utc": (
            forecast.get(
                "generated_at_utc"
            )
        ),

        "agent_model": (
            OPENAI_MODEL
        ),

        "power_model": (
            forecast.get(
                "power_model"
            )
        ),

        "weather_model": (
            forecast.get(
                "weather_model"
            )
        ),

        "data_validation": (
            validation
        ),

        "analysis": (
            analysis
        ),
    }

    ANALYSIS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ANALYSIS_PATH.write_text(

        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),

        encoding="utf-8",
    )

    return result


# ============================================================
# CLI
# ============================================================

def main():

    result = (
        analyze_live_forecast()
    )

    print()
    print(
        "======================================"
    )

    print(
        " OPENAI AI ANALYSIS ГОТОВ"
    )

    print(
        "======================================"
    )

    analysis = result[
        "analysis"
    ]

    print()
    print(
        "SUMMARY:"
    )

    print(
        analysis.get(
            "summary"
        )
    )

    print()
    print(
        "24H:"
    )

    print(
        analysis.get(
            "trend_24h"
        )
    )

    print()
    print(
        "48H:"
    )

    print(
        analysis.get(
            "trend_48h"
        )
    )

    print()
    print(
        "Recalculate:",
        analysis.get(
            "recalculate"
        )
    )

    print()
    print(
        f"JSON:\n"
        f"{ANALYSIS_PATH.resolve()}"
    )


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        raise SystemExit(
            f"\nОШИБКА: {error}"
        ) from error
