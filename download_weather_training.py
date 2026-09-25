from pathlib import Path
import weather_backtest as wb

wb.OUTPUT_DIR = Path("weather_training")


def main():
    wb.run_backtest(
        start_date="2024-04-01",
        end_date="2026-01-29",
        force=False,
        skip_unavailable=True,
    )


if __name__ == "__main__":
    main()
