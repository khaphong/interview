# TransferService

## Issues

In a real-world environment (multi-server, load balancer, hundreds of transactions per second), the initial implementation has critical flaws:

1. **Race conditions / Lost updates**  
   - Multiple concurrent transfers can read the same balance, leading to double spending.

2. **Lack of atomicity**  
   - Debit and credit are saved in two separate `save()` calls. If the process crashes between them, money may vanish.

3. **No rollback mechanism**  
   - If updating the destination account fails, the source has already been debited → inconsistent state.

4. **No cross-server consistency**  
   - Multiple servers can update the same account simultaneously without proper locking, causing data corruption.

5. **No immutable ledger**  
   - Only balances are updated, no history is kept → no way to audit or reconcile discrepancies.

6. **Weak error handling**  
   - All exceptions return `False`, giving the caller no context (e.g., insufficient funds vs. DB error).

---

## Solutions

1. **Database transaction**  
   - Wrap debit + credit + ledger insert in one atomic transaction.  
   - Use `SELECT ... FOR UPDATE` to lock rows and prevent race conditions.

2. **Atomicity & rollback**  
   - Ensure both debit and credit happen together; rollback on failure.

3. **Immutable transfer ledger**  
   - Record every transfer in a separate table for audit and reconciliation.

4. **Idempotency key**  
   - Prevent duplicate transfers when clients retry requests.

5. **Concurrency control**  
   - Use row-level locks or optimistic versioning to avoid lost updates.

6. **Structured logging & error handling**  
   - Return clear error codes and log structured events for observability.

---

## Improve Code (Python)

```python
import logging
from datetime import datetime
from decimal import Decimal


class TransferService:
    def __init__(self, account_repository: AccountRepository):
        self.account_repository = account_repository
        self.logger = logging.getLogger(__name__)

    def transfer_money(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> bool:
        try:
            with self.account_repository.transaction() as tx:
                # Lock accounts for update
                source_account = tx.find_by_id_for_update(from_account_id)
                if not source_account:
                    raise RuntimeError("Source account not found")

                if source_account.balance < amount:
                    self.logger.warning(f"Insufficient funds in {from_account_id}")
                    return False

                destination_account = tx.find_by_id_for_update(to_account_id)
                if not destination_account:
                    raise RuntimeError("Destination account not found")

                # Update source account balance
                source_account.balance -= amount
                source_account.last_updated = datetime.now()
                tx.save(source_account)

                # Update destination account balance
                destination_account.balance += amount
                destination_account.last_updated = datetime.now()
                tx.save(destination_account)

                # Insert ledger entry
                tx.insert_transfer_ledger(
                    from_id=from_account_id,
                    to_id=to_account_id,
                    amount=amount,
                    tx_id=idempotency_key,
                )

                self.logger.info(
                    f"Transfer {amount} from {from_account_id} to {to_account_id} succeeded"
                )
                return True

        except Exception as e:
            self.logger.error(f"Transfer failed: {e}", exc_info=True)
            return False
