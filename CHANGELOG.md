# Changelog

## 0.4.0 — 2026-07-26

A test can now say which window it meant. Child modal dialogs are addressable by
the caption on their title bar, and every query answered through one stops at
that window's edge.

- **`app.dialog(title)`, and the claim it disproves.** The roadmap said a dialog
  that opened after launch was "invisible to the driver". That was never true,
  and measuring it was the first thing this release did: Tk owns a `Toplevel` at
  the Win32 level whether or not it is `transient`, UI Automation nests the
  window inside its owner's subtree, and `UiaLocator` searches the whole
  subtree — so `app.button("Only In Dialog")` found a dialog's button in v0.1,
  in both the `transient()` + `grab_set()` shape and the unowned one. The real
  gap was narrower and worse. The fixture app's dialog and its main window both
  carry a button named `Confirm`, and `app.button("Confirm")` resolves to one of
  them by an accident of z-order — measured with runtime ids, the dialog's while
  it is open and the main window's the instant it closes. A first-run wizard is
  a sequence of steps reusing `Next`, `Back` and `OK`, so a suite driving one
  could not express "the OK **in this dialog**" at all. `settings =
  app.dialog("Settings")` waits for the window, and `settings.button("Confirm")`
  is unambiguously the dialog's.

- **The scoping is a genuine narrowing, and that is the whole feature.** The
  temptation is to hand the dialog the search the app already has, which reads
  right and is wrong: the main window's subtree *contains* the dialog, so such a
  "scope" excludes nothing whatsoever. Instead the adapter resolves the child
  window — `UiaWindow.dialog_titled`, constrained to a `WindowControl` so a
  label carrying the same words cannot answer — and the `Dialog` searches from
  *that* control. The proof is `tests/test_dialog_end_to_end.py`: with the
  scoping backed out to the naive version, the spec that asks the dialog for a
  button only the main window has fails with `assert True is False`, while the
  spec that drives the shared `Confirm` goes on passing — because the tree
  happened to offer the dialog's copy first. That accident is exactly why the
  narrowing spec exists, and why passing was never evidence on its own.

- **A `Dialog` is not an `App`, deliberately.** Reusing `App` would have been
  one line and would have dragged `close()` and `pid` onto an object that owns
  no process and whose window a test has no business ending — borrowed
  semantics that fit the window underneath and not this one. What the two do
  share is the way in, so `button`, `textbox` and `text` come from one place
  (`ElementSource`) and behave identically in both, per-call `timeout=`
  included.

- **Two new failures, each naming a different suspect.** `DialogNotFound` is
  raised when a dialog never opens, rather than `WindowNotFound`, because the
  two send a reader to opposite ends of the problem: `WindowNotFound` means the
  application has nothing on screen and is what a launch waits through, while
  this one is raised by an app whose main window is right there — so the first
  suspect is the step that should have opened the dialog. `DialogStillOpen` is
  the other end, raised by `dialog.wait_closed()` when a wizard step will not
  leave. Both messages carry the caption and how long it was waited for
  (`no dialog titled 'Settings' opened within 5.0s; no window titled 'Settings'
  inside 'pytest-uia Tk Fixture' (pid 1234)`), on the same reasoning as
  `InputRefused` in 0.1.0: a gui failure usually leaves nothing behind but that
  string. Both are exported from the package, as is `Dialog`.

- **Waiting is still `poll`, and there is no new machinery.** A dialog opens on
  the application's own message pump, so `dialog()` polls exactly as
  `exists`/`wait_visible`/`wait_until_text_is` do, inside the element's implicit
  wait, with per-call `timeout=` overriding `--uia-timeout`. `wait_closed` polls
  the same way and asks the window *underneath* whether the dialog is still
  there, rather than interrogating a control that may already have been
  destroyed — "it raised" is not the same answer as "it is gone".

