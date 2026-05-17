"use strict";

const EXCLUDED_INPUT_TYPES = new Set(["hidden", "submit", "button", "reset", "file", "password"]);
const KINDS = ["text", "textarea", "select", "checkbox", "radio", "contenteditable"];
const MODES = ["replace", "append", "prepend", "skip_if_not_empty"];
const SENSITIVE_WORDS = ["password", "pass", "token", "secret", "auth", "credential"];

const state = {
  rules: [],
  selectedIndex: null,
  loadingEditor: false,
  bookmarklet: "",
  settingsName: "Formlet settings",
  settingsDescription: "",
  choiceValueByDisplay: new Map(),
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  bindEvents();
  populateStaticSelects();
  renderRules();
});

function bindElements() {
  for (const id of [
    "openHtmlButton",
    "loadSettingsButton",
    "saveSettingsButton",
    "loadExtractedButton",
    "addRuleButton",
    "duplicateRuleButton",
    "deleteRuleButton",
    "generateFillButton",
    "generateInspectButton",
    "generateExtractButton",
    "copyBookmarkletInlineButton",
    "htmlFileInput",
    "settingsFileInput",
    "extractedFileInput",
    "rulesBody",
    "selectedRuleText",
    "emptyEditorHint",
    "editorForm",
    "labelInput",
    "selectorInput",
    "kindSelect",
    "modeSelect",
    "enabledInput",
    "noteInput",
    "bookmarkletOutput",
    "statusText",
  ]) {
    elements[id] = document.getElementById(id);
  }
}

function bindEvents() {
  elements.openHtmlButton.addEventListener("click", () => elements.htmlFileInput.click());
  elements.loadSettingsButton.addEventListener("click", () => elements.settingsFileInput.click());
  elements.loadExtractedButton.addEventListener("click", () => elements.extractedFileInput.click());
  elements.saveSettingsButton.addEventListener("click", saveSettingsJson);
  elements.addRuleButton.addEventListener("click", addRule);
  elements.duplicateRuleButton.addEventListener("click", duplicateRule);
  elements.deleteRuleButton.addEventListener("click", deleteRule);
  elements.generateFillButton.addEventListener("click", () => generateBookmarklet(false));
  elements.generateInspectButton.addEventListener("click", () => generateBookmarklet(true));
  elements.generateExtractButton.addEventListener("click", generateExtractBookmarklet);
  elements.copyBookmarkletInlineButton.addEventListener("click", copyBookmarklet);
  elements.htmlFileInput.addEventListener("change", handleHtmlFile);
  elements.settingsFileInput.addEventListener("change", handleSettingsFile);
  elements.extractedFileInput.addEventListener("change", handleExtractedFile);
  elements.labelInput.addEventListener("input", updateSelectedRuleFields);
  elements.selectorInput.addEventListener("input", updateSelectedRuleFields);
  elements.kindSelect.addEventListener("input", updateSelectedRuleFields);
  elements.modeSelect.addEventListener("input", updateSelectedRuleFields);
  elements.enabledInput.addEventListener("input", updateSelectedRuleFields);
  elements.noteInput.addEventListener("input", updateSelectedRuleFields);
}

function populateStaticSelects() {
  fillSelect(elements.kindSelect, KINDS.map(value => [value, value]));
  fillSelect(elements.modeSelect, MODES.map(value => [value, value]));
}

async function handleHtmlFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const html = await file.text();
  const parsedRules = parseHtmlToRules(html);
  state.rules = parsedRules;
  state.selectedIndex = null;
  renderRules();
  setStatus(`${file.name} から ${parsedRules.length} 件の入力候補を読み込みました。`);
  event.target.value = "";
}

async function handleSettingsFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const settings = JSON.parse(await file.text());
    const incomingRules = Array.isArray(settings.rules) ? settings.rules.map(ruleFromObject) : [];
    state.settingsName = String(settings.name || state.settingsName);
    state.settingsDescription = String(settings.description || "");
    mergeRules(incomingRules, "json");
    renderRules();
    setStatus(`${file.name} から ${incomingRules.length} 件の設定を読み込みました。`);
  } catch (error) {
    setStatus(`設定JSON読込に失敗しました: ${error.message}`, true);
  }
  event.target.value = "";
}

