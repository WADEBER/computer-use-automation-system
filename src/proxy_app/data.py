"""Deterministic in-memory seed data for the proxy target app.

The seed is rebuilt on every import/restart: same member IDs, names and
balances each time. No database, no files -- Phase 2 spec decision.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    account_id: str
    type: str
    balance: float


@dataclass(frozen=True)
class Member:
    member_id: str
    full_name: str
    accounts: tuple[Account, ...]
    credit_limit: float


def build_seed() -> list[Member]:
    return [
        Member(
            member_id="M-1001",
            full_name="Alice Hartwell",
            accounts=(
                Account(account_id="CHK-2201", type="checking", balance=4250.75),
                Account(account_id="SAV-5101", type="savings", balance=15200.00),
            ),
            credit_limit=10000.00,
        ),
        Member(
            member_id="M-1002",
            full_name="Brian Okafor",
            accounts=(Account(account_id="CHK-2202", type="checking", balance=980.40),),
            credit_limit=2500.00,
        ),
        Member(
            member_id="M-1003",
            full_name="Carla Mendes",
            accounts=(
                Account(account_id="CHK-2203", type="checking", balance=312.00),
                Account(account_id="SAV-5103", type="savings", balance=8700.50),
            ),
            credit_limit=500.00,
        ),
    ]


MEMBERS: list[Member] = build_seed()

MEMBERS_BY_ID: dict[str, Member] = {m.member_id: m for m in MEMBERS}


def get_member(member_id: str) -> Member | None:
    return MEMBERS_BY_ID.get(member_id)


def search_members(query: str) -> list[Member]:
    normalized = query.strip().lower()
    if not normalized:
        return []
    return [
        m for m in MEMBERS if normalized in m.member_id.lower() or normalized in m.full_name.lower()
    ]