- **The Tk fixture app grew the wizard shape.** It now opens a modal `Toplevel`
  with `transient()` + `grab_set()`, carrying a `Folder` entry and a `Confirm`
  whose name is deliberately shared with a new `Confirm` on the main window; the
  dialog's saves to the status line and dismisses itself, so a spec can prove
  which of the two ran by what outlives the window. The WinForms fixture is
  untouched: one collision proves the point, and the Tk case is the one the
  sibling `tk-uia` had to be checked against. It needed no changes — its `<Map>`
  binding sits on the `all` bindtag, so a `Toplevel` built long after
  `enable()` is annotated exactly like the widgets that were there first.

## 0.3.0 — 2026-07-26

Waiting for an element's text to become what a test expects stops being every
suite's own hand-rolled poll and becomes one call on the driver.

- **`element.wait_until_text_is(expected, timeout=None)`.** A GUI is
  asynchronous: the application reacts on its own message pump, so the repaint
  lands after the call that caused it has already returned. The consequence is
  the most ordinary race in desktop testing — type into a box, assert on it in
  the next line, and read the value the box held before the keys arrived. v0.2
  gave a test `read_text()` and no way to wait on it, so the only way through
  was to build the affordance yourself, and **this repo's own specs were the
  evidence**: `tests/test_uia_tk_end_to_end.py` carried a `StillCatchingUp`
  exception, a `_once_the_tree_has_caught_up` helper and a hand-built
  `RetryPolicy` fed to `poll`, twelve lines of scaffolding to express one
  sentence. That sentence is now `app.textbox("Title").wait_until_text_is("Buy
  milk")`. It re-resolves the element on every look, exactly as `click` and
  `type_text` do — an element cached across the polls would go on reading the
  value the application has already replaced, which is the precise failure the
  method exists to absorb — and it returns the element itself, so a call can
  follow it the way one follows `wait_visible`.

- **A missing element is a miss; missing *text* is `TextNeverSettled`.** The
  timeout raises a new domain error rather than `ElementNotFound`, because the
  element *was* found, on every single look — what never happened is its text
  settling, and reporting that as a missing control sends whoever reads the
  failure hunting for something that is right there. Same distinction, and the
  same reasoning, as `InputRefused` in 0.1.0. The message carries both readings
  (`Textbox 'Title' — reads '', not 'Buy milk'`), because a gui failure usually
  leaves nothing behind but that string and "the text is wrong" is not something
  anybody can act on. A control that is *not* on screen yet stays an ordinary
  miss and keeps the wait going — the click that sets a label's text is usually
  the click that creates it, so both kinds of lateness share one deadline — and
  if it never appears, the failure is still an honest `ElementNotFound`.
  `TextNeverSettled` is exported from the package, so a suite can catch it by
  name.

- **No new waiting machinery.** The method polls through the domain's existing
  `poll`, inside the element's implicit wait, with the same precedence
  everything else has: per-call `timeout=` overrides `--uia-timeout`. There are
  no sleeps anywhere in it, and the unit specs that pin its retrying run against
  a fake clock in milliseconds.

- **The scaffolding it replaced is gone, and it was hiding a bug.** The new
  method was added first and measured against the hand-rolled spec while that
  spec still passed, so the two were never confused; the deletion followed. It
  is not only tidying: `_once_the_tree_has_caught_up` re-read *the same
  `Element` object* on every attempt instead of resolving through the chain, so
  against a window that rebuilt its controls it would have polled a stale
  object to the deadline and then blamed the application. That left two specs
  proving one journey by different means, and the one kept goes through the
  fluent element a reader's own suite would write, which exercises the chain
  and the adapter underneath it anyway.

- **The Tk fixture app keeps its accessible value in step with one call.**
  `tk-uia` 0.2.0 added `bind_value_variable`, so the closure, the `trace_add`
  and the easily-forgotten priming call that kept an entry's announced value
  truthful became a single line. Together with the deletion above, the fixture
  and its spec lost 72 lines and gained 18. Both changes were checked for being
  load-bearing rather than merely green: with the binding removed, the journey
  fails `TextNeverSettled: Textbox 'Title' — reads '', not 'Write the report'`.
  Note this raises the floor on the sibling: the Tk specs now need **tk-uia
  ≥ 0.2.0**, and without it installed they skip rather than fail.

## 0.2.0 — 2026-07-26

