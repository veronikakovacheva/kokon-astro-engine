"""Test environment setup.

main.py and geocoder.py read configuration from the environment at import
time (SERVICE_SECRET / ENVIRONMENT in main.py, CITY_REPOSITORY_SOURCE in
city_repository.py). We pin a known baseline here, before `main` is ever
imported by any test module, regardless of whatever the runner's shell
happens to export.
"""
import os

os.environ["ENVIRONMENT"] = "development"
os.environ.pop("SERVICE_SECRET", None)
os.environ.pop("CITY_REPOSITORY_SOURCE", None)
os.environ.pop("CITY_REPOSITORY_DSN", None)

import pytest
from fastapi.testclient import TestClient

import main as app_module


@pytest.fixture
def client():
    # raise_server_exceptions=False so unhandled exceptions in the app
    # surface as the actual HTTP response (e.g. 500) a real client would
    # see, instead of propagating into the test process.
    return TestClient(app_module.app, raise_server_exceptions=False)
