from proxy_app.data import MEMBERS, get_member


def test_seed_has_members() -> None:
    assert len(MEMBERS) >= 3


def test_member_ids_format_and_unique() -> None:
    ids = [m.member_id for m in MEMBERS]
    assert len(ids) == len(set(ids))
    for member_id in ids:
        assert member_id.startswith("M-")


def test_members_have_accounts_and_balances() -> None:
    for member in MEMBERS:
        assert member.accounts, f"{member.member_id} has no accounts"
        for account in member.accounts:
            assert account.balance >= 0
            assert account.account_id
        assert member.credit_limit > 0


def test_get_member_returns_match() -> None:
    first = MEMBERS[0]
    assert get_member(first.member_id) is first


def test_get_member_unknown_returns_none() -> None:
    assert get_member("M-9999") is None


def test_seed_is_deterministic() -> None:
    from proxy_app.data import build_seed

    seed_a = build_seed()
    seed_b = build_seed()
    assert [m.member_id for m in seed_a] == [m.member_id for m in seed_b]
    assert [m.full_name for m in seed_a] == [m.full_name for m in seed_b]
    for a, b in zip(seed_a, seed_b, strict=True):
        for acc_a, acc_b in zip(a.accounts, b.accounts, strict=True):
            assert acc_a.balance == acc_b.balance
