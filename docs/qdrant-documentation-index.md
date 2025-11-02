# Qdrant Integration Documentation Index

**Last Updated**: 2025-10-30
**Microstep**: 0.8 - Qdrant "Hello Write"

---

## 📚 Documentation Overview

This directory contains comprehensive documentation for Heimdex's Qdrant vector database integration. Choose the document that best fits your needs:

### For Quick Start

**→ [Qdrant Developer Guide](qdrant-developer-guide.md)** ⭐ **START HERE**

- 5-minute quick start
- Common tasks (create embeddings, search, debug)
- Code examples (Python, TypeScript, cURL)
- Troubleshooting guide

**Best for**: Daily development work

---

### For Understanding the System

**→ [Microstep 0.8: Qdrant Integration](microstep-0.8-qdrant-integration.md)**

- Complete implementation overview
- Architecture & design decisions
- What's mock vs production-ready
- Deployment guide
- Testing & validation results

**Best for**: Understanding how everything works, onboarding new team members, system architecture reviews

---

### For Planning Production

**→ [Production Readiness Checklist](qdrant-production-todos.md)**

- Priority-ordered task list (P0, P1, P2)
- Effort estimates
- Acceptance criteria
- Timeline projections (~30-45 days total)

**Best for**: Product managers, engineering leads planning the production rollout

---

### For Migration to Production

**→ [Migration Guide: Mock → Production](qdrant-mock-to-production.md)**

- Step-by-step migration phases
- Real embedding model integration
- API endpoint implementation
- Testing strategies
- Rollback plans

**Best for**: Engineers implementing production features

---

## 🚀 Quick Navigation

### I want to

| Goal | Document | Section |
|------|----------|---------|
| **Create my first embedding** | [Developer Guide](qdrant-developer-guide.md) | Quick Start |
| **Debug a failed job** | [Developer Guide](qdrant-developer-guide.md) | Troubleshooting |
| **Understand point IDs** | [Microstep 0.8](microstep-0.8-qdrant-integration.md) | Architecture → Deterministic Point IDs |
| **See what's done** | [Microstep 0.8](microstep-0.8-qdrant-integration.md) | What Was Implemented |
| **See what's left to do** | [Production TODOs](qdrant-production-todos.md) | All sections |
| **Plan production deployment** | [Production TODOs](qdrant-production-todos.md) | Timeline Estimate |
| **Migrate to real embeddings** | [Migration Guide](qdrant-mock-to-production.md) | All phases |
| **Choose an embedding model** | [Migration Guide](qdrant-mock-to-production.md) | Phase 1: Model Selection |
| **Set up GPU support** | [Migration Guide](qdrant-mock-to-production.md) | Phase 2: Worker Implementation |
| **Add search endpoint** | [Migration Guide](qdrant-mock-to-production.md) | Phase 3: API Implementation |
| **Monitor Qdrant health** | [Developer Guide](qdrant-developer-guide.md) | Check Service Health |

---

## 📊 Current State Summary

### ✅ What Works Today (Mock Implementation)

- **Infrastructure**: Qdrant v1.11.3 running in Docker Compose
- **API**: `POST /vectors/mock` creates deterministic mock embeddings
- **Worker**: `mock_embedding` actor generates vectors using seeded numpy
- **Qdrant**: Stores vectors with tenant isolation
- **Job Tracking**: Full lifecycle visibility (pending → processing → completed)
- **Idempotency**: Duplicate requests return same job_id and point_id
- **Health Probes**: Qdrant readiness checks integrated

### 🔴 What Needs Work (Production)

**Priority 0 (Critical)**:

- Real embedding model (SentenceTransformers, OpenAI, etc.)
- Production endpoints (`/vectors/embed`, `/vectors/search`)
- Text extraction & chunking pipeline

**Priority 1 (Important)**:

- Batch operations
- Advanced search (hybrid, re-ranking)
- Monitoring & observability
- Performance optimization

**Priority 2 (Nice to Have)**:

- Multi-model support
- Advanced Qdrant features (quantization, sparse vectors)
- Developer tools (playground UI, visualizations)

### ⏱️ Timeline

- **Mock → Basic Production**: ~8-13 days (P0 items)
- **Full Production**: ~18-31 days (P0 + P1 items)
- **All Features**: ~30-45 days (P0 + P1 + P2 items)

---

## 🎯 Key Concepts

### Deterministic Point IDs

Every vector in Qdrant has a unique ID. We generate IDs deterministically:

```
Input: (org_id, asset_id, segment_id, model, model_ver)
       ↓
SHA256 hash → first 128 bits → UUID
       ↓
Output: "753ee532-60b1-4aa4-dc7d-4fb151e78483"
```

**Why?** Same inputs always produce same ID → idempotent upserts.

### Transactional Outbox Pattern

Jobs are published to workers using the outbox pattern:

```
API Request → [Job + Outbox] written to DB (transaction)
                     ↓
              Outbox Dispatcher reads unsent messages
                     ↓
              Publishes to Dramatiq (Redis)
                     ↓
              Worker processes job
                     ↓
              Upserts vector to Qdrant
```

**Why?** Guarantees exactly-once delivery (no lost jobs, no duplicates).

### Tenant Isolation

Every vector belongs to an organization:

