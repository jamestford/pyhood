"""Moving money between a bank and Robinhood: `pyhood banks`, `deposit`,
`withdraw` and `cancel-transfer`.

A deposit or a withdrawal moves real money, so it works as an order does:
run once it only previews, and it acts when run again with the
confirmation code the preview printed. The code is tied to the direction,
the amount and the bank, so what is sent is what was shown.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from pyhood.cli import (
    UsageError,
    _amount,
    _wrong_code,
    as_json,
    confirmation_code,
    money,
    plain,
    program,
    table,
)
from pyhood.exceptions import PyhoodError

# States a transfer does not leave. Anything else may still be cancellable.
FINISHED_STATES = frozenset({
    "completed", "cancelled", "canceled", "failed", "rejected", "reversed", "returned",
})


def bank_name(bank: Any) -> str:
    """'Savings …1234 (Rainy day)'."""
    name = (bank.account_type or "account").capitalize()
    if bank.last_four:
        name += f" …{bank.last_four}"
    if bank.account_nickname:
        name += f" ({bank.account_nickname})"
    return name


def banks(client: Any, as_json_output: bool = False) -> int:
    """The bank accounts linked to Robinhood."""
    found = client.get_bank_accounts()
    if as_json_output:
        print(as_json([
            {"id": b.id, "type": b.account_type, "nickname": b.account_nickname,
             "last_four": b.last_four, "state": b.state}
            for b in found
        ]))
        return 0
    if not found:
        print("No bank accounts are linked. Link one in the Robinhood app.")
        return 1
    print(table(
        ["BANK ACCOUNT", "TYPE", "ENDING", "STATE"],
        [[b.account_nickname, b.account_type, b.last_four, b.state] for b in found],
    ))
    return 0


def find_bank(client: Any, selector: str | None) -> Any:
    """The linked bank to use: the only one, or the one `selector` picks out.

    The selector is part of the bank's nickname or type, or the last four
    digits of its account number. Only approved banks can be used.
    """
    usable = [b for b in client.get_bank_accounts() if b.state == "approved"]
    listing = ", ".join(bank_name(b) for b in usable) or "none"
    if not usable:
        raise UsageError(
            "No approved bank account is linked to Robinhood. Link one in the Robinhood app."
        )
    if selector is None:
        if len(usable) == 1:
            return usable[0]
        raise UsageError(f"Say which bank with --bank. Your banks: {listing}")
    wanted = selector.strip().lower()
    matches = [
        b for b in usable
        if wanted == b.last_four or wanted in (b.account_nickname or "").lower()
        or wanted in (b.account_type or "").lower()
    ]
    if len(matches) != 1:
        problem = "No bank matches" if not matches else "More than one bank matches"
        raise UsageError(f"{problem} {selector!r}. Your banks: {listing}")
    return matches[0]


def transfer(
    client: Any,
    direction: str,
    amount: float,
    bank: str | None = None,
    confirm: str | None = None,
    settle_seconds: float = 0.0,
) -> int:
    """Preview a deposit or a withdrawal, or make it when given its code.

    `direction` is 'deposit', bank to Robinhood, or 'withdraw', Robinhood
    to bank.
    """
    if round(amount, 2) != amount:
        raise UsageError(f"{amount} has more than two decimal places. Give dollars and cents.")
    target = find_bank(client, bank)
    code = confirmation_code("transfer", direction, f"{amount:.2f}", target.id)
    command = f"{program()} {direction} {plain(amount)}"
    if bank:
        command += f" --bank {bank}"
    if confirm is not None and confirm != code:
        return _wrong_code()

    name = bank_name(target)
    if direction == "deposit":
        summary = f"Deposit {money(amount)} from {name} into Robinhood"
    else:
        summary = f"Withdraw {money(amount)} from Robinhood to {name}"

    if confirm is not None:
        try:
            sent = client.initiate_transfer(amount, direction, target.url)
        except PyhoodError as e:
            print(f"Robinhood did not accept the transfer: {e}", file=sys.stderr)
            return 1
        if settle_seconds:
            time.sleep(settle_seconds)
        print(f"SENT: {summary}")
        print(f"  Status:       {sent.state or '-'}")
        if sent.expected_landing_date:
            print(f"  Expected by:  {sent.expected_landing_date}")
        print(f"  Transfer ID:  {sent.id}")
        print(f"\nCancel it while it is pending with: {program()} cancel-transfer {sent.id}")
        return 0

    print("PREVIEW. Nothing has been sent.\n")
    print(f"  {summary}")
    warnings = []
    if direction == "withdraw":
        accounts = client.get_all_accounts()
        available = _amount(accounts[0], "withdrawable_cash") if accounts else None
        print(f"  {'Withdrawable cash:':<20}{money(available)}")
        if available is not None and amount > available:
            warnings.append(
                "This is more than your withdrawable cash. Robinhood is likely to "
                "reject it. Money from a recent sale or deposit takes time to become "
                "withdrawable."
            )
    else:
        warnings.append(
            "Robinhood takes this from your bank account. Make sure the money is there."
        )
    warnings.append("A bank transfer takes a few business days to arrive.")
    for warning in warnings:
        print(f"\n  Note: {warning}")
    print("\nTo make this transfer, show this preview to the user. If they say yes, run:")
    print(f"  {command} --confirm {code}")
    return 0


def cancel_transfer(client: Any, transfer_id: str) -> int:
    """Cancel a transfer that has not gone through yet, at once."""
    found = next((t for t in client.get_transfers() if t.id == transfer_id), None)
    if found is None:
        raise UsageError(f"No transfer has the ID {transfer_id}.")
    summary = f"{found.direction} of {money(found.amount)}, created {found.created_at[:10]}"
    if found.state in FINISHED_STATES:
        print(f"That transfer is already {found.state}, so there is nothing to cancel.")
        print(f"  {summary}")
        return 1
    client.cancel_transfer(transfer_id)
    after = next((t for t in client.get_transfers() if t.id == transfer_id), found)
    if after.state in ("cancelled", "canceled"):
        print(f"CANCELLED: {summary}")
        return 0
    print(f"Cancel requested. The transfer is now {after.state}: {summary}")
    return 0
