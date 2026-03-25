# intervals-mcp

A remote MCP server that exposes [Intervals.icu](https://intervals.icu) training data as tools for Claude.ai, deployed on Railway.

## Tools

### Activities

| Tool | Description |
|------|-------------|
| `get_recent_activities` | List activities from the last N days (default: 28) |
| `get_activity_detail` | Full activity detail including HR, pace, power, and cadence streams |
| `get_activity_intervals` | Detected interval/lap breakdown for a specific activity |
| `update_activity` | Update activity name, notes, RPE, or sport type |
| `update_activity_intervals` | Edit detected interval boundaries or labels |

### Fitness & Wellness

| Tool | Description |
|------|-------------|
| `get_fitness_metrics` | CTL (fitness), ATL (fatigue), TSB (form) for a date range |
| `get_wellness_entry` | Wellness snapshot for a single day (HRV, sleep, fatigue, weight) |
| `update_wellness_entry` | Log or update wellness data for a day |

### Athlete Profile

| Tool | Description |
|------|-------------|
| `get_athlete_profile` | FTP, heart rate zones, pace zones, and sport settings |

### Training Calendar

| Tool | Description |
|------|-------------|
| `get_calendar_events` | Planned workouts and races for a date range |
| `create_calendar_event` | Schedule a new workout on the calendar |
| `update_calendar_event` | Reschedule or modify a planned workout |
| `delete_calendar_event` | Remove a workout from the calendar |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `INTERVALS_API_KEY` | Your Intervals.icu API key (Settings → API) |
| `INTERVALS_ATHLETE_ID` | Your athlete ID from the Intervals.icu URL (e.g. `i12345`) |
| `MCP_AUTH_TOKEN` | Secret token to protect the `/sse` endpoint (recommended for production) |
| `PORT` | Port to listen on — set automatically by Railway |

## Local Setup

```bash
# 1. Clone the repo and enter the directory
git clone <repo-url>
cd intervals-mcp

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API key and athlete ID

# 5. Start the server
python server.py
```

The server will start on `http://localhost:8000`.

## Deploy to Railway

1. Push this repo to GitHub.
2. Create a new Railway project and connect the repo.
3. Set the environment variables in Railway's dashboard:
   - `INTERVALS_API_KEY`
   - `INTERVALS_ATHLETE_ID`
   - `MCP_AUTH_TOKEN` — generate with `openssl rand -hex 32`
4. Railway will detect the `Procfile` and deploy automatically.
5. Your server URL will be something like `https://intervals-mcp-production.up.railway.app`.

## Connect to Claude.ai

1. Go to **Claude.ai → Settings → Integrations → Add MCP Server**.
2. Enter your server URL with the `/sse` path and your auth token:
   ```
   https://<your-app>.railway.app/sse?token=<your-MCP_AUTH_TOKEN>
   ```
3. Save — Claude will now have access to your Intervals.icu training data.

## Finding Your Credentials

- **API Key**: Log in to Intervals.icu → Settings → scroll to the API section → copy your key.
- **Athlete ID**: Visible in the URL after logging in, e.g. `intervals.icu/athlete/i12345/...` → your ID is `i12345`.
