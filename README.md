# pytest-uia

**Windows GUI acceptance testing for pytest — through the accessibility tree, not pixels.**

`pytest-uia` lets you write desktop acceptance tests the way you'd describe them to a person:
"click the button named *New Task*, then the window should say *task created*." Elements are
located through the Windows **UI Automation** (UIA) accessibility tree — by accessible name,
role, and state — so tests survive theme changes, DPI scaling, resolution changes, and
multi-monitor layouts that break screenshot/OCR tools.

OCR exists in the design as a **deliberate last resort**, for surfaces that expose no
accessibility tree at all (canvas-drawn UI, Tkinter windows). The fallback is a locator
chain: UIA answers first; OCR is only consulted when the accessibility tree has nothing
to say.

## Why not SikuliX / Airtest / PyAutoGUI?

Those are image-and-OCR-first: they match pixels, so they are at their weakest exactly
where GUI tests need them most — empty input boxes, dark mode, font anti-aliasing, DPI
scaling. UIA hands you element names, roles, and states directly, which turns "find the
empty textbox labeled *Title*" from a computer-vision problem into a query.

## The ATDD angle

You control the app under test. Instead of adding *visible* text to make UI locatable,
add **accessible names** — the same act that makes your app testable makes it work with
screen readers. Design for testability and accessibility become one habit.

## Status

Alpha, under active development. Current layer: the locator core (UIA adapter + fallback
chain). See [ROADMAP.md](ROADMAP.md).

## Requirements

- Windows 10/11
- Python 3.10+

## License

MIT
