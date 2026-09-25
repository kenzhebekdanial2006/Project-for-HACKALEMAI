import os
import requests


NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def analyze_forecast(forecast_data):

    payload = {
        "model": "MODEL_NAME",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты аналитический агент ветроэлектростанции. "
                    "Не изменяй числовой прогноз ML-модели. "
                    "Анализируй качество данных, аномалии и тренды."
                )
            },
            {
                "role": "user",
                "content": str(forecast_data)
            }
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        URL,
        json=payload,
        headers=headers,
        timeout=60
    )

    response.raise_for_status()

    return response.json()