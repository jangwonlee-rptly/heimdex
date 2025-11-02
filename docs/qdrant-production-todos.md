# Qdrant Integration - Production Readiness Checklist

**Current Status**: Mock Implementation Complete ✅
**Target**: Production-Ready Vector Search

---

## Priority 0: Critical for Production Launch

### 1. Real Embedding Model Integration

**Owner**: TBD
**Status**: 🔴 Not Started
**Deadline**: TBD

- [ ] **Model Selection**
  - [ ] Evaluate SentenceTransformers models (all-MiniLM-L6-v2, all-mpnet-base-v2)
  - [ ] Evaluate OpenAI embeddings (text-embedding-3-small, text-embedding-3-large)
  - [ ] Evaluate Cohere embeddings
  - [ ] Run benchmark: quality (BEIR), latency, cost
  - [ ] Document model selection decision

- [ ] **Model Infrastructure**
  - [ ] Create `ModelManager` class for loading/caching models
  - [ ] Add model warmup on worker startup
  - [ ] Implement model version tracking
  - [ ] Add GPU support to worker Dockerfile
  - [ ] Test model memory footprint (ensure fits in container limits)

- [ ] **Worker Implementation**
  - [ ] Create `generate_embedding` actor (replace `mock_embedding`)
  - [ ] Add text preprocessing (truncation, normalization)
  - [ ] Implement batch inference (multiple segments per forward pass)
  - [ ] Add error handling (OOM, model errors)
  - [ ] Update progress tracking for real embedding steps

- [ ] **Testing**
  - [ ] Unit tests for embedding generation
  - [ ] Verify embedding reproducibility
  - [ ] Load test with realistic document sizes
  - [ ] Measure latency: p50, p95, p99

**Acceptance Criteria**:

- ✅ Worker generates real embeddings from text input
- ✅ Embeddings are identical for same text (reproducibility)
- ✅ Latency < 100ms per embedding (with GPU) or < 500ms (CPU only)
- ✅ Model version tracked in Qdrant payload
- ✅ Out-of-memory errors handled gracefully

---

### 2. Production API Endpoints

**Owner**: TBD
**Status**: 🔴 Not Started
**Deadline**: TBD

- [ ] **POST /vectors/embed**
  - [ ] Request validation (text length limits, asset_id format)
  - [ ] Support optional `model` parameter
  - [ ] Return job_id for async processing
  - [ ] Add rate limiting (10 req/min per org)

- [ ] **POST /vectors/search**
  - [ ] Accept query text (to embed on-the-fly)
  - [ ] Support limit parameter (default: 10, max: 100)
  - [ ] Support org_id filtering (enforce tenant isolation)
  - [ ] Support asset_id filtering (search within document)
  - [ ] Return scored results with metadata
  - [ ] Add caching for common queries

- [ ] **GET /vectors/{point_id}**
  - [ ] Retrieve vector by ID
  - [ ] Verify tenant ownership (403 if wrong org)
  - [ ] Return payload metadata

- [ ] **DELETE /vectors/{point_id}**
  - [ ] Soft delete (mark as deleted in payload)
  - [ ] Verify tenant ownership
  - [ ] Update associated job status

- [ ] **Documentation**
  - [ ] Update OpenAPI schema
  - [ ] Add usage examples to docs
  - [ ] Document rate limits

**Acceptance Criteria**:

- ✅ All CRUD operations functional
- ✅ Semantic search returns relevant results
- ✅ Rate limits prevent abuse
- ✅ Proper error responses (400, 401, 403, 404, 429, 500)
- ✅ OpenAPI docs up to date

---

### 3. Text Extraction & Chunking Pipeline

**Owner**: TBD
**Status**: 🔴 Not Started
**Deadline**: TBD

- [ ] **Text Extraction**
  - [ ] PDF: Use `pymupdf` or `pdfplumber`
  - [ ] DOCX: Use `python-docx`
  - [ ] TXT: Direct read with encoding detection
  - [ ] HTML: Use `beautifulsoup4` with tag filtering
  - [ ] Handle multi-language documents (UTF-8, CJK)

- [ ] **Chunking Strategy**
  - [ ] Implement fixed-size chunking (512 tokens with 50-token overlap)
  - [ ] Implement semantic chunking (paragraph/sentence boundaries)
  - [ ] Add chunk metadata:
    - [ ] Original text
    - [ ] Page number / position
    - [ ] Chunk index
    - [ ] Total chunks
  - [ ] Handle edge cases (very short/long documents)

