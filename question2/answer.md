# Notification Service

## 📌 Code

```python
from abc import ABC, abstractmethod

# Abstraction
class NotificationChannel(ABC):
    @abstractmethod
    def send(self, user, message): ...


class EmailChannel(NotificationChannel):
    def send(self, user, message):
        print(f"[EMAIL] to {user['email']}: {message}")


class SmsChannel(NotificationChannel):
    def send(self, user: dict[str, str], message: str):
        print(f"[SMS] to {user['phone']}: {message}")


class NotificationService:
    def __init__(self, channels: dict[str, NotificationChannel]):
        self.channels = channels

    def notify(self, user: dict[str, str], message: str):
        for pref in user["preferences"]:
            channel = self.channels.get(pref)
            if channel:
                channel.send(user, message)


# Example usage
test_channels = {"EMAIL": EmailChannel(), "SMS": SmsChannel()}
service = NotificationService(test_channels)

user1 = {"email": "a@test.com", "phone": "123", "preferences": ["EMAIL"]}
user2 = {"email": "b@test.com", "phone": "456", "preferences": ["SMS", "EMAIL"]}

service.notify(user1, "Order shipped!")
service.notify(user2, "Payment received!")