Tkinter moves out of the OCR fallback and into the accessibility tree, and the
pixel path is left with a window that genuinely has no tree at all. Along the
way, a click that could succeed without pressing anything is fixed.

- **Tkinter is drivable through UI Automation, and the OCR fallback is now a
  regression path rather than Tk's road in.** v0.1 shipped honest about this:
  bare Tk puts every widget in the tree under no name and mostly the wrong
  control type, so a query by name and role matched nothing and OCR carried
  Tkinter entirely. That was a statement about *bare* Tk, and the missing word
  was "bare". MSAA lets a process annotate the accessible properties of its own
  windows through `IAccPropServices`, and UI Automation reads those annotations
  back out through a proxy that outranks the plain one — so an application can
  say who its widgets are. That work is its own project,
  [`tk-uia`](../tk-uia) (MIT, zero runtime dependencies, not published), because
  "a library that makes Tkinter apps work with screen readers" and "a pytest
  plugin that drives Windows GUIs" are each one clean sentence and explain each
  other badly when welded together. Read back through UIA from a separate
  process, one `tk_uia.enable(root)` turns `tk.Button` into a `ButtonControl`
  with a real name, `tk.Label` into a `TextControl` rather than an
  `ImageControl`, and `tk.Entry` into an `EditControl` carrying a `ValuePattern`
  that did not previously exist. `app.textbox("Title")` and
  `app.text("task created")` work against Tk from that point, and the README's
  journey now runs verbatim against both the WinForms and the Tk fixture app,
  parametrised in `tests/test_public_api_end_to_end.py`. Deliberately not
  supported: a Tk application whose source you cannot change. Annotation is
  in-process only — reaching across silently does nothing and can corrupt an
  annotation the other process made properly — so that case is exactly what the
  pixel fallback is still here for.

- **`_CONTROL_TYPE_FOR_ROLE` is byte for byte what it was.** The table mapping
  `button → ButtonControl`, `text → TextControl` and `textbox → EditControl` did
  not move a character to make Tk work, and that is the point rather than a
  detail: Tk became drivable by fixing the *application*, not by loosening the
  *locator*. The alternative was not merely worse, it does not work — widening
  `text` to accept `PaneControl` would match every anonymous themed widget in a
  Tk window, and those carry no name to match on either. A locator that matches
  more things matches the wrong ones.

- **Never trust an action pattern the MSAA proxy is only pretending to
  support.** `UiaElement` treated "the call raised nothing" as "the call
  worked", which is true of a real provider and false of the bridge Windows
  fabricates for any plain window whose owner never wrote one. That bridge
  synthesises `Invoke` from a posted `BM_CLICK`, and every Tk button is
  owner-drawn, so the message reaches nothing: measured against a click counter
  inside the application, `InvokePattern.Invoke()` and
  `LegacyIAccessible.DoDefaultAction()` both return cleanly and fire nothing.
  **A Tk test could pass having pressed nothing at all** — the exact failure this
  project exists to refuse. Action patterns are now taken only from a provider
  that will honour them, and where the generic proxy is doing the talking the
  mouse and the keyboard do the work instead; typing there clicks first and then
  sends keys, because Tk owns focus through its own model and Win32 focus on a
  child window is not focus. `ValuePattern.SetValue` is gated identically —
  `put_accValue` into the same void — while *reads* are deliberately left
  ungated, since a property served out of an annotation store is the
  application's own word about itself and only acting through a proxy is a
  guess. The discriminator was measured twice before it was written: both
  WinForms and Tk are served by that same generic proxy, so its marker alone
  separates nothing, and their buttons are both `BS_OWNERDRAW`, so the window
  style separates nothing either. `FrameworkId` does — `'WinForm'` against Tk's
  `'Win32'`. `test_the_winforms_button_is_still_invoked_through_its_pattern_rather_than_clicked`
  drives the WinForms fixture with a recording mouse and asserts `clicks == []`
  while the application still reacts, so the rule cannot quietly widen into the
  frameworks whose patterns are real.