- [ ] **Asset Integration**
  - [ ] Create `extract_and_chunk` worker actor
  - [ ] Trigger chunking on asset upload
  - [ ] Store chunks in separate table (or expand asset model)
  - [ ] Link chunks to embeddings via `segment_id`

- [ ] **Testing**
  - [ ] Test with various document types
  - [ ] Test with large documents (>1000 pages)
  - [ ] Verify chunk overlap correctness
  - [ ] Test with non-English text

**Acceptance Criteria**:

- ✅ Extracts text from PDF, DOCX, TXT, HTML
- ✅ Chunks respect token limits and semantic boundaries
- ✅ Metadata includes source location (page, paragraph)
- ✅ Handles documents up to 10MB / 1000 pages
- ✅ Multi-language support (at least: en, es, fr, de, zh, ja)

---

## Priority 1: Important for Production

### 4. Batch Operations

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Batch Embedding Endpoint**
  - [ ] `POST /vectors/embed/batch`
  - [ ] Accept array of text segments
  - [ ] Create single job for entire batch
  - [ ] Return job_id

- [ ] **Worker Optimization**
  - [ ] Process segments in batches of 32-64
  - [ ] Use model batch inference (5-10x speedup)
  - [ ] Report progress per batch
  - [ ] Handle partial failures (some segments succeed, some fail)

- [ ] **Testing**
  - [ ] Benchmark batch vs individual requests
  - [ ] Test with 1000+ segments
  - [ ] Verify all segments processed

**Benefits**:

- 5-10x faster for large documents
- Better GPU utilization
- Lower API overhead

---

### 5. Advanced Search Features

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Hybrid Search** (Vector + Keyword)
  - [ ] Add keyword scoring (BM25 via Qdrant sparse vectors)
  - [ ] Implement score fusion (RRF or linear combination)
  - [ ] Tune keyword vs vector weight

- [ ] **Re-Ranking**
  - [ ] Implement MMR (Maximal Marginal Relevance) for diversity
  - [ ] Add cross-encoder re-ranking (optional, expensive)

- [ ] **Multi-Vector Queries**
  - [ ] Support multiple query vectors (e.g., query + example doc)
  - [ ] Implement fusion strategies

- [ ] **Search Explanations**
  - [ ] Return why each result matched (keywords, semantic similarity)
  - [ ] Add snippet highlighting

- [ ] **Pagination**
  - [ ] Support offset/limit for large result sets
  - [ ] Add cursor-based pagination for deep pagination

**Acceptance Criteria**:

- ✅ Hybrid search outperforms vector-only (measured on test set)
- ✅ MMR increases result diversity
- ✅ Pagination works for 10k+ results

---

### 6. Monitoring & Observability

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Metrics**
  - [ ] Expose Prometheus metrics:
    - `heimdex_embeddings_total{status="success|failure"}`
    - `heimdex_embeddings_duration_seconds`
    - `heimdex_search_total`
    - `heimdex_search_duration_seconds`
    - `heimdex_qdrant_vector_count`
  - [ ] Create Grafana dashboard

- [ ] **Alerts**
  - [ ] Alert on high error rate (>5%)
  - [ ] Alert on collection missing
  - [ ] Alert on Qdrant service down
  - [ ] Alert on embedding latency spike (>1s p95)

- [ ] **Tracing**
  - [ ] Add OpenTelemetry instrumentation
  - [ ] Trace embedding generation (model inference)
  - [ ] Trace Qdrant operations (upsert, search)

- [ ] **Query Analytics**
  - [ ] Log search queries (for quality analysis)
  - [ ] Track zero-result queries
  - [ ] Track slow queries (>500ms)

**Acceptance Criteria**:

- ✅ Grafana dashboard shows key metrics
- ✅ Alerts fire correctly (test with chaos engineering)
- ✅ Traces visible in Jaeger/Zipkin
- ✅ Query logs available for analysis

---

### 7. Performance Optimization

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Benchmarking**
  - [ ] Load 1M vectors into Qdrant
  - [ ] Measure search latency at scale
  - [ ] Measure upsert throughput
  - [ ] Test concurrent operations (100 concurrent searches)

