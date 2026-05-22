# AI Integration Bootcamp API

**Production-ready AI API with conversation memory, RAG, cost tracking, and real-time streaming.**

Live demo: https://ai-bootcamp-api.onrender.com/docs

---

## What This API Does

### 1. AI Chat with Memory
Remembers conversation context across sessions. Ask "What is my name?" after telling it once — it knows.

```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/memory \
  -H "Content-Type: application/json" \
  -d '{"message":"My name is Anthony","user_id":"demo-user"}'
  ```
#### Screenshot:
![Screenshot](images/screenshot1.png)



### 2. Budget Guardrails
Blocks expensive requests before they happen. Set a $0.001 limit — get a 402 error if the request would cost more.

```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/budget \
  -H "Content-Type: application/json" \
  -d '{"message":"Write a 500-word essay on quantum ","user_id":"budget-test","max_budget_usd":0.001}'
```
##### Returns: Error:: "Reduce max_tokens or increase budget"
#### Screenshot:
![Screenshot](images/screenshot2.png)




### 3. RAG — Answers From Your Documents
Upload documents. Ask questions. Get cited answers. If no relevant document exists, it refuses instead of hallucinating.
```bash
curl -X POST https://ai-bootcamp-api.onrender.com/documents/ingest \
  -d '{"title":"Refund Policy","content":"Full refunds within 30 days..."}'
  ```

```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/rag \
  -d '{"message":"What is the refund policy?","user_id":"rag-test"}'

```
##### Returns: "Full refunds within 30 days (Source: Refund Policy)"
#### Screenshot:
![Screenshot](images/screenshot3.png)




### 4. Function Calling — AI Takes Actions
AI checks inventory, looks up orders, and presents results naturally.
```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/functions \
  -H "Content-Type: application/json" \
  -d '{"message": "Do you have the iPhone 15 in stock?", "user_id": "func-test-1"}'
```

##### Returns: Should return no of units available, its price and ask if you want to buy.
#### Screenshot:
![Screenshot](images/screenshot4.png)




### 5. Real-Time Streaming

Words appear one by one instead of waiting for the full response.
```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Count from 1 to 5", "model": "gpt-4o-mini"}'
```

##### Returns: data: {"token":"1"} data: {"token":"2"} ...
#### Screenshot:
![Screenshot](images/screenshot5.png)





### 6. Vision Analysis
Upload an image URL. Get a detailed description.
```bash
curl -X POST https://ai-bootcamp-api.onrender.com/chat/image \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://images.unsplash.com/photo-1579353977828-2a4eab540b9a?w=800", "question": "Describe this image in one sentence"}'
```
##### Returns: data: Describes the image in the image url ...
#### Screenshot:
![Screenshot](images/screenshot6.png)



### Tech Stack
| Layer      | Technology                       |
| ---------- | -------------------------------- |
| Backend    | FastAPI + Uvicorn                |
| AI         | OpenAI GPT-4o / GPT-4o-mini      |
| Database   | PostgreSQL + pgvector            |
| Deployment | Docker + Render                  |
| Testing    | Pytest (22+ tests, 84% coverage) |

---

### Cost Transparency
| Feature                            | Cost Per Request  |
| ---------------------------------- | ----------------- |
| Basic chat                         | ~\$0.00002        |
| Memory chat                        | ~\$0.00002        |
| RAG (with search)                  | ~\$0.00005        |
| Function calling                   | ~\$0.00007        |
| Image analysis                     | ~\$0.004          |
| **1,000 support interactions/day** | **~\$0.40 total** |


---

### Run Locally
```bash
git clone https://github.com/tiusoro/ai-integration-bootcamp.git
cd ai-integration-bootcamp
docker-compose up --build
# API available at http://localhost:8000/docs
```


#### Hire Me
I build production AI APIs for e-commerce, CRM, and SaaS platforms.
What I deliver:
- Custom AI chatbots with your business data (RAG)
- Inventory-aware recommendation engines
- Cost-controlled AI integrations (never surprise bills)
- Full deployment to Render, AWS, or your infrastructure

Contact: [tiusoro@gmail.com] | [[Upwork profile](https://www.upwork.com/freelancers/~01ab4627fa40c9d148)] | [[Fiverr gig](https://www.fiverr.com/tiusoro/buying?source=avatar_menu_profile)]

---



