from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel
from typing import Optional, Dict
import uuid
import asyncio
from datetime import datetime, timedelta
import threading
import time

app = FastAPI()

# Models
class PaymentRequest(BaseModel):
    amount: float
    currency: str
    recipient: str
    reference: str

class PaymentResponse(BaseModel):
    transaction_id: str
    status: str
    amount: float
    currency: str
    timestamp: datetime

# Storage for idempotency keys
class IdempotencyStore:
    def __init__(self):
        self.store: Dict[str, dict] = {}
        self.locks: Dict[str, threading.Lock] = {}
        self.expiry_time = timedelta(hours=24)
        
    def get_lock(self, key: str) -> threading.Lock:
        """Get or create a lock for a specific idempotency key"""
        if key not in self.locks:
            self.locks[key] = threading.Lock()
        return self.locks[key]
    
    def store_request(self, key: str, request: PaymentRequest):
        """Store a new request with processing status"""
        with self.get_lock(key):
            self.store[key] = {
                'request': request,
                'response': None,
                'status': 'processing',  # processing, completed, error
                'created_at': datetime.now(),
                'expires_at': datetime.now() + self.expiry_time
            }
    
    def store_response(self, key: str, response: PaymentResponse):
        """Store the response for a completed request"""
        with self.get_lock(key):
            if key in self.store:
                self.store[key]['response'] = response
                self.store[key]['status'] = 'completed'
    
    def store_error(self, key: str, error: dict):
        """Store an error response"""
        with self.get_lock(key):
            if key in self.store:
                self.store[key]['response'] = error
                self.store[key]['status'] = 'error'
    
    def get(self, key: str) -> Optional[dict]:
        """Get stored data for a key"""
        # Clean expired keys first
        self.clean_expired()
        
        with self.get_lock(key):
            return self.store.get(key)
    
    def clean_expired(self):
        """Remove expired keys from storage"""
        current_time = datetime.now()
        expired_keys = []
        
        for key, data in self.store.items():
            if data['expires_at'] < current_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            with self.get_lock(key):
                if key in self.store and self.store[key]['expires_at'] < current_time:
                    del self.store[key]
                    if key in self.locks:
                        del self.locks[key]

# Global store instance
idempotency_store = IdempotencyStore()

# Payment processing simulation
async def process_payment(request: PaymentRequest) -> PaymentResponse:
    """Simulate payment processing with a delay"""
    # Simulate processing time
    await asyncio.sleep(0.1)
    
    # Generate a transaction ID
    transaction_id = str(uuid.uuid4())
    
    # Return response
    return PaymentResponse(
        transaction_id=transaction_id,
        status="completed",
        amount=request.amount,
        currency=request.currency,
        timestamp=datetime.now()
    )

# API Endpoint
@app.post("/payments", response_model=PaymentResponse)
async def create_payment(
    request: PaymentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    # Validate idempotency key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required"
        )
    
    # Check if we've seen this key before
    stored_data = idempotency_store.get(idempotency_key)
    
    if stored_data:
        # Verify the request is the same
        if stored_data['request'].dict() != request.dict():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Idempotency key reused with different request parameters"
            )
        
        # If request is still processing, wait for completion
        while stored_data['status'] == 'processing':
            await asyncio.sleep(0.01)
            stored_data = idempotency_store.get(idempotency_key)
            if not stored_data:
                break
        
        # Return stored response if available
        if stored_data and stored_data['response']:
            if isinstance(stored_data['response'], dict) and 'detail' in stored_data['response']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=stored_data['response']['detail']
                )
            return stored_data['response']
    
    # Store the new request
    idempotency_store.store_request(idempotency_key, request)
    
    try:
        # Process the payment
        response = await process_payment(request)
        idempotency_store.store_response(idempotency_key, response)
        return response
    except Exception as e:
        # Store error
        idempotency_store.store_error(idempotency_key, {"detail": str(e)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# Test Cases
if __name__ == "__main__":
    import pytest
    import requests
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    def test_successful_payment():
        """Test successful payment with idempotency key"""
        key = str(uuid.uuid4())
        request_data = {
            "amount": 100.0,
            "currency": "USD",
            "recipient": "test@example.com",
            "reference": "test-123"
        }
        
        # First request
        response1 = client.post(
            "/payments",
            json=request_data,
            headers={"Idempotency-Key": key}
        )
        assert response1.status_code == 200
        transaction_id = response1.json()["transaction_id"]
        
        # Second request with same key
        response2 = client.post(
            "/payments",
            json=request_data,
            headers={"Idempotency-Key": key}
        )
        assert response2.status_code == 200
        assert response2.json()["transaction_id"] == transaction_id
    
    def test_different_requests_same_key():
        """Test error when same key is used with different requests"""
        key = str(uuid.uuid4())
        request1 = {
            "amount": 100.0,
            "currency": "USD",
            "recipient": "test1@example.com",
            "reference": "test-123"
        }
        request2 = {
            "amount": 200.0,  # Different amount
            "currency": "USD",
            "recipient": "test1@example.com",
            "reference": "test-123"
        }
        
        # First request
        response1 = client.post(
            "/payments",
            json=request1,
            headers={"Idempotency-Key": key}
        )
        assert response1.status_code == 200
        
        # Second request with same key but different data
        response2 = client.post(
            "/payments",
            json=request2,
            headers={"Idempotency-Key": key}
        )
        assert response2.status_code == 422
    
    def test_concurrent_requests():
        """Test handling of concurrent requests with same idempotency key"""
        import threading
        
        key = str(uuid.uuid4())
        request_data = {
            "amount": 100.0,
            "currency": "USD",
            "recipient": "test@example.com",
            "reference": "test-123"
        }
        
        results = []
        errors = []
        
        def make_request():
            try:
                response = client.post(
                    "/payments",
                    json=request_data,
                    headers={"Idempotency-Key": key}
                )
                results.append(response.json()["transaction_id"])
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All responses should have the same transaction ID
        assert len(set(results)) == 1, "All requests should return the same transaction ID"
        assert len(results) == 5, "All requests should complete successfully"
        assert len(errors) == 0, "No requests should fail"
    
    def test_missing_idempotency_key():
        """Test error when idempotency key is missing"""
        request_data = {
            "amount": 100.0,
            "currency": "USD",
            "recipient": "test@example.com",
            "reference": "test-123"
        }
        
        response = client.post("/payments", json=request_data)
        assert response.status_code == 400
    
    def test_key_expiration():
        """Test that keys expire after the specified time"""
        # Create a store with short expiration for testing
        test_store = IdempotencyStore()
        test_store.expiry_time = timedelta(seconds=1)  # 1 second expiration
        
        key = str(uuid.uuid4())
        request = PaymentRequest(
            amount=100.0,
            currency="USD",
            recipient="test@example.com",
            reference="test-123"
        )
        
        # Store request
        test_store.store_request(key, request)
        
        # Verify it's stored
        assert test_store.get(key) is not None
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Verify it's expired
        assert test_store.get(key) is None
    
    # Run all tests
    test_successful_payment()
    print("✓ Test successful payment passed")
    
    test_different_requests_same_key()
    print("✓ Test different requests with same key passed")
    
    test_concurrent_requests()
    print("✓ Test concurrent requests passed")
    
    test_missing_idempotency_key()
    print("✓ Test missing idempotency key passed")
    
    test_key_expiration()
    print("✓ Test key expiration passed")
    
    print("\nAll tests passed! 🎉")