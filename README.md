# Image Processor Service

A production-ready, domain-agnostic image processing microservice built with FastAPI, SQLAlchemy, Celery, and Redis.

## Features

*   **Asynchronous Processing**: Offloads heavy image processing to Celery workers.
*   **Database Agnostic**: Uses SQLAlchemy 2.0 (AsyncIO) supporting SQLite (dev) and PostgreSQL (prod).
*   **Repository Pattern**: Clean architecture separating business logic from data access.
*   **Scalable Storage**: Supports Local filesystem and AWS S3.
*   **Security**: OAuth 2.0 Resource Server with JWT validation (HS256/RS256).
*   **Observability**: Prometheus metrics, structured JSON logging, and correlation IDs.
*   **Resilience**: Circuit breakers, rate limiting, and automatic retries.

## Architecture

The application follows a clean layered architecture:

1.  **API Layer (`app/api`)**: Handles HTTP requests, validation, and dependency injection.
2.  **Service Layer (`app/services`)**: Contains business logic (`ImageService`, `ProcessorService`).
3.  **Repository Layer (`app/repositories`)**: Abstracts database interactions (`JobRepository`, `EventRepository`).
4.  **Data Layer (`app/db`)**: SQLAlchemy models and session management.
5.  **Task Layer (`app/tasks`)**: Celery tasks for background processing.

## Database Migration

This project uses **Alembic** for database migrations.

To apply migrations:
```bash
alembic upgrade head
```

To create a new migration after model changes:
```bash
alembic revision --autogenerate -m "description of change"
```

## Setup & Run

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Copy `.env.example` to `.env` and configure settings.
    ```bash
    cp .env.example .env
    ```

3.  **Run Workers**:
    ```bash
    celery -A app.tasks.celery_app worker --loglevel=info
    ```

4.  **Run API**:
    ```bash
    uvicorn app.main:app --reload
    ```

## Testing

Run tests with Pytest:
```bash
pytest
```

## API Documentation

Once running, visit:
*   Swagger UI: `http://localhost:8000/docs`
*   ReDoc: `http://localhost:8000/redoc`
*   Dashboard: `http://localhost:8000/dashboard`
