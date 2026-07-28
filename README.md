# pytest-uia

[![tests](https://github.com/HuzPro/pytest-uia/actions/workflows/tests.yml/badge.svg)](https://github.com/HuzPro/pytest-uia/actions/workflows/tests.yml)
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
| A Tkinter app **you own** | **pytest-uia**, plus [`tk-uia`](https://github.com/HuzPro/tk-uia) inside the app itself. One call there gives every widget a name and a role, and every query here is then an ordinary UIA query — full accessibility tree, no OCR. Read [The Tkinter case](#the-tkinter-case-stated-precisely) for what it does and does not buy. |
| A Tkinter app you **cannot modify** | **pytest-uia**, with the OCR fallback. Annotation is in-process only, so somebody else's Tk app is the case the pixel path still exists for — with all of the caveats below. |

## Quickstart

```bash
pip install "pytest-uia[ocr]"     # drop [ocr] if you never need the pixel fallback
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

`todo_app.py` above stands for *your* application. To run something real before you have
one, point it at a fixture app from this repo — they are the same three windows the
suite here drives:

```python
import sys
from pathlib import Path

import pytest

FIXTURE_APPS = Path("path/to/pytest-uia/tests/fixture_apps")


@pytest.mark.gui
def test_the_tk_fixture_app_can_be_driven(gui):
    app = gui.launch([sys.executable, str(FIXTURE_APPS / "tk_canvas_app.py")])

    assert app.title == "pytest-uia Canvas Fixture"
```

`tk_canvas_app.py` needs nothing but Python; `tk_app.py` additionally needs
[`tk-uia`](https://github.com/HuzPro/tk-uia) installed, and the WinForms one is a
PowerShell script that has to be launched the way `tests/conftest.py` launches it
(`-Sta` is not optional, and `-WindowStyle Hidden` keeps the console host from being a
second window owned by the same pid).

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
| `app.tab(name)` | One tab of a notebook; `click()` selects it. A notebook unmaps every page but the open one, so this is what a test reaches before anything behind it. |
| `app.checkbox` / `radio` / `slider` / `spinbox` / `combobox` / `listbox` / `tree` / `progressbar` / `scrollbar` / `group` / `image` / `split_button` / `separator` / `thumb` / `tab_strip` | The rest of the controls, one call each. A `listbox` and a `tree` are findable; their *rows* are not — see the caveats. |
| `element.is_checked()` | Whether a checkbox or radio button is on. A read, so it works through the MSAA proxy that cannot be *driven*. Anything with no toggle state answers `False`. |
| `element.click()` / `.type_text(s)` / `.read_text()` | Act on it, or read it. |
| `element.exists(timeout=None)` | `True`/`False` instead of an exception, for both directions of assertion. Two things still raise through it — see [what `exists()` does not absorb](#what-exists-does-not-absorb). |
| `element.wait_visible(timeout=None)` | Block until it is actually painted, then return itself so a call can follow. |
| `element.wait_until_text_is(expected, timeout=None)` | Block until it reads exactly `expected`, then return itself so a call can follow. |
| `app.dialog(title, timeout=None)` | Wait for a child window and return a `Dialog` whose queries stop at that window's edge. |
| `dialog.button(name)` / `.textbox(name)` / … | Every query an `App` has, answered inside the dialog only. |
| `dialog.wait_closed(timeout=None)` | Block until the application has taken the dialog off screen. |
| `app.has_dialog(title, timeout=None)` | `True`/`False` instead of an exception, the way `element.exists()` is. |
| `app.close()` / `app.pid` / `app.title` | End it, or ask about it. |
| `app.dump()` / `dialog.dump()` | Every control in that window, each with the query that would find it. Returns a `Dump`: `str()` for the tree, `.queries` for the same list as data, `.with_window_chrome()` to unfold the title bar. Takes no input and steals no foreground. |
| `app.dump(limits=DumpLimits(max_nodes=5000, budget=30.0))` | Raise the node cap or the wall-clock budget when the dump says it stopped early. |
| `python -m pytest_uia --title "..."` | The same dump from a terminal, against a window already on screen — no test needed. `--all`, `--max-nodes`, `--budget`, `--attach-timeout`. |
| `--uia-timeout SECONDS` | The implicit wait every lookup inherits. Default 5 s; any call can override it with `timeout=`. |

Names are matched **exactly** in v1. Substring and regex matching are on the roadmap.

### The failures, and what each one blames

Every one of these is exported from the package, so a suite can catch it by name. That
is the whole point of there being more than one: a gui failure usually leaves nothing
behind but its message, and which exception it is says where to start looking.

| Failure | What it means |
|---|---|
| `ElementNotFound` | Nothing matched the query for the whole wait. Carries how long it waited and what each link of the chain saw. |
| `WindowNotFound` | The application has nothing on screen at all — including the case where it *had* something and the application has since exited. |
| `LaunchFailed` | The launched command was over before it owned a window, with the exit code it ended on. |
| `DialogNotFound` | The main window is right there and the addressed child window is not, so the first suspect is the step that was supposed to open it. |
| `DialogStillOpen` | Nothing is missing; a dialog a test waited to see the back of is still up. |
| `TextNeverSettled` | The element was found on every look and never read what was expected. |
| `InputRefused` | Windows dropped this process's synthetic input, or would not bring the window under test to the front. Not the application's fault, and the message names what was in the way. |
| `ProcessStillRunning` | Every way of ending an application was tried and it is still there — so the next test is about to share the desktop with it. |

### What `exists()` does not absorb

`exists()` turns an `ElementNotFound` into `False`, and that is deliberately all it
turns into `False`. Two failures still come out of it, because answering "no" to either
would be a confident report about something never actually looked at:

- **`OcrUnavailable`** — Windows has no OCR language pack installed for any of this
  user's languages, so the pixel link could not read anything and never will. Only
  reachable with the `ocr` extra installed.
- **`InputRefused`** — the window under test would not come to the front for the whole
  wait, so a screen grab would have photographed whatever is covering it. Also only
  reachable through the pixel link.

Both mean *this machine could not answer the question*, which is a different thing from
*the control is not there*.

### Driving a dialog

A first-run wizard is a sequence of dialogs that reuse their captions — `Next`,
`Back`, `Browse…`, `OK` — and usually over a main window carrying some of the same
words. Address the window, and every query inside it means that window:

```python
@pytest.mark.gui
def test_choosing_a_folder_in_the_settings_dialog(gui):
    app = gui.launch([sys.executable, "todo_app.py"])
    app.button("Open Settings").click()

    settings = app.dialog("Settings")          # waits for it to open
    settings.textbox("Folder").type_text(r"C:\data")
    settings.button("Confirm").click()         # unambiguously the dialog's Confirm

    settings.wait_closed()                     # the step is over when it is gone
    assert app.text("settings saved").exists()
```

`app.button("Confirm")` would also have found *a* Confirm — the main window's subtree
contains the dialog, so an unscoped query reaches both windows and answers with
whichever the accessibility tree offers first. `settings.button("Confirm")` searches
from the dialog's own window instead, so the main window's controls are out of reach:
`settings.button("New Task").exists()` is `False` while `app.button("New Task").exists()`
is `True`.

A dialog that never opens raises **`DialogNotFound`** (not `WindowNotFound`, which means
the application has nothing on screen at all — a different first suspect), and one that
will not go away raises **`DialogStillOpen`** from `wait_closed()`. Both messages name
the caption, where it was looked for, and how long. Both are exported, as is `Dialog`.

## Finding your control's name

Every query here is a name and a role, so the first question anyone actually has is
*what is my control called?* The accessible name is often not the visible caption, and
for a control nobody thought about it is often the empty string.

**`app.dump()` answers it in the tool you already have.** With the app on screen and no
test written yet:

```powershell
python -m pytest_uia --title "pytest-uia WinForms Fixture"
```

```
'pytest-uia WinForms Fixture' -- 10 controls: 3 addressable, 0 ambiguous, 1 unreachable, 5 chrome
WindowControl 'pytest-uia WinForms Fixture'  the window this dump was taken of
  TextControl 'ready'  id=4524358            app.text("ready")
  EditControl 'Title'  id=14420026           app.textbox("Title")
  ButtonControl 'New Task'  id=9963754       app.button("New Task")
  TitleBarControl ''                         5 more controls folded: this window's own
                                             chrome (System, Minimize, Maximize, Close).
                                             They are queryable;
                                             dump.with_window_chrome() lists them.

queries this window authorises:
  app.text("ready")
  app.textbox("Title")
  app.button("New Task")
```

**Each line carries the query that would find that control**, which is the point: this
is not a picture of a tree, it is a list of lines to paste. Inside a test the same thing
is one call:

```python
print(app.dump())            # needs `pytest -s`, or pytest captures it
pytest.fail(f"no such control\n{app.dump()}")   # or attach it to the failure
```

`app.dump()` returns a `Dump`, whose `__str__` is that text and whose `.queries` is the
same list as data, so a test can assert on it without parsing layout. `dialog.dump()` is
the same call scoped to a child window.

**It takes no input and steals no foreground.** The dump only reads properties: it never
clicks, never types, never brings a window forward and never photographs the screen. So
unlike everything on the pixel path, it keeps working while
[Windows is refusing this process's synthetic input](#the-fallback-paths-depend-on-synthetic-mouse-input-and-that-can-be-refused)
— which is exactly the situation in which you most want to know what your controls are
called. It is also safe to point at an application somebody is using: `attach` never
terminates what it attached to.

### What the dump will not do

**It never quietly leaves anything out.** A control no query can reach is printed with
the reason instead of a query, rather than being skipped — a tidy tree that disagrees
with the window on screen is worse than no tree. The same rule is why there is no depth
limit (`uiautomation`'s `maxDepth` gives no signal that it pruned: measured, a browser
window at depth 8 yields 1486 of its 5437 controls and says nothing about the other
3951), why the folded window chrome is counted, named and reversible, and why the node
cap and the time budget each announce themselves and name the call that lifts them:

```
'Some Big Window' -- 500 controls: 431 addressable, 12 ambiguous, 52 unreachable, 5 chrome
  stopped after 500 controls and there are more: raise it with
  app.dump(limits=DumpLimits(max_nodes=5000)).
```

The four categories in that header plus the window itself always add up to the total; a
spec asserts it, because a count that does not add up would mean the dump had walked
something it never reported.

**The budget bounds the walk, not a single call.** It is checked between controls, and
that is all it can be: a provider stays inside one `GetFirstChildControl` for as long as
it likes and nothing on this thread can interrupt it. Measured, the desktop's
`Program Manager` window answers five controls in 4.1 seconds, all of it in one call —
so a dump of a hostile window can still block past its budget. It cannot run away, and
it does not lie about where it stopped.

**A window whose application has exited** raises `WindowNotFound`, exactly as `app.title`
does. A single control that stops answering part-way through is kept, marked
`<unreadable>`, and the walk carries on — dropping it would be the silent omission this
whole design refuses, and abandoning the dump would throw away every control that did
answer.

**`[mouse]` says what pytest-uia will do, not what your control supports.** A control
marked with it is one this plugin will drive with the real pointer instead of through
`Invoke`/`SetValue`, because the generic MSAA proxy speaks for it — see
[how it finds things](#how-it-finds-things). It is not a claim that the control is
broken: measured, every title-bar button is marked and its `Invoke` works perfectly.
`[offscreen]` means the control is in the tree with no pixels, which is what
`wait_visible()` exists for.

**`id=` is shown but cannot be queried.** v1 searches by name and role only. Do not pin
a test to an AutomationId: measured, WinForms derives it from the window handle and it
is different on every launch (`198966 / 723224 / 919832` for the same control across
three runs of the same app). It is worth showing because it is stable where an
application sets it deliberately — WPF, or `tk_uia.set_automation_id` — and querying by
it is [on the roadmap](ROADMAP.md).

### The window that has nothing to find

The canvas fixture is the other half of the argument, and the dump is just as useful
about it:

```
'pytest-uia Canvas Fixture' -- 9 controls: 0 addressable, 0 ambiguous, 3 unreachable, 5 chrome
WindowControl 'pytest-uia Canvas Fixture'  the window this dump was taken of
  PaneControl ''                           no query: PaneControl is not a role this plugin asks for
    PaneControl ''                         no query: nothing inside it, so what it shows is paint
  TitleBarControl ''                       5 more controls folded: this window's own
                                           chrome (System, Minimize, Maximize, Close).
                                           They are queryable; dump.with_window_chrome()
                                           lists them.

queries this window authorises:
  (none: nothing in this window carries a name a query can match. If it draws its own
  controls, the pixel fallback is what is left -- see the README's OCR section. If it is
  a Tk app you own, one tk_uia.enable(root) names them.)
```

That is the finding, not a failure of the tool: an empty pane is a surface whose
contents are pixels, and no name-based query will ever reach into it. See
[the Tkinter case](#the-tkinter-case-stated-precisely).

### The dialog collision, shown rather than described

With the Tk fixture's `Settings` dialog open, both windows carry a button named
`Confirm`, and the dump says so:

```
  WindowControl 'Settings'             app.dialog("Settings")
    ...
      ButtonControl 'Confirm'          app.dialog("Settings").button("Confirm")  [mouse]
      EditControl 'Folder'             app.dialog("Settings").textbox("Folder")  [mouse]
  ...
    ButtonControl 'Confirm'            ambiguous: 2 controls answer app.button("Confirm")  [mouse]
```

The unscoped call reaches both — a search runs over the main window's whole subtree, and
the dialog is inside it — and the scoped one reaches exactly one. That is
[driving a dialog](#driving-a-dialog) demonstrated on your own application.

### When you need more than this

**Accessibility Insights for Windows** ([accessibilityinsights.io](https://accessibilityinsights.io/))
is Microsoft's free inspector, and the one to reach for when the tree is big: hover any
control and it shows the name, the control type and the patterns, live.

**`inspect.exe`** ships with the Windows SDK, under
`C:\Program Files (x86)\Windows Kits\10\bin\<sdk version>\x64\inspect.exe`. It is the
older tool and it is fussier, but it is already on any machine with the SDK installed
and it shows the raw UIA property set, which is occasionally what you need.

Everything above is the **client-side** view: what Windows will tell a separate process
about your window. [`tk-uia`](https://github.com/HuzPro/tk-uia) has a sibling dump that
answers the other half — what a Tk application *wrote* into its own annotation ledger.
The two disagreeing is the most useful diagnostic there is for a widget that was
annotated and still cannot be found. Comparing them is deliberately **not** a feature of
either package: it spans two repos, so it belongs in a `probes/` script or a written
recipe, where nobody has to install one library to debug the other.

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
[`tk-uia`](https://github.com/HuzPro/tk-uia) — a sibling project, MIT, zero runtime
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

A `Toplevel` built long **after** that call is annotated too — `enable()` leaves its
`<Map>` binding on Tk's `all` bindtag, so a dialog's widgets are named and roled as they
appear. Measured, and it is the reason [driving a dialog](#driving-a-dialog) needed no
changes in the sibling at all.

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

### OCR ignores roles, so typing into what it found is refused

The recogniser can only see text. It cannot know whether the phrase it matched was
painted on a button, on a label, or inside a picture. The concrete consequence:

```python
app.textbox("Title").type_text("Buy milk")
```

resolved by OCR will match the **label** reading "Title" beside the box rather than the
empty box itself. Rather than click those words and send the keys wherever that put the
caret, this **raises `OcrTypingRefused`** naming the two things that do work: give the
box an accessible name so UIA can see it (for Tk, that is one `tk_uia.enable(root)`), or
type through an element UIA located. It is the same judgement the adapter already makes
about an `Invoke` the generic MSAA proxy only advertises — decline a call that would
return cleanly having reached nothing anybody chose — turned on this package's own API,
and it is what [ROADMAP.md](ROADMAP.md) always said the answer was.

Clicking, reading and `exists()` are unaffected: *where* a phrase is, is exactly what
OCR does know. Roles are honoured by UIA and by UIA alone, so if your app has an
accessibility tree none of this bites you — the chain never reaches OCR.

### With `[ocr]` installed, asserting absence repeatedly steals the foreground

```python
assert not app.text("error").exists()
```

is the cheapest-looking line in a suite and one of the most expensive. Nothing matches,
so every poll walks the whole chain, and the pixel link at the end of it brings the
window to the front and photographs it before it can say no. Measured against the
WinForms fixture at the default 5 s implicit wait: **7 grabs in 5.25 s, roughly 0.78 s
apart**, each one a foreground steal — because `uiautomation.SetActive()` sleeps half a
second unconditionally, whatever happened.

This is a behaviour, not only a latency: for five seconds the window under test is
repeatedly yanked in front of whatever else is on screen. Give assertions of absence a
short deadline of their own — `exists(timeout=0.5)` — since a control you expect to be
missing rarely deserves the wait a control you expect to appear does.

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
- The same applies one step earlier, to **bringing the window forward**. Every path that
  ends in the mouse, the keyboard or a screen grab has to put the window under test in
  front first, and `SetForegroundWindow` fails for entirely ordinary reasons with no
  integrity level involved anywhere — another application called
  `LockSetForegroundWindow`, or simply got there first. `SetActive`'s answer is kept
  too, and a window that would not come forward raises `InputRefused` naming it rather
  than being clicked at, or photographed, where it is not. The fixture apps in this repo
  dodge this with `-topmost`; your application does not.
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
double-click, keyboard chords, scrolling, dialogs opened from inside another dialog,
image-diff assertions, OCR-targeted `type_text`, non-built-in OCR engines, non-Windows,
elevated processes. See [ROADMAP](ROADMAP.md) for what is deferred and
what is refused outright.

## Launching apps that are really launchers

`gui.launch([sys.executable, "app.py"])` looks like it should be trivial, and on Windows
it is not: the `python.exe` inside a virtual environment is a copy of CPython's launcher,
which starts the real interpreter as a **child process** and waits for it. The pid
`subprocess` reports therefore owns no window, ever. Console-script shims and `.bat`
wrappers have the same shape.

pytest-uia resolves a window owned by the launched process **or by anything descending
from it**, walking a `CreateToolhelp32Snapshot` of the process table on each attempt. So
the obvious call works, which is the point.

The other half of that: a command that is *not* really a launcher, and simply dies —
a typo in the path, an import error in the app, a wrapper script returning non-zero —
fails immediately with **`LaunchFailed`** and the exit code it died on, rather than
spending the whole `ready_timeout` proving that a dead process still owns no window. The
window is looked for first and the process only questioned when there is none, because
`cmd /c`, a console-script shim and a `.bat` all exit the moment the real application is
up: an exit only means anything when there is nothing on screen.

## Measured

From the fixture apps in this repo, on a Windows 11 development machine:

| | |
|---|---|
| OCR recognition, warm | **4.5–13 ms** per grab of a fixture window, across four sessions — most recently 4.5–6.4 ms (median 5.1) against the 476×319 canvas fixture, on the worker thread 0.4.1 moved the recognise onto |
| OCR recognition, first call in a process | 12.9–83 ms (WinRT engine creation) |
| OCR accuracy on the canvas fixture | every word, every run — 12 pt Segoe UI, black on white |
| UIA window readiness after launch | ~0.33 s |
| Dominant cost of an OCR find | `uiautomation.SetActive()`'s unconditional `time.sleep(0.5)` |
| One `exists()` that finds nothing, with `[ocr]` installed | 7 grabs in 5.25 s at the default implicit wait — 7 foreground steals, ~0.78 s apart |
| Launch of a command that dies at once | 0.34 s to `LaunchFailed`, against 6.42 s of an overridden 6.2 s deadline before 0.4.1 |
| A one-shot UIA miss under a real window | well under 1 s (a spec asserts this, to catch `uiautomation` retrying underneath) |
| `app.dump()` of a fixture window | 10 controls in **26 ms** (WinForms); 21 in 39–44 ms (Tk with its dialog open); 9 in 15–24 ms (canvas) |
| `app.dump()` of a browser window showing a video page | 5437 controls in **1.75 s** — past the 500-control cap, so it stops and says so |
| `app.dump()` of the desktop's `Program Manager` | **5 controls in 4.1 s**, all of it inside a single `GetFirstChildControl` — which is why there is a wall-clock budget as well as a node cap |
| Per control walked | 0.55 ms for identity, +0.17 ms for the fact behind `[mouse]`. Pattern probing would add 0.19 ms and is not done: whether a provider *advertises* `Invoke` is the question the trust rule exists because you cannot believe |

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
uv pip install tk-uia              # what the Tk fixture app annotates itself with

pytest -m "not gui" -q             # instant; no windows, runs on any platform
pytest -m gui -q                   # drives real windows — hands off the mouse
pytest -q                          # everything

ruff check src tests
ruff format --check src tests
```

`tk-uia` is a **test-time** dependency and nothing more: it is what the Tk fixture app
calls to give its own widgets names and roles, so it belongs to the fixture rather than
to the plugin. Without it, every spec
that drives the Tk fixture skips with `install tk-uia` rather than failing — the app
would otherwise die during its own imports, and a skip that names the missing package
beats a `LaunchFailed` that can only report the exit code it died on.

**Two consequences of that being a skip rather than a failure.** A full run can go green
with the entire Tk half unexercised, and only the skip count says so — so read it. And
because nothing declares the dependency, nothing enforces the version either: the fixture
app calls `bind_value_variable`, added in **tk-uia 0.2.0**, so an older sibling fails at
that line instead of skipping cleanly.

The `gui` suite launches three fixture applications:

- **`tests/fixture_apps/winforms_app.ps1`** — a WinForms form with the rich accessibility
  tree it was born with, standing in for a well-behaved native app.
- **`tests/fixture_apps/tk_app.py`** — classic Tk widgets, made findable by
  `tk_uia.enable()`, plus the modal `Toplevel` (`transient()` + `grab_set()`) the
  dialog specs drive. Its `Confirm` shares a name with a `Confirm` on the main
  window on purpose: two controls answering one query is what makes "which window
  did you mean" a question at all. It asserts that call returned `ANNOTATED` and exits if it did
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
├── __main__.py      # `python -m pytest_uia`: argparse over the same attach and dump
├── domain/          # stdlib only — queries, the locator chain, waiting, the tree dump
├── adapters/        # uiautomation, comtypes, WinRT, mss, ctypes — nothing leaks past here
└── application/     # composes the two; imports pytest nowhere

tests/fixture_apps/
├── winforms_app.ps1  # a full accessibility tree, and always had one
├── tk_app.py         # classic Tk + a modal dialog, named by `tk_uia.enable()`
├── tk_canvas_app.py  # paint and nothing else: zero UIA children, never annotated
└── legible.py        # the DPI awareness and 12 pt black-on-white both Tk apps share
```

The layering is enforced by the Ubuntu CI lane: `domain/` and `application/` must import
and run with no Windows anywhere.

## License

[MIT](LICENSE)