async function handleExtractedFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    const incomingRules = rulesFromExtractedJson(data);
    mergeRules(incomingRules, "extracted");
    renderRules();
    setStatus(`${file.name} から ${incomingRules.length} 件の抽出値を反映しました。`);
  } catch (error) {
    setStatus(`抽出JSON読込に失敗しました: ${error.message}`, true);
  }
  event.target.value = "";
}

function parseHtmlToRules(html) {
  const documentObject = new DOMParser().parseFromString(html, "text/html");
  const elementsList = [...documentObject.querySelectorAll("input, textarea, select")]
    .filter(element => !EXCLUDED_INPUT_TYPES.has((element.getAttribute("type") || "text").toLowerCase()));
  const parsed = elementsList.map(element => formElementToRule(documentObject, element));
  return mergeRadioRules(parsed);
}

function formElementToRule(documentObject, element) {
  const tag = element.tagName.toLowerCase();
  const inputType = tag === "input" ? (element.getAttribute("type") || "text").toLowerCase() : tag;
  const { selector, confidence } = selectorForElement(element);
  const kind = kindForElement(tag, inputType);
  const valueOptions = [];
  if (tag === "select") {
    for (const option of element.querySelectorAll("option")) {
      if (!valueOptions.includes(option.value)) valueOptions.push(option.value);
    }
  }
  if ((kind === "checkbox" || kind === "radio") && element.getAttribute("value")) {
    valueOptions.push(element.getAttribute("value"));
  }
  return {
    enabled: !element.disabled && !element.readOnly,
    label: inferLabel(documentObject, element, selector),
    selector,
    kind,
    value: "",
    checked: kind === "checkbox" || kind === "radio" ? Boolean(element.checked) : null,
    mode: "replace",
    source: "html",
    note: "",
    confidence,
    valueOptions,
    name: element.getAttribute("name") || "",
    initialValue: element.getAttribute("value") || "",
  };
}

function selectorForElement(element) {
  const tag = element.tagName.toLowerCase();
  const type = (element.getAttribute("type") || (tag === "select" ? "select" : tag)).toLowerCase();
  if (type === "radio" && element.name) {
    return { selector: `${tag}[name="${cssAttributeEscape(element.name)}"]`, confidence: "medium" };
  }
  if (element.id) return { selector: `#${cssIdentifierEscape(element.id)}`, confidence: "high" };
  if (type === "checkbox" && element.name && element.hasAttribute("value")) {
    return {
      selector: `${tag}[name="${cssAttributeEscape(element.name)}"][value="${cssAttributeEscape(element.value || "")}"]`,
      confidence: "medium",
    };
  }
  if (element.name) return { selector: `${tag}[name="${cssAttributeEscape(element.name)}"]`, confidence: "medium" };
  if (element.placeholder) {
    return { selector: `${tag}[placeholder="${cssAttributeEscape(element.placeholder)}"]`, confidence: "medium_low" };
  }
  if (element.classList.length) return { selector: `${tag}.${cssIdentifierEscape(element.classList[0])}`, confidence: "low" };
  return { selector: tag, confidence: "dangerous" };
}

function inferLabel(documentObject, element, selector) {
  if (element.id) {
    const label = documentObject.querySelector(`label[for="${cssAttributeEscape(element.id)}"]`);
    if (label?.textContent?.trim()) return normalizeSpace(label.textContent);
  }
  return normalizeSpace(element.getAttribute("placeholder") || "")
    || normalizeSpace(element.getAttribute("name") || "")
    || normalizeSpace(element.id || "")
    || selector;
}

function kindForElement(tag, inputType) {
  if (tag === "textarea") return "textarea";
  if (tag === "select") return "select";
  if (inputType === "checkbox") return "checkbox";
  if (inputType === "radio") return "radio";
  return "text";
}

function mergeRadioRules(rules) {
  const result = [];
  const radioBySelector = new Map();
  for (const rule of rules) {
    if (rule.kind !== "radio") {
      result.push(rule);
      continue;
    }
    const key = rule.selector || rule.name;
    const existing = radioBySelector.get(key);
    if (!existing) {
      radioBySelector.set(key, rule);
      result.push(rule);
    } else {
      for (const value of rule.valueOptions || []) {
        if (value && !existing.valueOptions.includes(value)) existing.valueOptions.push(value);
      }
      if (rule.checked) {
        existing.checked = true;
        existing.value = rule.initialValue || existing.value;
      }
    }
  }
  return result;
}

