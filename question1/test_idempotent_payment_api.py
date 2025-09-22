import pytest
import httpx
import asyncio
import time
from fastapi.testclient import TestClient
from idempotent_payment_api import app, idempotency_store, PaymentRequest

# Test client setup
client = TestClient(app)

# Test data
BASE_URL = "http://localhost:8000/payments"
TEST_PAYMENT = {
    "amount": 100.0,
    "currency": "USD",
    "recipient": "merchant1"
}
IDEMPOTENCY_KEY = "idempotency_key"
IDEMPOTENCY_HEADER = {"Idempotency-Key": IDEMPOTENCY_KEY}

@pytest.fixture(autouse=True)
def clear_store():
    """Clear the idempotency store before each test"""
    with idempotency_store.lock:
        idempotency_store.store.clear()

@pytest.mark.asyncio
async def test_create_payment():
    """Test creating a new payment"""
    response = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["amount"] == TEST_PAYMENT["amount"]
    assert response.json()["currency"] == TEST_PAYMENT["currency"]
    assert response.json()["recipient"] == TEST_PAYMENT["recipient"]
    assert "transaction_id" in response.json()

@pytest.mark.asyncio
async def test_idempotent_request():
    """Test idempotency with same key and same request"""
    # First request
    response1 = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    assert response1.status_code == 200
    
    # Second request with same key
    response2 = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    assert response2.status_code == 200
    assert response1.json() == response2.json()  # Same response

@pytest.mark.asyncio
async def test_idempotent_different_request():
    """Test idempotency key reuse with different request parameters"""
    # First request
    await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    
    # Second request with different parameters
    different_payment = TEST_PAYMENT.copy()
    different_payment["amount"] = 200.0
    response = await httpx.AsyncClient().post(
        BASE_URL,
        json=different_payment,
        headers=IDEMPOTENCY_HEADER
    )
    assert response.status_code == 400
    assert "different request parameters" in response.json()["detail"]

@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test concurrent requests with same idempotency key"""
    async def make_request():
        return await httpx.AsyncClient().post(
            BASE_URL,
            json=TEST_PAYMENT,
            headers=IDEMPOTENCY_HEADER
        )

    # Launch multiple concurrent requests
    tasks = [make_request() for _ in range(5)]
    responses = await asyncio.gather(*tasks)
    
    # Verify all responses are identical
    first_response = responses[0].json()
    assert all(response.json() == first_response for response in responses)
    assert all(response.status_code == 200 for response in responses)

@pytest.mark.asyncio
async def test_expiration():
    """Test idempotency key expiration"""
    # Set short expiration for testing
    original_expiration = idempotency_store.expiration_seconds
    idempotency_store.expiration_seconds = 1  # 1 second expiration

    # Make first request
    response = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    assert response.status_code == 200
    
    # Wait for expiration and force cleanup
    await asyncio.sleep(2)  # Increased sleep to ensure expiration
    with idempotency_store.lock:
        idempotency_store.cleanup_expired()
        # Verify store is empty directly
        assert idempotency_store.store == {}  # Check store state directly
    
    # Make second request with same key
    response2 = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT,
        headers=IDEMPOTENCY_HEADER
    )
    assert response2.status_code == 200
    assert response2.json()["transaction_id"] != response.json()["transaction_id"]
    
    # Restore original expiration
    idempotency_store.expiration_seconds = original_expiration

@pytest.mark.asyncio
async def test_missing_idempotency_key():
    """Test request without idempotency key"""
    response = await httpx.AsyncClient().post(
        BASE_URL,
        json=TEST_PAYMENT
    )
    assert response.status_code == 422