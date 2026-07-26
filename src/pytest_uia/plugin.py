"""``pytest11`` entry-point module.

Re-exports the hook callables and fixtures so pytest discovers them when the
package is installed. Vendored setups can import the same names from a
repo-root ``conftest.py`` instead of installing the package.
"""

from pytest_uia.hooks import gui, pytest_addoption, pytest_configure

__all__ = [
    "gui",
    "pytest_addoption",
    "pytest_configure",
]
