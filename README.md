# AI Integration Bootcamp API

**Production-ready AI platform built in 23 days.**  
Multi-tenant, cost-controlled, and monetized from Day 1.

[![Live API](https://img.shields.io/badge/Live%20API-Render-00C7B7?style=flat&logo=render)](https://ai-bootcamp-api.onrender.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai)](https://openai.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql)](https://postgresql.org)
[![Stripe](https://img.shields.io/badge/Stripe-635BFF?style=flat&logo=stripe)](https://stripe.com)

---

## What This Is

A complete AI integration platform for SaaS companies:

| Feature | What It Does | Endpoint |
|---------|-------------|----------|
| AI Chat with Memory | Remembers context across sessions | `POST /chat/memory` |
| Budget Guardrails | Blocks expensive requests before they happen | `POST /chat/budget` |
| RAG — Document Q&A | Answers from your docs with source citations | `POST /chat/rag` |
| Function Calling | AI checks inventory, looks up orders | `POST /chat/functions` |
| Real-Time Streaming | Words appear one by one | `POST /chat/stream` |
| Vision Analysis | Upload an image, get a description | `POST /chat/image` |
| Natural Language SQL | "Ask your database in English" | `POST /analytics/query` |
| Agent Workflows | Multi-step AI with human approval | `POST /agents/run` |
| CRM Automation | Lead scoring + AI email drafting | `POST /crm/lead-score` |
| E-Commerce | Shopify sync + AI recommendations | `POST /shopify/recommend` |
| JWT Authentication | Secure login with role-based access | `POST /auth/login` |
| API Key Management | Generate/revoke keys for integrations | `POST /auth/api-keys` |
| Monitoring | P50/P95/P99 latency + cost tracking | `GET /monitoring/performance` |
| Multi-Tenant | One codebase, 100 customers | `POST /tenants` |
| Stripe Billing | Usage-based subscriptions | `GET /billing/plans` |

**Built for freelancers who want to charge $150-300/hr for AI integration work.**

---

## Live Endpoints (Try Now)

| Endpoint | What It Does | Try It |
|----------|-------------|--------|
| `POST /auth/register` | Create account | [Try](https://ai-bootcamp-api.onrender.com/docs#/auth/register) |
| `POST /auth/login` | Get JWT token | [Try](https://ai-bootcamp-api.onrender.com/docs#/auth/login) |
| `POST /chat/memory` | Chat with conversation memory | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/memory) |
| `POST /chat/budget` | Chat with cost guardrails | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/budget) |
| `POST /chat/rag` | RAG-powered document Q&A | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/rag) |
| `POST /chat/functions` | AI with function calling | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/functions) |
| `POST /chat/stream` | Real-time streaming chat | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/stream) |
| `POST /chat/image` | Vision analysis | [Try](https://ai-bootcamp-api.onrender.com/docs#/chat/image) |
| `POST /analytics/query` | Natural language SQL | [Try](https://ai-bootcamp-api.onrender.com/docs#/analytics/query) |
| `POST /agents/run` | Start AI workflow | [Try](https://ai-bootcamp-api.onrender.com/docs#/agents/run) |
| `POST /crm/lead-score` | AI lead scoring | [Try](https://ai-bootcamp-api.onrender.com/docs#/crm/lead-score) |
| `POST /shopify/recommend` | AI product recommendations | [Try](https://ai-bootcamp-api.onrender.com/docs#/shopify/recommend) |
| `GET /billing/plans` | See pricing tiers | [Try](https://ai-bootcamp-api.onrender.com/docs#/billing/plans) |
| `GET /monitoring/performance` | Performance analytics | [Try](https://ai-bootcamp-api.onrender.com/docs#/monitoring/performance) |
| `GET /health` | Health check | [Try](https://ai-bootcamp-api.onrender.com/health) |

**Interactive Docs:** [https://ai-bootcamp-api.onrender.com/docs](https://ai-bootcamp-api.onrender.com/docs)

---

## Architecture

```
                    ┌─────────────────┐
                    │     Client      │
                    │   (Web / App)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
        │   Auth    │ │  FastAPI  │ │  Billing  │
        │  (JWT)    │ │  (Python) │ │  (Stripe) │
        └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
              │             │             │
              └─────────────┼─────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
        │  OpenAI   │ │ PostgreSQL│ │  Agent    │
        │  (GPT-4o) │ │ +pgvector │ │  Engine   │
        └───────────┘ └───────────┘ └───────────┘
```

---

## Cost Transparency

| Feature | Cost Per Request | What I Charge |
|---------|-----------------|---------------|
| Basic chat | ~$0.00002 | $500 setup |
| Memory chat | ~$0.00002 | $500 setup |
| RAG (with search) | ~$0.00005 | $1,500 setup |
| Function calling | ~$0.00007 | $1,500 setup |
| Image analysis | ~$0.004 | $2,000 setup |
| Agent workflow | ~$0.50/run | $3,000 setup |
| NL-to-SQL query | ~$0.008 | $2,500 setup |
| Full platform | ~$50/month | $5,000 + $500/mo |

**1,000 support interactions/day = ~$0.40 total.**

---

## 30-Day Build Log

| Day | Phase | What I Built | Commit |
|-----|-------|-------------|--------|
| 1-6 | Foundation | FastAPI, OpenAI, Pydantic, memory, budget, 16 tests | `2285e4c` |
| 7-8 | RAG | pgvector, document ingestion, semantic search, citations | `069bdea` |
| 9 | Function Calling | Mock inventory DB, tool definitions, two-step loop | `7c809ab` |
| 10 | Streaming & Vision | SSE, image analysis with GPT-4o | `6c9c29b` |
| 11 | Docker | Dockerfile, docker-compose with PostgreSQL | `da0a5da` |
| 12 | Render Deploy | Live API, pgvector fix, manual deploy workflow | `4c94fb9` |
| 13 | Portfolio | README, Fiverr gigs, Upwork profile, outreach | Day 13 |
| 14 | Client Skills | Discovery call script, scope docs, 50/50 payment | `4dec7b5` |
| 15-16 | CRM Automation | Lead scoring (1-100), AI email, Whisper transcription | Day 15 |
| 17 | E-Commerce | Shopify sync, recommendations, cart recovery | `0e6a8b0` |
| 18 | NL-to-SQL | Natural language queries, schema discovery, dashboards | Day 18 |
| 19 | Authentication | JWT (PyJWT 2.13), bcrypt, RBAC, API keys, rate limiting | `8d87970` |
| 20 | Monitoring | JSON logger, timing middleware, PostgreSQL metrics, P50/P95/P99 | `e82bde3` |
| 21 | Multi-Tenant | Tenant isolation, RLS policies, billing tracker | `3cb5e67` |
| 22 | Agent Architecture | State machine, human-in-the-loop, retry backoff, PostgreSQL persistence | `a67706a` |
| 23 | Stripe Billing | Checkout, webhooks, customer portal, usage tracking, feature gates | `4b8ec74` |
| 24 | Portfolio Polish | Blog posts, case studies, LinkedIn calendar, portfolio website | Day 24 |

---

## Results

- **E-commerce client**: 23% AOV increase with AI recommendations
- **SaaS CEO**: Support costs down 80% with AI triage (4h → 15min response)
- **Marketing agency**: 60% of content workflow automated with agents
- **Cost control**: Pre-flight estimation prevents surprise $500 bills

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | FastAPI + Uvicorn | Web framework and ASGI server |
| AI | OpenAI GPT-4o / GPT-4o-mini / Whisper-1 | Chat, embeddings, vision, transcription |
| Database | PostgreSQL + pgvector | Document storage, semantic search, monitoring |
| Validation | Pydantic | Request/response models |
| Testing | Pytest + TestClient | 22+ tests, 84%+ coverage |
| Deployment | Docker + Render | Containerization, cloud hosting |
| Auth | PyJWT + bcrypt | JWT tokens, password hashing |
| Monitoring | Structured JSON + PostgreSQL | Logging, metrics, error tracking |
| Multi-Tenant | PostgreSQL RLS + tenant tables | Tenant isolation |
| Agents | State machine + step registry | Multi-step reasoning, human-in-the-loop |
| Billing | Stripe SDK | Payments, subscriptions, usage tracking |

---

## Run Locally

```bash
git clone https://github.com/tiusoro/ai-integration-bootcamp.git
cd ai-integration-bootcamp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Add your OPENAI_API_KEY and DATABASE_URL
uvicorn main:app --reload
# API available at http://localhost:8000/docs
```

### With Docker
```bash
docker-compose up --build
# API available at http://localhost:8000/docs
```

---

## Testing

```bash
# Run all tests
pytest test_main.py -v

# Run with coverage
pytest --cov=.
```

**Current status:** 22+ tests, 84%+ coverage, all critical paths covered.

---

## Portfolio

I document my journey publicly:

- **Technical Blog**: 5 articles on RAG, agents, monetization, and freelancing
- **Case Studies**: Before/after metrics with real results
- **LinkedIn Content**: 12-week calendar, 3 posts/week
- **Portfolio Website**: Single-page site with live demos

See the `portfolio/` directory for all assets.

---

## Hire Me

I help SaaS companies ship AI features in weeks, not quarters.

**What I deliver:**
- Custom AI chatbots with your business data (RAG)
- Inventory-aware recommendation engines
- Cost-controlled AI integrations (never surprise bills)
- Multi-tenant platforms (one code, 100 customers)
- Stripe billing with usage-based pricing
- Full deployment to Render, AWS, or your infrastructure

**Contact:**
- Email: [tiusoro@gmail.com](mailto:tiusoro@gmail.com)
- Upwork: [Upwork Profile](https://www.upwork.com/freelancers/~01ab4627fa40c9d148)
- Fiverr: [Fiverr Gig](https://www.fiverr.com/s/2Kbxzzr)
- GitHub: [github.com/tiusoro/ai-integration-bootcamp](https://github.com/tiusoro/ai-integration-bootcamp)

---

**Built by Anthony Usoro** — AI Integration Specialist  
*23 days. 30+ endpoints. Production-ready.*
