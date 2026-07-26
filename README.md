# pytest-uia

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Windows GUI acceptance testing for pytest — through the accessibility tree, not pixels.**

Write desktop acceptance tests the way you would describe them to a person: *click the
button named New Task, then the window should say task created.* Elements are located
through the Windows **UI Automation** (UIA) accessibility tree — by accessible name and
role — so tests survive theme changes, DPI scaling, resolution changes and multi-monitor
layouts that break screenshot-matching tools.

OCR exists as a **deliberate last resort**, for surfaces whose controls expose nothing a
name-based query can reach: Tkinter, canvas-drawn UI, anything custom-painted. The two
are a chain — UIA answers first, and OCR is only consulted when the accessibility tree
had nothing to say.

### Is this for you?

| Your situation | What to reach for |
|---|---|
| The app under test is a web page, or is Electron-in-a-browser | **Playwright / Selenium.** They own that surface completely; UIA reaches Chromium's tree, but through a far worse API than the DevTools protocol. |
| Cross-platform: the same suite has to run on macOS or Linux | **SikuliX** or **Airtest**. This is Windows-only and will stay that way. |
| Games, video, custom OpenGL/canvas — nothing is a control anywhere | **SikuliX** or **Airtest**. Image matching is the right tool when there is genuinely no structure to query; pytest-uia's OCR fallback reads *text*, not arbitrary imagery. |
| You need drag-and-drop, right-click, double-click, scrolling, menus, comboboxes, trees | **pywinauto**, today. Those are all v1 non-goals here — see [ROADMAP](ROADMAP.md). |
| You want raw coordinate control and nothing else | **PyAutoGUI.** It is 200 lines of what you want and no opinion at all. |
| A mature, broad Windows automation library with years of edge cases handled | **pywinauto.** It is the incumbent for a reason. pytest-uia is a small, opinionated *pytest plugin*, not a replacement for it. |
| Native Win32/WinForms/WPF/Electron desktop app, and you want acceptance tests that read like the acceptance criteria | **pytest-uia.** |
| Your app has **empty** input boxes to find, or dark mode, or per-monitor DPI | **pytest-uia.** "Find the empty textbox labelled *Title*" is a query here, and a computer-vision problem everywhere else. |
| You control the app under test and can add accessible names | **pytest-uia.** The act that makes it testable is the act that makes it work with screen readers. |
| Tkinter dialogs you cannot modify | **pytest-uia**, with the OCR fallback — and read [The Tkinter case](#the-tkinter-case-stated-precisely) first, because the honest answer has caveats. |

## Quickstart

pytest-uia is **not on PyPI** — publishing is out of scope for v1 (see [ROADMAP](ROADMAP.md)).
Install it from a clone:

```bash
git clone https://github.com/HuzPro/pytest-uia
cd pytest-uia
pip install -e ".[ocr]"     # drop [ocr] if you never need the pixel fallback
```

Then, in your own suite:

```python
import sys

import pytest


@pytest.mark.gui
def test_creating_a_task_updates_the_status_label(gui):
    app = gui.launch([sys.executable, "todo_app.py"])

    app.textbox("Title").type_text("Buy milk")
    app.button("New Task").click()

    assert app.text("task created").exists()
```

That is the whole API surface most suites need. `gui` is a function-scoped fixture the
plugin provides; it owns every app the test launches and shuts all of them down
afterwards, whether the test passed, failed or raised. The `gui` marker is registered by
the plugin, so `-m "not gui"` works with no ini changes, and `--strict-markers` does not
complain.

To drive something already on screen instead of launching it:

```python
app = gui.attach(title="pytest-uia WinForms Fixture")
```

An attached app is never terminated at teardown — it may be an application the developer
is using. A launched one always is.

### The API

| Call | What it does |
|---|---|
| `gui.launch(command, ready_timeout=30.0)` | Start a command, block until it owns a visible window, return an `App`. |
| `gui.attach(title=..., timeout=10.0)` | Take a handle on a window already on screen, by its caption. |
| `app.button(name)` / `app.textbox(name)` / `app.text(value)` | An element, resolved lazily and re-resolved on every interaction. |
| `element.click()` / `.type_text(s)` / `.read_text()` | Act on it, or read it. |
| `element.exists(timeout=None)` | `True`/`False` instead of an exception, for both directions of assertion. |
| `element.wait_visible(timeout=None)` | Block until it is actually painted, then return itself so a call can follow. |
| `app.close()` / `app.pid` / `app.title` | End it, or ask about it. |
| `--uia-timeout SECONDS` | The implicit wait every lookup inherits. Default 5 s; any call can override it with `timeout=`. |

Names are matched **exactly** in v1. Substring and regex matching are on the roadmap.

## How it finds things

One locator chain, consulted in order, per window:

1. **`UiaLocator`** — a one-shot UIA search under the window for a control of the right
   control type with that exact `Name`. Roles map `button → ButtonControl`,
   `textbox → EditControl`, `text → TextControl`.
2. **`OcrLocator`** — only if the `ocr` extra is installed. Brings the window to the
   front, grabs its rectangle with `mss`, hands the BGRA bytes straight to Windows'
   built-in `Windows.Media.Ocr` (no Tesseract, no install), and matches the phrase
   against the recognised words.

Nothing else waits. Adapters look **once** and raise; only the driver retries, inside the
element's implicit wait. That is deliberate: `uiautomation` retries for ten seconds
internally by default, and underneath a polling loop of our own that turns every
configured timeout into a multiple of itself.

Interactions prefer the accessibility pattern that needs no focus and steals none —
`InvokePattern` for a click, `ValuePattern` for typing — and fall back to the mouse and
keyboard only when the provider has nothing to offer or fails the call.

## The Tkinter case, stated precisely

It is often said that Tk exposes no accessibility tree. That is **not true**, and the
truth matters for what this plugin can promise.

Probed against the Tk fixture app in this repo:

- The toplevel **is** in the UIA tree, as a `WindowControl` with class `TkTopLevel` and
  the right title. Window-level UIA works fine — which is exactly what lets the OCR path
  find the window's rectangle and bring it to the front.
- The button **is** in the tree, as a `ButtonControl` — with an **empty accessible
  name**.
- The status label is exposed as an **`ImageControl`**, not a `TextControl`.

So the accurate statement is: **Tk exposes unnamed, mis-roled controls that no
name-based query can reach.** There is structure there; there is just nothing to match
on. `app.button("New Task")` cannot find that button through UIA no matter how the
search is written, because the button has no name and the label has the wrong role.

That is what the OCR fallback is for, and why it reads the window's pixels rather than
trying harder against the tree.

## Limitations you should know before adopting this

### OCR ignores roles

The recogniser can only see text. It cannot know whether the phrase it matched was
painted on a button, on a label, or inside a picture. The concrete consequence:

```python
app.textbox("Title").type_text("Buy milk")
```

resolved by OCR will match the **label** reading "Title" beside the box rather than the
empty box itself, and the keystrokes then go wherever clicking that label put the caret.
Roles are honoured by UIA, and by UIA alone. If your app has an accessibility tree, this
never bites you — the chain never reaches OCR.

### The OCR path depends on synthetic mouse input, and that can be refused

This is the sharpest argument for UIA-first, and it was measured rather than reasoned
about.

While a window owned by a **higher-integrity process** holds the foreground, Windows'
User Interface Privilege Isolation drops every input event a medium-integrity process
injects: `SetCursorPos` returns 0, the cursor does not move, and `SendInput` inserts
nothing. On the machine this was developed on, a SYSTEM-owned `GameInputServiceWindow`
(from the `GameInputSvc` service) takes the foreground and holds it — for hours, on a
bad day — and no medium-integrity process can displace it. `SetForegroundWindow`,
`SwitchToThisWindow`, `BringWindowToTop` were all tried; none of them moves it.

Throughout all of that, **UIA pattern calls, screen capture and OCR keep working
perfectly.** Invoking a button through its accessibility pattern is a provider call, not
an input event, so UIPI never sees it. Only the last-resort path — the mouse — is
affected. That is the thesis of this project demonstrated by accident.

pytest-uia handles it honestly rather than silently:

- `uiautomation.Click` discards Windows' answer about whether the event was delivered.
  pytest-uia does not: it keeps the return values of `SetCursorPos` and `SendInput` and
  raises `InputRefused` when they say the event was dropped.
- The driver **retries** a refused click inside the element's implicit wait, because the
  theft is usually transient. One deadline covers resolving and clicking, so a refusal
  never costs twice the configured timeout.
- If it is refused for the whole wait, the failure names the culprit instead of blaming
  your application:

  ```
  InputRefused: synthetic mouse input was refused for 5.0s; the foreground is held by
  'GameInputServiceWindow' (pid 6680), which runs at a higher integrity level than this
  process, so Windows drops every event this process injects; close that window, stop
  the service behind it, or run the suite elevated
  ```

  Before this, the same condition surfaced as `ElementNotFound: ... phrase not visible`
  about a phrase that was plainly on screen.

`InputRefused` is exported from the package, so a suite can decide for itself whether a
refusing desktop is a failure or a skip. This repo's own gui specs treat it as a skip:
the machine cannot run them, which is the same category as a missing OCR language pack.

**Keyboard injection is not checked.** `type_text`'s fallback path goes through
`uiautomation`'s `SendKeys`, which parses key names and has no return value to inspect,
so a refused *keystroke* is still silent. Clicks are checked; keys are not. The
`ValuePattern` path that `type_text` prefers is a provider call and is immune either way.

### gui runs own the desktop

Bringing a window to the front, moving the pointer and sending keys are global acts. A
gui run needs the machine to itself — do not use the mouse while one is going, and do not
lock the workstation (a locked session has no interactive desktop to inject into at all).

### Not in v1

Menus, comboboxes, checkboxes and radios, tables and trees, drag-and-drop, right- and
double-click, keyboard chords, scrolling, child modal dialogs, image-diff assertions,
OCR-targeted `type_text`, non-built-in OCR engines, non-Windows, elevated processes,
PyPI publishing. See [ROADMAP](ROADMAP.md) for what is deferred and what is refused
outright.

## Launching apps that are really launchers

`gui.launch([sys.executable, "app.py"])` looks like it should be trivial, and on Windows
it is not: the `python.exe` inside a virtual environment is a copy of CPython's launcher,
which starts the real interpreter as a **child process** and waits for it. The pid
`subprocess` reports therefore owns no window, ever. Console-script shims and `.bat`
wrappers have the same shape.

pytest-uia resolves a window owned by the launched process **or by anything descending
from it**, walking a `CreateToolhelp32Snapshot` of the process table on each attempt. So
the obvious call works, which is the point.

## Measured

From the fixture apps in this repo, on a Windows 11 development machine:

| | |
|---|---|
| OCR recognition, warm | **5–13 ms** per grab of a 460×240 window, across two sessions |
| OCR recognition, first call in a process | 15–75 ms (WinRT engine creation) |
| OCR accuracy on the Tk fixture | every word, every run — 12 pt Segoe UI, black on white |
| UIA window readiness after launch | ~0.33 s |
| Dominant cost of an OCR find | `uiautomation.SetActive()`'s unconditional `time.sleep(0.5)` |
| A one-shot UIA miss under a real window | well under 1 s (a spec asserts this, to catch `uiautomation` retrying underneath) |

The recogniser is not the bottleneck, and by two orders of magnitude. Bringing the
window to the front — so that the screen grab photographs the right application — is:
`SetActive` sleeps half a second every time, whatever happened.

None of this is a benchmark against another tool. It is here so that nobody has to guess
whether the OCR fallback is affordable. It is; the focus change in front of it is not.

## Development

```powershell
git clone https://github.com/HuzPro/pytest-uia
cd pytest-uia
py -m venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev,ocr]"     # or: pip install -e ".[dev,ocr]"

pytest -m "not gui" -q             # instant; no windows, runs on any platform
pytest -m gui -q                   # drives real windows — hands off the mouse
pytest -q                          # everything

ruff check src tests
ruff format --check src tests
```

The `gui` suite launches two fixture applications: a WinForms form (rich accessibility
tree, standing in for a well-behaved native app) and a Tkinter window (unnamed,
mis-roled controls, standing in for the ones that are not). The same journey runs
against both, through one test body — `tests/test_hybrid_end_to_end.py` is the spec that
justifies the whole design.

CI runs `pytest -m "not gui"` on {Ubuntu, Windows} × {3.10, 3.13}. The gui suite is
**local-only in v1**: it needs an interactive desktop it owns, and hosted runners are an
unproven environment for foreground and input injection. Trialling it on a GitHub
Windows runner is a roadmap item.

### Layout

```
src/pytest_uia/
├── plugin.py        # the pytest11 entry point: re-exports from hooks, nothing else
├── hooks.py         # the ONLY module that imports pytest
├── domain/          # stdlib only — queries, the locator chain, waiting, text matching
├── adapters/        # uiautomation, comtypes, WinRT, mss, ctypes — nothing leaks past here
└── application/     # composes the two; imports pytest nowhere
```

The layering is enforced by the Ubuntu CI lane: `domain/` and `application/` must import
and run with no Windows anywhere.

## License

[MIT](LICENSE)
