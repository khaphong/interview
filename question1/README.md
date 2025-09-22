# Idempotent Payment API

## Setup
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run API
```bash
uvicorn idempotent_payment_api:app --reload
```

## Test
```bash
python idempotent_payment_api.py
```