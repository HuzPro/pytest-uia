# Changelog

## 0.1.0 — 2026-07-26

First release. A pytest plugin that locates Windows GUI elements through the UI
Automation accessibility tree, with Windows' own OCR engine as a last resort for
surfaces whose controls expose nothing a name-based query can reach.

- **Locator chain: the accessibility tree first, pixels only if it had nothing to
  say.** `UiaLocator` searches under the window for a control of the right control
  type carrying that exact accessible name; `OcrLocator` brings the window to the
  front, grabs its rectangle with `mss` and hands the bytes to
  `Windows.Media.Ocr` — no Tesseract, no install, no model download. The chain
  reports every link that missed, so a failure says where it looked rather than
  only what it wanted. OCR joins the chain only when the `ocr` extra is present.

- **One authority on waiting.** Adapters are one-shot by contract and the driver
  is the only thing that retries, inside the element's implicit wait
  (`--uia-timeout`, default 5 s, overridable per call with `timeout=`). This is
  not a stylistic preference: `uiautomation` retries for ten seconds inside its
  own searches, and left alone underneath a polling loop it turns every
  configured timeout into a multiple of itself. A spec asserts that a miss
  against a real window returns in well under a second, so the property cannot
  quietly regress.

- **A fluent driver and a leak-proof `gui` fixture.** `app.button("New
  Task").click()`, `app.textbox("Title").type_text(...)`,
  `app.text("task created").exists()`; `gui.launch(...)` blocks until the app owns
  a visible window, `gui.attach(title=...)` takes a handle on one already on
  screen. Elements are proxies that re-resolve on every interaction, because a
  control cached across a repaint is a stale UIA element whose every property
  access fails. The fixture shuts down everything a test launched — close, then
  terminate, then `taskkill /t /f` — whatever the test did or failed to do.
  Attached apps are never killed; they may belong to the developer.

- **Synthetic mouse input that admits when Windows refused it.** Two gui specs
  were intermittently failing with "phrase not visible" about a phrase that was
  plainly on screen. The cause was not OCR: while a window owned by a
  higher-integrity process holds the foreground, User Interface Privilege
  Isolation drops every event a medium-integrity process injects — `SetCursorPos`
  returns 0 and the cursor does not move — and `uiautomation.Click` throws that
  answer away, so a click that never happened is indistinguishable from one the
  application ignored. Clicks now go through a checked pointer that keeps the
  return values of `SetCursorPos` and `SendInput` and raises `InputRefused`; the
  driver retries it inside the element's implicit wait, sharing one deadline with
  resolution rather than nesting a second one; and if it is refused for the whole
  wait, the failure names the window holding the foreground, its pid, and what to
  do about it. `InputRefused` is part of the public surface so a suite can decide
  for itself whether a refusing desktop is a failure or a skip. UIA pattern calls,
  screen capture and OCR are unaffected by any of this, which is the clearest
  argument for the accessibility-first design that the project could have asked
  for.

- **Windows owned by descendants of the launched process are found.**
  `gui.launch([sys.executable, "app.py"])` used to time out and never find a
  window: on Windows the `python.exe` inside a virtual environment is a copy of
  CPython's launcher and runs the real interpreter as a *child*, so the pid
  `subprocess` reports owns nothing that is ever painted. Console-script shims and
  `.bat` wrappers behave identically. Window resolution now accepts the launched
  process or anything descending from it, walking a `CreateToolhelp32Snapshot` of
  the process table on each attempt.

- **The Tkinter claim, corrected.** Tk does not "expose no accessibility tree" —
  its toplevel is a proper `WindowControl`, its button is a `ButtonControl` with
  an **empty accessible name**, and its label is exposed as an `ImageControl`
  rather than as text. The accurate statement, and the one the README makes, is
  that Tk exposes unnamed, mis-roled controls that no name-based query can reach.
  Window-level UIA works fine, which is exactly what lets the OCR path find the
  window and bring it to the front.

- **Ships type information**, verified present in the built wheel and sdist
  rather than assumed. CI runs `pytest -m "not gui"` on {Ubuntu, Windows} ×
  {3.10, 3.13}; the Ubuntu lane exists to prove the domain and application layers
  have stayed free of Windows, and that the win32-marked dependencies install
  cleanly on a machine that cannot use them. The gui suite is local-only in v1 —
  it needs an interactive desktop it owns.

- **Cut from this release:** screenshot-on-failure, which was designed and
  budgeted for v1 and lost its slot to the click-resilience work above. The
  capture adapter it needs already ships. See [ROADMAP.md](ROADMAP.md).
