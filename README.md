# 🔍 Job Research Agent

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.6-green)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/MCP-FastMCP-purple)](https://github.com/modelcontextprotocol/python-sdk)
[![Evals](https://img.shields.io/badge/Evals-5%20cases%206%20graders-orange)](evals/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock-yellow)](https://aws.amazon.com/bedrock/)
[![LangSmith](https://img.shields.io/badge/LangSmith-Traced-orange)](https://smith.langchain.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Paste a job URL. Get an honest match score, specific skill gaps, and roles that actually suit you, saved automatically to a local database.

---

## What it does

You paste your resume once at startup. Then you talk to it like a career coach that actually knows your background.

It scrapes the job listing, cross-references it against your resume, and gives you back a structured breakdown - match score, what you're missing, a one-sentence pitch, and smarter alternatives to consider. Every analysis gets saved to SQLite so you can review your research later.

It remembers the full conversation. You can ask follow-ups, compare two roles, or ask what you should apply to instead.

---

## Demo

A typical session:

```
$ uv run python client.py

Paste your resume below. Type END on a new line when done:

Ahmed Gamal
AI Engineer | LangGraph / LangChain / Agentic AI Systems
...
END

Agent ready. Type 'exit', 'quit' or 'end' to end the session.

You: https://jobs.lever.co/tryjeeves/03f901fc-7a43-4fae-9916-3b287a4bdff6

Agent: Strong alignment with your background. Your LangGraph
       and eval infrastructure experience directly maps to what
       they're looking for. Main gap is formal ML research...

==================================================
Match Score: 72/100

Top Gaps:
  • Formal ML research background - consider Arxiv paper reading
  • Distributed systems at scale - not demonstrated in portfolio
  • Senior-level ownership - the role expects 5+ years

Pitch:
  Strong agentic systems builder with production eval
  infrastructure - unusual combination for this stage.

Recommended Roles:
  • AI Engineer at early-stage AI startups
  • Solutions Engineer at LLM platform companies
  • MLOps Engineer at companies scaling LLM products
==================================================

You: what was my match score for that role?
Agent: 72/100 for the Senior AI Engineer role.

You: find me something more realistic to apply to right now
Agent: Given your current profile, here's what I'd target...
```

Scores and text vary between runs - this is a transcript, not a fixture.

---

## How to use it

**Step 1 - Start the search server**

Terminal 1:

```bash
uv run python servers/search_server.py
```

**Step 2 - Start the client**

Terminal 2:

```bash
uv run python client.py
```

The client starts the notes server itself as a stdio subprocess, so only the search server needs its own terminal.

**Step 3 - Paste your resume**

When prompted, paste your full resume directly into the terminal. It can be any format - plain text works best. When you're done, type `END` on a new line and press Enter.

```
Paste your resume below. Type END on a new line when done:

[paste your resume here]
[it can be as long as you want]
[blank lines are fine]
END
```

> ⚠️ Your resume is never written to disk or committed to the repo. It stays in memory for the duration of your session, and is only forwarded to LangSmith if you enable tracing.

**Step 4 - Start researching**

Paste any job URL and the agent handles the rest:

```
You: https://jobs.lever.co/glsllc/c1191357-09ab-4707-855b-a99c5cb99ac1
You: what are my top 3 gaps for this role?
You: compare this to the last job I sent you
You: what should I actually be applying to right now?
```

Type `exit`, `quit`, or `end` to end the session.

---

## Architecture

Two MCP servers, one LangGraph agent, one session.

```
┌──────────────────────────────────────────────┐
│                  client.py                   │
│              LangGraph Agent                 │
│          (Claude Haiku via Bedrock)          │
│          InMemorySaver checkpointer          │
└──────────────┬───────────────┬───────────────┘
               │               │
      stdio    │               │  streamable HTTP
               ▼               ▼
┌─────────────────────┐  ┌─────────────────────┐
│    notes_server     │  │    search_server    │
│                     │  │                     │
│   save_research     │  │ scrape_job_listing  │
│   get_all_research  │  │ extract_skills      │
│                     │  │                     │
│       SQLite        │  │    Deployed on      │
│       (local)       │  │      Render         │
└─────────────────────┘  └─────────────────────┘
```

The agent decides which tools to call and in what order. You don't script the sequence - it reasons through the task.

---

## Setup

**Requirements:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/), AWS account with Bedrock access

```bash
git clone https://github.com/0xSnow-1/MCP-Project.git
cd MCP-Project
uv sync
cp .env.example .env
# fill in your credentials
```

Not using `uv`? `pip install -r requirements.txt` installs the same runtime dependencies.

Your `.env` mirrors `.env.example`:

```bash
# .env
BEDROCK_MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=your_token_here

# Search MCP server: local by default, or your Render URL
SEARCH_SERVER_URL=http://127.0.0.1:8000/mcp

# Optional - LangSmith tracing, flip to true once LANGSMITH_API_KEY is set
LANGSMITH_API_KEY=your_key_here
LANGSMITH_TRACING=false
```

`AWS_BEARER_TOKEN_BEDROCK` is the only required variable.
The `LANGSMITH_*` pair is optional, and `SEARCH_SERVER_URL` only needs changing if you point the agent at a deployed search server.

---

## Run the search server in Docker

The search server also ships as a container, which is how it is deployed on Render:

```bash
docker build -f DockerFile -t mcp-search-server .
docker run -p 8000:8000 mcp-search-server
```

The image listens on `0.0.0.0` and honours the `PORT` environment variable, so it works as-is on Render or any other container host.
The client and the notes server stay local and are not containerised.

---

## Evals

```bash
uv run python evals/run_evals.py
```

Tests run against a synthetic resume in `evals/fixtures/` - your personal resume is never committed to the repo.

> ⚠️ Two prerequisites: `servers/search_server.py` must be listening on port 8000, and Bedrock credentials must be set in `.env`.

```
Recorded baseline from the last full run: 5/5 passed (100.0%)  |  threshold: 80%

Graders:
  ✓ no_error          - agent completed without crashing
  ✓ tools_called      - correct tools were invoked
  ✓ structured_valid  - Pydantic output fields are populated and typed correctly
  ✓ score_range       - match scores are sensible for the role type
  ✓ gaps_count        - minimum gap count returned
  ✓ llm_judge         - quality scored by Claude against rubric
```

Fixture cases point at live third-party job listings, so a case can fail because a posting was taken down rather than because the agent regressed.
Check the listing still resolves before treating a failure as a regression.

---

## LangSmith tracing

Every run is traced automatically when `LANGSMITH_TRACING=true`.
You can inspect tool calls, token usage, and latency in your LangSmith dashboard.

---

## Stack

| Layer | Tool |
|---|---|
| Agent orchestration | LangGraph |
| MCP servers | FastMCP |
| LLM | Claude Haiku via AWS Bedrock |
| MCP client | langchain-mcp-adapters |
| Structured output | Pydantic + `with_structured_output` |
| Session memory | LangGraph InMemorySaver |
| Persistence | SQLite via notes server |
| Observability | LangSmith |
| Search server hosting | Render |

---

## Project structure

```
├── client.py                  # entry point - agent + resume input + chat loop
├── servers/
│   ├── search_server.py       # scrapes jobs, extracts skills (streamable HTTP)
│   └── notes_server.py        # saves research to SQLite (stdio subprocess)
├── evals/
│   ├── golden_dataset.py      # 5 test cases
│   ├── graders.py             # 6 grader functions including LLM-as-judge
│   ├── run_evals.py           # eval runner
│   └── fixtures/
│       └── test_resume.txt    # synthetic resume for testing only
├── data/                      # SQLite database (git-ignored, created on first save)
├── DockerFile                 # container image for the search server
├── .env.example
├── requirements.txt
├── uv.lock
├── LICENSE
└── pyproject.toml
```

---

## License

MIT - see [LICENSE](LICENSE).

---

## Contact

**Ahmed Gamal** · GitHub: [0xSnow-1](https://github.com/0xSnow-1) · X: [_0xSnowEth](https://x.com/_0xSnowEth) · LinkedIn: [in/ahmed-gamal-363b47307](https://www.linkedin.com/in/ahmed-gamal-363b47307) · Website: [0xsnow-1.github.io](https://0xsnow-1.github.io) · Email: [0xahmed.gamal@gmail.com](mailto:0xahmed.gamal@gmail.com)
