# Changelog

## 0.7.1 - 2026-07-28

No library code changed.

- **Publishing is a tag push.** `.github/workflows/publish.yml` builds and
  uploads to PyPI through Trusted Publishing on any `v*` tag, and refuses a tag
  whose number differs from `__version__`. No API token is stored anywhere.
  `RELEASING.md` documents the flow.

## 0.7.0 - 2026-07-27

Fifteen new roles, and a survey that explains why they were needed. Reading
every widget class both Tk toolkits ship found 37 of them typed and named, and
**5** a test could ask for. Every checkbox, slider, listbox and tree in every Tk
application was announced correctly to a screen reader and reachable by nothing
here.

- **`app.checkbox` / `radio` / `slider` / `spinbox` / `combobox` / `listbox` /
  `tree` / `progressbar` / `scrollbar` / `group` / `image` / `split_button` /
  `separator` / `thumb` / `tab_strip`**, on `App` and on `Dialog` alike. Each is
  one control type, named the way somebody writing a test would say it (the
  precedent `textbox` set over `EditControl`) except the three with no everyday
  name, which take UI Automation's own: this plugin drives WinForms and WPF too,
  and naming a control after the Tk widget would be it speaking one toolkit.

- **`element.is_checked()`.** The one read a spec forced: a suite that clicks a
  checkbox and assumes it toggled passes just as happily when the click went
  nowhere, which on an owner-drawn Tk button it silently can. Ungated by
  provider trust, like `read_text` and for the same reason, a state the
  provider reports is a fact, where an action through it is a guess. A control
  with no toggle state answers `False` rather than raising.

- **No read for a slider.** Measured: an annotated Tk `Scale` reaches a client
  as a `SliderControl` offering no pattern at all, so there is no honest way to
  read its number. A `ttk.Progressbar` does carry a ValuePattern and `read_text()`
  already returns it. No API was added for the case that cannot be served.

- **The dump offers a query for every one of them**, derived from the same table
  the search reads, so widening what can be found and widening what is offered
  stay a single edit.

- **A gallery fixture and nineteen end-to-end specs.** One window holding one of
  every kind of control, each named the way a real application names it. One of
  the specs is about what a role must *not* match, and it asks the accessibility
  locator rather than the whole chain, measured, the pixel fallback answers a
  query for a button with the words painted on a checkbox, because OCR cannot
  see roles. That is the fallback behaving as documented, and the spec says so.

## 0.6.0 - 2026-07-27

`app.tab("Database").click()`. A notebook shows one page and unmaps the rest,
so a suite that could not change tabs could only ever assert on whichever page
the application opened with, however well every widget on the other pages was
named.

- **`Role.TAB`, and `app.tab(name)` / `dialog.tab(name)` alongside it.** The
  first entry added to `_CONTROL_TYPE_FOR_ROLE` since 0.1.0, and worth being
  precise about, because that table not moving has been evidence for the
  project's central claim. This is not the locator being widened to accept a
  control type it used to reject, widening `Role.TEXT` to take a `PaneControl`
  would match every anonymous `ttk` widget in a window and is still refused. It
  is a new role naming the control type a tab genuinely has. What changed is
  the tree underneath: Tk painted its tab strip inside the notebook's own
  window and exposed no tabs at all, and `tk-uia` 0.4.0 gives each one a window
  handle. A role that had nothing to match now has something.

- **Both halves are needed and neither shows up in a test.** `tk-uia` puts the
  tab in the tree; this plugin asks for the right control type. `app.tab(...)`
  reads like every other line, which is the point. Against WinForms, WPF and
  anything else that already exposed its tabs, this works with no `tk-uia` at
  all.

- **The dump offers a tab query for every tab it sees.** Derived from the same
  table as the search, so what a dump promises and what a locator can find stay
  one edit. A tab listed with no query beside it was the reader being shown a
  wall they could not pass.

- **Five end-to-end specs against a real Tk notebook**, including the two that
  say what a notebook actually does: clicking a tab brings its page into the
  tree, and the page left behind stops answering. A suite that asserted on two
  pages at once would be asserting on a window that never existed.

## 0.5.0 - 2026-07-26

