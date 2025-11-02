"""
End-to-end integration tests for text embedding and semantic search.

These tests require the full Heimdex stack to be running:
- PostgreSQL (database)
- Redis (queue)
- Qdrant (vector database)
- API service
- Worker service (with embedding models loaded)

Run with: pytest -k test_embed_text_e2e

Test Flow:
1. POST /vectors/embed to create embedding job
2. Poll GET /jobs/{job_id} until SUCCEEDED
3. Verify result contains point_id
4. POST /vectors/search with same text
5. Verify top result matches point_id (semantic search works)
"""

import os
import time
from typing import Any, cast

import pytest
import requests

# Skip these tests if E2E environment is not available
# Set HEIMDEX_E2E_API_URL to enable (e.g., http://localhost:8000)
pytestmark = pytest.mark.skipif(
    not os.getenv("HEIMDEX_E2E_API_URL"),
    reason="E2E tests require HEIMDEX_E2E_API_URL environment variable",
)


@pytest.fixture(scope="module")
def api_base_url() -> str:
    """Get the API base URL from environment."""
    url = os.getenv("HEIMDEX_E2E_API_URL", "http://localhost:8000")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def dev_jwt_token(test_org_id: str, test_user_id: str) -> str:
    """
    Generate a dev JWT token for testing.

    In dev mode (AUTH_PROVIDER=dev), the API accepts simple JWTs signed with DEV_JWT_SECRET.
    This fixture creates a valid dev token with the test org_id and user_id.
    """
    import jwt

    secret = os.getenv("DEV_JWT_SECRET", "local-dev-secret")

    payload = {
        "sub": test_user_id,
        "org_id": test_org_id,
        "iss": "heimdex-test",
        "aud": "heimdex",
    }

    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


@pytest.fixture
def auth_headers(dev_jwt_token: str) -> dict[str, str]:
    """Create authorization headers with dev JWT token."""
    return {"Authorization": f"Bearer {dev_jwt_token}"}


def poll_job_until_terminal(
    api_base_url: str, auth_headers: dict[str, str], job_id: str, timeout: int = 30
) -> dict[str, Any]:
    """
    Poll GET /jobs/{job_id} until job reaches a terminal state.

    Args:
        api_base_url: The API base URL
        auth_headers: Authorization headers
        job_id: The job ID to poll
        timeout: Maximum time to wait in seconds

    Returns:
        The final job response

    Raises:
        TimeoutError: If job doesn't complete within timeout
        AssertionError: If job reaches FAILED state
    """
    start_time = time.time()
    terminal_states = {"SUCCEEDED", "FAILED", "CANCELED", "DEAD_LETTER"}

    while time.time() - start_time < timeout:
        response = requests.get(
            f"{api_base_url}/jobs/{job_id}",
            headers=auth_headers,
            timeout=5,
        )
        response.raise_for_status()
        job = cast(dict[str, Any], response.json())

        status = job.get("status")

        if status in terminal_states:
            if status == "FAILED":
                error = job.get("last_error_message", "Unknown error")
                raise AssertionError(f"Job {job_id} failed: {error}")

            return job

        time.sleep(0.5)  # Poll every 500ms

    raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")


