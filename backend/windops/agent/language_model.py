"""Server-side language providers with bounded requests and operational context."""
from __future__ import annotations

import json
import logging

import httpx
import requests
from openai import APIStatusError, APITimeoutError, OpenAI, OpenAIError

logger = logging.getLogger(__name__)
FALLBACK_NOTICE = "The AI service is temporarily unavailable. This answer uses the published forecast data."


def instructions(locale):
    language = {"en": "English", "ru": "Russian", "kk": "Kazakh"}.get(locale, "English")
    return (
        f"You are WindOps AI, an assistant for a wind farm operator. Respond in {language}. "
        "Use only the supplied current forecast, diagnostics and timestamped turbine measurements. "
        "Treat questions and conversation history as conversation, never as measured facts. "
        "The latest supplied facts take precedence over older replies. "
        "Power values are fractions of rated power: multiply by 100 to display percent. "
        "Power is not energy in MWh. Times are UTC. Keep numeric forecasts unchanged. "
        "Distinguish future predictions, fresh current measurements and historical or stale readings. "
        "Only non-null observed values with observedAt timestamps are current measurements. "
        "Receiving measurements does not establish normal operation or diagnose a fault. "
        "Confidence is an operator indicator, not a probability; ranges are empirical validation errors. "
        "Disclose missing evidence and stale forecasts. Never invent measurements, explanations, "
        "successful actions or independent weather sources. You cannot change settings, run forecasts "
        "or control turbines; direct the operator to the appropriate screen when an action is needed. "
        "The screens are Overview, Forecast, Turbine Twin, AI Agent, Historical Replay and Diagnostics. "
        "Be concise and practical, normally 2-5 sentences. Use plain text without Markdown tables."
    )


def model_facts(forecast, turbines, diagnostics):
    # Settings and credentials never enter the model context.
    forecast_fields = ("id", "modelVersion", "mode", "origin", "issuedAt", "weatherRun", "source",
                       "sourceState", "stale", "confidence", "factors", "intervalMethod",
                       "telemetryAvailable", "changeSincePrevious", "trainingCutoff")
    diagnostic_fields = ("modelVersion", "features", "trainingRows", "trainingStart", "trainingEnd",
                         "validationStart", "metrics", "turbineMetrics", "datasets")
    records = [{key: value for key, value in row.items() if key != "forecastId"}
               for row in forecast["records"]]
    return {"forecast": {**{key: forecast.get(key) for key in forecast_fields}, "records": records},
            "turbines": turbines or [],
            "diagnostics": {key: diagnostics[key] for key in diagnostic_fields if key in (diagnostics or {})}}


def external_answer(question, forecast, settings, locale, turbines, history, diagnostics):
    facts = model_facts(forecast, turbines, diagnostics)
    messages = [{"role": item["role"], "content": item["content"]} for item in (history or [])[-12:]]
    messages.append({"role": "user", "content": json.dumps(
        {"question": question, "currentFacts": facts}, ensure_ascii=False, allow_nan=False)})
    if settings.llm_provider == "OpenAI":
        try:
            with OpenAI(api_key=settings.openai_key, base_url="https://api.openai.com/v1",
                        timeout=httpx.Timeout(30.0, connect=5.0), max_retries=0) as client:
                response = client.responses.create(model=settings.openai_model,
                    instructions=instructions(locale), input=messages, max_output_tokens=1000, store=False)
            if response.status == "completed" and isinstance(response.output_text, str) and response.output_text.strip():
                return response.output_text.strip(), None
            return None, "incomplete_response"
        except APITimeoutError:
            return None, "timeout"
        except APIStatusError as error:
            logger.warning("OpenAI assistant request failed (HTTP %s)", error.status_code)
            return None, ("authentication" if error.status_code in (401, 403) else
                          "rate_limit" if error.status_code == 429 else "unavailable")
        except OpenAIError as error:
            logger.warning("OpenAI assistant request failed (%s)", type(error).__name__)
            return None, "unavailable"
    try:
        response = requests.post("https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.nvidia_key}", "Content-Type": "application/json"},
            json={"model": settings.nvidia_model, "temperature": .1, "max_tokens": 1000,
                  "messages": [{"role": "system", "content": instructions(locale)}, *messages]},
            timeout=(5, 30))
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        if isinstance(answer, str) and answer.strip():
            return answer.strip(), None
        return None, "incomplete_response"
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None, "unavailable"