function renderRules() {
  elements.rulesBody.innerHTML = "";
  state.rules.forEach((rule, index) => {
    elements.rulesBody.appendChild(buildRuleRow(rule, index));
  });
  loadSelectedRuleEditor();
}

function buildRuleRow(rule, index) {
  const row = document.createElement("tr");
  row.dataset.index = String(index);
  row.className = index === state.selectedIndex ? "selected" : "";
  row.addEventListener("click", () => selectRule(index));
  tableValuesForRule(rule).forEach((value, cellIndex) => {
    const cell = document.createElement("td");
    if (cellIndex === 0) {
      cell.className = "enabled-cell";
      renderEnabledCell(cell, rule, index);
    } else if (cellIndex === 4) {
      cell.className = "value-cell";
      renderValueCell(cell, rule, index);
    } else {
      cell.textContent = value;
    }
    row.appendChild(cell);
  });
  return row;
}

function renderEnabledCell(cell, rule, index) {
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "table-enabled-checkbox";
  checkbox.checked = Boolean(rule.enabled);
  for (const eventName of ["pointerdown", "click", "dblclick"]) {
    checkbox.addEventListener(eventName, event => event.stopPropagation());
  }
  checkbox.addEventListener("focus", () => selectRule(index, { render: false }));
  checkbox.addEventListener("change", () => {
    rule.enabled = checkbox.checked;
    if (index === state.selectedIndex) elements.enabledInput.checked = checkbox.checked;
  });
  cell.appendChild(checkbox);
}

function renderValueCell(cell, rule, index) {
  const choices = choiceOptionsForRule(rule);
  const control = choices.length ? buildTableValueSelect(rule, choices) : buildTableValueTextControl(rule);
  for (const eventName of ["pointerdown", "click", "dblclick"]) {
    control.addEventListener(eventName, event => event.stopPropagation());
  }
  control.addEventListener("focus", () => selectRule(index, { render: false }));
  cell.appendChild(control);
}

function buildTableValueSelect(rule, choices) {
  const select = document.createElement("select");
  select.className = "table-value-select";
  fillSelect(select, choices);
  select.value = displayForValue(rule.value, choices);
  const update = () => {
    const displayedValue = select.value;
    updateRuleValue(rule, new Map(choices).get(displayedValue) ?? displayedValue);
  };
  select.addEventListener("input", update);
  select.addEventListener("change", update);
  return select;
}

function buildTableValueTextControl(rule) {
  const multiline = rule.kind === "textarea" || rule.kind === "contenteditable" || String(rule.value).includes("\n");
  const control = multiline ? document.createElement("textarea") : document.createElement("input");
  control.className = multiline ? "table-value-textarea" : "table-value-input";
  if (!multiline) {
    control.type = "text";
    control.autocomplete = "off";
  } else {
    control.rows = 2;
  }
  control.value = rule.value;
  control.addEventListener("input", () => updateRuleValue(rule, control.value));
  return control;
}

function selectRule(index, options = {}) {
  state.selectedIndex = index;
  markSelectedRow(index);
  loadSelectedRuleEditor();
  if (options.render) renderRules();
}

function markSelectedRow(index) {
  for (const row of elements.rulesBody.querySelectorAll("tr")) {
    row.classList.toggle("selected", row.dataset.index === String(index));
  }
}

function loadSelectedRuleEditor() {
  const rule = currentRule();
  state.loadingEditor = true;
  state.choiceValueByDisplay = new Map();
  if (!rule) {
    elements.selectedRuleText.textContent = "行を選択してください";
    elements.emptyEditorHint.classList.remove("hidden");
    elements.editorForm.classList.add("hidden");
    elements.labelInput.value = "";
    elements.selectorInput.value = "";
    elements.enabledInput.checked = false;
    elements.noteInput.value = "";
    state.loadingEditor = false;
    return;
  }

  elements.emptyEditorHint.classList.add("hidden");
  elements.editorForm.classList.remove("hidden");
  elements.selectedRuleText.textContent = `${rule.label || rule.selector || "(no label)"} / ${rule.kind} / ${rule.selector}`;
  elements.labelInput.value = rule.label;
  elements.selectorInput.value = rule.selector;
  elements.kindSelect.value = rule.kind;
  elements.modeSelect.value = rule.mode;
  elements.enabledInput.checked = Boolean(rule.enabled);
  elements.noteInput.value = rule.note || "";

  state.loadingEditor = false;
}

