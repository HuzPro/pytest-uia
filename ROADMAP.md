# Roadmap

Direction: the thing that makes this plugin worth having is that a locator is a
*query* rather than a picture — so every item below either extends what can be
queried, or removes a reason someone has to drop out of the query world and back
into coordinates. Breadth of widget support comes second to that, and speed comes
a distant third: a gui suite is bounded by the application's own repaint, not by
anything in here.

## Shipped in v0.5

The accessibility tree dump — the answer to the first question anyone
actually has, in the tool they already have installed.

- **`app.dump()` and `dialog.dump()`**, plus
  `python -m pytest_uia --title "..."` for an application that is on screen
  before any test exists. Each line names the control *and the query that
  would find it*, which is what turns a diagnostic into a copy-paste answer.
  It returns a `Dump`: `str()` for the tree, `.queries` for the same list as
  data, `.with_window_chrome()` to unfold the title bar. It does not print by
  itself — printing from a library call is a side effect a diagnostic should
  not have, and under pytest it would vanish into captured output anyway.

- **It does not quietly omit what it cannot see**, and that governed every
  other decision. A control no query reaches is printed with the reason
  instead of a query. The folded window chrome is counted, named and
  reversible. The node cap and the wall-clock budget each say when they bit
  and name the call that lifts them. There is **no depth limit**, refused
  rather than deferred: `uiautomation`'s `maxDepth` gives no signal that it
  pruned anything, and a browser window at depth 8 yields 1486 of its 5437
  controls in total silence — which is precisely the failure everything above
  exists to prevent.

- **Both limits are needed, and this was measured.** A node cap bounds how
  much there is to read; only a clock bounds how long it takes, because the
  desktop's `Program Manager` answers five controls in 4.1 seconds and spends
  all of it inside one call. The budget is checked between controls and cannot
  interrupt a provider that has stopped answering; that is documented rather
  than fixed, since fixing it means a worker thread and `uiautomation` is
  single-threaded-apartment-bound here.

- **`[mouse]` describes what pytest-uia will do, never what a control
  supports.** Measured: every title-bar button answers to the
  untrusted-provider rule and its `Invoke` works perfectly. A dump that told
  users their application was broken would be worse than no dump. The same
  care applies to the AutomationId, which is shown and captioned as
  unqueryable — for WinForms it is HWND-derived and different on every launch.

- **The sibling in-process dump in `tk-uia`, and the diff nobody built.**
  `tk-uia` reports what an application wrote into its own annotation ledger;
  this reports what Windows will tell another process. The two disagreeing is
  the best possible diagnostic for a widget that was annotated and still
  cannot be found — and comparing them spans two repositories, so it is a
  `probes/` script or a written recipe, deliberately not a feature of either
  package.

## Shipped in v0.4

Child modal dialogs — and a correction to what this roadmap used to say about
them.

- **`app.dialog(title)`**, which waits for a child window to open and answers
  with a `Dialog` whose `button`, `textbox` and `text` behave exactly as an
  `App`'s do, except that they are answered inside that window only. Timing out
  raises `DialogNotFound`; `dialog.wait_closed()` is the other end of a wizard
  step and raises `DialogStillOpen`; `app.has_dialog(title)` answers instead of
  raising, the way `element.exists()` does.

- **What this roadmap previously claimed was wrong, and it was measured wrong.**
  It said "a window is resolved once, at launch, and a dialog that opens
  afterwards is invisible to the driver". It never was. Tk owns a `Toplevel` at
  the Win32 level whether or not it is `transient`, so UI Automation nests it
  inside its owner's subtree, and `UiaLocator` searches the whole subtree — a
  button that exists only in a dialog was findable through `app.button(...)` in
  v0.1. What was actually missing was narrower and worse: **no way to say which
  window a query meant**. Both windows in the fixture app carry a button named
  `Confirm`, and `app.button("Confirm")` resolves to one of them by an accident
  of z-order — measured, the dialog's, and the main window's the moment it
  closes. A first-run wizard is a sequence of steps that reuse `Next`, `Back`
  and `OK`, so a suite driving one could not express "the OK **in this dialog**"
  at all.

