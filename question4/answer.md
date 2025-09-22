# Query Optimization for Transaction Pagination

## Issue
The current query for retrieving paginated transactions is:

```sql
SELECT * FROM transactions
WHERE account_number = ?
ORDER BY entry_date DESC
LIMIT 20 OFFSET ?;
```

Problems:
- The table has grown to billions of rows, with some accounts holding over 1 million transactions.
- Using `OFFSET` becomes increasingly slow for deep pagination because the database must scan and discard many rows.
- The primary key `transaction_id` is a UUID, which has no temporal ordering, making it unsuitable for keyset pagination.

---

## Solution
To optimize pagination:
1. Avoid `OFFSET`-based pagination and switch to **keyset pagination**.
2. Introduce a new sequential column (`entry_seq`) that reflects insertion order.
3. Create a composite index `(account_number, entry_seq DESC)` to efficiently filter and sort.
4. Use the new sequence column to paginate reliably and quickly.

---

## Step-by-Step Implementation

### 1. Add a new sequence column
```sql
ALTER TABLE transactions ADD COLUMN entry_seq BIGINT;
```

### 2. Create sequence and trigger for automatic assignment
```sql
CREATE SEQUENCE transactions_entry_seq_seq;

CREATE OR REPLACE FUNCTION set_entry_seq()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.entry_seq IS NULL THEN
    NEW.entry_seq := nextval('transactions_entry_seq_seq');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entry_seq
BEFORE INSERT ON transactions
FOR EACH ROW EXECUTE FUNCTION set_entry_seq();
```

### 3. Backfill existing rows in batches
```sql
UPDATE transactions
SET entry_seq = nextval('transactions_entry_seq_seq')
WHERE entry_seq IS NULL
LIMIT 10000;
```
*(Repeat until all rows are filled.)*

### 4. Create an index to speed up queries
```sql
CREATE INDEX CONCURRENTLY idx_acc_entryseq_desc
ON transactions (account_number, entry_seq DESC);
```

### 5. Rewrite the pagination query
- First page:
```sql
SELECT * FROM transactions
WHERE account_number = :acct
ORDER BY entry_seq DESC
LIMIT 20;
```

- Next page:
```sql
SELECT * FROM transactions
WHERE account_number = :acct
  AND entry_seq < :last_entry_seq
ORDER BY entry_seq DESC
LIMIT 20;
```

---

## Result
- No performance degradation with deep pagination.
- Query execution remains efficient even for accounts with millions of transactions.
- The solution scales well with the current and future data size.