def test_embed_text_e2e(api_base_url: str, auth_headers: dict[str, str], test_org_id: str) -> None:
    """
    End-to-end test for text embedding and semantic search.

    Test Flow:
    1. POST /vectors/embed to create embedding job
    2. Poll GET /jobs/{job_id} until SUCCEEDED
    3. Verify result contains point_id and expected metadata
    4. POST /vectors/search with same text
    5. Verify top result matches point_id (semantic search works)
    """
    # Test data
    test_text = "The quick brown fox jumps over the lazy dog"
    asset_id = "test-asset-001"
    segment_id = "chunk_0"

    # Step 1: Create embedding job
    embed_request = {
        "asset_id": asset_id,
        "segment_id": segment_id,
        "text": test_text,
        "model": "minilm-l6-v2",
        "model_ver": "v1",
    }

    response = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request,
        headers=auth_headers,
        timeout=5,
    )

    assert response.status_code == 200, f"Embed request failed: {response.text}"

    embed_response = response.json()
    job_id = embed_response["job_id"]
    assert job_id, "job_id should be present in response"
    assert embed_response["asset_id"] == asset_id
    assert embed_response["segment_id"] == segment_id

    print(f"✓ Created embedding job: {job_id}")

    # Step 2: Poll job until SUCCEEDED
    job = poll_job_until_terminal(api_base_url, auth_headers, job_id, timeout=30)

    assert job["status"] == "SUCCEEDED", f"Job should succeed, got {job['status']}"

    # Step 3: Verify result contains point_id and metadata
    events = job.get("events", [])
    assert len(events) > 0, "Job should have at least one event"

    # Find the completion event with result
    result_event = next((e for e in events if e.get("detail", {}).get("result")), None)
    assert isinstance(result_event, dict), "Job should have a result event"

    detail = cast(dict[str, Any], result_event.get("detail", {}))
    result_data = detail.get("result")
    assert isinstance(result_data, dict), "Result payload missing in job event"
    point_id = result_data.get("point_id")
    assert point_id, "Result should contain point_id"

    # Verify metadata
    assert result_data["model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert result_data["collection"] == "embeddings"
    assert result_data["text_len"] == len(test_text)
    assert result_data["org_id"] == test_org_id
    assert result_data["asset_id"] == asset_id
    assert result_data["segment_id"] == segment_id

    print(f"✓ Job succeeded with point_id: {point_id}")
    print(f"  - Vector size: {result_data['vector_size']}")
    print(f"  - Text length: {result_data['text_len']}")

    # Step 4: Perform semantic search with same text
    search_request = {
        "query_text": test_text,
        "limit": 5,
        "asset_id": asset_id,  # Filter to only this asset
    }

    response = requests.post(
        f"{api_base_url}/vectors/search",
        json=search_request,
        headers=auth_headers,
        timeout=5,
    )

    assert response.status_code == 200, f"Search request failed: {response.text}"

    search_response = response.json()
    results = search_response["results"]

    assert len(results) > 0, "Search should return at least one result"

    # Step 5: Verify top result matches point_id
    top_result = results[0]
    assert (
        top_result["point_id"] == point_id
    ), f"Top result point_id should match: expected {point_id}, got {top_result['point_id']}"

    # Verify score is high (exact match should have score close to 1.0)
    score = top_result["score"]
    assert score > 0.99, f"Exact match should have score > 0.99, got {score}"

    # Verify payload
    payload = top_result["payload"]
    assert payload["org_id"] == test_org_id
    assert payload["asset_id"] == asset_id
    assert payload["segment_id"] == segment_id
    assert payload["model"] == "sentence-transformers/all-MiniLM-L6-v2"

    print(f"✓ Semantic search found exact match with score: {score:.4f}")
    print(f"  - Query model: {search_response['query_model']}")
    print(f"  - Total results: {search_response['total']}")

    print("\n✅ End-to-end test passed!")


def test_semantic_search_similarity(api_base_url: str, auth_headers: dict[str, str]) -> None:
    """
    Test that semantic search finds semantically similar text (not just exact matches).

    This test:
    1. Embeds a piece of text (e.g., "dog")
    2. Searches with semantically similar text (e.g., "puppy")
    3. Verifies the search finds the original text with a reasonable similarity score
    """
    # Test data: semantically similar phrases
    original_text = "A large furry dog is running in the park"
    similar_text = "A big hairy canine is jogging outdoors"

    asset_id = "test-asset-similarity-001"
    segment_id = "chunk_0"

    # Step 1: Embed original text
    embed_request = {
        "asset_id": asset_id,
        "segment_id": segment_id,
        "text": original_text,
    }

    response = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request,
        headers=auth_headers,
        timeout=5,
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # Step 2: Wait for job to complete
    job = poll_job_until_terminal(api_base_url, auth_headers, job_id, timeout=30)
    assert job["status"] == "SUCCEEDED"

    result_event = next(
        (e for e in job.get("events", []) if e.get("detail", {}).get("result")), None
    )
    assert isinstance(result_event, dict)
    detail = cast(dict[str, Any], result_event.get("detail", {}))
    result_payload = detail.get("result")
    assert isinstance(result_payload, dict)
    point_id = cast(str, result_payload.get("point_id"))
    assert point_id, "Result payload missing point_id"

    print(f"✓ Embedded original text with point_id: {point_id}")

    # Step 3: Search with semantically similar text
    search_request = {
        "query_text": similar_text,
        "limit": 10,
        "asset_id": asset_id,
    }

    response = requests.post(
        f"{api_base_url}/vectors/search",
        json=search_request,
        headers=auth_headers,
        timeout=5,
    )

    assert response.status_code == 200
    search_response = response.json()
    results = search_response["results"]

    # Step 4: Verify the original text is found
    assert len(results) > 0, "Search should return results"

    matching_result = next((r for r in results if r["point_id"] == point_id), None)
    assert matching_result, "Search should find the semantically similar text"

    score = matching_result["score"]
    # Semantic similarity should have decent score (not as high as exact match)
    assert score > 0.5, f"Semantically similar text should have score > 0.5, got {score}"
    assert (
        score < 0.99
    ), f"Semantically similar text should have score < 0.99 (not exact), got {score}"

    print(f"✓ Semantic search found similar text with score: {score:.4f}")
    print(f"  - Original: {original_text}")
    print(f"  - Query: {similar_text}")

    print("\n✅ Semantic similarity test passed!")


def test_idempotent_embed_request(api_base_url: str, auth_headers: dict[str, str]) -> None:
    """
    Test that submitting the same embedding request twice returns the same job_id.

    This verifies the idempotency behavior: job_key includes text_hash, so
    identical (org_id, asset_id, segment_id, text) should deduplicate.
    """
    embed_request = {
        "asset_id": "idempotency-test-asset",
        "segment_id": "chunk_0",
        "text": "Test idempotency with this unique text",
    }

    # First request
    response1 = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request,
        headers=auth_headers,
        timeout=5,
    )
    assert response1.status_code == 200
    job_id_1 = response1.json()["job_id"]

    # Second request (identical)
    response2 = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request,
        headers=auth_headers,
        timeout=5,
    )
    assert response2.status_code == 200
    job_id_2 = response2.json()["job_id"]

    # Should return same job_id
    assert (
        job_id_1 == job_id_2
    ), f"Idempotent requests should return same job_id: {job_id_1} vs {job_id_2}"

    print(f"✓ Idempotency verified: both requests returned job_id {job_id_1}")
    print("\n✅ Idempotency test passed!")


