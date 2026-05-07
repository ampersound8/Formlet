from __future__ import annotations

from datetime import datetime
import json
import re

try:
    from .models import FillRule, SENSITIVE_WORDS
except ImportError:  # pragma: no cover
    from models import FillRule, SENSITIVE_WORDS


class BookmarkletMinifier:
    def minify(self, javascript: str) -> str:
        return re.sub(r"\s+", " ", javascript.strip())


class BookmarkletBuilder:
    def __init__(self, minifier: BookmarkletMinifier | None = None) -> None:
        self.minifier = minifier or BookmarkletMinifier()

    def build_fill_bookmarklet(self, rules: list[FillRule], inspect_only: bool = False) -> str:
        bookmarklet_rules = [
            self._expanded_rule(rule).to_bookmarklet_mapping()
            for rule in rules
            if rule.enabled
        ]
        rules_json = json.dumps(bookmarklet_rules, ensure_ascii=False, separators=(",", ":"))
        inspect_json = json.dumps(inspect_only)
        script = f"""
        (() => {{
          const rules = {rules_json};
          const inspectOnly = {inspect_json};
          const okSelectors = [];
          const failedSelectors = [];
          function fire(element) {{
            element.dispatchEvent(new Event("input", {{bubbles:true}}));
            element.dispatchEvent(new Event("change", {{bubbles:true}}));
          }}
          function setNativeValue(element, value) {{
            const prototype = element instanceof HTMLTextAreaElement
              ? HTMLTextAreaElement.prototype
              : HTMLInputElement.prototype;
            const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
            if (descriptor && descriptor.set) {{
              descriptor.set.call(element, value);
            }} else {{
              element.value = value;
            }}
          }}
          function nextValue(currentValue, rule) {{
            if (rule.mode === "append") return currentValue + rule.value;
            if (rule.mode === "prepend") return rule.value + currentValue;
            if (rule.mode === "skip_if_not_empty" && currentValue !== "") return null;
            return rule.value;
          }}
          function checkboxStateFromValue(value) {{
            const normalized = String(value || "").trim().toLowerCase();
            if (["true","1","yes","y","on","checked","check","選択","はい"].includes(normalized)) return true;
            if (["false","0","no","n","off","unchecked","uncheck","未選択","いいえ"].includes(normalized)) return false;
            return null;
          }}
          function candidatesFor(rule, fallbackElement) {{
            try {{
              const candidates = Array.from(document.querySelectorAll(rule.selector));
              return candidates.length ? candidates : [fallbackElement];
            }} catch (error) {{
              return [fallbackElement];
            }}
          }}
          function radioCandidatesFor(rule, fallbackElement) {{
            if (fallbackElement && fallbackElement.name) {{
              const grouped = Array.from(document.querySelectorAll('input[type="radio"]'))
                .filter(candidate => candidate.name === fallbackElement.name);
              if (grouped.length) return grouped;
            }}
            return candidatesFor(rule, fallbackElement);
          }}
          function applyCheckbox(rule, element) {{
            const valueState = checkboxStateFromValue(rule.value);
            if (valueState !== null) {{
              element.checked = valueState;
            }} else if (String(rule.value || "") !== "") {{
              element.checked = element.value === String(rule.value);
            }} else if (rule.checked !== null && rule.checked !== undefined) {{
              element.checked = Boolean(rule.checked);
            }}
            fire(element);
            return true;
          }}
          function applyRadio(rule, element) {{
            const requestedValue = String(rule.value || "");
            let target = element;
            if (requestedValue !== "") {{
              target = radioCandidatesFor(rule, element).find(candidate => candidate.value === requestedValue) || null;
              if (!target) return false;
              target.checked = true;
            }} else if (rule.checked !== null && rule.checked !== undefined) {{
              target.checked = Boolean(rule.checked);
            }} else {{
              target.checked = true;
            }}
            fire(target);
            return true;
          }}
          for (const rule of rules) {{
            let element = null;
            try {{
              element = document.querySelector(rule.selector);
            }} catch (error) {{
              failedSelectors.push(rule.selector + " (invalid selector)");
              continue;
            }}
            if (!element) {{
              failedSelectors.push(rule.selector);
              continue;
            }}
            okSelectors.push(rule.selector);
            if (inspectOnly) continue;
            if (rule.kind === "checkbox") {{
              if (!applyCheckbox(rule, element)) failedSelectors.push(rule.selector + " (value not found)");
              continue;
            }}
            if (rule.kind === "radio") {{
              if (!applyRadio(rule, element)) {{
                okSelectors.pop();
                failedSelectors.push(rule.selector + " (value not found: " + rule.value + ")");
              }}
              continue;
            }}
            if (rule.kind === "select") {{
              element.value = rule.value;
              fire(element);
              continue;
            }}
            if (rule.kind === "contenteditable") {{
              element.textContent = rule.value;
              fire(element);
              continue;
            }}
            const updatedValue = nextValue(element.value || "", rule);
            if (updatedValue === null) continue;
            setNativeValue(element, updatedValue);
            fire(element);
          }}
          if (inspectOnly) {{
            alert("OK:\\n" + (okSelectors.join("\\n") || "(none)") + "\\n\\nNG:\\n" + (failedSelectors.join("\\n") || "(none)"));
          }} else {{
            alert("入力成功件数: " + okSelectors.length + "\\n失敗件数: " + failedSelectors.length + (failedSelectors.length ? "\\n\\n" + failedSelectors.join("\\n") : ""));
          }}
        }})();
        """
        return "javascript:" + self.minifier.minify(script)

    def build_extract_bookmarklet(self) -> str:
        script = r"""
        (() => {
          const excluded = new Set(["hidden","submit","button","reset","file","password"]);
          function cssEscape(value) {
            if (window.CSS && CSS.escape) return CSS.escape(value);
            return String(value).replace(/[^a-zA-Z0-9_-]/g, ch => "\\" + ch.charCodeAt(0).toString(16) + " ");
          }
          function attrEscape(value) {
            return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
          }
          function selectorFor(element) {
            const tag = element.tagName.toLowerCase();
            const type = (element.getAttribute("type") || (tag === "select" ? "select" : tag)).toLowerCase();
            if (element.id) return "#" + cssEscape(element.id);
            if ((type === "checkbox" || type === "radio") && element.name && element.hasAttribute("value")) {
              return tag + "[name=\"" + attrEscape(element.name) + "\"][value=\"" + attrEscape(element.value || "") + "\"]";
            }
            if (element.name) return tag + "[name=\"" + attrEscape(element.name) + "\"]";
            if (element.placeholder) return tag + "[placeholder=\"" + attrEscape(element.placeholder) + "\"]";
            if (element.classList && element.classList.length) return tag + "." + cssEscape(element.classList[0]);
            return tag;
          }
          const items = Array.from(document.querySelectorAll("input,textarea,select"))
            .filter(element => !excluded.has((element.getAttribute("type") || "text").toLowerCase()))
            .map(element => {
              const tag = element.tagName.toLowerCase();
              const type = (element.getAttribute("type") || (tag === "select" ? "select" : tag)).toLowerCase();
              return {
                selector: selectorFor(element),
                tag,
                type,
                id: element.id || "",
                name: element.name || "",
                value: element.value || "",
                hasValueAttribute: element.hasAttribute("value"),
                checked: type === "checkbox" || type === "radio" ? Boolean(element.checked) : null
              };
            })
            .filter(item => item.type === "checkbox" || item.type === "radio" ? item.checked === true : item.value !== "");
          const text = JSON.stringify(items, null, 2);
          function fallback() {
            prompt("抽出JSONをコピーしてください", text);
          }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
              alert("入力値JSONをクリップボードにコピーしました: " + items.length + "件");
            }).catch(fallback);
          } else {
            fallback();
          }
        })();
        """
        return "javascript:" + self.minifier.minify(script)

    def warnings_for_rules(self, rules: list[FillRule]) -> list[str]:
        warnings: list[str] = []
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.confidence == "dangerous" or rule.selector.strip() in {"input", "textarea", "select"}:
                warnings.append(f"危険なセレクタ: {rule.selector or '(empty)'}")
            haystack = " ".join([rule.selector, rule.label, rule.note]).lower()
            for word in SENSITIVE_WORDS:
                if word in haystack:
                    warnings.append(f"機密情報に関係する可能性: {rule.label or rule.selector} ({word})")
                    break
        return warnings

    def _expanded_rule(self, rule: FillRule) -> FillRule:
        now = datetime.now()
        cloned = rule.clone()
        cloned.value = (
            cloned.value.replace("{{today}}", now.strftime("%Y-%m-%d"))
            .replace("{{now}}", now.strftime("%Y-%m-%d %H:%M:%S"))
        )
        return cloned