1. **Point ID**: Includes `org_id` in hash → unique per tenant
2. **Payload**: Stores `org_id` → enables filtering
3. **API**: JWT provides `org_id` → enforces access control

**Result**: Org A cannot access Org B's vectors.

---

## 🏗️ Architecture Diagram

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /vectors/mock
       ↓
┌─────────────────────────────────────┐
│          API Service                │
│  - Authenticate (JWT)               │
│  - Create Job (DB)                  │
│  - Create Outbox (DB)               │
│  - Commit transaction               │
└──────────┬──────────────────────────┘
           │
    ┌──────┴──────────┐
    │ Outbox          │
    │ Dispatcher      │ (Background thread)
    │ - Read unsent   │
    │ - Publish to    │
    │   Dramatiq      │
    └──────┬──────────┘
           │ (via Redis)
           ↓
┌─────────────────────────────────────┐
│        Worker Service               │
│  - Consume from Dramatiq            │
│  - Generate vector (mock)           │
│  - Upsert to Qdrant                 │
│  - Update job status                │
└──────────┬──────────────────────────┘
           │
           ↓
┌─────────────────────────────────────┐
│         Qdrant                      │
│  - Store vector + metadata          │
│  - Index for similarity search      │
│  - Persist to disk                  │
└─────────────────────────────────────┘
```

---

## 🔍 Code Locations

### Key Files

| Component | File | Lines |
|-----------|------|-------|
| **Vector Repository** | `packages/common/src/heimdex_common/vector/qdrant_repo.py` | ~260 |
| **Mock Embedding Actor** | `apps/worker/src/heimdex_worker/tasks.py` | 231-376 |
| **Vectors API** | `apps/api/src/heimdex_api/vectors.py` | ~200 |
| **Qdrant Probe** | `packages/common/src/heimdex_common/probes.py` | 173-188 |
| **Config** | `packages/common/src/heimdex_common/config.py` | 115-122 |
| **Docker Compose** | `deploy/docker-compose.yml` | 34-46 |

### Tests

| Test | File | Purpose |
|------|------|---------|
| **End-to-End** | `test_e2e_qdrant.py` | Full flow: API → worker → Qdrant |
| **Auth** | `packages/common/tests/test_auth.py` | JWT token generation |

---

## 📈 Metrics to Monitor

### Application Metrics

```
heimdex_embeddings_total{status="success|failure"}
heimdex_embeddings_duration_seconds
heimdex_search_total
heimdex_search_duration_seconds
```

### Qdrant Metrics (from `:6333/metrics`)

```
qdrant_rest_responses_total
qdrant_collections_vector_count
qdrant_collections_points_count
```

### Job Metrics (from database)

```sql
-- Success rate
SELECT
  status,
  COUNT(*) as count,
  AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration_sec
FROM job
WHERE type = 'mock_embedding'
GROUP BY status;
```

---

## 🐛 Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Job stuck in "pending" | Worker not running | `docker compose up -d worker` |
| Job fails with "Connection refused" | Qdrant not running | `docker compose up -d qdrant` |
| "Collection not found" | Collection creation failed | Check worker logs for errors |
| "Invalid point ID" | Using hex string instead of UUID | Ensure `point_id_for()` returns UUID |
| Slow search | Large collection, no indexes | Tune HNSW parameters, add payload indexes |

See [Troubleshooting](qdrant-developer-guide.md#troubleshooting) for detailed solutions.

---

## 🤝 Contributing

### Adding Documentation

When adding new features:

1. Update **Developer Guide** with usage examples
2. Update **Microstep 0.8** with architecture details
3. Add tasks to **Production TODOs** if production work needed
4. Update **Migration Guide** if it affects the migration path

### Documentation Standards

- Use concrete examples (real commands, real code)
- Include expected output
- Add "Why?" explanations for design decisions
- Link related docs
- Keep quick reference concise

---

## 📞 Support

### Internal Resources

- **Slack**: #heimdex-engineering
- **Team Wiki**: [Heimdex Architecture](https://wiki.company.com/heimdex)
- **Runbook**: [On-Call Procedures](https://wiki.company.com/oncall)

### External Resources

- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Qdrant API Reference](https://qdrant.tech/documentation/api-reference/)
- [SentenceTransformers Docs](https://www.sbert.net/)
- [Dramatiq Documentation](https://dramatiq.io/)

---

## 📅 Documentation Versions

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-30 | Initial documentation for Microstep 0.8 |

---

## ✅ Checklist for New Developers

Before you start working with Qdrant:

- [ ] Read the [Developer Guide](qdrant-developer-guide.md) (30 min)
- [ ] Complete the [Quick Start](qdrant-developer-guide.md#quick-start-5-minutes) (5 min)
- [ ] Skim [Microstep 0.8](microstep-0.8-qdrant-integration.md) for architecture understanding (15 min)
- [ ] Review [Production TODOs](qdrant-production-todos.md) to see what's next (10 min)
- [ ] Run `test_e2e_qdrant.py` successfully (5 min)
- [ ] Create your first mock embedding via API (5 min)
- [ ] Query Qdrant directly to see your vector (5 min)

**Total time**: ~1.5 hours

---

**Need help?** Start with the [Developer Guide](qdrant-developer-guide.md) or ask in #heimdex-engineering.