- [ ] **Qdrant Tuning**
  - [ ] Tune HNSW parameters:
    - `m`: 16 (default) vs 32 vs 64
    - `ef_construct`: 100 (default) vs 200 vs 400
  - [ ] Test quantization (scalar, product)
  - [ ] Add payload indexing for common filters (org_id, asset_id)

- [ ] **Application Tuning**
  - [ ] Implement embedding cache (Redis)
  - [ ] Add connection pooling for Qdrant client
  - [ ] Batch upserts (write 100 points at once)

- [ ] **Resource Optimization**
  - [ ] Measure Qdrant memory usage vs vector count
  - [ ] Test with lower-precision vectors (float16 vs float32)
  - [ ] Evaluate storage compression

**Acceptance Criteria**:

- ✅ Search latency < 50ms (p95) for 1M vectors
- ✅ Upsert throughput > 1000 vectors/second
- ✅ Qdrant memory usage < 2x raw vector size

---

## Priority 2: Nice to Have

### 8. Multi-Model Support

**Owner**: TBD
**Status**: 🟢 Not Started
**Deadline**: TBD

- [ ] Support multiple embedding models running simultaneously
- [ ] Add model selection parameter to API (`?model=minilm-l6-v2`)
- [ ] Track model performance metrics (latency, quality)
- [ ] Create model recommendation system (suggest best model for use case)

**Use Cases**:

- Fast model for large-scale indexing (MiniLM)
- Accurate model for high-value queries (MPNet, OpenAI)
- Domain-specific models (legal, medical, code)

---

### 9. Advanced Qdrant Features

**Owner**: TBD
**Status**: 🟢 Not Started
**Deadline**: TBD

- [ ] **Quantization** - Reduce storage by 4-8x
  - [ ] Test scalar quantization
  - [ ] Test product quantization
  - [ ] Measure quality impact

- [ ] **Sparse Vectors** - Keyword search
  - [ ] Generate BM25 sparse vectors
  - [ ] Store alongside dense vectors
  - [ ] Use for hybrid search

- [ ] **Multi-Vector Embeddings**
  - [ ] Store multiple vectors per document (late interaction)
  - [ ] Use for ColBERT-style retrieval

---

### 10. Developer Experience

**Owner**: TBD
**Status**: 🟢 Not Started
**Deadline**: TBD

- [ ] **Vector Playground UI**
  - [ ] Web interface for testing embeddings
  - [ ] Live search demo
  - [ ] Visualize nearest neighbors

- [ ] **Embedding Visualization**
  - [ ] Reduce dimensions with t-SNE/UMAP
  - [ ] Plot vectors in 2D/3D
  - [ ] Color by document/topic

- [ ] **Relevance Testing Tool**
  - [ ] Define test queries with expected results
  - [ ] Measure nDCG, MRR, Recall@k
  - [ ] Compare models/configurations

- [ ] **Quality Metrics Dashboard**
  - [ ] Track embedding quality over time
  - [ ] Show distribution of cosine similarities
  - [ ] Identify outliers/anomalies

---

## Testing & Validation

### 11. Comprehensive Testing

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Unit Tests**
  - [ ] `qdrant_repo.py`: all functions
  - [ ] `embedding.py`: model loading, inference
  - [ ] `chunking.py`: text extraction, splitting

- [ ] **Integration Tests**
  - [ ] Worker actor end-to-end
  - [ ] API endpoints with auth
  - [ ] Search relevance tests

- [ ] **Load Tests**
  - [ ] 1M vectors upsert
  - [ ] 1000 concurrent searches
  - [ ] Sustained load (1000 req/min for 1 hour)

- [ ] **Chaos Tests**
  - [ ] Qdrant service down during upsert
  - [ ] Network partition during search
  - [ ] Worker OOM during embedding
  - [ ] Disk full on Qdrant

**Acceptance Criteria**:

- ✅ >90% code coverage
- ✅ All integration tests pass
- ✅ Load tests meet SLA (p95 < 100ms)
- ✅ Chaos tests: system recovers gracefully

---

### 12. Security Audit

**Owner**: TBD
**Status**: 🟡 Not Started
**Deadline**: TBD

- [ ] **Tenant Isolation**
  - [ ] Verify org A cannot access org B's vectors
  - [ ] Test filter injection attempts
  - [ ] Verify point_id collisions impossible

