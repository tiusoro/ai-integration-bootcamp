### Part 2: Discovery Call — Using Your Day 14 Script
#### The Call (30 Minutes)

**You:** "Sarah, thanks for reaching out. Before I tell you what I can do, I want to understand what you're dealing with. What's the biggest pain point in your support operation right now?"

**Sarah:** "Our agents are drowning. 500 tickets a month, 4-hour average response time. We're spending 18,000/month on support salaries, and customer satisfaction is 72%. We need to hire 2 more agents, but that's another $8,000/month we can't afford."

**You:** "Got it. If you could wave a magic wand, what does 'fixed' look like in 3 months?"

**Sarah:** "Response time under 30 minutes. Satisfaction above 90%. And ideally, we don't need to hire those 2 agents — maybe even reduce the workload on the current team."

**You:** "That's exactly what I built for a SaaS CEO last month. Reduced response time from 4 hours to 15 minutes, cut support costs by 80%, and satisfaction went from 72% to 91%. Let me show you the live system."

[Share screen, open https://ai-bootcamp-api.onrender.com/docs]

**You:** "This is the API I built. Try the RAG endpoint — ask it 'What's the refund policy?' It answers from actual documents, with source citations. No hallucinations."

**Sarah:** "That's... actually impressive. How long to build something like this for us?"

**You:** "Two weeks for the core system. Five days for a working prototype you'll see in action. Here's how it breaks down:

* Days 1-2: RAG pipeline with your existing help docs
* Days 3-5: Chat interface with memory and streaming
* Days 6-10: Testing, deployment, documentation
* Days 11-14: Buffer for feedback and refinements"

**Sarah:** "And cost?"
**You:** "I estimate 20 hours at $150/hr = $3,000 total. That includes testing, documentation, and deployment to your infrastructure. Most freelancers quote 1,500 but don't include testing or deployment — which costs you $2,000 later in bug fixes."

**Sarah:** "That's reasonable. What about ongoing?"
You: "I offer a $500/month optimization retainer. I monitor performance, retrain the AI with new documents as you add them, and provide priority support. Most clients see an additional 10-15% improvement in months 2-3. Want to start with the build and decide on the retainer after you see results?"

**Sarah:** "Yes. Let's do the build. Can you start Monday?"

**You:** "I can. I'll send the scope document today for your review. Once you sign, I'll invoice 50% upfront ($1,500), and we kick off Monday. Sound good?"

**Sarah:** "Perfect."

##### Discovery Call Notes (Save This)
```markdown
# Discovery Call Notes — SupportFlow / Sarah Chen

## Date: [Today's Date]
## Attendees: Anthony Usoro, Sarah Chen (CEO, SupportFlow)

### Pain Points
1. 500 tickets/month, $18,000/month support costs
2. 4-hour average response time
3. 72% customer satisfaction
4. Need to hire 2 more agents ($8,000/month) but can't afford

### Goals (3 Months)
1. Response time &lt; 30 minutes
2. Satisfaction &gt; 90%
3. No additional hires, possibly reduce current workload

### Current Stack
- Python/FastAPI backend
- PostgreSQL database
- 8 support agents, 2 developers

### Budget
- $5,000-8,000 initial build
- Open to retainer after seeing results

### Timeline
- Start: Monday
- Prototype: Day 5
- Delivery: Day 14

### Next Steps
1. Send scope document today
2. Invoice 50% upfront ($1,500)
3. Kickoff call Monday 10 AM
4. Daily updates at 5 PM

### Proposed Solution
- AI support triage with RAG
- Cost guardrails (pre-flight estimation)
- Real-time dashboard
- Deployment to their Render account

### Upsell Seed Planted
- $500/month optimization retainer mentioned
- Client wants to see results first (good — let performance sell it)

```
