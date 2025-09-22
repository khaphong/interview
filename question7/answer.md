# Multi-Channel Notification System Design


## 1. Solution Approach

The system designed around **REST APIs + Message Queue (Kafka/RabbitMQ)** for asynchronous processing.

### Core Components

- **Notification API (REST)**
  - Exposes REST endpoints for creating notification requests.
  - Handles authentication & validation.
  - Publishes notification events to Kafka/RabbitMQ.

- **Message Broker (Kafka/RabbitMQ)**
  - Decouples producers (API) and consumers (workers).
  - Supports partitioning for scalability and ordering by account or user ID.
  - Enables retry & dead-letter queues for failures.

- **Notification Workers**
  - Dedicated consumers per channel (Email Worker, SMS Worker, Push Worker).
  - Process messages asynchronously based on priority.
  - Implements retry with exponential backoff.
  - Push delivery status back to DB or tracking service.

- **Database (PostgreSQL/NoSQL)**
  - Stores notification requests, delivery status, user preferences.
  - Indexed by user_id + created_at for efficient querying.

- **Monitoring & Logging**
  - Centralized logging (ELK/Prometheus/Grafana).
  - Alerts on delivery failures and SLA breaches.

---

## 2. Workflow

1. **Client** calls REST API `/notifications` with payload:

   ```json
   {
     "user_id": "123",
     "channel": "EMAIL",
     "priority": "HIGH",
     "message": "Your OTP is 123456"
   }
   ```

2. **Notification API** validates request and publishes to Kafka topic `notifications`.
3. **Kafka** partitions messages (e.g., by user_id).
4. **Notification Worker (Email)** consumes from topic, processes, and calls Email provider API.
5. **Delivery result** (sent, failed, retry) is stored in DB and optionally pushed back to client.
6. **Retries** handled via retry queue / dead-letter topic.

---

## 3. Advantages of REST + Kafka

- **Asynchronous & scalable**: Decouples request submission from delivery.
- **Simplicity**: REST is easier to adopt across teams.
- **Resilient**: Kafka ensures durability and replayability.
- **Extensible**: Easy to add new channels (e.g., WhatsApp, Telegram) by creating new consumers.

---

## 4. Step-by-Step Implementation Plan

1. **Define Database Schema**
   - `notifications(id, user_id, channel, priority, status, created_at, updated_at)`

2. **Build REST API**
   - Endpoint: `POST /notifications`
   - Validates request, stores metadata in DB, and publishes to Kafka.

3. **Set up Kafka Topics**
   - `notifications.high`, `notifications.medium`, `notifications.low`
   - Use partitions to distribute load.

4. **Develop Workers**
   - Separate workers for Email, SMS, Push.
   - Implement retry + exponential backoff.
   - Update delivery status in DB.

5. **Add Monitoring**
   - Track delivery success rate, queue lag, worker failures.
   - Expose Prometheus metrics.

6. **Optimize**
   - Introduce caching (Redis) for user preferences.
   - Use batch sending for SMS/Email providers to reduce cost.