- [ ] **Injection Attacks**
  - [ ] Test SQL injection in filters (should be safe with Qdrant)
  - [ ] Test NoSQL injection in filters
  - [ ] Test XSS in search results (if HTML returned)

- [ ] **Authentication**
  - [ ] Verify all endpoints require valid JWT
  - [ ] Test with expired tokens
  - [ ] Test with wrong org_id in token

- [ ] **Data Privacy**
  - [ ] Document what data is stored in Qdrant (text? metadata?)
  - [ ] Define data retention policy
  - [ ] Add PII detection/scrubbing (if required)

**Acceptance Criteria**:

- ✅ No cross-tenant data leaks
- ✅ All injection attacks blocked
- ✅ Auth required and enforced on all endpoints
- ✅ PII handling documented and compliant

---

## Migration & Deployment

### 13. Production Deployment Checklist

**Owner**: TBD
**Status**: 🟢 Not Started
**Deadline**: TBD

- [ ] **Pre-Deployment**
  - [ ] Backup existing Qdrant data (if any)
  - [ ] Test deployment on staging environment
  - [ ] Document rollback procedure
  - [ ] Review resource quotas (CPU, memory, storage)

- [ ] **Deployment**
  - [ ] Deploy Qdrant v1.11.3 to production
  - [ ] Update worker containers with GPU support
  - [ ] Set environment variables (QDRANT_URL, VECTOR_SIZE)
  - [ ] Enable Qdrant in readiness probes (ENABLE_QDRANT=true)
  - [ ] Deploy API changes
  - [ ] Run smoke tests

- [ ] **Post-Deployment**
  - [ ] Monitor error rates for 24 hours
  - [ ] Verify metrics in Grafana
  - [ ] Test with production traffic
  - [ ] Document any issues

- [ ] **Rollback Plan**
  - [ ] Keep old API version deployed
  - [ ] Feature flag to disable new endpoints
  - [ ] Database rollback procedure

---

## Timeline Estimate

| Priority | Work Items | Estimated Effort | Dependencies |
|----------|------------|------------------|--------------|
| **P0** | Real embedding model integration | 3-5 days | Model selection decision |
| **P0** | Production API endpoints | 2-3 days | Embedding model ready |
| **P0** | Text extraction & chunking | 3-5 days | None |
| **P1** | Batch operations | 2 days | P0 complete |
| **P1** | Advanced search | 3 days | P0 complete |
| **P1** | Monitoring | 2-3 days | P0 complete |
| **P1** | Performance optimization | 3-5 days | P0 complete, production load |
| **P2** | Multi-model support | 2-3 days | P0 complete |
| **P2** | Advanced Qdrant features | 3-5 days | P1 complete |
| **P2** | Developer experience | 2 days | P0 complete |
| **Testing** | Comprehensive testing | 3-5 days | P0 complete |
| **Security** | Security audit | 2 days | P0 complete |

**Total**: ~30-45 days of engineering effort

**Critical Path**: P0 items (8-13 days) → Production-ready for basic use cases
**Full Production**: P0 + P1 (18-31 days) → Production-ready with monitoring and optimization

---

## Notes

### Model Selection Criteria

When selecting an embedding model, consider:

1. **Quality**: Benchmark on your domain (legal docs? code? general text?)
2. **Latency**: GPU vs CPU, batch size, sequence length
3. **Cost**: OpenAI charges per token, open-source models are free
4. **Licensing**: Some models restrict commercial use
5. **Vector Size**: Smaller = faster search, larger = better quality

**Recommended Starting Point**: `sentence-transformers/all-MiniLM-L6-v2`

- Vector size: 384
- Quality: Good for general text
- Speed: Fast (even on CPU)
- License: Apache 2.0 (commercial use OK)

### Qdrant Scaling Considerations

**When to scale**:

- **Vertical**: Add more RAM/CPU when search latency increases
- **Horizontal**: Shard collection when vector count > 10M

**Monitoring metrics**:

- Vector count per collection
- Search latency (p50, p95, p99)
- Upsert throughput
- Memory usage

**Scaling strategy**:

1. Start with single Qdrant instance
2. Scale vertically to 16GB RAM, 4 CPU
3. Add replicas for read scaling
4. Shard collections for write scaling

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-30 | 1.0 | Initial checklist based on Microstep 0.8 completion |

---

**Owner**: Assign owners for each priority 0 item before starting work.
**Review Cadence**: Update this checklist weekly during active development.