function choiceOptionsForRule(rule) {
  if (rule.kind === "checkbox") return displayValueOptions(uniqueOptions(["true", "false", ...(rule.valueOptions || [])]));
  if (rule.kind === "radio") return displayValueOptions(uniqueOptions([...(rule.valueOptions || []), rule.value]));
  if (rule.kind === "select") {
    const values = uniqueOptions([...(rule.valueOptions || []), rule.value], true);
    if (!values.some(value => value !== "")) return [];
    return displayValueOptions(values, true);
  }
  return [];
}

function displayValueOptions(values, showEmpty = false) {
  return values.flatMap(value => {
    if (value === "" && showEmpty) return [["(空)", ""]];
    if (value === "") return [];
    return [[value, value]];
  });
}

function displayForValue(value, choices) {
  const choice = choices.find(([_display, optionValue]) => optionValue === value);
  return choice ? choice[0] : value || choices[0]?.[0] || "";
}

function updateRuleValue(rule, value) {
  if (state.loadingEditor) return;
  if (!rule) return;
  rule.value = value;
  if (rule.kind === "checkbox") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "y", "on", "checked", "check", "選択", "はい"].includes(normalized)) rule.checked = true;
    if (["false", "0", "no", "n", "off", "unchecked", "uncheck", "未選択", "いいえ"].includes(normalized)) rule.checked = false;
  }
}

function updateSelectedRuleFields() {
  if (state.loadingEditor) return;
  const rule = currentRule();
  if (!rule) return;
  const previousKind = rule.kind;
  rule.label = elements.labelInput.value;
  rule.selector = elements.selectorInput.value;
  rule.kind = elements.kindSelect.value;
  rule.mode = elements.modeSelect.value;
  rule.enabled = elements.enabledInput.checked;
  rule.note = elements.noteInput.value;
  updateRuleRow(state.selectedIndex);
  if (rule.kind !== previousKind) loadSelectedRuleEditor();
}

function updateRuleRow(index) {
  if (index == null || index < 0 || index >= state.rules.length) return;
  const row = elements.rulesBody.querySelector(`tr[data-index="${index}"]`);
  if (!row) return;
  row.replaceWith(buildRuleRow(state.rules[index], index));
}

function tableValuesForRule(rule) {
  return [
    String(Boolean(rule.enabled)),
    rule.label,
    rule.selector,
    rule.kind,
    previewValue(rule.value),
    rule.mode,
    rule.confidence || "",
    rule.source || "",
    rule.note || "",
  ];
}

function currentRule() {
  if (state.selectedIndex == null) return null;
  return state.rules[state.selectedIndex] || null;
}

function addRule() {
  state.rules.push(emptyRule());
  state.selectedIndex = state.rules.length - 1;
  renderRules();
}

function duplicateRule() {
  const rule = currentRule();
  if (!rule) return;
  const clone = structuredClone(rule);
  clone.source = "manual";
  state.rules.splice(state.selectedIndex + 1, 0, clone);
  state.selectedIndex += 1;
  renderRules();
}

function deleteRule() {
  if (state.selectedIndex == null) return;
  state.rules.splice(state.selectedIndex, 1);
  state.selectedIndex = Math.min(state.selectedIndex, state.rules.length - 1);
  if (state.selectedIndex < 0) state.selectedIndex = null;
  renderRules();
}

function emptyRule() {
  return {
    enabled: true,
    label: "",
    selector: "",
    kind: "text",
    value: "",
    checked: null,
    mode: "replace",
    source: "manual",
    note: "",
    confidence: "",
    valueOptions: [],
  };
}

function ruleFromObject(data) {
  return {
    enabled: Boolean(data.enabled ?? true),
    label: String(data.label || ""),
    selector: String(data.selector || ""),
    kind: String(data.kind || "text"),
    value: String(data.value || ""),
    checked: data.checked === true ? true : data.checked === false ? false : null,
    mode: String(data.mode || "replace"),
    source: String(data.source || "json"),
    note: String(data.note || ""),
    confidence: String(data.confidence || ""),
    valueOptions: Array.isArray(data.valueOptions) ? data.valueOptions.map(String) : [],
  };
}