The accessibility tree dump. A newcomer's first real question is *what is my
control called?*, and until now this project's answer was "go and install
Accessibility Insights", or a four-line `uiautomation` walk the README taught
them to write by hand. It is now one call, and the answer arrives in the tool
they already have.

- **`app.dump()`, `dialog.dump()`, and `python -m pytest_uia --title "..."`.**
  Each line names the control type, the accessible name, the AutomationId
  where there is one, and (the point of the whole feature) **the query that
  would find it**: `app.button("New Task")`, ready to paste. That is the
  difference between a picture of a tree and an answer. The command line
  exists because the person this is for has an application on screen and no
  test yet, so an answer beginning "first write a test" is the wall the
  feature was built to remove; it is a thin shell over the same `attach` and
  `dump` a test makes, and a session that did not start a process never ends
  one. A `Dump` is a value object: `str()` for the tree, `.queries` for the
  same list as data so a spec need not parse layout, `.with_window_chrome()`
  for the rendering that folds nothing. It does **not** print by itself,
  printing from a library call is a side effect a diagnostic should not have,
  and under pytest it would vanish into captured output; `print(app.dump())`
  with `-s`, or put it in the failure message, or use the command line.

- **The rule the whole design answers to: it must not quietly omit what it
  cannot see.** A control no query can reach is printed with the reason
  instead, `no query: PaneControl is not a role this plugin asks for`, or for
  a canvas window's empty pane, `no query: nothing inside it, so what it shows
  is paint`. A tidy tree that disagrees with the window on screen would be
  worse than no tree at all: the reader would conclude their button was
  somewhere in it. The same rule is why the folded window chrome is counted,
  named and reversible rather than dropped, why the header's four categories
  plus the window itself must sum to the total (a spec asserts the
  arithmetic), and why a control whose provider dies mid-walk is kept and
  marked `<unreadable>` rather than either dropped or allowed to abandon the
  four hundred controls that did answer.

- **No depth limit, refused rather than deferred.** `uiautomation`'s own
  `maxDepth` cannot report that it pruned anything. Measured: a browser window
  cut at depth 8 yields 1486 of its 5437 controls and says nothing whatsoever
  about the other 3951. That is exactly the silent omission above, so a node
  cap and a wall-clock budget do the bounding instead, and both know when
  they bit, and both name the call that lifts them.

- **Both limits are needed, and one window proved it.** The desktop's
  `Program Manager` has **five controls and takes 4.1 seconds**, all of it
  inside a single `GetFirstChildControl`. A node cap bounds how much there is
  to read and bounds the time not at all. The budget is checked between
  controls and cannot interrupt a provider that has stopped answering; that is
  documented rather than fixed, because fixing it means a worker thread and
  `uiautomation` is explicitly single-threaded-apartment-bound in this
  codebase. Against that, the three fixture windows dump in 15–44 ms.

- **Ambiguity is counted over what a query actually reaches, not over
  matching names.** The Tk fixture has a `Confirm` in its Settings dialog and
  another on the window underneath, and the dump reports
  `ambiguous: 2 controls answer app.button("Confirm")` on the outer one while
  offering `app.dialog("Settings").button("Confirm")` plainly on the inner,
  because an unscoped search runs over the main window's whole subtree,
  dialogs included, and a scoped one does not. Marking both would have been
  the dump contradicting the very API it documents, and sending readers back
  to coordinates over a call that works. `dialog.dump()` answers in that
  dialog's own calls for the same reason.

- **`[mouse]` states what pytest-uia will do, never what a control supports.**
  Measured: every title-bar button answers to the untrusted-provider rule
  (`FrameworkId` is empty, so the generic MSAA proxy speaks for it) and its
  `Invoke` works perfectly. A dump that told users their application was
  broken would be worse than no dump, so the marker and its legend are worded
  as this plugin's own rule and the legend appears only where the marker does
 , a distinction the end-to-end run caught, since folding the chrome away had
  been leaving four lines of explanation under a WinForms tree with no
  `[mouse]` anywhere in it. `[offscreen]` marks a control that is in the tree
  with no pixels, which is what `wait_visible()` exists for.

- **The AutomationId is shown and captioned as unqueryable.** v1 searches by
  name and role only, and measured, WinForms derives the id from the window
  handle: the same three controls of the same app came back as
  `198966 / 723224 / 919832` across three launches. Showing it is useful,
  Accessibility Insights shows it, and WPF and `tk_uia.set_automation_id` set
  it deliberately, but a reader must not pin a test to one, so the README
  says so and the dump never offers it as a query.

- **The dump takes no input and steals no foreground.** It reads properties;
  it never clicks, types, brings a window forward or photographs the screen.
  So it keeps working while Windows is refusing this process's synthetic input
 , which is exactly the situation in which somebody most needs to know what
  their controls are called. Its own gui specs are immune to the skip the rest
  of the gui suite needs.

- **Left out on purpose.** The cross-repo diff against `tk-uia`'s in-process
  annotation ledger, which spans two repositories and is therefore a `probes/`
  recipe rather than a feature of either package. Dump-on-failure, which wants
  the same plumbing as the deferred screenshot-on-failure and should be built
  with it. Querying by AutomationId, JSON output, and `element.dump()`, all
  on the roadmap, none needed yet.

## 0.4.1 - 2026-07-26

Bug fixes and documentation, all of them from an external review. The theme is
the one this project already claimed: a failure has to name what actually
happened. Five places were not keeping that promise, and the worst of them was
the scenario the design is proudest of handling.

- **An application that dies mid-test no longer answers in raw HRESULTs.** The
  whole driver (proxy elements, re-resolved on every interaction, an implicit
  wait that retries a miss) exists to absorb a window that is not what it was
  a moment ago. Its extreme is a window that is not there at all: a crash, or
  the test's own click landing on Quit. Reproduced by launching the WinForms
  fixture, killing it, and asking the two simplest questions in the API:
  `exists()` and `App.title` both raised `_ctypes.COMError: (-2147220991, 'An
  event was unable to invoke any of the subscribers', ...)`, from the call
  documented as answering True or False *for both directions of assertion*, and
  from a package whose errors module opens by promising that a test never has
  to read a comtypes HRESULT. Neither was a near miss: the adapter never
  translated `COMError` into anything the retry loop recognised, so nothing
  retried and nothing explained. Every boundary now translates, the
  accessibility-tree search, the pixel search behind it, the child-window
  search, the window's own `title`, `pid` and `close`, and every property an
  element reads, into the domain error that fits, carrying "the window is
  gone: the application behind it has exited". `exists()` answers `False`,
  `has_dialog` answers `False`, and `App.title` raises `WindowNotFound` naming
  the window where it can. Specified twice over: with doubles for the parts
  that take a control (`tests/test_uia_dead_window.py`), and end to end against
  a real fixture app that has been shut down for the three searches that build
  their own `uiautomation` objects and cannot be handed a misbehaving one
  (`tests/test_dead_app_end_to_end.py`).

- **A launch whose command is already over fails at once, with the exit code.**
  `gui.launch([sys.executable, "-c", "import sys; sys.exit(3)"])` used to wait
  out the entire `ready_timeout` (measured at 6.42 s against an overridden
  6.2 s, and thirty seconds by default) and then raise `WindowNotFound: no
  visible top-level window for pid 19940`, about a process that had been dead
  almost immediately, mentioning neither the exit nor its code. That is the
  first wall every newcomer with a typo in a command path walks into, and the
  answer it gave sent them looking at the window instead of at the command. The
  poll now questions the process when it finds no window, and the new
  **`LaunchFailed`** says `the launched command exited with code 3 before it
  owned a window`. Same command, 0.34 s. Deliberately in that order (window
  first, process only if there is none) because `cmd /c`, a console-script
  shim and a `.bat` all exit the moment the real application is up, so an exit
  is evidence of nothing while there is a window on screen. A spec pins that
  ordering, since the obvious implementation gets it backwards and breaks every
  launcher the 0.1.0 process-family work existed to support.

- **`SetActive`'s answer stops being thrown away, so misdirected input is
  detectable.** The marquee feature of 0.1.0 is refusing to let a dropped click
  impersonate a delivered one, and four call sites brought the window under
  test to the front and discarded the bool that says whether it worked.
  `SetForegroundWindow` fails for entirely ordinary reasons with no UIPI
  anywhere near it: another application called `LockSetForegroundWindow`, or
  simply got there first. Carrying on regardless produces exactly the two
  failures this project exists to refuse, the mouse presses coordinates
  another application now owns, and the screen grab photographs whatever is
  covering the window, after which OCR reports "phrase not visible" about a
  phrase that is plainly there. It now raises `InputRefused`, which the driver
  already retries inside the implicit wait and reports against the deadline, so
  a foreground race costs a retry and a stolen foreground costs an honest
  failure naming the window. The fixture apps dodge all of this with
  `-topmost`; a user's application does not, which is why no spec was failing.
  One measured subtlety pins the design: a window whose application has
  **exited** answers `SetActive` with False too, because its native handle has
  become 0, so the refusal reads the window's caption, which a live window
  answers and a dead one raises on, and the two get opposite reports.

- **`OcrElement.type_text` refuses instead of half-working, and that is a
  deliberate behaviour change in a patch release.** `ROADMAP.md` lists
  OCR-targeted `type_text` among the things refused outright ("typing into
  something it located is a coin-flip dressed up as an API") and the code
  implemented that coin-flip: click the recognised phrase, then `SendKeys`. The
  README then documented the misfire, keystrokes landing "wherever clicking
  that label put the caret", as a limitation of a feature the roadmap says does
  not exist. It now raises `OcrTypingRefused`, naming the two things that do
  work: annotate the box so UIA can see it, or type through a UIA-located
  element. This is the same judgement the adapter already makes about an
  `Invoke` the generic MSAA proxy only advertises (decline a call that returns
  cleanly having reached nothing anybody chose) turned on this package's own
  API. It is normally minor-bump material and it is in a patch anyway, on three
  grounds stated plainly: the current behaviour is a documented non-goal that
  silently misfires, nothing is published on PyPI so no installed version can
  regress, and no spec depended on it succeeding, there was no spec for it at
  all, which is its own comment on the feature.

- **`AppProcess.terminate` no longer returns quietly with the process alive.**
  It escalates through `terminate`, `kill` and `taskkill /t /f`, and if every
  rung failed the loop simply ended and the method returned as though it had
  worked. A wedged app then sat on the next test's screen with nothing anywhere
  saying which run left it there. It raises **`ProcessStillRunning`** naming the
  pid. The session's teardown, which is blind by design so that one unkillable
  app strands none of the others, now warns rather than swallowing it in
  silence, blind is not the same as silent, and the run that caused the leak
  is the only one that knows about it.

- **Every failure raised against a deadline now names it.** `DialogNotFound`
  and `InputRefused` carried theirs and `ElementNotFound` did not, so a control
  that was never going to appear read exactly like one that had been given a
  tenth of a second to; it now leads with `not on screen after 5.0s;` before
  the chain's own account of where each link looked. Fixing only that would
  have left `TextNeverSettled` as the last one without a deadline, immediately
  after the reason for adding them had been argued, so it carries one too,
  `still not reading it after 5.0s;` in front of the two readings it already
  reported.

- **OCR recognition moved off `asyncio.run`, which was a crash waiting for the
  first async test.** `asyncio.run` refuses to start a second event loop on a
  thread that already has one, so any `pytest-asyncio` suite whose async test
  reached OCR got a bare `RuntimeError` about event loops, from a call with no
  visible connection to asyncio, and from outside the domain's error contract
  entirely. The obvious fix, the WinRT operation's own blocking `get()`, does
  not work either: it refuses to be called from the single-threaded apartment
  that importing `uiautomation` has already put the caller in, which is why
  this needed measuring rather than reasoning about. The recognise is waited
  for on a fresh joined thread instead, which has neither problem, no loop,
  and no apartment until something asks for one. That is the contingency this
  module's first version wrote down and did not need yet. It is also faster:
  1.34 ms a recognition against 1.96 ms on a 460×280 image over twenty rounds,
  because the event loop it no longer builds and tears down cost more than the
  thread does. Warm recognition against the canvas fixture measured 4.5–6.4 ms,
  median 5.1.

- **Two new exported failures**, `LaunchFailed` and `ProcessStillRunning`, both
  on the same reasoning as every failure before them: a suite can only decide
  what a condition means if it can catch it by name. `OcrTypingRefused` is
  deliberately *not* exported, exactly as `OcrUnavailable` is not, both belong
  to the optional pixel path, and neither is something a suite should be
  catching rather than fixing.

- **Documentation, from the same review.** A CI badge, for a workflow that has
  been real and green all along. A **"finding your control's name"** section,
  the actual first question a newcomer has, previously answered nowhere: a
  four-line `uiautomation` tree walk with its verified output against the
  WinForms fixture, plus Accessibility Insights and `inspect.exe`. A runnable
  Quickstart, since `todo_app.py` never existed and the fixture apps' launch
  incantations lived only in `tests/conftest.py`. A table of every failure and
  what it blames, and an explicit note on the two things `exists()` still
  raises rather than absorbing, `OcrUnavailable` and now `InputRefused`, both
  meaning *this machine could not answer* rather than *the control is absent*.
  And the foreground cost of asserting absence with `[ocr]` installed, which
  was disclosed as a latency number and is really a behaviour: measured at 7
  grabs in 5.25 s at the default implicit wait, each one yanking the window
  under test in front of whatever else is on screen.

- **Deferred, with reasons.** Pinning a `Dialog` to the window it opened as,
  rather than re-finding it by caption, is on [ROADMAP.md](ROADMAP.md) against
  the nested-dialogs item: for one dialog over one main window the current
  behaviour is right, it is nesting that turns the caption collision into the
  ordinary case, and doing them together grows the `Window` port once instead
  of twice. A tree dump built into `App` is a 0.5.0 feature rather than a patch,
  which is why the README teaches the manual walk in the meantime.

## 0.4.0 - 2026-07-26

A test can now say which window it meant. Child modal dialogs are addressable by
the caption on their title bar, and every query answered through one stops at
that window's edge.

- **`app.dialog(title)`, and the claim it disproves.** The roadmap said a dialog
  that opened after launch was "invisible to the driver". That was never true,
  and measuring it was the first thing this release did: Tk owns a `Toplevel` at
  the Win32 level whether or not it is `transient`, UI Automation nests the
  window inside its owner's subtree, and `UiaLocator` searches the whole
  subtree, so `app.button("Only In Dialog")` found a dialog's button in v0.1,
  in both the `transient()` + `grab_set()` shape and the unowned one. The real
  gap was narrower and worse. The fixture app's dialog and its main window both
  carry a button named `Confirm`, and `app.button("Confirm")` resolves to one of
  them by an accident of z-order, measured with runtime ids, the dialog's while
  it is open and the main window's the instant it closes. A first-run wizard is
  a sequence of steps reusing `Next`, `Back` and `OK`, so a suite driving one
  could not express "the OK **in this dialog**" at all. `settings =
  app.dialog("Settings")` waits for the window, and `settings.button("Confirm")`
  is unambiguously the dialog's.

- **The scoping is a genuine narrowing, and that is the whole feature.** The
  temptation is to hand the dialog the search the app already has, which reads
  right and is wrong: the main window's subtree *contains* the dialog, so such a
  "scope" excludes nothing whatsoever. Instead the adapter resolves the child
  window (`UiaWindow.dialog_titled`, constrained to a `WindowControl` so a
  label carrying the same words cannot answer) and the `Dialog` searches from
  *that* control. The proof is `tests/test_dialog_end_to_end.py`: with the
  scoping backed out to the naive version, the spec that asks the dialog for a
  button only the main window has fails with `assert True is False`, while the
  spec that drives the shared `Confirm` goes on passing, because the tree
  happened to offer the dialog's copy first. That accident is exactly why the
  narrowing spec exists, and why passing was never evidence on its own.

- **A `Dialog` is not an `App`, deliberately.** Reusing `App` would have been
  one line and would have dragged `close()` and `pid` onto an object that owns
  no process and whose window a test has no business ending, borrowed
  semantics that fit the window underneath and not this one. What the two do
  share is the way in, so `button`, `textbox` and `text` come from one place
  (`ElementSource`) and behave identically in both, per-call `timeout=`
  included.

- **Two new failures, each naming a different suspect.** `DialogNotFound` is
  raised when a dialog never opens, rather than `WindowNotFound`, because the
  two send a reader to opposite ends of the problem: `WindowNotFound` means the
  application has nothing on screen and is what a launch waits through, while
  this one is raised by an app whose main window is right there, so the first
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
  destroyed, "it raised" is not the same answer as "it is gone".

- **The Tk fixture app grew the wizard shape.** It now opens a modal `Toplevel`
  with `transient()` + `grab_set()`, carrying a `Folder` entry and a `Confirm`
  whose name is deliberately shared with a new `Confirm` on the main window; the
  dialog's saves to the status line and dismisses itself, so a spec can prove
  which of the two ran by what outlives the window. The WinForms fixture is
  untouched: one collision proves the point, and the Tk case is the one the
  sibling `tk-uia` had to be checked against. It needed no changes, its `<Map>`
  binding sits on the `all` bindtag, so a `Toplevel` built long after
  `enable()` is annotated exactly like the widgets that were there first.

## 0.3.0 - 2026-07-26

Waiting for an element's text to become what a test expects stops being every
suite's own hand-rolled poll and becomes one call on the driver.

- **`element.wait_until_text_is(expected, timeout=None)`.** A GUI is
  asynchronous: the application reacts on its own message pump, so the repaint
  lands after the call that caused it has already returned. The consequence is
  the most ordinary race in desktop testing, type into a box, assert on it in
  the next line, and read the value the box held before the keys arrived. v0.2
  gave a test `read_text()` and no way to wait on it, so the only way through
  was to build the affordance yourself, and **this repo's own specs were the
  evidence**: `tests/test_uia_tk_end_to_end.py` carried a `StillCatchingUp`
  exception, a `_once_the_tree_has_caught_up` helper and a hand-built
  `RetryPolicy` fed to `poll`, twelve lines of scaffolding to express one
  sentence. That sentence is now `app.textbox("Title").wait_until_text_is("Buy
  milk")`. It re-resolves the element on every look, exactly as `click` and
  `type_text` do, an element cached across the polls would go on reading the
  value the application has already replaced, which is the precise failure the
  method exists to absorb, and it returns the element itself, so a call can
  follow it the way one follows `wait_visible`.

- **A missing element is a miss; missing *text* is `TextNeverSettled`.** The
  timeout raises a new domain error rather than `ElementNotFound`, because the
  element *was* found, on every single look, what never happened is its text
  settling, and reporting that as a missing control sends whoever reads the
  failure hunting for something that is right there. Same distinction, and the
  same reasoning, as `InputRefused` in 0.1.0. The message carries both readings
  (`Textbox 'Title' -- reads '', not 'Buy milk'`), because a gui failure usually
  leaves nothing behind but that string and "the text is wrong" is not something
  anybody can act on. A control that is *not* on screen yet stays an ordinary
  miss and keeps the wait going (the click that sets a label's text is usually
  the click that creates it, so both kinds of lateness share one deadline) and
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
  fails `TextNeverSettled: Textbox 'Title' -- reads '', not 'Write the report'`.
  Note this raises the floor on the sibling: the Tk specs now need **tk-uia
  ≥ 0.2.0**, and without it installed they skip rather than fail.

## 0.2.0 - 2026-07-26

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
  back out through a proxy that outranks the plain one, so an application can
  say who its widgets are. That work is its own project,
  [`tk-uia`](https://github.com/HuzPro/tk-uia) (MIT, zero runtime dependencies), because
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
  in-process only (reaching across silently does nothing and can corrupt an
  annotation the other process made properly) so that case is exactly what the
  pixel fallback is still here for.

- **`_CONTROL_TYPE_FOR_ROLE` is byte for byte what it was.** The table mapping
  `button → ButtonControl`, `text → TextControl` and `textbox → EditControl` did
  not move a character to make Tk work, and that is the point rather than a
  detail: Tk became drivable by fixing the *application*, not by loosening the
  *locator*. The alternative was not merely worse, it does not work, widening
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
  **A Tk test could pass having pressed nothing at all**: the exact failure this
  project exists to refuse. Action patterns are now taken only from a provider
  that will honour them, and where the generic proxy is doing the talking the
  mouse and the keyboard do the work instead; typing there clicks first and then
  sends keys, because Tk owns focus through its own model and Win32 focus on a
  child window is not focus. `ValuePattern.SetValue` is gated identically,
  `put_accValue` into the same void, while *reads* are deliberately left
  ungated, since a property served out of an annotation store is the
  application's own word about itself and only acting through a proxy is a
  guess. The discriminator was measured twice before it was written: both
  WinForms and Tk are served by that same generic proxy, so its marker alone
  separates nothing, and their buttons are both `BS_OWNERDRAW`, so the window
  style separates nothing either. `FrameworkId` does, `'WinForm'` against Tk's
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
  `tests/fixture_apps/tk_canvas_app.py` is new, one `tk.Canvas`, everything
  drawn with `create_text`, measured to expose zero UIA children. The OCR specs
  moved onto it. They were reading a window that had become accessible
  underneath them, which is a bad place for the specs that exist to prove the
  pixel path still works, and a new guard,
  `test_the_canvas_window_exposes_nothing_a_name_based_query_could_reach`,
  asserts the tree has nothing to answer with, without it, a well-meaning edit
  that made this fixture accessible would leave the OCR specs passing against a
  chain that never reaches OCR.

- **The hybrid spec was vacuous, and is now two specs that count.** It claimed to
  prove that the same journey runs against a window with an accessibility tree
  and one without. The moment Tk gained one, the chain's first link answered for
  both, OCR was never consulted, and the spec went on passing under a parameter
  id reading `tkinter-through-ocr` that had become a lie, passing while proving
  strictly less than it said. Passing is no longer the evidence; **which link
  answered is**. `tests/test_uia_hybrid_end_to_end.py` wraps the pixel locator in
  a counting decorator over the real one, and asserts `pixels.asked == 0` for
  both windows with a tree and `pixels.asked > 0` for the canvas.

- **The honest cost of the Tk support.** A Tk control is found through the tree
  but *driven* by synthesised input, because its `Invoke` is pretence, so a Tk
  suite is exposed to the User Interface Privilege Isolation refusal documented
  in 0.1.0 where a WinForms suite, going through real patterns, is not. Tk gains
  UIA's precision (roles, empty text boxes, independence from fonts and themes
  and DPI) and not UIA's immunity to a higher-integrity window holding the
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

## 0.1.0 - 2026-07-26

First release. A pytest plugin that locates Windows GUI elements through the UI
Automation accessibility tree, with Windows' own OCR engine as a last resort for
surfaces whose controls expose nothing a name-based query can reach.

- **Locator chain: the accessibility tree first, pixels only if it had nothing to
  say.** `UiaLocator` searches under the window for a control of the right control
  type carrying that exact accessible name; `OcrLocator` brings the window to the
  front, grabs its rectangle with `mss` and hands the bytes to
  `Windows.Media.Ocr`, no Tesseract, no install, no model download. The chain
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
  access fails. The fixture shuts down everything a test launched (close, then
  terminate, then `taskkill /t /f`) whatever the test did or failed to do.
  Attached apps are never killed; they may belong to the developer.

- **Synthetic mouse input that admits when Windows refused it.** Two gui specs
  were intermittently failing with "phrase not visible" about a phrase that was
  plainly on screen. The cause was not OCR: while a window owned by a
  higher-integrity process holds the foreground, User Interface Privilege
  Isolation drops every event a medium-integrity process injects (`SetCursorPos`
  returns 0 and the cursor does not move) and `uiautomation.Click` throws that
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

- **The Tkinter claim, corrected.** Tk does not "expose no accessibility tree",
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
  cleanly on a machine that cannot use them. The gui suite is local-only in v1,
  it needs an interactive desktop it owns.

- **Cut from this release:** screenshot-on-failure, which was designed and
  budgeted for v1 and lost its slot to the click-resilience work above. The
  capture adapter it needs already ships. See [ROADMAP.md](ROADMAP.md).
