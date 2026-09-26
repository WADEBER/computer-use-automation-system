import pytest
from flask.testing import FlaskClient


def _post_disburse(client: FlaskClient, member_id: str, data: dict) -> tuple[int, str]:
    response = client.post(f"/members/{member_id}/loans/disburse", data=data)
    return response.status_code, response.get_data(as_text=True)


def test_disburse_empty_amount_shows_errors(client: FlaskClient) -> None:
    status, html = _post_disburse(client, "M-1001", {"account_id": "CHK-2201", "amount": ""})
    assert status == 200
    assert "error" in html.lower()
    assert "DISB-" not in html


def test_disburse_non_numeric_amount_shows_errors(client: FlaskClient) -> None:
    status, html = _post_disburse(client, "M-1001", {"account_id": "CHK-2201", "amount": "abc"})
    assert status == 200
    assert "error" in html.lower()
    assert "DISB-" not in html


@pytest.mark.parametrize("amount", ["0", "-5"])
def test_disburse_non_positive_amount_shows_errors(client: FlaskClient, amount: str) -> None:
    status, html = _post_disburse(client, "M-1001", {"account_id": "CHK-2201", "amount": amount})
    assert status == 200
    assert "error" in html.lower()
    assert "DISB-" not in html


def test_disburse_over_credit_limit_shows_errors(client: FlaskClient) -> None:
    status, html = _post_disburse(client, "M-1001", {"account_id": "CHK-2201", "amount": "99999"})
    assert status == 200
    assert "error" in html.lower()
    assert "DISB-" not in html


def test_disburse_valid_renders_confirmation_without_executing(client: FlaskClient) -> None:
    status, html = _post_disburse(client, "M-1001", {"account_id": "CHK-2201", "amount": "250"})
    assert status == 200
    assert "confirm" in html.lower()
    assert "Alice Hartwell" in html
    assert "250" in html
    assert "DISB-" not in html
    assert "receipt" not in html.lower()


def test_execute_receipt_fields(client: FlaskClient) -> None:
    response = client.post(
        "/members/M-1001/loans/disburse/execute",
        data={"account_id": "CHK-2201", "amount": "250"},
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DISB-0001" in html
    assert "Alice Hartwell" in html
    assert "M-1001" in html
    assert "CHK-2201" in html
    assert "250.00" in html
    assert "4500.75" in html  # 4250.75 + 250


def test_execute_invalid_summary_no_500(client: FlaskClient) -> None:
    response = client.post(
        "/members/M-1001/loans/disburse/execute",
        data={"account_id": "CHK-2201", "amount": "not-a-number"},
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "error" in html.lower()
    assert "DISB-" not in html


def test_execute_missing_fields_no_500(client: FlaskClient) -> None:
    response = client.post("/members/M-1001/loans/disburse/execute", data={})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "error" in html.lower()
    assert "DISB-" not in html