function rulesFromExtractedJson(data) {
  if (!Array.isArray(data)) throw new Error("抽出JSONは配列である必要があります。");
  return data.map(item => {
    const tag = String(item.tag || "");
    const type = String(item.type || "");
    const value = String(item.value || "");
    const name = String(item.name || "");
    let selector = String(item.selector || "");
    if (type === "radio" && name) {
      selector = `input[name="${cssAttributeEscape(name)}"]`;
    } else if (type === "checkbox" && name && value && item.hasValueAttribute === true && !selector.includes("[value=")) {
      selector = `input[name="${cssAttributeEscape(name)}"][value="${cssAttributeEscape(value)}"]`;
    }
    return {
      ...emptyRule(),
      label: name || String(item.id || "") || selector,
      selector,
      kind: kindForElement(tag, type),
      value,
      checked: item.checked === true ? true : item.checked === false ? false : null,
      source: "extracted",
      valueOptions: type === "radio" && value ? [value] : [],
    };
  });
}

function mergeRules(incomingRules, sourceForNew) {
  const existingBySelector = new Map(state.rules.filter(rule => rule.selector).map(rule => [rule.selector, rule]));
  for (const incoming of incomingRules) {
    const existing = existingBySelector.get(incoming.selector);
    if (existing) {
      if (incoming.source !== "extracted") {
        existing.enabled = incoming.enabled;
        existing.label = incoming.label || existing.label;
        existing.kind = incoming.kind || existing.kind;
        existing.mode = incoming.mode || existing.mode;
        existing.note = incoming.note || "";
        existing.source = incoming.source || existing.source;
      }
      existing.value = incoming.value;
      existing.checked = incoming.checked;
    } else {
      const clone = structuredClone(incoming);
      if (!clone.source || clone.source === "manual" || clone.source === "json") clone.source = sourceForNew;
      state.rules.push(clone);
    }
  }
}

function saveSettingsJson() {
  const payload = {
    name: state.settingsName,
    description: state.settingsDescription,
    rules: state.rules.map(rule => ({
      enabled: rule.enabled,
      label: rule.label,
      selector: rule.selector,
      kind: rule.kind,
      value: rule.value,
      checked: rule.checked,
      mode: rule.mode,
      source: rule.source,
      note: rule.note,
      valueOptions: rule.valueOptions || [],
    })),
  };
  downloadText("formlet-settings.json", JSON.stringify(payload, null, 2), "application/json");
}

function generateBookmarklet(inspectOnly) {
  const enabledRules = state.rules.filter(rule => rule.enabled);
  if (!enabledRules.length) {
    setStatus("enabled=true のルールがありません。", true);
    return;
  }
  const warnings = warningsForRules(enabledRules);
  if (warnings.length && !confirm(`${warnings.slice(0, 10).join("\n")}\n\n続行しますか？`)) return;
  state.bookmarklet = buildFillBookmarklet(enabledRules, inspectOnly);
  elements.bookmarkletOutput.value = state.bookmarklet;
  setStatus(inspectOnly ? "検査Bookmarkletを生成しました。" : "Bookmarkletを生成しました。");
}

function generateExtractBookmarklet() {
  state.bookmarklet = buildExtractBookmarklet();
  elements.bookmarkletOutput.value = state.bookmarklet;
  copyText(state.bookmarklet);
  setStatus("入力欄読取Bookmarkletを生成してコピーしました。");
}

function copyBookmarklet() {
  const text = elements.bookmarkletOutput.value;
  if (!text) return;
  copyText(text);
  setStatus("Bookmarkletをコピーしました。");
}

