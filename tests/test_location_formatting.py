import sys
import types

import pytest

if "robocorp" not in sys.modules:
    robocorp_stub = types.ModuleType("robocorp")
    browser_stub = types.ModuleType("browser")
    browser_stub.configure = lambda *args, **kwargs: None  # type: ignore
    robocorp_stub.browser = browser_stub  # type: ignore[attr-defined]
    sys.modules["robocorp"] = robocorp_stub
    sys.modules["robocorp.browser"] = browser_stub

from linkedin.utils.apply_tools import (
    _desired_location_strings,
    _location_value_matches,
    _prepare_location_context,
)


def _make_profile() -> dict:
    return {
        "location": "Worcester, MA",
        "address_city": "Worcester",
        "address_state": "MA",
        "address_country": "US",
    }


def test_prepare_location_context_normalizes_country_and_state():
    profile = _make_profile()
    context = _prepare_location_context(profile["location"], profile)

    assert context["state_abbrev"] == "MA"
    assert context["state_full"] == "Massachusetts"
    assert context["country"] == "United States"


def test_desired_location_strings_prioritizes_full_state_first():
    profile = _make_profile()
    context = _prepare_location_context("", profile)
    strings = _desired_location_strings(context)

    assert strings[0] == "Worcester, Massachusetts, United States"
    assert "Worcester, MA" in strings
    assert strings.index("Worcester, Massachusetts, United States") < strings.index("Worcester, MA")


def test_location_value_matches_accepts_county_result():
    profile = _make_profile()
    context = _prepare_location_context("", profile)

    assert _location_value_matches(context, "Worcester County, Massachusetts, United States")
