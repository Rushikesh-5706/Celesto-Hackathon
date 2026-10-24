import importlib
import pytest

def test_debug_setting_parsed_as_boolean():
    # Import the configuration module where defaults are defined
    config = importlib.import_module('conf.app')
    # Simulate a configuration where the debug flag is set as a string "true"
    config.DEFAULTS['debug'] = "true"
    # The expected behavior is that get_setting returns a boolean True,
    # but the current implementation returns the raw string value.
    assert config.get_setting('debug') is True, "debug flag should be parsed as True"
