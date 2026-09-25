"""Data-grounded operator answers, with an optional server-side language model."""
from __future__ import annotations

import re

from .language_model import FALLBACK_NOTICE, external_answer


def percent(value):
    return f"{round(value * 100)}%"


def answer_question(question, forecast, settings, locale="en", turbines=None, *, history=None, diagnostics=None):
    rows = forecast["records"]
    peak = max(rows, key=lambda row: row["WT01"]["prediction"])
    low = min(rows, key=lambda row: row["windSpeed120m"])
    question_lower = question.lower()
    references = ["Forecast data", "Weather forecast"]
    if re.search(r"peak|highest|maximum|пик|максим|ең жоғары|жоғары қуат", question_lower):
        answer = f"Expected peak: WT-01 {percent(peak['WT01']['prediction'])} at {peak['timestamp']} UTC; WT-02 {percent(peak['WT02']['prediction'])}. Wind at 120 m: {peak['windSpeed120m']:.1f} m/s."
    elif re.search(r"confiden|уверен|довер|над[её]ж|сенімді", question_lower):
        answer = f"System confidence: {forecast['confidence']}/100. It uses weather completeness, validation error and freshness. Turbine behaviour verification and independent weather agreement are unavailable. This is not a probability of forecast accuracy."
        references = ["Forecast data", "Diagnostics"]
    elif re.search(r"decreas|drop|decline|tomorrow|пада|снижа|сниже|сниз|завтра|төменде|азая|ертең", question_lower):
        answer = f"Lowest forecast wind: {low['windSpeed120m']:.1f} m/s at {low['timestamp']} UTC. Expected power: WT-01 {percent(low['WT01']['prediction'])}, WT-02 {percent(low['WT02']['prediction'])}. Select this hour in the chart to see the model contributions."
    elif re.search(r"compar|twin|anomal|deviat|telemetr|current power|сравн|аномал|отклон|телеметр|показани|текущая мощность|салыстыр|ауытқу|өлшем|ағымдағы қуат", question_lower):
        first = rows[0]
        references = ["Twin comparison", "Forecast data"]
        answer = f"Next-hour expected power: WT-01 {percent(first['WT01']['prediction'])}, WT-02 {percent(first['WT02']['prediction'])}. Current power telemetry is not connected. Historical readings cannot establish the current operating state or a current anomaly."
        fresh = [turbine for turbine in turbines or [] if turbine.get("observed") is not None]
        if fresh:
            readings = {turbine["id"]: turbine for turbine in fresh}
            one, two = readings.get("WT-01"), readings.get("WT-02")
            answer = (f"Current measurements: WT-01 {percent(one['observed']) if one else 'Unavailable'} at {one['observedAt'] if one else 'Unavailable'}; "
                      f"WT-02 {percent(two['observed']) if two else 'Unavailable'} at {two['observedAt'] if two else 'Unavailable'}. "
                      "Receiving measurements alone does not confirm normal operation or an anomaly. Compare power only for matching times and averaging intervals.")
            references.append("Current turbine readings")
        elif any(turbine.get("measurement") is not None for turbine in turbines or []):
            answer = "Current turbine measurements are out of date or unavailable. Check the measurement source before comparing turbine behaviour."
            references.append("Current turbine readings")
    elif re.search(r"chang|previous|измен|предыдущ|өзгер|алдыңғы", question_lower):
        change = forecast.get("changeSincePrevious")
        answer = (f"Average expected power changed by {change:+.2f} percentage points across hours shared with the previous forecast."
                  if change is not None else "No previous forecast is available for comparison. Refresh the forecast to compare overlapping hours.")
        references = ["Forecast data", "Agent event log"]
    else:
        answer = "Ask about peak power, wind conditions, turbine comparison, forecast changes or confidence. Answers are calculated from the published forecast and available measurements."
    provider = "Data analysis"
    failure = None
    if settings.llm_provider:
        generated, failure = external_answer(question, forecast, settings, locale, turbines, history, diagnostics)
        if generated:
            answer, provider = generated, settings.llm_provider
            references = list(dict.fromkeys([*references, "Forecast data", "Diagnostics",
                *(["Current turbine readings"] if any(row.get("observed") is not None for row in turbines or []) else [])]))
    return {"answer": answer, "references": references, "provider": provider,
            "model": settings.llm_model if provider != "Data analysis" else None,
            "forecastId": forecast["id"], "fallback": bool(failure), "fallbackReason": failure,
            "notice": FALLBACK_NOTICE if failure else None}
