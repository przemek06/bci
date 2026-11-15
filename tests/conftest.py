"""Shared pytest setup.

The headlight features are switched off in the shipped game (`settings.HEADLIGHTS_ENABLED = False`),
but their code and the tests that guard it are kept. So every test runs with the feature ON,
unless it asks for the shipped default by using the `headlights_default` fixture.
"""

import pytest

from nightdrive import settings as S


@pytest.fixture
def headlights_default():
    """Ask for the game's shipped setting (headlights off) instead of the test default (on)."""


@pytest.fixture(autouse=True)
def _headlights_enabled_for_tests(request, monkeypatch):
    if "headlights_default" not in request.fixturenames:
        monkeypatch.setattr(S, "HEADLIGHTS_ENABLED", True)
