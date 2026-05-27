## The Onboarding Document

```markdown
# Contractor Onboarding — AI Integration Bootcamp Team

## Our Stack
- Python 3.11, FastAPI, Pydantic v2
- PostgreSQL + pgvector + async SQLAlchemy
- OpenAI API (GPT-4o, embeddings)
- Docker + Render
- Pytest + TestClient (100% coverage on critical paths)
- GitHub + GitHub Projects

## Our Standards
- [Link to endpoint standard]
- [Link to test standard]
- [Link to documentation standard]
- [Link to security checklist]

## Communication
- Daily async standup in Slack #dev-updates
- Urgent: DM me directly
- Non-urgent: GitHub issue or Slack thread
- Weekly sprint review: [Day] at [Time]

## Your First Task
[Link to GitHub issue]
- Budget: $[Amount]
- Due: [Date]
- Questions? Ask in Slack #dev-help

## My Expectations
- Ask questions early (not 2 hours before deadline)
- Test your code before submitting PR
- Write README-worthy documentation
- Communicate delays before they become problems
- Treat client projects like your own business

## Payment
- Invoicing: Weekly, net 7 days
- Method: [Wise/PayPal/Deel]
- First invoice: After first task delivery
```

#### Part 6: Quality Assurance Checklist

##### Before Client Delivery

**Contractor completes:**
- [ ] All acceptance criteria met
- [ ] Tests pass (pytest -v)
- [ ] Coverage > 80% (pytest --cov)
- [ ] Linting passes (ruff check .)
- [ ] Type checking passes (mypy)
- [ ] Manual test on staging (curl or Swagger UI)
- [ ] README updated (if API changed)

**You verify:**

- [ ] Architecture review (Layer 4)
- [ ] Security check (auth, input validation)
- [ ] Client-facing impact (will this break anything?)
- [ ] Cost check (new OpenAI calls? Budget impact?)
- [ ]  Staging demo (show client before production)
Client sees:
- [ ] Working feature on staging
- [ ] Clean demo (no errors, no debug output)
- [ ] Documentation they can reference
- [ ] Clear next steps

---

### Part 7: Pricing for Team Projects

##### The Margin Math
| Client Pays | Contractor Cost          | Your Time | Your Profit | Margin |
| ----------- | ------------------------ | --------- | ----------- | ------ |
| \$2,000     | \$800 (20 hrs × \$40)    | 5 hrs     | \$1,200     | 60%    |
| \$5,000     | \$2,000 (40 hrs × \$50)  | 10 hrs    | \$3,000     | 60%    |
| \$10,000    | \$4,000 (60 hrs × \$65)  | 15 hrs    | \$6,000     | 60%    |
| \$20,000    | \$7,500 (100 hrs × \$75) | 20 hrs    | \$12,500    | 63%    |

**Your rate for client:**  $150-200/hr (your expertise)
**Contractor rate:**  $40-75/hr (their execution)
**Your time:** Architecture, review, client management
**Margin:** 60-65%
**Why this works:** Clients pay for your expertise and your team's delivery. You capture the difference.

```markdown

Hi [Name],

For this project, I am proposing a team approach:

**Me (Anthony):** Architecture, client communication, quality review
**[Contractor Name]:** Implementation, testing, documentation
**Timeline:** 2 weeks (vs 4 weeks solo)
**Cost:** $5,000 (vs $7,500 solo — team efficiency)

**What you get:**
- Faster delivery (2 weeks vs 4)
- Same quality (I review every line)
- Lower cost (team efficiency)
- Ongoing support (retainer available)

**Next steps:**
1. Scope call (30 min)
2. Architecture plan (I deliver)
3. Development (2 weeks)
4. Review and deploy (3 days)

Worth a call this week?

— Anthony

```

