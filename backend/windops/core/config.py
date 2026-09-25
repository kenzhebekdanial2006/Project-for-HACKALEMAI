"""Server-only settings. No secret is returned by any API response."""
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / ".env")


def local_path(name: str, default: str) -> Path:
    path = Path(os.environ.get(name) or default).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    task_dir: Path = local_path("WINDOPS_TASK_DIR", "task")
    storage_dir: Path = local_path("WINDOPS_STORAGE_DIR", "storage")
    refresh_seconds: int = max(300, int(os.environ.get("WINDOPS_REFRESH_SECONDS") or 3600))
    weather_key: str = field(default=os.environ.get("OPEN_METEO_API_KEY", ""), repr=False)
    openai_key: str = field(default=os.environ.get("OPENAI_API_KEY", "").strip(), repr=False)
    openai_model: str = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-5.4-mini"
    nvidia_key: str = field(default=os.environ.get("NVIDIA_API_KEY", ""), repr=False)
    nvidia_model: str = os.environ.get("NVIDIA_MODEL", "")
    telemetry_file: Path | None = local_path("WINDOPS_TELEMETRY_FILE", "") if os.environ.get("WINDOPS_TELEMETRY_FILE") else None
    telemetry_key: str = field(default=os.environ.get("WINDOPS_TELEMETRY_KEY", ""), repr=False)
    telemetry_max_age_seconds: int = max(60, int(os.environ.get("WINDOPS_TELEMETRY_MAX_AGE_SECONDS") or 1200))

    @property
    def llm_provider(self) -> str | None:
        if self.openai_key:
            return "OpenAI"
        if self.nvidia_key and self.nvidia_model:
            return "NVIDIA"
        return None

    @property
    def llm_model(self) -> str | None:
        if self.llm_provider == "OpenAI":
            return self.openai_model
        return self.nvidia_model if self.llm_provider == "NVIDIA" else None


settings = Settings()
