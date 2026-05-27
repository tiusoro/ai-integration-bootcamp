## Part 2: Code Review Workflow
#### The 

You hire a contractor. They write code. You merge it. Client finds a bug. You fix it at 2 AM. You swear never to hire again.
**The solution:**  A review process that catches issues before they reach production.

---

#### The 4-Layer Review System
┌─────────────────────────────────────────┐
│  Layer 1: Automated (CI/CD)             │
│  - Linting (ruff, black)                │
│  - Type checking (mypy)                 │
│  - Tests (pytest, 80%+ coverage)        │
│  - Security scan (bandit)               │
├─────────────────────────────────────────┤
│  Layer 2: Self-Review (Contractor)      │
│  - PR description with checklist        │
│  - Screenshots/logs of working code     | 
│  - Test results pasted in PR            │
├─────────────────────────────────────────┤
│  Layer 3: Peer Review (Other contractor)│
│  - Code readability                     │
│  - Edge cases                           │
│  - Performance concerns                 │
├─────────────────────────────────────────┤
│  Layer 4: Your Review (Architecture)    │
│  - API design consistency               │
│  - Database schema impact               │
│  - Security and auth                    │
│  - Client-facing changes                │
└─────────────────────────────────────────┘
**Your time investment:** Layer 4 only. 10-15 minutes per PR. The other layers are automated or delegated.

---

#### Layer 1: Automated CI/CD

Add to your GitHub repo:
```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install ruff black mypy pytest pytest-cov bandit
      
      - name: Lint
        run: ruff check .
      
      - name: Format check
        run: black --check .
      
      - name: Type check
        run: mypy .
      
      - name: Security scan
        run: bandit -r .
      
      - name: Test with coverage
        run: pytest --cov=. --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

```
**Why this matters:** Catches 70% of issues before a human reviews. Style, types, security, coverage — all automated.

---
#### Layer 2: Self-Review Checklist

Contractor must complete before requesting your review:
## PR Checklist

- [ ] Code follows project style (ruff + black pass)
- [ ] All tests pass (pytest)
- [ ] New code has tests (coverage &gt; 80%)
- [ ] Type hints added (mypy passes)
- [ ] API changes documented in README
- [ ] Error handling covers edge cases
- [ ] No hardcoded secrets or API keys
- [ ] Database migrations included (if schema changed)
- [ ] Screenshot or curl output showing it works
- [ ] PR description explains what and why

## Testing Evidence

```bash
# Paste output of: pytest -v
[... test output here ...]
```
#### Screenshots
[Attach screenshot of Swagger docs or API response]


**Why this matters:** Contractors catch their own mistakes when forced to document them. And you review faster when you have context.

---

### Layer 3: Peer Review (Optional, then mandatory)

Once you have 2+ contractors, they review each other's code.

**Peer review guidelines:**
- "Does this make sense to me?" (readability)
- "What happens if...?" (edge cases)
- "Could this be simpler?" (complexity)
- "Is this consistent with the rest of the codebase?" (style)

**Not the peer's job:**
- Architecture decisions (that's yours)
- API design (that's yours)
- Database schema changes (that's yours)

**Incentive:** Contractors who give good reviews get priority on new projects. Contractors who ignore reviews get warned, then fired.

---

### Layer 4: Your Review (The Gate)

You review only what matters:

| Check | What to Look For | Time |
|-------|-----------------|------|
| **API design** | Consistent with existing endpoints? RESTful? | 2 min |
| **Database impact** | New migrations? Index needed? RLS policy? | 3 min |
| **Security** | Auth decorators? Input validation? SQL injection risk? | 3 min |
| **Client-facing** | Will this break existing clients? Versioning needed? | 2 min |
| **Performance** | N+1 queries? Missing indexes? Unnecessary API calls? | 3 min |
| **Cost** | New OpenAI calls? Token estimation? Budget impact? | 2 min |

**Total: 15 minutes per PR.** Not 2 hours. Not line-by-line.

**Your review comment template:**
```markdown
## ✅ Approved
- Clean API design, consistent with existing endpoints
- Good error handling on edge cases
- Tests cover happy path and 2 error cases

## ⚠️ Suggestions (non-blocking)
- Consider adding an index on `tenant_id` for performance
- Document the new endpoint in README.md

## 🚀 Next Steps
- Merge when ready
- Deploy to staging first, verify with client

**Why this matters:** Contractors learn from specific feedback. "Add an index" teaches them something. "LGTM" teaches them nothing.