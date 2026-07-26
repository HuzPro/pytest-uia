# Roadmap

Direction: the thing that makes this plugin worth having is that a locator is a
*query* rather than a picture — so every item below either extends what can be
queried, or removes a reason someone has to drop out of the query world and back
into coordinates. Breadth of widget support comes second to that, and speed comes
a distant third: a gui suite is bounded by the application's own repaint, not by
anything in here.

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
- **Screenshot on failure.** Designed, specified, and cut from v1 when click
  resilience turned out to matter more. `mss` is already a core dependency and
  the capture adapter already exists; what is missing is the pytest hook, a
  `--uia-screenshot-dir` option, and node-id-to-filename sanitising.
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
- **Elevated processes.** Driving a window that runs at a higher integrity level
  than the test process requires the test process to be elevated too, and a
  testing tool that asks for administrator is a testing tool nobody runs.
- **Publishing to PyPI.** Out of scope for v1 by decision, not by omission.
