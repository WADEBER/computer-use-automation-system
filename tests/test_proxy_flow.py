from flask.testing import FlaskClient


def test_landing_has_search_form(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'action="/members/search"' in html
    assert 'name="q"' in html


def test_search_found_returns_results(client: FlaskClient) -> None:
    response = client.get("/members/search", query_string={"q": "Alice"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Alice Hartwell" in html
    assert "M-1001" in html
    assert "/members/M-1001" in html


def test_search_not_found_returns_200_with_message(client: FlaskClient) -> None:
    response = client.get("/members/search", query_string={"q": "zzz-no-such-member"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "member not found" in html.lower()


def test_member_detail(client: FlaskClient) -> None:
    response = client.get("/members/M-1001")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Alice Hartwell" in html
    assert "CHK-2201" in html
    assert "4250.75" in html
    assert "/loans/disburse" in html


def test_member_detail_unknown_id_404(client: FlaskClient) -> None:
    response = client.get("/members/M-9999")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "MemberServ" in html
    assert "not found" in html.lower()
    assert "M-9999" in html


def test_core_flow_smoke(client: FlaskClient) -> None:
    landing = client.get("/")
    assert landing.status_code == 200

    search = client.get("/members/search", query_string={"q": "M-1001"})
    assert search.status_code == 200
    assert "Alice Hartwell" in search.get_data(as_text=True)

    detail = client.get("/members/M-1001")
    assert detail.status_code == 200

    confirm = client.post(
        "/members/M-1001/loans/disburse",
        data={"account_id": "CHK-2201", "amount": "100"},
    )
    assert confirm.status_code == 200
    confirm_html = confirm.get_data(as_text=True)
    assert "confirm" in confirm_html.lower()
    assert "DISB-" not in confirm_html

    receipt = client.post(
        "/members/M-1001/loans/disburse/execute",
        data={"account_id": "CHK-2201", "amount": "100"},
    )
    assert receipt.status_code == 200
    receipt_html = receipt.get_data(as_text=True)
    assert "DISB-0001" in receipt_html
    assert "100.00" in receipt_html
    assert "4350.75" in receipt_html


def test_no_data_testid_in_rendered_pages(client: FlaskClient) -> None:
    pages: list[tuple[str, dict]] = [
        ("GET", {"path": "/"}),
        ("GET", {"path": "/members/search", "query_string": {"q": "Alice"}}),
        ("GET", {"path": "/members/search", "query_string": {"q": "zzz-none"}}),
        ("GET", {"path": "/members/M-1001"}),
        ("GET", {"path": "/members/M-9999"}),
        ("GET", {"path": "/members/M-1001/loans/disburse"}),
        (
            "POST",
            {
                "path": "/members/M-1001/loans/disburse",
                "data": {"account_id": "CHK-2201", "amount": "50"},
            },
        ),
        (
            "POST",
            {
                "path": "/members/M-1001/loans/disburse/execute",
                "data": {"account_id": "CHK-2201", "amount": "50"},
            },
        ),
    ]
    for method, kwargs in pages:
        if method == "GET":
            response = client.get(kwargs.pop("path"), **kwargs)
        else:
            response = client.post(kwargs.pop("path"), **kwargs)
        html = response.get_data(as_text=True)
        assert "data-testid" not in html, f"data-testid leaked in {method} {kwargs}"
        assert 'lang="en"' in html