- **The scope is a real narrowing, and a spec proves it.** Searching starts at
  the dialog's own control, not at the main window's, so the main window's
  controls are out of reach from inside a dialog — which is what a naive
  implementation gets wrong, and what `tests/test_dialog_end_to_end.py` fails on
  when the scoping is backed out. `tk-uia` needed no changes: its `<Map>`
  binding sits on the `all` bindtag, so a `Toplevel` built long after
  `enable()` is annotated like everything else.

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

- **Querying by AutomationId.** The dump shows it; no query can search by it.
  Worth having only for frameworks that set one deliberately — WPF, and any
  application calling `tk_uia.set_automation_id` — because measured, WinForms
  derives it from the window handle and it differs on every launch. Which is
  also why the dump captions it rather than offering it as a query.
- **Dump on failure.** A pytest hook attaching `app.dump()` to the report of a
  test that could not find a control. It is the same shape as screenshot on
  failure, below, and wants the same `--uia-*-dir` plumbing — so they get done
  together or not at all.
- **Dialogs within dialogs, and pinning a dialog to the window it opened as.**
  `App.dialog` addresses a child of the main window; a `Browse…` sheet opened
  from a wizard step is a child of *that* step, and reaching it means `Dialog`
  growing the same call. Not built because nothing has needed it yet, and
  because a dialog's scope already includes its own children — so the ambiguity
  only returns when two nested windows reuse a caption. Which is exactly where
  the second half of this item bites: `Dialog` remembers its *caption*, not the
  window it was handed, so `wait_closed` re-searches by name and a second
  window reusing that caption would keep it waiting forever, and `dialog_titled`
  searches at any depth and so could answer with a grandchild. Pinning the
  window by its UIA runtime id at `App.dialog` time fixes both, and it belongs
  here rather than on its own: for one dialog over one main window the current
  behaviour is right, and it is nesting that turns the edge case into the
  ordinary case. Doing them together also avoids growing the `Window` port
  twice.
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
- **Keyboard injection that reports refusal.** Clicks surface Windows' refusal,
  and since 0.4.1 so does a window that would not come to the front — which is
  the step in front of every keystroke, so a great deal of the silence is
  gone. What is left is the injection itself: `SendKeys` has no return value to
  inspect, so a keystroke Windows drops after the window *did* come forward is
  still silent. Fixing that means owning key-name parsing rather than borrowing
  it.

## Non-goals for v1

These are deliberate omissions, not oversights. Each would be a reasonable
addition later; none is missing by accident.

- **Widgets:** what is *inside* a list, a tree or a menu. The widgets themselves
  came off this list in 0.7.0 — fifteen roles, from `checkbox` to `tab_strip` —
  after a survey of every Tk widget class found 37 typed and named and 5 a test
  could ask for. Their rows and items need MSAA's `IAccessible` child-id model,
  which is a COM server and a different piece of work; `app.listbox(...)` finds
  the list and says nothing about what is in it.
- **Interactions:** drag-and-drop, right-click, double-click, keyboard chords,
  scrolling.
- **Assertions:** image-diff comparisons. If a test needs to compare pixels, this
  is the wrong tool — see the README's table.
- **OCR-targeted `type_text`.** OCR cannot see roles, so it cannot distinguish an
  input box from the label beside it; typing into something it located is a
  coin-flip dressed up as an API. **Refused in code since 0.4.1**, not merely
  in this list: `OcrElement.type_text` used to click the recognised phrase and
  send keys, which is precisely the coin-flip, and the README documented the
  misfire as a limitation of a feature this page says does not exist. It now
  raises `OcrTypingRefused` naming the two things that work instead.
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
