from __future__ import annotations

from html.parser import HTMLParser
import re

try:
    from .models import FormElement
except ImportError:  # pragma: no cover - direct script execution support
    from models import FormElement


EXCLUDED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "file", "password"}


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def css_identifier_escape(value: str) -> str:
    """Small CSS.escape-like helper for id and class selector fragments."""
    if not value:
        return value
    escaped: list[str] = []
    for index, character in enumerate(value):
        is_safe = bool(re.match(r"[A-Za-z0-9_-]", character))
        starts_with_digit = index == 0 and character.isdigit()
        starts_dash_digit = index == 1 and value[0] == "-" and character.isdigit()
        if is_safe and not starts_with_digit and not starts_dash_digit:
            escaped.append(character)
        else:
            escaped.append(f"\\{ord(character):x} ")
    return "".join(escaped)


def css_attribute_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")


def attrs_to_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in attrs}


class HtmlFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[FormElement] = []
        self._labels_by_for: dict[str, str] = {}
        self._active_label_for: str | None = None
        self._active_label_text: list[str] = []
        self._active_textarea_index: int | None = None
        self._active_select_index: int | None = None
        self._active_option_select_index: int | None = None
        self._active_option_value: str | None = None
        self._active_option_text: list[str] = []

    def parse(self, html: str) -> list[FormElement]:
        self.elements = []
        self._labels_by_for = {}
        self._active_label_for = None
        self._active_label_text = []
        self._active_textarea_index = None
        self._active_select_index = None
        self._active_option_select_index = None
        self._active_option_value = None
        self._active_option_text = []
        self.feed(html)
        self.close()
        self._apply_labels()
        self._apply_grouped_value_options()
        return self.elements

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = attrs_to_dict(attrs)

        if tag == "label":
            self._active_label_for = attributes.get("for")
            self._active_label_text = []
            return

        if tag == "input":
            input_type = attributes.get("type", "text").lower() or "text"
            if input_type in EXCLUDED_INPUT_TYPES:
                return
            self.elements.append(self._element_from_attributes(tag, attributes))
            return

        if tag == "textarea":
            element = self._element_from_attributes(tag, attributes)
            self.elements.append(element)
            self._active_textarea_index = len(self.elements) - 1
            return

        if tag == "select":
            element = self._element_from_attributes(tag, attributes)
            self.elements.append(element)
            self._active_select_index = len(self.elements) - 1
            return

        if tag == "option" and self._active_select_index is not None:
            self._active_option_select_index = self._active_select_index
            self._active_option_value = attributes.get("value")
            self._active_option_text = []
            if "selected" in attributes:
                selected_value = attributes.get("value", "")
                self.elements[self._active_select_index].initial_value = selected_value
                self.elements[self._active_select_index].selected = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "label" and self._active_label_for:
            text = normalize_space("".join(self._active_label_text))
            if text:
                self._labels_by_for[self._active_label_for] = text
            self._active_label_for = None
            self._active_label_text = []
        elif tag == "textarea":
            self._active_textarea_index = None
        elif tag == "select":
            self._active_select_index = None
        elif tag == "option" and self._active_option_select_index is not None:
            option_value = self._active_option_value
            if option_value is None:
                option_value = normalize_space("".join(self._active_option_text))
            element = self.elements[self._active_option_select_index]
            if option_value not in element.value_options:
                element.value_options.append(option_value)
            self._active_option_select_index = None
            self._active_option_value = None
            self._active_option_text = []

    def handle_data(self, data: str) -> None:
        if self._active_label_for is not None:
            self._active_label_text.append(data)
        if self._active_textarea_index is not None:
            element = self.elements[self._active_textarea_index]
            element.initial_value += data
        if self._active_option_select_index is not None:
            self._active_option_text.append(data)

    def _element_from_attributes(self, tag: str, attributes: dict[str, str]) -> FormElement:
        input_type = attributes.get("type", "text").lower() if tag == "input" else tag
        selector, confidence = self._build_selector(tag, attributes, input_type)
        element = FormElement(
            tag=tag,
            element_id=attributes.get("id", ""),
            name=attributes.get("name", ""),
            class_name=attributes.get("class", ""),
            input_type=input_type,
            placeholder=attributes.get("placeholder", ""),
            maxlength=attributes.get("maxlength", ""),
            initial_value=attributes.get("value", ""),
            checked=True if "checked" in attributes else (False if input_type in {"checkbox", "radio"} else None),
            selected="selected" in attributes,
            disabled="disabled" in attributes,
            readonly="readonly" in attributes,
            selector=selector,
            confidence=confidence,
            kind=self._infer_kind(tag, input_type),
        )
        if element.kind in {"checkbox", "radio"} and element.initial_value:
            element.value_options.append(element.initial_value)
        element.label = self._infer_label(element)
        return element

    def _build_selector(self, tag: str, attributes: dict[str, str], input_type: str) -> tuple[str, str]:
        element_id = attributes.get("id", "")
        name = attributes.get("name", "")
        value = attributes.get("value", "")
        placeholder = attributes.get("placeholder", "")
        class_name = attributes.get("class", "")

        if element_id:
            return f"#{css_identifier_escape(element_id)}", "high"
        if input_type in {"checkbox", "radio"} and name and value:
            return (
                f'{tag}[name="{css_attribute_escape(name)}"][value="{css_attribute_escape(value)}"]',
                "medium",
            )
        if name:
            return f'{tag}[name="{css_attribute_escape(name)}"]', "medium"
        if placeholder:
            return f'{tag}[placeholder="{css_attribute_escape(placeholder)}"]', "medium_low"
        if class_name:
            first_class = class_name.split()[0]
            return f"{tag}.{css_identifier_escape(first_class)}", "low"
        return tag, "dangerous"

    def _infer_kind(self, tag: str, input_type: str) -> str:
        if tag == "textarea":
            return "textarea"
        if tag == "select":
            return "select"
        if input_type == "checkbox":
            return "checkbox"
        if input_type == "radio":
            return "radio"
        return "text"

    def _infer_label(self, element: FormElement) -> str:
        return (
            normalize_space(element.placeholder)
            or normalize_space(element.name)
            or normalize_space(element.element_id)
            or element.selector
        )

    def _apply_labels(self) -> None:
        for element in self.elements:
            if element.element_id and element.element_id in self._labels_by_for:
                element.label = self._labels_by_for[element.element_id]

    def _apply_grouped_value_options(self) -> None:
        radio_options_by_name: dict[str, list[str]] = {}
        for element in self.elements:
            if element.kind != "radio" or not element.name or not element.initial_value:
                continue
            radio_options_by_name.setdefault(element.name, [])
            if element.initial_value not in radio_options_by_name[element.name]:
                radio_options_by_name[element.name].append(element.initial_value)

        for element in self.elements:
            if element.kind == "radio" and element.name in radio_options_by_name:
                element.value_options = list(radio_options_by_name[element.name])
