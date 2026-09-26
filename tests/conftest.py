import pytest
from flask import Flask
from flask.testing import FlaskClient

from proxy_app.app import create_app


@pytest.fixture()
def client() -> FlaskClient:
    app: Flask = create_app()
    app.config["TESTING"] = True
    return app.test_client()
