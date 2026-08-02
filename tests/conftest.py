"""Test environment setup.

main.py and geocoder.py read configuration from the environment at import
time (SERVICE_SECRET / ENVIRONMENT in main.py, CITY_REPOSITORY_SOURCE in
city_repository.py). We pin a known baseline here, before `main` is ever
imported by any test module, regardless of whatever the runner's shell
happens to export.

IMPORTANT: these are set to "" rather than popped. geocoder.py calls its own
load_dotenv(), which by default only fills in keys that are *absent* from
os.environ — a popped key would get silently repopulated from a real local
.env file (e.g. a developer's actual SERVICE_SECRET or a real
CITY_REPOSITORY_DSN pointing at a live database), which would both break
test isolation and risk this suite hitting a real external database. Setting
to "" makes the key present-but-empty, which load_dotenv() will not touch.
"""
import os

os.environ["ENVIRONMENT"] = "development"
os.environ["SERVICE_SECRET"] = ""
os.environ["CITY_REPOSITORY_SOURCE"] = ""
os.environ["CITY_REPOSITORY_DSN"] = ""

import pytest
from fastapi.testclient import TestClient

import main as app_module


@pytest.fixture
def client():
    # raise_server_exceptions=False so unhandled exceptions in the app
    # surface as the actual HTTP response (e.g. 500) a real client would
    # see, instead of propagating into the test process.
    return TestClient(app_module.app, raise_server_exceptions=False)