function buildFillBookmarklet(rules, inspectOnly) {
  const bookmarkletRules = rules.map(rule => ({
    enabled: rule.enabled,
    label: rule.label,
    selector: rule.selector,
    kind: rule.kind,
    value: expandVariables(rule.value),
    checked: rule.checked,
    mode: rule.mode,
  }));
  const rulesJson = JSON.stringify(bookmarkletRules);
  const script = `
    (() => {
      const rules = ${rulesJson};
      const inspectOnly = ${JSON.stringify(inspectOnly)};
      const okSelectors = [];
      const failedSelectors = [];
      function fire(element) {
        element.dispatchEvent(new Event("input", {bubbles:true}));
        element.dispatchEvent(new Event("change", {bubbles:true}));
      }
      function setNativeValue(element, value) {
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
        if (descriptor && descriptor.set) descriptor.set.call(element, value);
        else element.value = value;
      }
      function nextValue(currentValue, rule) {
        if (rule.mode === "append") return currentValue + rule.value;
        if (rule.mode === "prepend") return rule.value + currentValue;
        if (rule.mode === "skip_if_not_empty" && currentValue !== "") return null;
        return rule.value;
      }
      function checkboxStateFromValue(value) {
        const normalized = String(value || "").trim().toLowerCase();
        if (["true","1","yes","y","on","checked","check","選択","はい"].includes(normalized)) return true;
        if (["false","0","no","n","off","unchecked","uncheck","未選択","いいえ"].includes(normalized)) return false;
        return null;
      }
      function candidatesFor(rule, fallbackElement) {
        try {
          const candidates = Array.from(document.querySelectorAll(rule.selector));
          return candidates.length ? candidates : [fallbackElement];
        } catch (error) {
          return [fallbackElement];
        }
      }
      function radioCandidatesFor(rule, fallbackElement) {
        if (fallbackElement && fallbackElement.name) {
          const grouped = Array.from(document.querySelectorAll('input[type="radio"]')).filter(candidate => candidate.name === fallbackElement.name);
          if (grouped.length) return grouped;
        }
        return candidatesFor(rule, fallbackElement);
      }
      function applyCheckbox(rule, element) {
        const valueState = checkboxStateFromValue(rule.value);
        if (valueState !== null) element.checked = valueState;
        else if (String(rule.value || "") !== "") element.checked = element.value === String(rule.value);
        else if (rule.checked !== null && rule.checked !== undefined) element.checked = Boolean(rule.checked);
        fire(element);
        return true;
      }
      function applyRadio(rule, element) {
        const requestedValue = String(rule.value || "");
        let target = element;
        if (requestedValue !== "") {
          target = radioCandidatesFor(rule, element).find(candidate => candidate.value === requestedValue) || null;
          if (!target) return false;
          target.checked = true;
        } else if (rule.checked !== null && rule.checked !== undefined) target.checked = Boolean(rule.checked);
        else target.checked = true;
        fire(target);
        return true;
      }
      for (const rule of rules) {
        let element = null;
        try { element = document.querySelector(rule.selector); }
        catch (error) { failedSelectors.push(rule.selector + " (invalid selector)"); continue; }
        if (!element) { failedSelectors.push(rule.selector); continue; }
        okSelectors.push(rule.selector);
        if (inspectOnly) continue;
        if (rule.kind === "checkbox") { if (!applyCheckbox(rule, element)) failedSelectors.push(rule.selector + " (value not found)"); continue; }
        if (rule.kind === "radio") {
          if (!applyRadio(rule, element)) { okSelectors.pop(); failedSelectors.push(rule.selector + " (value not found: " + rule.value + ")"); }
          continue;
        }
        if (rule.kind === "select") { element.value = rule.value; fire(element); continue; }
        if (rule.kind === "contenteditable") { element.textContent = rule.value; fire(element); continue; }
        const updatedValue = nextValue(element.value || "", rule);
        if (updatedValue === null) continue;
        setNativeValue(element, updatedValue);
        fire(element);
      }
      if (inspectOnly) alert("OK:\\n" + (okSelectors.join("\\n") || "(none)") + "\\n\\nNG:\\n" + (failedSelectors.join("\\n") || "(none)"));
      else alert("入力成功件数: " + okSelectors.length + "\\n失敗件数: " + failedSelectors.length + (failedSelectors.length ? "\\n\\n" + failedSelectors.join("\\n") : ""));
    })();
  `;
  return `javascript:${minifyJavaScript(script)}`;
}

