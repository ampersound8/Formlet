from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

try:
    from .bookmarklet_builder import BookmarkletBuilder
    from .html_form_parser import HtmlFormParser
    from .models import FillRule, KINDS, MODES, SavedFormSettings
    from .yaml_settings import FormSettingsYaml, YamlSettingsError
except ImportError:  # pragma: no cover
    from bookmarklet_builder import BookmarkletBuilder
    from html_form_parser import HtmlFormParser
    from models import FillRule, KINDS, MODES, SavedFormSettings
    from yaml_settings import FormSettingsYaml, YamlSettingsError


class ClipboardService:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root

    def copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()


HELP_TEXT = """Formlet の使い方

1. 対象フォームのHTMLを保存します。
   ブラウザの「名前を付けて保存」または DevTools の Elements から outerHTML を保存します。

2. Formletを起動して「HTMLを開く」を押します。
   input / textarea / select が一覧に表示されます。

3. 行をダブルクリックして入力値を設定します。
   value に入力したい文字列を入れます。selector や label も手動編集できます。
   select は option の value、radio は選択したい value、checkbox は true/false/on/off/1/0 などを value に入れられます。
   valueセルを直接ダブルクリックすると、select / radio / checkbox は候補からインライン選択できます。

4. 「検査Bookmarklet生成」を押して「コピー」します。
   ブラウザのブックマークURL欄に貼り付け、対象ページで実行すると selector の検出結果だけ確認できます。

5. 問題なければ「Bookmarklet生成」を押して「コピー」します。
   同じようにブックマークURL欄へ貼り付け、対象ページで実行すると自動入力されます。

6. 設定を再利用したい場合は「YAML保存」を押します。
   次回は HTML を開いた後に「YAML読込」を押すと、同じ selector の入力値が復元されます。

入力値抽出の使い方

1. 対象フォームに一度手入力します。
2. Formletで「入力欄読取Bookmarklet生成」を押します。Bookmarkletは自動でコピーされます。
   これは入力欄読み取り用のBookmarkletです。
3. ブラウザのブックマークURL欄に貼り付け、対象ページで実行します。
4. 入力済み項目のJSONがクリップボードにコピーされます。
5. JSONを .json ファイルとして保存します。
6. Formletで「抽出JSON読込」を押すと、既存 selector は value/checked が更新され、未知の selector は source=extracted として追加されます。

サンプル手順

1. 付属の html_bookmarklet_input_assistant/settings/sample_form.html をブラウザで開きます。
   HTML解析のサンプルとして使う場合は、Formletの「HTMLを開く」から同じファイルを選びます。

   内容は次のようなフォームです。

   <html>
   <body>
     <label for="mtlItemName">品目名</label>
     <input id="mtlItemName" class="x8" name="mtlItemName" type="text" maxlength="45" placeholder="全角">
     <textarea class="memo" name="memo"></textarea>
     <select name="category">
       <option value="">選択してください</option>
       <option value="A">A</option>
       <option value="B">B</option>
     </select>
     <label><input type="checkbox" name="confirmed"> 確認済み</label>
   </body>
   </html>

2. Formletで sample_form.html を「HTMLを開く」から読み込みます。
3. #mtlItemName の行をダブルクリックし、value に「テスト」と入力して保存します。
4. textarea[name="memo"] または textarea.memo の行にメモ文を入力します。
5. select の value に「B」、checkbox の value に「true」、radio の value に「urgent」を入力します。
6. 「検査Bookmarklet生成」から検出確認をします。
7. 「Bookmarklet生成」から自動入力用Bookmarkletを作ります。

注意

- password / file は自動入力対象から除外されます。
- Bookmarkletには入力値が直接含まれるため、パスワード、トークン、秘密情報は入れないでください。
- tagだけの selector は複数要素に当たりやすいため、必要に応じて手動で selector を直してください。
"""


class HelpDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Formlet 使い方")
        self.geometry("820x680")
        self.transient(parent)
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        text = tk.Text(frame, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.insert("1.0", HELP_TEXT)
        text.configure(state=tk.DISABLED)

        ttk.Button(frame, text="閉じる", command=self.destroy).grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))


class RuleEditDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, rule: FillRule) -> None:
        super().__init__(parent)
        self.title("入力ルール編集")
        self.resizable(True, True)
        self.result: FillRule | None = None
        self.rule = rule.clone()

        self.enabled_var = tk.BooleanVar(value=self.rule.enabled)
        self.label_var = tk.StringVar(value=self.rule.label)
        self.selector_var = tk.StringVar(value=self.rule.selector)
        self.kind_var = tk.StringVar(value=self.rule.kind if self.rule.kind in KINDS else "text")
        self.mode_var = tk.StringVar(value=self.rule.mode if self.rule.mode in MODES else "replace")
        self.checked_var = tk.StringVar(value=self._checked_to_string(self.rule.checked))

        self._build()
        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(frame, text="enabled", variable=self.enabled_var).grid(row=0, column=0, columnspan=2, sticky="w")
        self._entry(frame, "label", self.label_var, 1)
        self._entry(frame, "selector", self.selector_var, 2)
        self._option(frame, "kind", self.kind_var, KINDS, 3)
        self._option(frame, "mode", self.mode_var, MODES, 4)
        self._option(frame, "checked", self.checked_var, ("", "true", "false"), 5)

        ttk.Label(frame, text="value").grid(row=6, column=0, sticky="nw", pady=4)
        self.value_text = tk.Text(frame, height=6, width=64)
        self.value_text.grid(row=6, column=1, sticky="nsew", pady=4)
        self.value_text.insert("1.0", self.rule.value)

        ttk.Label(frame, text="note").grid(row=7, column=0, sticky="nw", pady=4)
        self.note_text = tk.Text(frame, height=3, width=64)
        self.note_text.grid(row=7, column=1, sticky="nsew", pady=4)
        self.note_text.insert("1.0", self.rule.note)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="保存", command=self._save).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="キャンセル", command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _entry(self, frame: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)

    def _option(self, frame: ttk.Frame, label: str, variable: tk.StringVar, options: tuple[str, ...], row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.OptionMenu(frame, variable, variable.get(), *options).grid(row=row, column=1, sticky="w", pady=4)

    def _save(self) -> None:
        self.rule.enabled = self.enabled_var.get()
        self.rule.label = self.label_var.get()
        self.rule.selector = self.selector_var.get()
        self.rule.kind = self.kind_var.get()
        self.rule.mode = self.mode_var.get()
        self.rule.checked = self._string_to_checked(self.checked_var.get())
        self.rule.value = self.value_text.get("1.0", "end-1c")
        self.rule.note = self.note_text.get("1.0", "end-1c")
        self.result = self.rule
        self.destroy()

    def _checked_to_string(self, value: bool | None) -> str:
        if value is True:
            return "true"
        if value is False:
            return "false"
        return ""

    def _string_to_checked(self, value: str) -> bool | None:
        if value == "true":
            return True
        if value == "false":
            return False
        return None


class MainApplication:
    columns = ("enabled", "label", "selector", "kind", "value", "mode", "confidence", "source", "note")

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Formlet")
        self.root.geometry("1200x720")
        self.rules: list[FillRule] = []
        self.settings_name = ""
        self.settings_description = ""
        self.generated_bookmarklet = ""
        self.inline_value_editor: tk.Widget | None = None
        self.inline_value_item_id = ""
        self.inline_value_by_display: dict[str, str] = {}

        self.parser = HtmlFormParser()
        self.yaml_service = FormSettingsYaml()
        self.builder = BookmarkletBuilder()
        self.clipboard = ClipboardService(self.root)

        self._build_widgets()

    def run(self) -> None:
        self.root.mainloop()

    def _build_widgets(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)
        buttons = [
            ("使い方", self.show_help),
            ("HTMLを開く", self.open_html),
            ("YAML読込", self.load_yaml),
            ("YAML保存", self.save_yaml),
            ("抽出JSON読込", self.load_extracted_json),
            ("行追加", self.add_rule),
            ("編集", self.edit_selected_rule),
            ("行削除", self.delete_rule),
            ("行複製", self.duplicate_rule),
            ("Bookmarklet生成", lambda: self.generate_bookmarklet(False)),
            ("検査Bookmarklet生成", lambda: self.generate_bookmarklet(True)),
            ("入力欄読取Bookmarklet生成", self.generate_extract_bookmarklet),
            ("コピー", self.copy_bookmarklet),
        ]
        for label, command in buttons:
            ttk.Button(top, text=label, command=command).pack(side=tk.LEFT, padx=3)

        tree_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=self.columns, show="headings", selectmode="extended")
        for column in self.columns:
            self.tree.heading(column, text=column)
        widths = {
            "enabled": 70,
            "label": 170,
            "selector": 240,
            "kind": 100,
            "value": 180,
            "mode": 130,
            "confidence": 100,
            "source": 90,
            "note": 200,
        }
        for column, width in widths.items():
            self.tree.column(column, width=width, anchor=tk.W)
        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.bind("<ButtonRelease-1>", self.edit_value_at_event)
        self.tree.bind("<Double-1>", self.edit_rule_at_event)
        self.tree.bind("<Return>", self.edit_selected_rule)
        self.tree.bind("<F2>", self.edit_selected_value_inline)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(side=tk.BOTTOM, fill=tk.BOTH)
        ttk.Label(bottom, text="生成Bookmarklet").pack(anchor=tk.W)
        self.bookmarklet_text = tk.Text(bottom, height=7, wrap=tk.WORD)
        self.bookmarklet_text.pack(fill=tk.BOTH, expand=False)

    def open_html(self) -> None:
        path_text = filedialog.askopenfilename(
            title="HTMLを開く",
            filetypes=(("HTML files", "*.html *.htm"), ("All files", "*.*")),
        )
        if not path_text:
            return
        try:
            html = self._read_html(Path(path_text))
            elements = self.parser.parse(html)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("HTML読み込み失敗", str(error))
            return
        self.rules = [FillRule.from_form_element(element) for element in elements]
        self.refresh_tree()

    def show_help(self) -> None:
        HelpDialog(self.root)

    def load_yaml(self) -> None:
        path_text = filedialog.askopenfilename(
            title="YAML読込",
            filetypes=(("YAML files", "*.yaml *.yml"), ("All files", "*.*")),
        )
        if not path_text:
            return
        try:
            settings = self.yaml_service.load(Path(path_text))
        except (OSError, YamlSettingsError) as error:
            messagebox.showerror("YAML読み込み失敗", str(error))
            return
        self.settings_name = settings.name
        self.settings_description = settings.description
        self.merge_rules(settings.rules)
        self.refresh_tree()

    def save_yaml(self) -> None:
        name = simpledialog.askstring("設定名", "name", initialvalue=self.settings_name, parent=self.root)
        if name is None:
            return
        description = simpledialog.askstring(
            "説明",
            "description",
            initialvalue=self.settings_description,
            parent=self.root,
        )
        if description is None:
            return
        path_text = filedialog.asksaveasfilename(
            title="YAML保存",
            defaultextension=".yaml",
            filetypes=(("YAML files", "*.yaml *.yml"), ("All files", "*.*")),
        )
        if not path_text:
            return
        self.settings_name = name
        self.settings_description = description
        try:
            self.yaml_service.save(
                Path(path_text),
                SavedFormSettings(name=name, description=description, rules=self.rules),
            )
        except (OSError, YamlSettingsError) as error:
            messagebox.showerror("YAML保存失敗", str(error))

    def load_extracted_json(self) -> None:
        path_text = filedialog.askopenfilename(
            title="抽出JSON読込",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path_text:
            return
        try:
            data = json.loads(Path(path_text).read_text(encoding="utf-8"))
            extracted_rules = self._rules_from_extracted_json(data)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("抽出JSON読み込み失敗", str(error))
            return
        self.merge_rules(extracted_rules, update_source_for_new="extracted")
        self.refresh_tree()

    def add_rule(self) -> None:
        self.rules.append(FillRule.empty())
        self.refresh_tree()

    def delete_rule(self) -> None:
        indexes = self._selected_indexes()
        if not indexes:
            return
        for index in sorted(indexes, reverse=True):
            del self.rules[index]
        self.refresh_tree()

    def duplicate_rule(self) -> None:
        indexes = self._selected_indexes()
        if not indexes:
            return
        insert_after = max(indexes) + 1
        clones = [self.rules[index].clone() for index in indexes]
        for offset, clone in enumerate(clones):
            clone.source = "manual"
            self.rules.insert(insert_after + offset, clone)
        self.refresh_tree()

    def edit_rule_at_event(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None
        column_id = self.tree.identify_column(event.x)
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        if self._column_name(column_id) == "value":
            self.start_inline_value_edit(item_id, open_choices=True)
            return "break"
        self.edit_rule_by_item_id(item_id)
        return "break"

    def edit_value_at_event(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None
        column_id = self.tree.identify_column(event.x)
        if self._column_name(column_id) != "value":
            return None
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self.start_inline_value_edit(item_id, open_choices=True)
        return "break"

    def edit_selected_value_inline(self, _event: tk.Event | None = None) -> str | None:
        item_id = self.tree.focus()
        if not item_id:
            selected = self.tree.selection()
            item_id = selected[0] if selected else ""
        if item_id:
            self.start_inline_value_edit(item_id, open_choices=True)
            return "break"
        return None

    def start_inline_value_edit(self, item_id: str, open_choices: bool = False) -> None:
        self.close_inline_value_editor(save=False)
        try:
            index = int(item_id)
        except ValueError:
            return
        if index < 0 or index >= len(self.rules):
            return

        cell_box = self.tree.bbox(item_id, "value")
        if not cell_box:
            return
        x, y, width, height = cell_box
        self.inline_value_item_id = item_id
        value_options = self._inline_value_options(self.rules[index])
        self.inline_value_by_display = {display: value for display, value in value_options}
        if value_options:
            displays = [display for display, _value in value_options]
            self.inline_value_editor = ttk.Combobox(self.tree, values=displays, state="readonly")
            self.inline_value_editor.set(self._display_for_inline_value(self.rules[index].value, displays))
            self.inline_value_editor.bind("<<ComboboxSelected>>", lambda _event: self.close_inline_value_editor(save=True))
            if open_choices:
                self.root.after(60, self.open_inline_value_choices)
        else:
            self.inline_value_editor = ttk.Entry(self.tree)
            self.inline_value_editor.insert(0, self.rules[index].value)
            self.inline_value_editor.select_range(0, tk.END)
        self.inline_value_editor.place(x=x, y=y, width=width, height=height)
        self.inline_value_editor.focus_set()
        self.inline_value_editor.bind("<Return>", lambda _event: self.close_inline_value_editor(save=True))
        self.inline_value_editor.bind("<Escape>", lambda _event: self.close_inline_value_editor(save=False))
        self.inline_value_editor.bind("<FocusOut>", lambda _event: self.close_inline_value_editor(save=True))

    def open_inline_value_choices(self) -> None:
        editor = self.inline_value_editor
        if not isinstance(editor, ttk.Combobox):
            return
        try:
            self.root.tk.call("ttk::combobox::Post", str(editor))
        except tk.TclError:
            editor.event_generate("<Button-1>")

    def close_inline_value_editor(self, save: bool) -> None:
        editor = self.inline_value_editor
        item_id = self.inline_value_item_id
        if editor is None:
            return

        displayed_value = editor.get()
        value = self.inline_value_by_display.get(displayed_value, displayed_value)
        self.unpost_inline_value_choices()
        self.inline_value_editor = None
        self.inline_value_item_id = ""
        self.inline_value_by_display = {}
        editor.destroy()

        if not save:
            return
        try:
            index = int(item_id)
        except ValueError:
            return
        if index < 0 or index >= len(self.rules):
            return
        self.rules[index].value = value
        self._update_tree_row(index)

    def unpost_inline_value_choices(self) -> None:
        editor = self.inline_value_editor
        if not isinstance(editor, ttk.Combobox):
            return
        try:
            self.root.tk.call("ttk::combobox::Unpost", str(editor))
        except tk.TclError:
            pass

    def _inline_value_options(self, rule: FillRule) -> list[tuple[str, str]]:
        if rule.kind == "checkbox":
            return self._display_value_options(self._unique_options(["true", "false", *rule.value_options]))
        if rule.kind == "select":
            values = self._unique_options([*rule.value_options, rule.value], keep_empty=True)
            non_empty_values = [value for value in values if value != ""]
            if not non_empty_values:
                return []
            return self._display_value_options(values, show_empty_label=True)
        if rule.kind == "radio":
            return self._display_value_options(self._unique_options([*rule.value_options, rule.value]))
        return []

    def _display_value_options(self, values: list[str], show_empty_label: bool = False) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        for value in values:
            if value == "" and show_empty_label:
                options.append(("(空)", value))
            elif value != "":
                options.append((value, value))
        return options

    def _display_for_inline_value(self, value: str, displays: list[str]) -> str:
        for display, option_value in self.inline_value_by_display.items():
            if option_value == value:
                return display
        return displays[0] if displays else value

    def _unique_options(self, values: list[str], keep_empty: bool = False) -> list[str]:
        options: list[str] = []
        for value in values:
            if value == "" and not keep_empty:
                continue
            if value in options:
                continue
            options.append(value)
        return options

    def edit_selected_rule(self, _event: tk.Event | None = None) -> None:
        indexes = self._selected_indexes()
        if not indexes:
            return
        self.edit_rule_by_index(indexes[0])

    def edit_rule_by_item_id(self, item_id: str) -> None:
        try:
            index = int(item_id)
        except ValueError:
            return
        self.edit_rule_by_index(index)

    def edit_rule_by_index(self, index: int) -> None:
        if index < 0 or index >= len(self.rules):
            return
        dialog = RuleEditDialog(self.root, self.rules[index])
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.rules[index] = dialog.result
            self.refresh_tree()

    def generate_bookmarklet(self, inspect_only: bool) -> None:
        enabled_rules = [rule for rule in self.rules if rule.enabled]
        if not enabled_rules:
            messagebox.showwarning("Bookmarklet生成", "enabled=true のルールがありません。")
            return
        warnings = self.builder.warnings_for_rules(enabled_rules)
        if warnings:
            proceed = messagebox.askyesno("警告", "\n".join(warnings[:10]) + "\n\n続行しますか？")
            if not proceed:
                return
        self.generated_bookmarklet = self.builder.build_fill_bookmarklet(self.rules, inspect_only=inspect_only)
        self._set_bookmarklet_text(self.generated_bookmarklet)

    def generate_extract_bookmarklet(self) -> None:
        self.generated_bookmarklet = self.builder.build_extract_bookmarklet()
        self._set_bookmarklet_text(self.generated_bookmarklet)
        self.clipboard.copy(self.generated_bookmarklet)
        messagebox.showinfo("コピー", "入力値抽出Bookmarkletを生成し、クリップボードにコピーしました。")

    def copy_bookmarklet(self) -> None:
        text = self.bookmarklet_text.get("1.0", "end-1c")
        if not text:
            return
        self.clipboard.copy(text)
        messagebox.showinfo("コピー", "Bookmarkletをクリップボードにコピーしました。")

    def merge_rules(self, incoming_rules: list[FillRule], update_source_for_new: str = "yaml") -> None:
        existing_by_selector = {rule.selector: rule for rule in self.rules if rule.selector}
        for incoming in incoming_rules:
            if incoming.selector and incoming.selector in existing_by_selector:
                existing = existing_by_selector[incoming.selector]
                existing.enabled = incoming.enabled
                existing.label = incoming.label or existing.label
                existing.kind = incoming.kind or existing.kind
                existing.value = incoming.value
                existing.checked = incoming.checked
                existing.mode = incoming.mode or existing.mode
                existing.note = incoming.note
                if incoming.source not in {"yaml", "extracted"}:
                    existing.source = incoming.source
            else:
                new_rule = incoming.clone()
                if new_rule.source in {"", "manual", "yaml"}:
                    new_rule.source = update_source_for_new
                self.rules.append(new_rule)

    def refresh_tree(self) -> None:
        self.close_inline_value_editor(save=True)
        self.tree.delete(*self.tree.get_children())
        for index, rule in enumerate(self.rules):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=self._tree_values_for_rule(rule),
            )

    def _update_tree_row(self, index: int) -> None:
        item_id = str(index)
        if self.tree.exists(item_id):
            self.tree.item(item_id, values=self._tree_values_for_rule(self.rules[index]))

    def _tree_values_for_rule(self, rule: FillRule) -> tuple[str, str, str, str, str, str, str, str, str]:
        value_preview = rule.value.replace("\n", "\\n")
        if len(value_preview) > 80:
            value_preview = value_preview[:77] + "..."
        return (
            str(rule.enabled).lower(),
            rule.label,
            rule.selector,
            rule.kind,
            value_preview,
            rule.mode,
            rule.confidence,
            rule.source,
            rule.note,
        )

    def _column_name(self, column_id: str) -> str:
        if not column_id.startswith("#"):
            return ""
        try:
            column_index = int(column_id.removeprefix("#")) - 1
        except ValueError:
            return ""
        if column_index < 0 or column_index >= len(self.columns):
            return ""
        return self.columns[column_index]

    def _read_html(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="cp932", errors="replace")

    def _set_bookmarklet_text(self, text: str) -> None:
        self.bookmarklet_text.delete("1.0", tk.END)
        self.bookmarklet_text.insert("1.0", text)

    def _selected_indexes(self) -> list[int]:
        indexes: list[int] = []
        for item_id in self.tree.selection():
            try:
                indexes.append(int(item_id))
            except ValueError:
                continue
        return sorted(indexes)

    def _rules_from_extracted_json(self, data: Any) -> list[FillRule]:
        if not isinstance(data, list):
            raise ValueError("抽出JSONは配列である必要があります。")
        rules: list[FillRule] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector", "") or "")
            tag = str(item.get("tag", "") or "")
            input_type = str(item.get("type", "") or "")
            kind = self._kind_from_extracted(tag, input_type)
            label = str(item.get("name") or item.get("id") or selector)
            checked = item.get("checked")
            if checked not in (True, False, None):
                checked = None
            rules.append(
                FillRule(
                    enabled=True,
                    label=label,
                    selector=selector,
                    kind=kind,
                    value=str(item.get("value", "") or ""),
                    checked=checked,
                    mode="replace",
                    source="extracted",
                    note="",
                    confidence="",
                )
            )
        return rules

    def _kind_from_extracted(self, tag: str, input_type: str) -> str:
        if tag == "textarea":
            return "textarea"
        if tag == "select":
            return "select"
        if input_type == "checkbox":
            return "checkbox"
        if input_type == "radio":
            return "radio"
        return "text"
