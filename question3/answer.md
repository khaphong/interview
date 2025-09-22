
# Question 3

## Code Review Issues

- No Error Handling: This is the most severe architectural flaw. The code assumes every operation (payment processing, email sending) will always succeed.

- TransactionService creates its own dependencies, making testing and substitution difficult.

- The code works with Stripe, but TransactionService is tightly coupled to StripePaymentProcessor. If we want to add Momo or switch to another provider, we’d need to modify TransactionService directly, which violates the Open/Closed Principle. A cleaner design would introduce an abstraction for PaymentProcessor and inject the concrete implementation (Stripe, Momo, Zalo pay, etc.) into TransactionService, so the service doesn’t depend on specific providers.

## Code improve

```python
import logging
import time
from decimal import Decimal
from typing import Protocol


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STRIPE_TX_PREFIX = "stripe-tx"


class PaymentProcessingError(Exception): ...


class EmailSendingError(Exception): ...


class PaymentProcessor(Protocol):
    def process_payment(self, amount: Decimal, card_number: str) -> str: ...


class StripePaymentProcessor:
    def process_payment(self, amount: Decimal, card_number: str) -> str:
        try:
            masked_card = f"****-****-****-{card_number[-4:]}"
            logger.info(f"Connecting to Stripe API...")
            logger.info(f"Processing payment of ${amount} with card {masked_card}")
            return f"{STRIPE_TX_PREFIX}-{int(time.time())}"
        except Exception as e:
            raise PaymentProcessingError(f"Error processing payment: {str(e)}")


class EmailSender:
    def send_confirmation(self, email: str, tx_id: str, amount: Decimal) -> None:
        try:
            logger.info(f"Sending payment confirmation email to {email}")
        except Exception as e:
            raise EmailSendingError(f"Error sending email: {str(e)}")


class TransactionService:
    def __init__(self, payment_processor: PaymentProcessor, email_sender: EmailSender):
        self.payment_processor = payment_processor
        self.email_sender = email_sender

    def process_transaction(self, amount: Decimal, card_number: str, email: str) -> str:
        """Process transaction and send confirmation email."""
        tx_id = self.payment_processor.process_payment(amount, card_number)
        self.email_sender.send_confirmation(email, tx_id, amount)
        return tx_id


def main():
    payment_processor = StripePaymentProcessor()
    email_sender = EmailSender()
    service = TransactionService(payment_processor, email_sender)
    try:
        tx_id = service.process_transaction(
            Decimal("99.99"), "1234-5678-9012-3456", "customer@example.com"
        )
        logger.info(f"Transaction completed successfully: {tx_id}")
    except (PaymentProcessingError, EmailSendingError, ValueError) as e:
        logger.error(f"Transaction failed: {e}")


if __name__ == "__main__":
    main()
