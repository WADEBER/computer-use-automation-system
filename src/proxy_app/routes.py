"""Routes for the proxy target app (Phase 2 legacy banking UI)."""

from flask import Blueprint, current_app, render_template, request

from proxy_app.data import Member, get_member, search_members

web = Blueprint("web", __name__)


def validate_disbursement(
    member: Member, account_id: str, amount_raw: str
) -> tuple[list[str], float | None]:
    errors: list[str] = []
    amount: float | None = None

    account = next((a for a in member.accounts if a.account_id == account_id), None)
    if account is None:
        errors.append("Invalid account selection.")

    stripped = amount_raw.strip()
    if not stripped:
        errors.append("Amount is required.")
    else:
        try:
            amount = float(stripped)
        except ValueError:
            errors.append("Amount must be a number.")
            amount = None
        else:
            if amount <= 0:
                errors.append("Amount must be greater than zero.")
                amount = None
            elif amount > member.credit_limit:
                errors.append(f"Amount exceeds credit limit of {member.credit_limit:.2f}.")
                amount = None

    return errors, amount


@web.get("/")
def index() -> str:
    return render_template("index.html")


@web.get("/members/search")
def member_search() -> str:
    query = request.args.get("q", "")
    results = search_members(query)
    return render_template("search_results.html", query=query, results=results)


@web.get("/members/<member_id>")
def member_detail(member_id: str):
    member = get_member(member_id)
    if member is None:
        return render_template("error_404.html", member_id=member_id), 404
    return render_template("member_detail.html", member=member)


@web.route("/members/<member_id>/loans/disburse", methods=["GET", "POST"])
def disburse(member_id: str):
    member = get_member(member_id)
    if member is None:
        return render_template("error_404.html", member_id=member_id), 404

    errors: list[str] = []
    account_id = ""
    amount_raw = ""

    if request.method == "POST":
        account_id = request.form.get("account_id", "")
        amount_raw = request.form.get("amount", "")
        errors, amount = validate_disbursement(member, account_id, amount_raw)

        if not errors and amount is not None:
            return render_template(
                "confirm.html",
                member=member,
                account_id=account_id,
                amount=amount,
            )

    return render_template(
        "disburse_form.html",
        member=member,
        errors=errors,
        account_id=account_id,
        amount_raw=amount_raw,
    )


@web.post("/members/<member_id>/loans/disburse/execute")
def disburse_execute(member_id: str):
    member = get_member(member_id)
    if member is None:
        return render_template("error_404.html", member_id=member_id), 404

    account_id = request.form.get("account_id", "")
    amount_raw = request.form.get("amount", "")
    errors, amount = validate_disbursement(member, account_id, amount_raw)

    if errors or amount is None:
        return render_template(
            "disburse_form.html",
            member=member,
            errors=errors or ["Invalid disbursement summary."],
            account_id=account_id,
            amount_raw=amount_raw,
        )

    executed: list[dict] = current_app.config.setdefault("DISBURSEMENTS", [])
    seq = len(executed) + 1
    disbursement_no = f"DISB-{seq:04d}"

    account = next(a for a in member.accounts if a.account_id == account_id)
    prior = sum(d["amount"] for d in executed if d["account_id"] == account_id)
    new_balance = account.balance + prior + amount

    executed.append(
        {
            "disbursement_no": disbursement_no,
            "member_id": member.member_id,
            "account_id": account_id,
            "amount": amount,
        }
    )

    return render_template(
        "receipt.html",
        member=member,
        disbursement_no=disbursement_no,
        account_id=account_id,
        amount=amount,
        new_balance=new_balance,
    )