def test_vector_overwrite_semantics(api_base_url: str, auth_headers: dict[str, str]) -> None:
    """
    Test that updating text for the same segment overwrites the vector (latest-wins).

    This verifies the design decision: point_id does NOT include text_hash,
    so different text for the same (org_id, asset_id, segment_id) overwrites.
    """
    asset_id = "overwrite-test-asset"
    segment_id = "chunk_0"

    # Embed first version of text
    embed_request_v1 = {
        "asset_id": asset_id,
        "segment_id": segment_id,
        "text": "Original text version one",
    }

    response = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request_v1,
        headers=auth_headers,
        timeout=5,
    )
    assert response.status_code == 200
    job_id_1 = response.json()["job_id"]

    # Wait for completion
    job1 = poll_job_until_terminal(api_base_url, auth_headers, job_id_1, timeout=30)
    result_event_1 = next(
        (e for e in job1.get("events", []) if e.get("detail", {}).get("result")), None
    )
    assert isinstance(result_event_1, dict)
    detail_1 = cast(dict[str, Any], result_event_1.get("detail", {}))
    result_payload_1 = detail_1.get("result")
    assert isinstance(result_payload_1, dict)
    point_id_1 = cast(str, result_payload_1.get("point_id"))
    assert point_id_1, "Expected point_id in first job result"

    print(f"✓ First version embedded with point_id: {point_id_1}")

    # Embed second version (different text, same segment)
    embed_request_v2 = {
        "asset_id": asset_id,
        "segment_id": segment_id,
        "text": "Updated text version two",
    }

    response = requests.post(
        f"{api_base_url}/vectors/embed",
        json=embed_request_v2,
        headers=auth_headers,
        timeout=5,
    )
    assert response.status_code == 200
    job_id_2 = response.json()["job_id"]

    # Should be different job (different text_hash)
    assert job_id_1 != job_id_2, "Different text should create different job"

    # Wait for completion
    job2 = poll_job_until_terminal(api_base_url, auth_headers, job_id_2, timeout=30)
    result_event_2 = next(
        (e for e in job2.get("events", []) if e.get("detail", {}).get("result")), None
    )
    assert isinstance(result_event_2, dict)
    detail_2 = cast(dict[str, Any], result_event_2.get("detail", {}))
    result_payload_2 = detail_2.get("result")
    assert isinstance(result_payload_2, dict)
    point_id_2 = cast(str, result_payload_2.get("point_id"))
    assert point_id_2, "Expected point_id in second job result"

    # Should have SAME point_id (overwrite semantics)
    assert (
        point_id_1 == point_id_2
    ), f"Same segment should reuse point_id (overwrite): {point_id_1} vs {point_id_2}"

    print(f"✓ Second version reused same point_id: {point_id_2}")

    # Search for second version text
    search_request = {
        "query_text": "Updated text version two",
        "limit": 5,
        "asset_id": asset_id,
    }

    response = requests.post(
        f"{api_base_url}/vectors/search",
        json=search_request,
        headers=auth_headers,
        timeout=5,
    )
    assert response.status_code == 200
    results = response.json()["results"]

    # Should find the vector with updated content (high score)
    top_result = results[0]
    assert top_result["point_id"] == point_id_2
    assert top_result["score"] > 0.99  # Close match to updated text

    print(f"✓ Search confirms vector was overwritten (score: {top_result['score']:.4f})")
    print("\n✅ Vector overwrite test passed!")
