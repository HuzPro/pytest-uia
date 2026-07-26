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
name-based query can reach: canvas-drawn UI, custom-painted controls, anything whose
interface is a picture of an interface. The two are a chain — UIA answers first, and OCR
is only consulted when the accessibility tree had nothing to say. Tkinter used to be on
that list; it is not any more, and
[The Tkinter case](#the-tkinter-case-stated-precisely) says exactly why.

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
| A Tkinter app **you own** | **pytest-uia**, plus [`tk-uia`](../tk-uia) inside the app itself. One call there gives every widget a name and a role, and every query here is then an ordinary UIA query — full accessibility tree, no OCR. Read [The Tkinter case](#the-tkinter-case-stated-precisely) for what it does and does not buy. |
| A Tkinter app you **cannot modify** | **pytest-uia**, with the OCR fallback. Annotation is in-process only, so somebody else's Tk app is the case the pixel path still exists for — with all of the caveats below. |

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
| `element.wait_until_text_is(expected, timeout=None)` | Block until it reads exactly `expected`, then return itself so a call can follow. |
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

The implicit wait covers *finding* an element, and it also covers waiting for one to say
something. An application reacts on its own message pump, so the repaint lands after the
call that caused it has already returned — the classic race is typing into a box and
asserting on it in the next line:

```python
app.textbox("Title").type_text("Buy milk")
app.textbox("Title").wait_until_text_is("Buy milk")
```

That re-resolves the element and re-reads it until it says exactly that, inside the same
implicit wait, and honours a per-call `timeout=` like everything else. Timing out raises
**`TextNeverSettled`**, not `ElementNotFound`, and the message carries both what it read
and what it expected — the control *was* found on every look, and blaming a missing
element would send whoever reads the failure hunting for something that is right there.
A control that has not been painted yet is an ordinary miss and keeps the wait going,
since the click that sets a label's text is usually the click that creates it; if it
never appears at all, that is still an `ElementNotFound`. `TextNeverSettled` is exported
from the package alongside the other failures.

Interactions prefer the accessibility pattern that needs no focus and steals none —
`InvokePattern` for a click, `ValuePattern` for typing — and fall back to the mouse and
keyboard in three cases: the provider offers no such pattern, it offers one and fails the
call, or it is the generic **MSAA proxy** speaking for a control whose owner never wrote
a provider at all.

That third case is the subtle one, and there the pattern is not even attempted. The proxy
synthesises `Invoke` from a posted `BM_CLICK`; against an owner-drawn widget — every Tk
button is one — that message reaches nothing, so the call returns cleanly, the
application never hears about it, and a test passes having pressed nothing. `SetValue` on
such a control is the same call into the same void, so typing goes the long way round
instead — click the control, *then* send the keys, because a Tk widget owns focus within
its toplevel through Tk's own model and Win32 focus on its child window is not focus at
all. Reading is deliberately *not* gated that way: a name or a value the proxy serves out
of an annotation store is the application's own word about itself, and only *acting*
through the proxy is a guess.

Framework matters more than the proxy marker does, and this was measured rather than
assumed: WinForms is served by that same generic proxy, and its `Invoke` works. So a
control is trusted when its `FrameworkId` names a toolkit that implements accessibility
itself — `WinForm`, `WPF`, `XAML` and their kin — and distrusted when it does not, which
is where Tk's `Win32` lands. A spec drives the WinForms fixture with a recording mouse
and asserts it was never touched, so the rule cannot quietly widen.

## The Tkinter case, stated precisely

It is often said that Tk exposes no accessibility tree. That is **not true**, and the
truth matters for what this plugin can promise.

Probed against a **bare** Tk 8.6.15 window — one whose application does nothing about
accessibility:

- The toplevel **is** in the UIA tree, as a `WindowControl` with class `TkTopLevel` and
  the right title. Window-level UIA works fine — which is exactly what lets the OCR path
  find the window's rectangle and bring it to the front.
- The button **is** in the tree, as a `ButtonControl` — with an **empty accessible
  name**.
- The status label is exposed as an **`ImageControl`**, not a `TextControl`.
- The entry is an anonymous `PaneControl` with no `ValuePattern` at all, so there is
  nothing to read out of it and nothing to set.

So the accurate statement is: **by default, Tk exposes unnamed, mis-roled controls that
no name-based query can reach.** There is structure there; there is just nothing to match
on. `app.button("New Task")` cannot find that button through UIA no matter how the
search is written, because the button has no name and the label has the wrong role.

### And it is fixable, from inside the application

"By default" is carrying real weight in that sentence. A Tk application can say who its
widgets are, and Windows will carry it: MSAA lets a process annotate the accessible
properties of its own windows through `IAccPropServices`, and UI Automation reads those
annotations back out through a proxy that takes priority over the plain one.
[`tk-uia`](../tk-uia) — a sibling project in this workspace, MIT, zero runtime
dependencies — is one call:

```python
import tk_uia

tk_uia.enable(root)
```

Read back through UIA **from a separate process**, after that call: `tk.Button` is a
`ButtonControl` with a real name, `tk.Label` is a **`TextControl`** rather than an
`ImageControl`, and `tk.Entry` is an **`EditControl` carrying a `ValuePattern` that did
not previously exist** — annotating a role is not putting a label on an object, it
changes which patterns the bridge offers for it at all. `app.textbox("Title")` and
`app.text("task created")` work against Tk from that point on, and the journey at the top
of this README runs **verbatim** against both the WinForms fixture app and the Tk one.

Note what did **not** have to change for that: `_CONTROL_TYPE_FOR_ROLE`, the three-line
table mapping `button → ButtonControl`, `text → TextControl` and `textbox → EditControl`,
is byte for byte what it was. Tk became drivable by fixing the *application*, not by
loosening the locator — and loosening it was never the cheaper option, because it does
not work: widening `text` to accept `PaneControl` would match every anonymous themed
widget in the window, and those have no name to match on either.

Classic `tk`, never `ttk`. Measured across all fifteen themed widget types, every one of
them arrives as an anonymous `PaneControl` and `ttk.Button` has no `InvokePattern` at
all, so the modern-looking toolkit is the worse starting point. `tk-uia` annotates both
families; the advice stands anyway.

### What it still costs

- **`Invoke` still lies, so a Tk click is a real mouse click.** An annotated Tk button
  advertises an `InvokePattern` and a `DefaultAction` of "Press", and both are pretence:
  measured against a click counter inside the application, `InvokePattern.Invoke()` and
  `LegacyIAccessible.DoDefaultAction()` each return cleanly and fire nothing. pytest-uia
  therefore refuses to *act* through a pattern the generic proxy is inventing, and uses
  the mouse and the keyboard instead. The consequence is not free: a Tk suite is exposed
  to the [refusal of synthetic input](#the-fallback-paths-depend-on-synthetic-mouse-input-and-that-can-be-refused)
  described below, where a WinForms suite is not. Tk gains UIA's precision — roles, empty
  text boxes, independence from fonts and themes and DPI — but not UIA's immunity to a
  higher-integrity window holding the foreground.
- **A Tk app you cannot modify is still an OCR case.** Annotation is in-process only.
  Reaching for another process's window handle does not raise; it silently does nothing,
  and can corrupt an annotation that process made for itself. `tk-uia`'s README documents
  a narrow, names-only cross-process rescue and the warnings that come with it; here, the
  pixel fallback is the supported answer.

And all of this is temporary, deliberately. **TIP 733 is Final for Tk 9.1**:
`win/tkWinAccessibility.c` is merged, MSAA-based, with the same role mapping and the same
`<Map>` registration, so a Tk 9.1 application is accessible with nothing added. Tk 9.1 is
in beta, with stable expected around **September 2026** — but CPython 3.13 and 3.14 bundle
Tk 8.6.15, CPython 3.15 bundles Tk 9.0.4, and neither carries any of it, so the earliest
bundled accessible Tk is realistically **CPython 3.16**. `tk_uia.enable()` already detects
a Tk that answers for itself and stands down, and what pytest-uia does with such a window
— whether the trust rule admits it automatically once the proxy is out of the picture — is
an open question on the [ROADMAP](ROADMAP.md), unanswerable until Tk 9.1 is installable.

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

### The fallback paths depend on synthetic mouse input, and that can be refused

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
an input event, so UIPI never sees it. What is affected is everything that ends in the
mouse: a click on a phrase OCR located, and a click on a control the generic proxy speaks
for on behalf of a toolkit that implements no accessibility of its own — a Tk widget,
annotated or not. That is the thesis of this project
demonstrated by accident, and it is also the honest cost of the Tk support above: a
WinForms suite goes through patterns and is immune, a Tk suite injects real input and is
not.

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
| OCR recognition, warm | **5–13 ms** per grab of a fixture window, across three sessions — most recently 8–12 ms against the 460×280 canvas fixture |
| OCR recognition, first call in a process | 15–83 ms (WinRT engine creation) |
| OCR accuracy on the canvas fixture | every word, every run — 12 pt Segoe UI, black on white |
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
uv pip install -e ..\tk-uia        # the sibling repo (>= 0.2.0), cloned beside this one

pytest -m "not gui" -q             # instant; no windows, runs on any platform
pytest -m gui -q                   # drives real windows — hands off the mouse
pytest -q                          # everything

ruff check src tests
ruff format --check src tests
```

`tk-uia` is a **test-time** dependency and nothing more: it is what the Tk fixture app
calls to give its own widgets names and roles, so it belongs to the fixture rather than
to the plugin. It is not on PyPI either, hence the path install. Without it, every spec
that drives the Tk fixture skips with `install tk-uia` rather than failing — the app
would otherwise die during its own imports and surface as a baffling thirty-second "no
visible top-level window".

**Two consequences of that being a skip rather than a failure.** A full run can go green
with the entire Tk half unexercised, and only the skip count says so — so read it. And
because nothing declares the dependency, nothing enforces the version either: the fixture
app calls `bind_value_variable`, added in **tk-uia 0.2.0**, so an older sibling fails at
that line instead of skipping cleanly.

The `gui` suite launches three fixture applications:

- **`tests/fixture_apps/winforms_app.ps1`** — a WinForms form with the rich accessibility
  tree it was born with, standing in for a well-behaved native app.
- **`tests/fixture_apps/tk_app.py`** — classic Tk widgets, made findable by
  `tk_uia.enable()`. It asserts that call returned `ANNOTATED` and exits if it did
  not, because a version gate that mis-fired leaves every widget exactly as bare Tk
  left it, and the specs would then be quietly measuring bare Tk. `enable()` names
  what a widget can be named from; the app supplies the rest, which is the honest
  shape of the work — the entry has no `-text` to infer a name from, and neither
  its value nor the status line's text follows the widget on its own.
- **`tests/fixture_apps/tk_canvas_app.py`** — one `tk.Canvas` and `create_text`, exposing
  **zero** UIA children, deliberately never annotated. It is the only window left that
  the pixel path has to carry, and it exists so that OCR keeps real coverage.

`tests/fixture_apps/legible.py` holds what the two Tk apps share: DPI awareness and the
12 pt black-on-white that keeps OCR's job honest.

The same journey runs against all three, and
`tests/test_uia_hybrid_end_to_end.py` is the pair of specs that justifies the whole
design. They assert **which link answered**, not merely that the journey passed: the
pixel locator is wrapped in a counting decorator, and the count has to be `0` for both
windows with an accessibility tree and greater than `0` for the canvas. Passing alone
stopped being evidence the moment Tk became accessible — the old single spec went on
passing under a parameter id that had become a lie.

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

tests/fixture_apps/
├── winforms_app.ps1  # a full accessibility tree, and always had one
├── tk_app.py         # classic Tk, given names and roles by `tk_uia.enable()`
├── tk_canvas_app.py  # paint and nothing else: zero UIA children, never annotated
└── legible.py        # the DPI awareness and 12 pt black-on-white both Tk apps share
```

The layering is enforced by the Ubuntu CI lane: `domain/` and `application/` must import
and run with no Windows anywhere.

## License

[MIT](LICENSE)