- **`read_text()` no longer raises `AttributeError` at whoever ran the test.**
  `uiautomation.GetPattern` answers `None` rather than raising when a provider
  offers no such pattern, and the result was dereferenced unguarded, so reading
  an edit control whose provider never offered a `ValuePattern` escaped as a
  bare `AttributeError`. Not an `ElementNotFound`, so `poll` never retried it
  and the driver never turned it into a miss: a half-built accessibility tree
  surfaced as a crash. It now falls back to the control's `Name` when there is no
  pattern at all. What it does *not* do is fall back on an empty value: an
  annotated Tk entry nobody has typed into reads as `''`, not as `'Title'`, and a
  spec pins that, because `pattern.Value or Name` is the plausible fix that would
  make an empty box report the text of the label beside it and let an assertion
  pass for the wrong reason.

- **Three fixture applications, not two.** WinForms still stands in for a
  well-behaved native app; `tests/fixture_apps/tk_app.py` was rewritten as
  classic Tk that annotates itself and refuses to start unless
  `tk_uia.enable()` reports `ANNOTATED`, so a version gate that mis-fired fails a
  test instead of quietly leaving the specs measuring bare Tk; and
  `tests/fixture_apps/tk_canvas_app.py` is new — one `tk.Canvas`, everything
  drawn with `create_text`, measured to expose zero UIA children. The OCR specs
  moved onto it. They were reading a window that had become accessible
  underneath them, which is a bad place for the specs that exist to prove the
  pixel path still works, and a new guard,
  `test_the_canvas_window_exposes_nothing_a_name_based_query_could_reach`,
  asserts the tree has nothing to answer with — without it, a well-meaning edit
  that made this fixture accessible would leave the OCR specs passing against a
  chain that never reaches OCR.

- **The hybrid spec was vacuous, and is now two specs that count.** It claimed to
  prove that the same journey runs against a window with an accessibility tree
  and one without. The moment Tk gained one, the chain's first link answered for
  both, OCR was never consulted, and the spec went on passing under a parameter
  id reading `tkinter-through-ocr` that had become a lie — passing while proving
  strictly less than it said. Passing is no longer the evidence; **which link
  answered is**. `tests/test_uia_hybrid_end_to_end.py` wraps the pixel locator in
  a counting decorator over the real one, and asserts `pixels.asked == 0` for
  both windows with a tree and `pixels.asked > 0` for the canvas.

- **The honest cost of the Tk support.** A Tk control is found through the tree
  but *driven* by synthesised input, because its `Invoke` is pretence — so a Tk
  suite is exposed to the User Interface Privilege Isolation refusal documented
  in 0.1.0 where a WinForms suite, going through real patterns, is not. Tk gains
  UIA's precision — roles, empty text boxes, independence from fonts and themes
  and DPI — and not UIA's immunity to a higher-integrity window holding the
  foreground. This recurred while the work was being done: a
  SYSTEM-owned `GameInputServiceWindow` held the foreground for about fifty
  minutes and the suite reported `85 passed, 6 skipped`. Nothing failed falsely,
  which is the guard from 0.1.0 behaving exactly as designed.

- **`ttk` is strictly worse than classic `tk`**, measured across all fifteen
  themed widget types: every one arrives as an anonymous `PaneControl` and
  `ttk.Button` has no `InvokePattern` at all, where classic `tk.Button` at least
  arrives as a `ButtonControl`. The fixture apps are classic `tk` throughout, and
  so should yours be.

- **Upstream makes this temporary, and slowly.** TIP 733 is Final for Tk 9.1:
  `win/tkWinAccessibility.c` is merged, MSAA-based, with the same role mapping,
  so a Tk 9.1 application is accessible with nothing added and `tk_uia.enable()`
  stands down for it. Tk 9.1 is in beta with stable expected around September
  2026, but CPython 3.13 and 3.14 bundle Tk 8.6.15 and CPython 3.15 bundles Tk
  9.0.4, neither of which carries any of it, so the earliest bundled accessible
  Tk is realistically CPython 3.16. What the trust rule should do with a Tk that
  answers for itself is an open question until then, and it is on
  [ROADMAP.md](ROADMAP.md) rather than guessed at here.

- **Still cut:** screenshot-on-failure, deferred again. Nothing about it got
  harder; the click-correctness work above simply mattered more.

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
