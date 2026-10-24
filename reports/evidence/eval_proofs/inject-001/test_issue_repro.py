import importlib
import pytest

def test_debug_setting_parsed_from_env(monkeypatch):
    """Bug: Boolean config flags from strings are not parsed correctly.
    The function should interpret the environment variable ``DEBUG`` set to
    a truthy string (e.g., "true") as ``True``.
    """
    # Set environment variable to a truthy string
    monkeypatch.setenv('DEBUG', 'true')
    # Reload the module to simulate reading env (if it were implemented)
    app = importlib.import_module('conf.app')
    importlib.reload(app)
    # Expect the setting to be True, but current implementation returns False
    assert app.get_setting('debug') is True
