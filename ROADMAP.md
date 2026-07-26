# Roadmap

Direction: the thing that makes this plugin worth having is that a locator is a
*query* rather than a picture — so every item below either extends what can be
queried, or removes a reason someone has to drop out of the query world and back
into coordinates. Breadth of widget support comes second to that, and speed comes
a distant third: a gui suite is bounded by the application's own repaint, not by
anything in here.

## Shipped in v0.3

One call for the wait every asynchronous GUI forces on its tests.

- **`element.wait_until_text_is(expected, timeout=None)`**, polling through the
  same implicit wait as everything else and re-resolving the element on every
  look. Timing out raises `TextNeverSettled` — the element was found, its text
  never settled — carrying both what it read and what was expected.

- **The scaffolding it replaced was deleted**, and the Tk fixture app took up
  `tk-uia`'s new `bind_value_variable` in place of a hand-written variable
  trace. Between them the fixture and its spec lost 72 lines and gained 18. One
  consequence for anyone running the gui suite: the Tk specs now need
  **tk-uia >= 0.2.0**.

## Shipped in v0.2

Tkinter driven through the accessibility tree rather than through its pixels,
an adapter that refuses to act on a pattern a provider only advertises, and a
fixture set that makes it visible which link of the chain answered.

- **`tk-uia`, a sibling project.** Tk is unnamed and mis-roled *by default*, and
  an application can fix that for itself: one `enable(root)` annotates every
  widget's MSAA name and role through `IAccPropServices`, which Windows bridges
  into UI Automation. It is a separate package (MIT, zero runtime dependencies,
  not published) because making a Tk app usable with a screen reader is a
  broader problem than making it testable. Nothing shipped here imports it: only
  the Tk fixture app does, and the specs that drive that app skip when it is
  absent.
- **The untrusted-provider rule.** An action pattern served by the generic MSAA
  proxy is not attempted at all: `Invoke` and `SetValue` there succeed and reach
  nothing, so the mouse and keyboard do the work instead. Reads stay ungated.
- **Three fixture applications**, the third of them deliberately inaccessible —
  a canvas-drawn Tk window with zero UIA children, so the pixel path keeps real
  coverage now that Tk no longer provides it.
- **Specs that count which link answered**, rather than only that the journey
  passed: `pixels.asked == 0` for both windows with an accessibility tree, and
  greater than zero for the one without.

## Shipped in v0.1

The UIA-first locator chain with an OCR last resort, a fluent driver, the `gui`
fixture, and two fixture applications that prove the same journey runs against a
window with a rich accessibility tree and one without.

- **Locator chain.** `UiaLocator` then `OcrLocator`, first answer wins, with a
  failure that names the query and what every link saw instead of it. The OCR link
  joins only when the `ocr` extra is installed, so a project that never needs it
  never pays for it.
- **One authority on waiting.** Adapters look once; only the driver retries, inside
  the element's implicit wait (`--uia-timeout`, default 5 s, overridable per call).
- **Windows' built-in OCR**, through the pywinrt projections — no Tesseract, no
  install, no model download.
- **Honest refusal of synthetic input.** A click Windows drops is now
  distinguishable from a click the application ignored; see the README.
- **Windows owned by descendants of the launched process** are resolved, so
  `gui.launch([sys.executable, "app.py"])` works despite the venv launcher.

## Next

- **Child modal dialogs.** The first thing a real suite hits after the main
  window, and the first thing that would be built next: a first-run wizard is a
  sequence of them. Currently a window is resolved once, at launch, and a dialog
  that opens afterwards is invisible to the driver.
- **Substring and regex name matching.** v1 matches accessible names exactly,
  which breaks the moment an app appends a count or a state to a caption
  ("Inbox (3)").
- **Wire the Tk 9.1 native path.** `tk-uia` detects a Tk that answers
  `WM_GETOBJECT` for itself, stands down and reports `NATIVE`; wiring the `tk
  accessible` commands is its own roadmap item, blocked on Tk 9.1 being
  installable. What that means *here* is a question nobody can answer yet: once
  Tk carries a real provider the generic MSAA proxy is out of the picture, and
  whether the trust rule then admits Tk automatically, or needs a check of its
  own, has to be measured rather than predicted. It is on this list so that the
  day Tk 9.1 can be installed, somebody looks.
- **`--uia-trust-invoke={auto,always,never}`.** The rule that decides whether a
  provider's action patterns can be believed is a hardcoded set of framework
  ids, and overriding it means editing the package. It will be wrong in one
  direction or the other eventually — a toolkit that honours `Invoke` and is not
  on the list, or a proxied control whose `Invoke` really does reach its
  application — and an escape hatch is cheaper than a release. `auto` is what
  ships today; `never` is a suite that would rather click everything than risk a
  silent no-op; `always` is somebody who has measured their own app and knows
  better.
- **Screenshot on failure.** Designed, specified, cut from v1 when click
  resilience turned out to matter more, and deferred again in 0.2 for the
  correctness work on what a click even *is*. `mss` is already a core
  dependency and the capture adapter already exists; what is missing is the
  pytest hook, a `--uia-screenshot-dir` option, and node-id-to-filename
  sanitising.
- **Trial the gui suite on a GitHub Windows runner.** The gui specs are
  local-only today. Whether a hosted runner offers a desktop that accepts
  foreground changes and synthetic input reliably enough to be a gate — rather
  than a source of the exact flakiness v0.1 spent its budget removing — is an
  open question that deserves an experiment rather than an assumption.
- **Keyboard injection that reports refusal.** Clicks now surface Windows'
  refusal; keystrokes do not, because `SendKeys` has no return value to inspect.
  Fixing it means owning key-name parsing rather than borrowing it.

## Non-goals for v1

These are deliberate omissions, not oversights. Each would be a reasonable
addition later; none is missing by accident.

- **Widgets:** menus, comboboxes, checkboxes and radio buttons, tables and trees.
- **Interactions:** drag-and-drop, right-click, double-click, keyboard chords,
  scrolling.
- **Assertions:** image-diff comparisons. If a test needs to compare pixels, this
  is the wrong tool — see the README's table.
- **OCR-targeted `type_text`.** OCR cannot see roles, so it cannot distinguish an
  input box from the label beside it; typing into something it located is a
  coin-flip dressed up as an API.
- **Other OCR engines.** Windows' built-in recogniser is the whole point: no
  install, no model, no second thing to configure.
- **Non-Windows.** UI Automation is a Windows API. The domain layer is kept free
  of it so the platform-independent parts can be tested anywhere, not because a
  port is planned.
- **Annotating an application this plugin did not write.** Giving a Tk window
  accessible names is the *application's* own job, and Windows offers no
  supported way to do it from outside the process: reaching for another
  process's window handle does not raise, it silently does nothing, and it can
  corrupt an annotation that process made properly. A Tk app you cannot modify
  stays an OCR case, deliberately.
- **Elevated processes.** Driving a window that runs at a higher integrity level
  than the test process requires the test process to be elevated too, and a
  testing tool that asks for administrator is a testing tool nobody runs.
- **Publishing to PyPI.** Out of scope for v1 by decision, not by omission.
