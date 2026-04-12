# DevPulse AI — Demo Guide

## 1. Running locally

**Prerequisites**

- Docker Desktop (running)
- Python 3.11
- A `.env` file copied from `.env.example` with all values filled in

**Start the stack**

```bash
docker-compose up
# or
make dev
```

Swagger UI: http://localhost:8000/docs

**Run migrations**

```bash
make migrate
# or
docker-compose exec api alembic upgrade head
```

---

## 2. Testing webhooks locally with ngrok

1. Install ngrok: https://ngrok.com/download
2. Start a tunnel:
   ```bash
   ngrok http 8000
   ```
3. Copy the `https://xxxx.ngrok.io` forwarding URL.
4. In your GitHub repo: **Settings → Webhooks → Add webhook**
   - **Payload URL**: `https://xxxx.ngrok.io/api/v1/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: value of `GITHUB_WEBHOOK_SECRET` from your `.env`
   - **Events**: select **Pull requests**
5. Click **Add webhook**. GitHub sends a `ping` event — the API responds with `{"message": "pong"}`.

---

## 3. End-to-end flow

**Step 1 — Sign in via GitHub OAuth**

Open in browser:
```
GET http://localhost:8000/api/v1/auth/github
```
You will be redirected to GitHub, then back to the frontend with a JWT token.

**Step 2 — Connect a repository**

```bash
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"github_repo_id": 123, "full_name": "owner/repo"}'
```

**Step 3 — Wait for indexing**

Poll until `index_status` is `"indexed"`:
```bash
curl http://localhost:8000/api/v1/repositories/{id} \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Step 4 — Open a PR on the connected GitHub repo**

Create or update a pull request on the repo you connected.

**Step 5 — Webhook fires automatically**

GitHub sends the `pull_request` event → the API queues a Celery task → the worker runs the full review pipeline (diff fetch → RAG → Claude → inline GitHub comments).

**Step 6 — Inline comments appear on the PR**

Open the PR on GitHub. AI review comments appear inline on the diff.

---

## 4. Manually triggering a review

```bash
curl -X POST http://localhost:8000/api/v1/repositories/{repo_id}/prs/{pr_number}/review \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

The API returns `202 Accepted` and queues the review task.

---

## 5. Verifying Bedrock is working

```bash
curl http://localhost:8000/api/v1/health
```

Look for `"bedrock": "ok"` in the response. If it shows `"bedrock": "error"`, check that `AWS_REGION`, `AWS_ACCESS_KEY_ID`, and `BEDROCK_EMBEDDING_MODEL_ID` are set correctly in `.env`.

---

## 6. Verifying the Celery worker is running

```bash
docker-compose logs worker --tail 20
```

Look for `ready` in the output. If the worker is not running, tasks will queue but never execute.

---

## Notes

- The `scripts/deploy.sh` script is copied to EC2 on every deploy. If you change it locally, the new version will be used on the next deploy — but the old cached version runs until then. After any `deploy.sh` change, trigger a manual deploy to refresh it.
- Rate limits are active in all environments: webhooks at 100 req/min per IP, OAuth callback at 10 req/min per IP, manual review trigger at 10 req/min per user.
