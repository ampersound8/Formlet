# Formlet

Formlet analyzes saved HTML forms and generates bookmarklets for automatic form input.

The repository now contains two local versions:

- `web/`: browser-only local app built with HTML, CSS, and JavaScript.
- `html_bookmarklet_input_assistant/`: Python + Tkinter desktop app.

## Run Browser Version

Open this file in your browser:

```text
web/index.html
```

The browser version works as a static local app. It reads saved HTML files, edits rules, imports extracted JSON, and generates bookmarklets without a server. Settings are saved and loaded as JSON.

## Run Python Version

### Requirements

- Python 3.10+
- Tkinter
- PyYAML

Install dependencies:

```bash
pip install -r requirements.txt
```

### Start

```bash
python3 html_bookmarklet_input_assistant/main.py
```

## Basic Flow

1. Save the target web form as an `.html` or `.htm` file.
2. Open the HTML file in Formlet.
3. Edit each rule's `value`, selector, kind, and mode as needed.
4. Generate an inspection bookmarklet to verify selectors.
5. Generate the input bookmarklet and run it on the target page.
6. Save or reload rules. The browser version uses JSON; the Python version uses YAML.

Sample files are available in `html_bookmarklet_input_assistant/settings/`.
