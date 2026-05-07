# Formlet

Formlet is a desktop GUI tool that analyzes saved HTML forms and generates bookmarklets for automatic form input.

## Requirements

- Python 3.10+
- Tkinter
- PyYAML

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 html_bookmarklet_input_assistant/main.py
```

## Basic Flow

1. Save the target web form as an `.html` or `.htm` file.
2. Open the HTML file in Formlet.
3. Edit each rule's `value`, selector, kind, and mode as needed.
4. Generate an inspection bookmarklet to verify selectors.
5. Generate the input bookmarklet and run it on the target page.
6. Save or reload rules as YAML.

Sample files are available in `html_bookmarklet_input_assistant/settings/`.
