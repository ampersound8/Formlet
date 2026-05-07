from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_MODE = "replace"
DEFAULT_KIND = "text"

KINDS = ("text", "textarea", "select", "checkbox", "radio", "contenteditable")
MODES = ("replace", "append", "prepend", "skip_if_not_empty")
SENSITIVE_WORDS = ("password", "pass", "token", "secret", "auth", "credential")


@dataclass(slots=True)
class FormElement:
    tag: str
    element_id: str = ""
    name: str = ""
    class_name: str = ""
    input_type: str = ""
    placeholder: str = ""
    maxlength: str = ""
    initial_value: str = ""
    checked: bool | None = None
    selected: bool = False
    disabled: bool = False
    readonly: bool = False
    label: str = ""
    selector: str = ""
    confidence: str = ""
    kind: str = DEFAULT_KIND
    value_options: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FillRule:
    enabled: bool = True
    label: str = ""
    selector: str = ""
    kind: str = DEFAULT_KIND
    value: str = ""
    checked: bool | None = None
    mode: str = DEFAULT_MODE
    source: str = "manual"
    note: str = ""
    confidence: str = ""
    value_options: list[str] = field(default_factory=list)

    @classmethod
    def from_form_element(cls, element: FormElement) -> "FillRule":
        return cls(
            enabled=not element.disabled and not element.readonly,
            label=element.label,
            selector=element.selector,
            kind=element.kind,
            value="",
            checked=element.checked,
            mode=DEFAULT_MODE,
            source="html",
            note="",
            confidence=element.confidence,
            value_options=list(element.value_options),
        )

    @classmethod
    def empty(cls) -> "FillRule":
        return cls()

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source: str = "yaml") -> "FillRule":
        checked = data.get("checked")
        if checked == "":
            checked = None
        return cls(
            enabled=bool(data.get("enabled", True)),
            label=str(data.get("label", "") or ""),
            selector=str(data.get("selector", "") or ""),
            kind=str(data.get("kind", DEFAULT_KIND) or DEFAULT_KIND),
            value=str(data.get("value", "") or ""),
            checked=checked if checked in (True, False, None) else None,
            mode=str(data.get("mode", DEFAULT_MODE) or DEFAULT_MODE),
            source=str(data.get("source", source) or source),
            note=str(data.get("note", "") or ""),
            confidence=str(data.get("confidence", "") or ""),
            value_options=[str(value) for value in data.get("value_options", [])]
            if isinstance(data.get("value_options"), list)
            else [],
        )

    def to_yaml_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "label": self.label,
            "selector": self.selector,
            "kind": self.kind,
            "value": self.value,
            "checked": self.checked,
            "mode": self.mode,
            "source": self.source,
            "note": self.note,
        }

    def to_bookmarklet_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "label": self.label,
            "selector": self.selector,
            "kind": self.kind,
            "value": self.value,
            "checked": self.checked,
            "mode": self.mode,
        }

    def clone(self) -> "FillRule":
        return FillRule(
            enabled=self.enabled,
            label=self.label,
            selector=self.selector,
            kind=self.kind,
            value=self.value,
            checked=self.checked,
            mode=self.mode,
            source=self.source,
            note=self.note,
            confidence=self.confidence,
            value_options=list(self.value_options),
        )


@dataclass(slots=True)
class SavedFormSettings:
    name: str = ""
    description: str = ""
    rules: list[FillRule] = field(default_factory=list)
