# Heimdex API Documentation

## Overview

The Heimdex API provides endpoints for job submission and status tracking. All responses are JSON-formatted.

## Base URL

```
http://localhost:8000
```

## Endpoints

### Health Check

**GET** `/healthz`

Returns API health status and metadata.

**Response:**
```json
{
  "ok": true,
  "service": "heimdex-api",
  "version": "0.0.1",
  "env": "local",
  "started_at": "2025-10-28T12:00:00.000000Z"
}
```

---

### Create Job

**POST** `/jobs`

Submits a new job for async processing.

**Request Body:**
```json
{
  "type": "mock_process",
  "fail_at_stage": null
}
```

**Parameters:**
- `type` (string): Job type. Currently only `"mock_process"` is supported.
- `fail_at_stage` (string, optional): Stage name to trigger deterministic failure for testing. Options: `"extracting"`, `"analyzing"`, `"indexing"`. Default: `null`.

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"type": "mock_process"}'
```

---

### Get Job Status

**GET** `/jobs/{job_id}`

Retrieves the current status of a job.

**Path Parameters:**
- `job_id` (UUID): The job identifier returned from job creation

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "stage": "analyzing",
  "progress": 45,
  "result": null,
  "error": null,
  "created_at": "2025-10-28T12:00:00.000000Z",
  "updated_at": "2025-10-28T12:00:03.000000Z"
}
```

**Status Values:**
- `pending`: Job queued but not yet started
- `processing`: Job actively running
- `completed`: Job finished successfully
- `failed`: Job failed after retries exhausted

**Example:**
```bash
curl http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

## Testing Workflow

### 1. Submit a successful job
```bash
make test-job
```

### 2. Check job progress
```bash
make check-job
```

Run this multiple times to watch the job progress through stages:
- `extracting` (2 seconds)
- `analyzing` (3 seconds)
- `indexing` (1 second)

### 3. Test failure and retry behavior
```bash
make test-job-fail
# Wait ~10 seconds for retries
make check-job
```

The job will fail at the `analyzing` stage, retry 3 times with exponential backoff, then move to `failed` status.

---

## Mock Processing Stages

The current implementation simulates a video processing pipeline:

| Stage      | Duration | Simulates                |
|------------|----------|--------------------------|
| extracting | 2 sec    | Frame extraction         |
| analyzing  | 3 sec    | Scene detection, ASR     |
| indexing   | 1 sec    | Vector embedding storage |

Total job duration: ~6 seconds (excluding queue time)

---

## Error Handling

**404 Not Found:**
```json
{
  "detail": "Job not found"
}
```

**500 Internal Server Error:**
Returned if database or Redis connection fails. Check service logs:
```bash
make logs
```
