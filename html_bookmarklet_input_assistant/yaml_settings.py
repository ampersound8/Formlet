from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - handled by GUI
    yaml = None  # type: ignore[assignment]

try:
    from .models import FillRule, SavedFormSettings
except ImportError:  # pragma: no cover
    from models import FillRule, SavedFormSettings


class YamlSettingsError(ValueError):
    pass


class FormSettingsYaml:
    def load(self, path: Path) -> SavedFormSettings:
        if yaml is None:
            raise YamlSettingsError("PyYAML がインストールされていません。pip install PyYAML を実行してください。")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            data = yaml.safe_load(path.read_text(encoding="cp932", errors="replace"))
        except Exception as error:  # noqa: BLE001 - GUIにそのまま分かるエラーを返す
            raise YamlSettingsError(str(error)) from error

        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise YamlSettingsError("YAML のルートは mapping である必要があります。")

        rules_data = data.get("rules", [])
        if not isinstance(rules_data, list):
            raise YamlSettingsError("rules は list である必要があります。")

        rules: list[FillRule] = []
        for index, item in enumerate(rules_data, start=1):
            if not isinstance(item, dict):
                raise YamlSettingsError(f"rules[{index}] は mapping である必要があります。")
            rules.append(FillRule.from_mapping(item, source="yaml"))

        return SavedFormSettings(
            name=str(data.get("name", "") or ""),
            description=str(data.get("description", "") or ""),
            rules=rules,
        )

    def save(self, path: Path, settings: SavedFormSettings) -> None:
        if yaml is None:
            raise YamlSettingsError("PyYAML がインストールされていません。pip install PyYAML を実行してください。")
        data: dict[str, Any] = {
            "name": settings.name,
            "description": settings.description,
            "rules": [rule.to_yaml_mapping() for rule in settings.rules],
        }
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

