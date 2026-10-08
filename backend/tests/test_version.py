from fastapi.testclient import TestClient

from app import main


def test_a_checkout_reports_itself_as_dev(temp_db):
    # The release workflow stamps the tag's version into the image (INSKECT_VERSION); anything
    # built or run from a checkout has none, and says so rather than an old release's number.
    client = TestClient(main.app)

    assert main.VERSION == "dev"
    assert client.get("/health").json()["version"] == "dev"
    assert client.get("/openapi.json").json()["info"]["version"] == "dev"
