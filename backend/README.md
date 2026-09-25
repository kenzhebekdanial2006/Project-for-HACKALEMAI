# WindOps Python backend

Python-код разделён по назначению. Существующие скрипты организованы в пакет. FastAPI-сервер для live-прогноза находится в корневом `main.py` и использует корневой `forecast_live.py`.

## Live forecast API

Из корня репозитория:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn main:app --reload
```

Swagger: http://127.0.0.1:8000/docs. Для прогноза нужна модель
`models/catboost_weather.cbm`. Результаты сохраняются в
`predictions/live/forecast_live.csv` и `predictions/live/forecast_live.json`.
Эти пути привязаны к расположению `forecast_live.py`.

| Метод | Маршрут | Результат |
| --- | --- | --- |
| GET | `/api/status` | Состояние сервера и наличие прогноза |
| GET | `/api/forecast/latest` | Последний сохранённый прогноз для обеих турбин |
| GET | `/api/forecast/latest/WT_1` | Прогноз первой турбины |
| GET | `/api/forecast/latest/WT_2` | Прогноз второй турбины |
| POST | `/api/recalculate` | Полный цикл: ECMWF → CatBoost → OpenAI-анализ |
| POST | `/api/analysis/recalculate` | Анализ последнего сохранённого прогноза через OpenAI |
| GET | `/api/analysis/latest` | Последний сохранённый AI-анализ |

`GET /api/analysis/latest` возвращает содержимое
`predictions/live/analysis_live.json`, включая `analysis.summary`,
`analysis.trend_24h`, `analysis.trend_48h`, риски и рекомендации.
Запрос не вызывает OpenAI. Если файла нет, возвращается 404;
если файл повреждён или недоступен — 500. Для создания или обновления
анализа задайте `OPENAI_API_KEY` и запустите `python ai_agent.py` из корня.
Время исходного прогноза указано в `forecast_generated_at_utc`.
`POST /api/recalculate` обновляет прогноз, затем анализ; отдельный
`POST /api/analysis/recalculate` обновляет только анализ. Полный цикл возвращает
`forecast_count`, `power_model`, `agent`, `analysis_summary` и `recalculate`.
Поле `recalculate` — рекомендация агента, автоматический повтор не запускается.
При сбое OpenAI запрос возвращает 500; уже записанный новый прогноз сохраняется,
а прежний анализ может относиться к предыдущему прогнозу.

Перед запуском Uvicorn задайте `$env:OPENAI_API_KEY = "ваш_ключ"`
в том же терминале. Если сервер уже работает, перезапустите его из этого
терминала: переменная из другого PowerShell ему не передаётся.

GET читает сохранённый JSON. Если прогноз ещё не создан, общий маршрут
прогноза возвращает 404; вызовите POST `/api/recalculate`, которому нужен
доступ к Open-Meteo и OpenAI. Пересчёт выполняется в пуле потоков.
CORS разрешает `http://localhost:5173` и `http://127.0.0.1:5173`.

```javascript
const response = await fetch('http://localhost:8000/api/forecast/latest');
if (!response.ok) throw new Error(`Forecast API: ${response.status}`);
const data = await response.json();
console.log(data.forecasts);
```

```text
backend/
  windops/
    core/paths.py         единые пути к данным и артефактам
    data/preparation.py   загрузка CSV, очистка, почасовые данные и признаки времени
    weather/client.py     Open-Meteo, проверка ответа, сохранение погодных снимков
    ml/training.py        обучение CatBoost, validation, метрики и сохранение модели
    agent/analysis.py     существующий клиент аналитического агента
    api/                  место для будущих FastAPI routes и schemas
  tests/                  проверки Python-части
  requirements.txt        зависимости существующих модулей
  .env.example            пример переменных окружения
```

## Установка и запуск

Команды выполняются из корня репозитория. Для отдельного Python-окружения:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

Подготовка данных:

```powershell
backend/.venv/Scripts/python.exe -m backend.windops.data.preparation
```

Обучение модели — отдельная длительная операция, запускается явно:

```powershell
backend/.venv/Scripts/python.exe -m backend.windops.ml.training
```

Загрузка текущего прогноза погоды — обращается к Open-Meteo:

```powershell
backend/.venv/Scripts/python.exe -m backend.windops.weather.client
```

На macOS/Linux путь интерпретатора окружения — `backend/.venv/bin/python`. Если зависимости уже установлены в активном окружении, используйте обычный `python`.

Запускайте модули через `-m`, а не прямым путём к `.py`: это сохраняет корректность импортов пакета. Из папки `backend/` допустим короткий вариант `python -m windops.data.preparation` и аналогичные команды для остальных модулей.

## Файлы данных

По умолчанию все пути определяет `windops/core/paths.py`:

| Что                                        | Где                                               |
| ------------------------------------------ | ------------------------------------------------- |
| Исходные измерения                         | `storage/data/raw/turbine_1.csv`, `turbine_2.csv` |
| Почасовые данные                           | `storage/data/processed/hourly_training.csv`      |
| Модели и metadata                          | `storage/models/`                                 |
| Исходные погодные ответы и CSV по запускам | `storage/weather/<timestamp>/`                    |
| Экспортированные прогнозы                  | `storage/forecasts/`                              |
| Будущие отчёты                             | `storage/reports/`                                |

Эти пути не зависят от текущей рабочей папки. Для больших данных можно задать отдельный диск:

```powershell
$env:WINDOPS_STORAGE_DIR = 'D:\WindOpsData'
```

Тогда внутри `D:\WindOpsData` ожидается та же структура `data/raw`, `data/processed`, `models`, `weather`. Относительное значение переменной разрешается относительно корня репозитория. `.env.example` — документация: автоматическая загрузка `.env` пока не добавлена.

Агент читает `NVIDIA_API_KEY` из окружения. В существующем `agent/analysis.py` ещё указан `MODEL_NAME`; для настоящего вызова необходимо выбрать модель. Реорганизация не подключает этот клиент к frontend и не отправляет прогнозы во внешний сервис.

## Как расширять

- Загрузку и проверку новых источников размещать в `weather/` и `data/`.
- При росте ML-кода выделять признаки, обучение, оценку и inference в отдельные модули внутри `ml/`.
- Решения агента и его workflow хранить в `agent/`; HTTP routes должны только вызывать сервисы.
- Общие настройки и инфраструктуру хранить в `core/`.
- Модели, CSV, parquet и другие большие артефакты хранить в `storage/`, а не рядом с Python-кодом.
- Не запускать обучение или сетевые запросы при импорте модулей. Существующие CLI защищены `if __name__ == '__main__'`.

## Проверки без сети и обучения

Из корня репозитория:

```sh
python -m unittest discover -s backend/tests -t .
```

Эти тесты проверяют маршрутизацию файлов и не требуют pandas/CatBoost. При реорганизации обучение модели и внешние API не запускались; алгоритмы сохранены, изменены расположение файлов, импорты путей и документация.
