## Part 1: The Contractor Hiring Process
#### Where to Find Contractors
| Platform     | Best For                              | Rate Range  | My Experience                            |
| ------------ | ------------------------------------- | ----------- | ---------------------------------------- |
| **Upwork**   | Generalist developers, short projects | \$25-75/hr  | Good for first hires, high volume        |
| **Toptal**   | Vetted senior developers              | \$75-150/hr | Expensive but reliable, pre-screened     |
| **Arc.dev**  | Remote senior developers              | \$60-120/hr | Good for long-term, timezone matching    |
| **Gun.io**   | Freelance senior engineers            | \$80-140/hr | US-based, higher rates                   |
| **LinkedIn** | Direct outreach to specialists        | Variable    | Best for niche skills (pgvector, Stripe) |
| **GitHub**   | Open source contributors              | Variable    | Hire people who already use your stack   |


**My rule:** Start with Upwork for small projects ($500-1,000). If they deliver, offer ongoing work. If they don't, you've lost $500, not $5,000.

**The Vetting Process (3-Step Filter)**
Step 1: The Job Post (Filters out 80%)
Post a specific, technical job. Vague posts attract vague applicants.
#### Job: FastAPI + PostgreSQL API Endpoint

We need a developer to build a CRUD endpoint for a tenant management system.

**Requirements:**
- FastAPI + Pydantic v2
- PostgreSQL + async SQLAlchemy
- JWT authentication (PyJWT)
- Test with pytest + TestClient
- Deploy to Render (Docker)

**Deliverable:**
- POST /tenants endpoint
- GET /tenants/{id} endpoint
- 100% test coverage on both
- Swagger docs auto-generated

**Budget:** $500 fixed price
**Timeline:** 3 days

**To apply:**
1. Link to a FastAPI project on GitHub
2. Explain how you handle JWT token validation in 2 sentences
3. Tell me your rate for ongoing work (not this project)

**No agencies. Solo developers only.**

# Job: FastAPI + PostgreSQL API Endpoint

We need a developer to build a CRUD endpoint for a tenant management system.

**Requirements:**
- FastAPI + Pydantic v2
- PostgreSQL + async SQLAlchemy
- JWT authentication (PyJWT)
- Test with pytest + TestClient
- Deploy to Render (Docker)

**Deliverable:**
- POST /tenants endpoint
- GET /tenants/{id} endpoint
- 100% test coverage on both
- Swagger docs auto-generated

**Budget:** $500 fixed price
**Timeline:** 3 days

**To apply:**
1. Link to a FastAPI project on GitHub
2. Explain how you handle JWT token validation in 2 sentences
3. Tell me your rate for ongoing work (not this project)

**No agencies. Solo developers only.**

**Why this works:**
* Specific tech stack = only qualified people apply
* "Link to GitHub" = filters out people with no work to show
* "2 sentences" = tests reading comprehension and brevity
* "Rate for ongoing work" = you're hiring for long-term, not one project
* "No agencies" = avoids middlemen who markup 50%

---
**Step 2: The Test Project (Filters out 90% of remaining)**
Give the top 5 applicants a $200 test project.
## Test Project: Build a Simple RAG Endpoint

**Task:** Build a POST /documents/ingest endpoint that:
1. Accepts a JSON payload with {title, content}
2. Generates embeddings using OpenAI text-embedding-3-small
3. Stores in PostgreSQL + pgvector
4. Returns the document ID

**Requirements:**
- FastAPI + Pydantic
- PostgreSQL + pgvector
- Error handling for missing fields
- One test with TestClient
- README with setup instructions

**Budget:** $200
**Timeline:** 24 hours

**What I evaluate:**
- Code quality (not just "it works")
- Error handling (not just happy path)
- Test coverage (at least one meaningful test)
- Documentation (can I run it without asking questions?)
- Communication (do they ask clarifying questions or just guess?)

**Why $200:** Enough to filter out people who won't take it seriously. Not so much that you care if they fail.
**Red flags:**
* Delivers in 2 hours without questions = rushed, didn't think
* Delivers in 48 hours with no communication = poor time management
* No tests = doesn't care about quality
* No README = doesn't care about maintainability
* Code works but is messy = junior, needs mentoring
**Green flags:**
* Asks 1-2 clarifying questions = thoughtful
* Delivers in 20 hours with clean code = fast and careful
* Includes edge case handling = experienced
* README includes Docker setup = goes above and beyond

---
**Step 3: The Interview (Final filter)**
Call the top 2-3 candidates. 15 minutes.
**Your questions:**

"Walk me through your test project. What would you do differently with more time?" (Tests self-awareness)
"How do you handle a client who changes requirements mid-project?" (Tests scope creep defense)
"What's your process for learning a new API or library?" (Tests adaptability)
"Tell me about a bug that took you hours to fix. What did you learn?" (Tests humility + growth)

**What you're really evaluating:**

Do they communicate clearly?
Do they take ownership of problems?
Do they ask questions or make assumptions?
Would I trust them with a $3,000 client project?

**My hiring rate:** I interview 20, test 5, hire 1. That's a 5% hire rate. But my contractors stick around for 6+ months and deliver quality work.

---

**How to Pay Contractors**
| Model                 | When to Use                          | Pros                    | Cons                                    |
| --------------------- | ------------------------------------ | ----------------------- | --------------------------------------- |
| **Hourly**            | Ongoing work, scope changes          | Flexible for both sides | Harder to budget, risk of padding hours |
| **Fixed per project** | Well-defined deliverables            | Predictable cost        | Scope creep eats your margin            |
| **Monthly retainer**  | Dedicated contractor, 20-40 hrs/week | Predictable for both    | Requires steady workload                |
| **Revenue share**     | High-risk, high-reward projects      | Aligns incentives       | Complex to track and dispute            |

**My recommendation for first hire:**   
Fixed per project ($500-2,000) for the first 2-3 projects. If they deliver, switch to monthly retainer ($2,000-4,000/month for 20-40 hours).

**Payment terms:**
50% upfront, 50% on delivery (for fixed projects)
Weekly invoicing, net 7 days (for hourly/retainer)
Use Wise, PayPal, or Deel for international contractors
Always have a signed contract (template below)

---

