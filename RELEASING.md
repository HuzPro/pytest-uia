# Releasing

A release is a tag push. `.github/workflows/publish.yml` builds the sdist and
wheel and uploads them to PyPI through
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): PyPI trusts
the workflow's identity directly, so no API token exists anywhere.

## Before you tag

1. Both suites green: `pytest -m "not gui" -q`, then `pytest -m gui -q` on a
   quiet desktop (foreground contention fails specs that are not wrong).
2. `ruff check src tests` and `ruff format --check src tests` clean.
3. `__version__` in `src/pytest_uia/__init__.py` is the version being shipped;
   the workflow refuses a tag that disagrees with it.
4. `CHANGELOG.md`'s top section is `## <version> - <date>` with today's date.

## Publish

Bump `__version__` and retitle the CHANGELOG's top section in the same commit,
then:

```powershell
git push origin main
git tag -a v0.7.1 -m "0.7.1"
git push origin v0.7.1
```

`gh run watch` shows the rest. Versions that reach PyPI are permanent;
re-uploading an existing one is refused.

## One-time setup, before the first tag ever pushed

On PyPI, under **Account settings > Publishing**, add a pending publisher:
project `pytest-uia`, publisher GitHub, owner `HuzPro`, repository
`pytest-uia`, workflow `publish.yml`, environment `pypi`. No token to create or
store. A pending publisher is not a reservation: the first successful upload is
what claims the name.

## After the first publish

Flip the README's install instructions from the clone to
`pip install pytest-uia[ocr]`, strike *PyPI publishing* from the ROADMAP's
not-yet list, cut a GitHub release from the CHANGELOG section, and verify with
a `pip install pytest-uia` in a virtual environment that has never seen this
repository.
