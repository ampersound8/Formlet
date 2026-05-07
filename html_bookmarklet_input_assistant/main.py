from __future__ import annotations

try:
    from .app_gui import MainApplication
except ImportError:  # pragma: no cover - direct script execution support
    from app_gui import MainApplication


def main() -> None:
    app = MainApplication()
    app.run()


if __name__ == "__main__":
    main()

