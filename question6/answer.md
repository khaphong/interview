# Transfer API Review

## Issues

1. **No ownership validation**
   - The code does not check whether the source account belongs to the authenticated user.
   - **Consequence:** A malicious user could transfer money from accounts they do not own.

2. **Raw SQL usage / potential SQL injection**
   - `db.session.query("SELECT * FROM accounts WHERE id = %s", (source_account_id,))` is not valid SQLAlchemy ORM usage and looks like raw SQL.
   - **Consequence:** If not properly parameterized, attackers may inject malicious SQL.

3. **No validation of amount**
   - `amount` is not checked.
   - **Consequence:** Users could submit negative or zero values to manipulate balances.

4. **No validation of destination account**
   - The destination account is retrieved but not checked for existence or validity.
   - **Consequence:** Transfers may be sent to invalid/non-existent accounts.

5. **Missing real transfer logic**
   - The `TransferService` simply returns a dummy transaction result without updating balances.
   - **Consequence:** Funds are never actually moved, and no consistency is enforced.

---

## Solutions

- **Check account ownership**  
  Ensure the source account belongs to the authenticated profile (`current_profile_id`).

- **Use ORM/parameterized queries**  
  Prevent SQL injection by using SQLAlchemy ORM methods instead of raw SQL.

- **Validate transfer amount**  
  Ensure the amount is positive and within balance limits.

- **Verify destination account**  
  Ensure the destination account exists and is active before transferring.

- **Implement proper transfer logic**  
  Deduct from the source, credit the destination, and insert a ledger entry — all inside a database transaction.

---

## Fixed Example Code

```python
from flask import Flask, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db, Account, TransactionLog
from decimal import Decimal
from datetime import datetime

app = Flask(__name__)

class TransferService:
    def execute_transfer(self, source_account, destination_account, amount, description, profile_id):
        # Validate balance
        if source_account.balance < amount:
            raise ValueError("Insufficient funds")

        # Perform transfer inside DB transaction
        with db.session.begin():
            source_account.balance -= amount
            destination_account.balance += amount

            # Create transaction log
            txn = TransactionLog(
                source_account_id=source_account.id,
                destination_account_id=destination_account.id,
                amount=amount,
                description=description,
                profile_id=profile_id,
                created_at=datetime.utcnow()
            )
            db.session.add(txn)

        return {"transaction_id": txn.id, "status": "COMPLETED"}


transfer_service = TransferService()

@app.route("/api/transfers/execute", methods=["POST"])
@jwt_required()
def execute_transfer():
    current_profile_id = get_jwt_identity()
    data = request.get_json()

    source_account_id = data.get("source_account_id")
    destination_account_id = data.get("destination_account_id")
    amount = Decimal(str(data.get("amount", "0")))
    description = data.get("description")

    if amount <= 0:
        return jsonify({"error": "Invalid transfer amount"}), 400

    source_account = (
        db.session.query(Account)
        .filter_by(id=source_account_id, profile_id=current_profile_id)
        .first()
    )
    if not source_account:
        return jsonify({"error": "Unauthorized source account"}), 403

    destination_account = db.session.get(Account, destination_account_id)
    if not destination_account:
        return jsonify({"error": "Invalid destination account"}), 400

    try:
        result = transfer_service.execute_transfer(
            source_account, destination_account, amount, description, current_profile_id
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Transfer failed"}), 500


if __name__ == "__main__":
    app.run(debug=True)