function buildExtractBookmarklet() {
  const script = `
    (() => {
      const excluded = new Set(["hidden","submit","button","reset","file","password"]);
      function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/[^a-zA-Z0-9_-]/g, ch => "\\\\" + ch.charCodeAt(0).toString(16) + " ");
      }
      function attrEscape(value) {
        return String(value).replace(/\\\\/g, "\\\\\\\\").replace(/"/g, '\\\\"');
      }
      function selectorFor(element) {
        const tag = element.tagName.toLowerCase();
        const type = (element.getAttribute("type") || (tag === "select" ? "select" : tag)).toLowerCase();
        if (element.id) return "#" + cssEscape(element.id);
        if ((type === "checkbox" || type === "radio") && element.name && element.hasAttribute("value")) return tag + "[name=\\"" + attrEscape(element.name) + "\\"][value=\\"" + attrEscape(element.value || "") + "\\"]";
        if (element.name) return tag + "[name=\\"" + attrEscape(element.name) + "\\"]";
        if (element.placeholder) return tag + "[placeholder=\\"" + attrEscape(element.placeholder) + "\\"]";
        if (element.classList && element.classList.length) return tag + "." + cssEscape(element.classList[0]);
        return tag;
      }
      const items = Array.from(document.querySelectorAll("input,textarea,select"))
        .filter(element => !excluded.has((element.getAttribute("type") || "text").toLowerCase()))
        .map(element => {
          const tag = element.tagName.toLowerCase();
          const type = (element.getAttribute("type") || (tag === "select" ? "select" : tag)).toLowerCase();
          return { selector: selectorFor(element), tag, type, id: element.id || "", name: element.name || "", value: element.value || "", hasValueAttribute: element.hasAttribute("value"), checked: type === "checkbox" || type === "radio" ? Boolean(element.checked) : null };
        })
        .filter(item => item.type === "checkbox" || item.type === "radio" ? item.checked === true : item.value !== "");
      const text = JSON.stringify(items, null, 2);
      function fallback() { prompt("抽出JSONをコピーしてください", text); }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => alert("入力値JSONをクリップボードにコピーしました: " + items.length + "件")).catch(fallback);
      else fallback();
    })();
  `;
  return `javascript:${minifyJavaScript(script)}`;
}

function warningsForRules(rules) {
  const warnings = [];
  for (const rule of rules) {
    if (rule.confidence === "dangerous" || ["input", "textarea", "select"].includes(rule.selector.trim())) {
      warnings.push(`危険なセレクタ: ${rule.selector || "(empty)"}`);
    }
    const haystack = `${rule.selector} ${rule.label} ${rule.note}`.toLowerCase();
    const sensitiveWord = SENSITIVE_WORDS.find(word => haystack.includes(word));
    if (sensitiveWord) warnings.push(`機密情報に関係する可能性: ${rule.label || rule.selector} (${sensitiveWord})`);
  }
  return warnings;
}

function expandVariables(value) {
  const now = new Date();
  const pad = number => String(number).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const timestamp = `${today} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  return String(value).replaceAll("{{today}}", today).replaceAll("{{now}}", timestamp);
}

function minifyJavaScript(script) {
  return script.trim().replace(/\s+/g, " ");
}

function cssIdentifierEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/[^a-zA-Z0-9_-]/g, character => `\\${character.charCodeAt(0).toString(16)} `);
}

function cssAttributeEscape(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\a ");
}

function normalizeSpace(value) {
  return String(value || "").split(/\s+/).filter(Boolean).join(" ");
}

function uniqueOptions(values, keepEmpty = false) {
  const result = [];
  for (const value of values) {
    const text = String(value ?? "");
    if (text === "" && !keepEmpty) continue;
    if (!result.includes(text)) result.push(text);
  }
  return result;
}

function previewValue(value) {
  const preview = String(value || "").replaceAll("\n", "\\n");
  return preview.length > 80 ? `${preview.slice(0, 77)}...` : preview;
}

function fillSelect(select, pairs) {
  select.innerHTML = "";
  for (const [display, value] of pairs) {
    const option = document.createElement("option");
    option.value = display;
    option.textContent = display;
    option.dataset.value = value;
    select.appendChild(option);
  }
}

function downloadText(filename, text, type) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type }));
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    elements.bookmarkletOutput.focus();
    elements.bookmarkletOutput.select();
    document.execCommand("copy");
  }
}

function setStatus(message, isError = false) {
  elements.statusText.textContent = message;
  elements.statusText.classList.toggle("danger", isError);
}
