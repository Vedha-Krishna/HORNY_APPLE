# PettyCrimeSG — Project Documentation

**Hackathon project** | Theme E: AI-native infrastructure for agent systems  
**Stack:** Python · FastAPI · LangGraph · OpenAI · Supabase · Next.js · Leaflet

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Folder Structure](#2-folder-structure)
3. [How It All Fits Together](#3-how-it-all-fits-together)
4. [Step-by-Step Data Flow](#4-step-by-step-data-flow)
5. [Backend](#5-backend)
   - 5.1 [API Server (main.py)](#51-api-server-mainpy)
   - 5.2 [Crawler Agent](#52-crawler-agent)
   - 5.3 [Cleaner Agent](#53-cleaner-agent)
   - 5.4 [Classifier Agent](#54-classifier-agent)
   - 5.5 [Decision Agent](#55-decision-agent)
   - 5.6 [LangGraph Pipeline](#56-langgraph-pipeline)
   - 5.7 [Multimodal Verifier](#57-multimodal-verifier)
6. [Database](#6-database)
   - 6.1 [Supabase Client](#61-supabase-client)
   - 6.2 [Core Incidents Table](#62-core-incidents-table)
   - 6.3 [Incident Queue Table](#63-incident-queue-table)
   - 6.4 [Incident Analysis Table](#64-incident-analysis-table)
   - 6.5 [Incident Decisions Table](#65-incident-decisions-table)
   - 6.6 [Incident Locations Table](#66-incident-locations-table)
   - 6.7 [Incident Agent Messages Table](#67-incident-agent-messages-table)
   - 6.8 [Agent Feedback Table](#68-agent-feedback-table)
   - 6.9 [Incident Full View](#69-incident-full-view)
   - 6.10 [Deprecated: Mock Official Reports](#610-deprecated-mock-official-reports-table)
7. [API Reference](#7-api-reference)
8. [Frontend](#8-frontend)
   - 8.1 [App Shell](#81-app-shell)
   - 8.2 [Store (Zustand)](#82-store-zustand)
   - 8.3 [Map View](#83-map-view)
   - 8.4 [Incident Detail Panel](#84-incident-detail-panel)
   - 8.5 [Severity Sidebar](#85-severity-sidebar)
   - 8.6 [Mock Data](#86-mock-data)
9. [Data Schemas](#9-data-schemas)
10. [Agent Feedback Loop](#10-agent-feedback-loop)
11. [Environment Variables](#11-environment-variables)
12. [Setup and Running](#12-setup-and-running)
13. [Known Issues](#13-known-issues)
14. [Ethics Rules](#14-ethics-rules)

---

## 1. What This Project Does

People post about petty crimes (theft, vandalism, harassment) on Reddit all the time, but those posts are messy and hard to act on. PettyCrimeSG reads those posts, figures out which ones are likely real incidents, and puts them on an interactive map of Singapore.

**The pipeline in plain English:**

1. Pull posts from Reddit (or load from a test JSON file)
2. Throw out jokes, opinions, vague warnings, and duplicates
3. Extract the key details: what happened, where, and when
4. Score each post — how likely is it to be real? How serious?
5. Decide: publish it, send it back for more info, or reject it
6. Save approved incidents to a database
7. Show them as pins on a live Singapore map

**Crime types the system handles:**

| Type | What it covers |
|---|---|
| `theft` | Stealing, pickpocketing, snatch theft |
| `attempted_theft` | Tried to steal but failed |
| `vandalism` | Graffiti, broken property |
| `suspicious_activity` | Loitering, prowling, anything that feels off |
| `harassment` | Threats, intimidation, being followed |

**Posts that always get rejected:**

- Jokes, memes, satire
- Opinions ("Singapore crime is so bad these days")
- Vague warnings ("everyone be careful!")
- Non-crime complaints (MRT delays, bad service)
- Anything already covered in official news
- Duplicate posts about the same incident

---

## 2. Folder Structure

```
HORNY_APPLE/
├── .env.example                    # Copy this to .env and fill in your keys
├── README.md                       # Quick-start guide
├── graph.png                       # Picture of the LangGraph pipeline
│
├── backend/
│   ├── main.py                     # All API routes live here
│   ├── orchestration.py            # Run the pipeline from the command line
│   ├── requirements.txt            # Python packages needed
│   │
│   ├── agents/
│   │   ├── cleaner/
│   │   │   └── cleaner_agent.py    # Rewrites messy posts into clean summaries
│   │   │
│   │   ├── crawler/
│   │   │   ├── deterministic.py    # Keyword-based post filter (main crawler)
│   │   │   ├── reddit_crawler.py   # Pulls live posts from Reddit
│   │   │   ├── multimodal.py       # Checks if images/videos support a post
│   │   │   ├── orchestration6_DB.py  # Full LangGraph pipeline (saves to DB)
│   │   │   └── orchestration7.py     # Improved version with better categories
│   │   │
│   │   └── langchain/
│   │       ├── state.py            # Defines what data flows through the graph
│   │       ├── cleaner.py          # Cleaner step inside the graph
│   │       ├── classifier.py       # Classifier step inside the graph
│   │       ├── decider.py          # Decision step — also saves to Supabase
│   │       └── workflow.py         # Assembles all steps into a graph
│   │
│   └── db/
│       ├── supabase.py             # Sets up the database connection
│       ├── incidents.py            # Read/write incidents table
│       ├── feedback.py             # Read/write agent feedback table
│       └── mock_reports.py         # Read/write mock official reports table
│
├── data/
│   ├── category_keywords.json      # Keywords for each crime type
│   ├── incident_drafts.json        # Output from the crawler (auto-generated)
│   ├── mock_posts.json             # 10 test posts for pipeline testing
│   └── sample_posts.json           # 15+ test posts for API testing
│
├── docs/
│   └── DOCUMENTATION.md            # This file
│
└── frontend/
    ├── next.config.ts
    ├── package.json
    ├── public/
    │   └── data/
    │       └── sg-planning-areas.geojson   # Singapore map area polygons
    └── src/
        ├── app/
        │   ├── globals.css
        │   ├── layout.tsx
        │   └── page.tsx
        └── components/
            └── safewatch/
                ├── Dashboard.tsx           # Root layout
                ├── Header.tsx              # Top nav bar
                ├── MapView.tsx             # Map with pins
                ├── IncidentDetailPanel.tsx # Slide-in panel for one incident
                ├── SeveritySidebar.tsx     # Filterable incident list
                ├── mockData.ts             # 55 fake incidents for testing
                └── store.ts                # Global state (Zustand)
```

---

## 3. How It All Fits Together

```
DATA SOURCES
  Reddit r/singapore (live)  |  Mock JSON files (for testing)
              │
              ▼
        CRAWLER AGENT
  Filters posts by keywords, rejects bad ones,
  extracts location and time
              │
              ▼
        CLEANER AGENT
  GPT-4o-mini rewrites the post as a clean 1–2 sentence summary.
  Fills in proper location name, coordinates, and timestamp.
              │
              ▼
      CLASSIFIER AGENT
  Picks the crime category using vector similarity.
  Scores the post for authenticity and severity.
              │
              ▼
       DECISION AGENT
  Says: publish / needs_revision / reject.
  Saves the result to Supabase.
              │
              ▼
      SUPABASE DATABASE
  Stores all incidents with their status and scores.
              │
  GET /api/db/incidents?published_only=true
              │
              ▼
      FASTAPI BACKEND
  Serves incidents to the frontend.
              │
              ▼
     NEXT.JS FRONTEND
  Shows incidents as coloured pins on a Singapore map.
```

**Feedback runs backwards** when an agent can't finish its job:

```
Decision Agent → Classifier  (re-score this incident)
Classifier     → Crawler     (find more details about location)
```

---

## 4. Step-by-Step Data Flow

### Step 1 — Post comes in

A post enters the system as a simple object:

```json
{
  "post_id": "mock_001",
  "platform": "mock_forum",
  "source_url": "mock://community/mock_001",
  "timestamp": "2026-04-18T22:15:00+08:00",
  "text": "My bicycle was stolen outside Bedok MRT last night."
}
```

### Step 2 — Crawler filters it (`deterministic.py`)

1. Strips `@mentions` and phone numbers from the text
2. Checks rejection rules — throws out jokes, vague posts, opinions
3. Scores the post against each crime category using keyword matches
4. Checks for duplicates against posts already seen
5. Finds a Singapore place name in the text (matches against 28 names)
6. Finds a time phrase using regex

Output: an incident draft with `candidate: true/false`, `category`, `location_text`, and `lat/lng` set to `null` (geocoding happens later).

### Step 3 — Cleaner rewrites it (`cleaner_agent.py`)

Runs on posts stored in Supabase with `status=queued`:

1. Locks the row so no other agent touches it at the same time
2. Sends the raw text to GPT-4o-mini with a prompt to produce a clean summary
3. GPT returns: `cleaned_content`, `location_text`, `latitude`, `longitude`, `normalized_time`
4. Saves results back to Supabase

### Step 4 — Classifier scores it

1. GPT-4o-mini extracts `location`, `time`, `action` as structured fields
2. The text is embedded using `text-embedding-3-small`
3. Cosine similarity against category prototypes picks the crime type
4. A 19-feature scoring rubric gives an `authenticity_score` and `severity`

**The rubric has 4 parts:**

| Part | Weight | What it checks |
|---|---|---|
| Detail | 25% | Specific location, time, action, person, outcome |
| Evidence | 25% | First-hand, clear description, media, links, follow-up |
| Consistency | 15% | No contradictions, fields align, no exaggeration |
| Risk flags | −5% | Rumour language, missing location/time, ragebait |

```
authenticity_score = (0.25 × detail) + (0.25 × evidence) + (0.15 × consistency) − (0.05 × risk)
severity           = (0.4 × detail) + (0.3 × evidence) + (0.3 × risk)
```

### Step 5 — Decision Agent decides

1. If `authenticity_score >= 0.7` and `category` is known → `publish`
2. Otherwise → `needs_revision` (up to 2 retries, then forced reject)
3. **Saves the result to Supabase** — status becomes `published`, `rejected`, or `needs_revision`

### Step 6 — Frontend shows it

Published incidents are served by `GET /api/db/incidents?published_only=true`. The Next.js map matches each incident's `location.area` to a Singapore planning area polygon and draws a coloured pin.

---

## 5. Backend

### 5.1 API Server (`main.py`)

Start the server from the project root:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive docs: `http://127.0.0.1:8000/docs`

**All routes:**

| Method | Path | What it does |
|---|---|---|
| `GET` | `/` | API info and database status |
| `GET` | `/health` | Health check |
| `GET` | `/api/incidents` | Runs the crawler on a local JSON file (no database needed) |
| `GET` | `/api/db/incidents` | Gets incidents from Supabase |
| `GET` | `/api/db/incidents/{id}` | Gets one incident by UUID |
| `GET` | `/api/db/incidents/{id}/feedback` | Gets agent feedback history for one incident |
| `POST` | `/api/db/incidents` | Saves a new incident to the database |
| `POST` | `/api/db/incidents/{id}/feedback` | Sends agent-to-agent feedback |
| `GET` | `/api/db/official-reports` | Gets all mock official reports |
| `POST` | `/api/pipeline/run` | Runs the LangGraph pipeline on a list of posts |

**Query params for `GET /api/db/incidents`:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | null | Filter by status (`published`, `rejected`, etc.) |
| `published_only` | bool | false | Shortcut — return only published incidents |
| `limit` | int | 50 | Max rows (1–500) |

---

### 5.2 Crawler Agent

Two versions exist:

#### `deterministic.py` — Keyword-based (main crawler)

Reads posts from `data/sample_posts.json`. Uses keyword lists and regex — no AI calls.

**Key lists:**

| Name | Purpose |
|---|---|
| `CATEGORY_RULES` | Keywords for each of the 5 crime types |
| `REJECTION_RULES` | Rules for jokes, vague posts, opinions, complaints, news |
| `LOCATION_HINTS` | 28 Singapore place names |
| `TIME_PATTERNS` | 4 regex patterns for time phrases |

**Score formula:**

```
score = min(1.0, 0.35 + (0.25 × keyword_matches))
```

1 match → 0.60, 2 matches → 0.85. Coordinates are always `None` here — the Cleaner handles geocoding.

**Main functions:**

| Function | What it does |
|---|---|
| `process_post(post, seen)` | Runs the full pipeline for one post |
| `process_posts(posts)` | Runs it for a list of posts |
| `load_posts(path)` | Reads and validates a JSON file |

**Run it directly:**

```bash
python -m backend.agents.crawler.deterministic --input data/sample_posts.json --output data/incident_drafts.json
```

#### `reddit_crawler.py` — Live Reddit scraper

Pulls posts from `r/singapore` using Reddit's public JSON API (no login needed). Uses a HuggingFace zero-shot classifier to filter for relevant posts.

**Key settings:**

| Setting | Value | Purpose |
|---|---|---|
| `DEFAULT_SUBREDDIT` | `"singapore"` | Target subreddit |
| `RELEVANCE_THRESHOLD` | `0.25` | Minimum confidence to keep a post |
| `DEFAULT_REQUEST_DELAY` | `0.35s` | Polite gap between requests |

**Deduplication:** Remembers the last seen `source_item_id` so it only pulls new posts each run.

**Run it:**

```bash
# Test — print matches without saving
python -m backend.agents.crawler.reddit_crawler --stats --pretty

# Save to Supabase
python -m backend.agents.crawler.reddit_crawler --upload --stats

# Pull 100 newest posts from scratch
python -m backend.agents.crawler.reddit_crawler --backfill --upload
```

---

### 5.3 Cleaner Agent

**File:** `backend/agents/cleaner/cleaner_agent.py`

Rewrites raw community text into a clean, formal summary. Runs one incident at a time.

**What GPT-4o-mini produces:**

| Field | Type | Description |
|---|---|---|
| `cleaned_content` | string | Formal 1–2 sentence summary, no slang or handles |
| `topic_bucket` | string | `singapore_news`, `singapore_viral`, or `other` |
| `location_text` | string? | Normalised place name (e.g. "Ang Mo Kio MRT") |
| `latitude` | float? | Approx GPS latitude (Singapore: 1.1–1.5) |
| `longitude` | float? | Approx GPS longitude (Singapore: 103.6–104.1) |
| `normalized_time` | string? | ISO-8601 timestamp in Singapore time |

**Row locking:** Before processing, it sets the row to `in_progress`. If another process already locked it, it skips. On success it resets to `queued`. On failure it sets `failed` and logs the error.

**Run it:**

```bash
python -m backend.agents.cleaner.cleaner_agent
```

---

### 5.4 Classifier Agent

Two versions:

#### `langchain/classifier.py` — Simple version (used by the main LangGraph graph)

Uses hardcoded keyword scores. Known issue: vandalism (0.64) and harassment (0.66) scores fall below the 0.70 publish threshold, so those categories never get published through this path.

#### `orchestration6_DB.py` / `orchestration7.py` — Full version

1. GPT extracts `location`, `time`, `action` as JSON
2. Text is embedded with `text-embedding-3-small`
3. Cosine similarity picks the crime category
4. A 19-feature rubric computes `authenticity_score` and `severity`

`orchestration7.py` has more category prototypes (10 categories, 3–4 examples each) for better matching.

---

### 5.5 Decision Agent

**File:** `backend/agents/langchain/decider.py`

Makes the final call on each incident and saves the result to Supabase.

**Logic:**

1. If `authenticity_score >= 0.7` and `category` is known → `publish`
2. Otherwise → `needs_revision`
3. If `revision_count >= 2` → forced reject (no LLM call)

**Supabase write (new):**  
After deciding, the agent calls `insert_incident` with:

| Field | Value |
|---|---|
| `source_platform` | `"langgraph_pipeline"` |
| `raw_text` | The original post text |
| `status` | `published`, `rejected`, or `needs_revision` |
| `decision` | The decision string |
| `category` | From the classifier |
| `authenticity_score` | From the classifier |
| `agent_notes` | All notes collected through the pipeline |

If the Supabase write fails, it logs the error and continues — it never crashes the pipeline.

**Decision thresholds (in the full pipeline LLM prompt):**
- Score ≥ 0.25 with concrete location + time + action → can publish
- Community posts don't need police confirmation or media links
- `needs_revision` only if missing info could realistically be found

---

### 5.6 LangGraph Pipeline

Two complete pipelines exist side by side:

#### `langchain/workflow.py` — Main pipeline (wired to the API)

```
START → crawler → cleaner → classifier → decider → END
                                              ↑
                      (if needs_revision and retry_count < 2) ←──
```

The compiled graph is exported as `graph`. Trigger it via the API: `POST /api/pipeline/run`.

**State fields:**

| Field | Type | Set by |
|---|---|---|
| `post_id` | string | Input |
| `raw_text` | string | Input |
| `candidate` | bool? | Crawler |
| `category` | string? | Classifier |
| `authenticity_score` | float? | Classifier |
| `decision` | string? | Decider |
| `revision_count` | int | Decider |
| `notes` | list[string] | All nodes |

#### `orchestration6_DB.py` / `orchestration7.py` — Standalone pipelines

```
START → crawler → classifier → decider → END
                                   ↑
            (if needs_retry and retry_count < 2) ←──
```

No separate cleaner node here — the classifier does both extraction and scoring. Run directly from the command line. Does not connect to the FastAPI server.

**Run them:**

```bash
# Simple graph — one hardcoded test post
python -m backend.orchestration

# Full pipeline — runs on data/mock_posts.json
python -m backend.agents.crawler.orchestration6_DB
```

---

### 5.7 Multimodal Verifier

**File:** `backend/agents/crawler/multimodal.py`

Checks whether attached files (images, videos, audio, documents) actually support what a post claims. Not connected to the main pipeline — standalone utility.

**Supported file types:**

| Type | Extensions | How it checks |
|---|---|---|
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` | GPT-4.1-mini vision |
| Documents | `.pdf`, `.docx`, `.txt`, `.csv` | Text extraction + GPT |
| Videos | `.mp4`, `.mov`, `.avi` | Frame sampling + audio transcription |
| Audio | `.mp3`, `.wav`, `.m4a` | Whisper transcription + GPT |

**Main function:**

```python
result = verify_post_against_evidence(post_text, evidence_paths)
# Returns: { support, confidence, reasoning, matched_claims, missing_claims, contradictions }
```

---

## 6. Database

All DB code lives in `backend/db/`. Import everything from `backend.db` — not from the individual files.

### 6.1 Supabase Client

**File:** `backend/db/supabase.py`

Creates one shared client per process (cached with `@lru_cache`).

**Key order:** Tries `SUPABASE_SERVICE_ROLE_KEY` first (bypasses row-level security). Falls back to `SUPABASE_ANON_KEY`.

```python
from backend.db import is_supabase_configured, get_supabase_client

if is_supabase_configured():
    client = get_supabase_client()
```

---

### 6.2 Core Incidents Table

**File:** `backend/db/incidents.py` | **Table:** `incidents`

Stores the raw incident entry and source metadata. Linked to other tables for analysis, decisions, location, and queue status.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `incident_id` | uuid | PRIMARY KEY | Auto-generated unique identifier |
| `dedupe_key` | text | NOT NULL, UNIQUE | Key for deduplication across sources |
| `source_platform` | enum | NOT NULL | e.g. `"reddit"`, `"mock_forum"`, `"langgraph_pipeline"` |
| `source_type` | enum | NULL | Type of post (comment, thread, post, etc.) |
| `source_item_id` | text | NULL | Platform-specific post ID |
| `parent_source_item_id` | text | NULL | ID of parent post if this is a reply |
| `source_url` | text | NULL | Direct link to the original post |
| `raw_text` | text | NOT NULL | Original unmodified post text |
| `language_code` | text | DEFAULT `'en'` | ISO-639 language code |
| `timestamp_text` | text | NULL | Raw timestamp string from source |
| `normalized_time` | timestamptz | NULL | Parsed timestamp in Singapore time |
| `duplicate_of` | uuid | FOREIGN KEY | Points to primary incident if duplicate |
| `created_at` | timestamptz | DEFAULT now() | Record creation timestamp |
| `updated_at` | timestamptz | DEFAULT now() | Record last update timestamp |

**Relationships:**
- `incident_analysis` (1:1) — Classification, scoring, and cleaned content
- `incident_queue` (1:1) — Workflow status and agent locking
- `incident_locations` (1:1) — Geographic coordinates
- `incident_decisions` (1:1) — Final decision and report status
- `incident_agent_messages` (1:N) — Log of all agent activities

**Available functions:**

```python
insert_incident(data: dict) -> dict
get_incident_by_id(incident_id: str) -> dict | None
get_all_incidents(status_filter=None, limit=50) -> list[dict]
get_published_incidents(limit=100) -> list[dict]
update_incident(incident_id: str, updates: dict) -> dict
update_incident_status(incident_id: str, new_status: str) -> dict
append_agent_note(incident_id: str, note: str, existing_notes: list) -> dict
```

---

### 6.3 Incident Queue Table

**File:** `backend/db/incidents.py` (in queue management) | **Table:** `incident_queue`

Tracks workflow state, agent processing, and row locking to prevent concurrent modifications.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `incident_id` | uuid | PRIMARY KEY, FK | References `incidents.incident_id` |
| `status` | enum | NOT NULL, DEFAULT `'raw'` | Workflow stage: `raw`, `queued`, `in_progress`, `candidate`, `classified`, `published`, `rejected`, `needs_revision`, `failed` |
| `current_agent` | enum | NULL | Which agent is currently processing this |
| `next_agent` | enum | NULL | Which agent will process this next |
| `retry_count` | integer | NOT NULL, DEFAULT 0 | Number of failed attempts |
| `max_attempts` | integer | NOT NULL, DEFAULT 3 | Maximum retry limit before forced reject |
| `available_at` | timestamptz | NOT NULL, DEFAULT now() | When this incident becomes available for processing |
| `locked_by` | text | NULL | Name of agent that currently holds the lock |
| `locked_at` | timestamptz | NULL | Timestamp when the lock was acquired |
| `last_error` | text | NULL | Error message from most recent failure |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | Last status update |

**Status values:**

| Status | Meaning |
|---|---|
| `raw` | Just saved, not yet processed |
| `queued` | Ready for the next agent |
| `in_progress` | An agent currently holds a lock on it |
| `candidate` | Crawler approved it as a valid incident |
| `classified` | Classifier has scored it |
| `published` | Approved — shows on the map |
| `rejected` | Not good enough — not shown |
| `needs_revision` | Sent back for more info (max 2 retries) |
| `failed` | An agent encountered an error |

---

### 6.4 Incident Analysis Table

**File:** `backend/agents/langchain/classifier.py` | **Table:** `incident_analysis`

Stores the output from the classification pipeline: cleaned content, category, scores, and extracted data.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `incident_id` | uuid | PRIMARY KEY, FK | References `incidents.incident_id` |
| `cleaned_content` | text | NULL | Clean, formal summary from Cleaner Agent (1–2 sentences) |
| `topic_bucket` | enum | NULL | Categorized topic: `singapore_news`, `singapore_viral`, or `other` |
| `topic_similarity_score` | numeric | NULL | Confidence (0.0–1.0) that this matches the topic |
| `category` | enum | NULL | Crime category: `theft`, `attempted_theft`, `vandalism`, `suspicious_activity`, `harassment` |
| `authenticity_score` | numeric | NULL | Confidence (0.0–1.0) this is a real incident, not a joke |
| `severity` | numeric | NULL | Severity (0.0–1.0): 0 = minor, 1 = critical |
| `category_score` | numeric | NULL | Confidence (0.0–1.0) that the category assignment is correct |
| `extracted_entities` | jsonb | DEFAULT `{}` | Structured fields: location, people, items, times |
| `candidate_scores` | jsonb | NULL | Scores for each candidate category |
| `matched_signals` | jsonb | NULL | Which scoring rubric signals matched |
| `classified_at` | timestamptz | DEFAULT now() | Classification timestamp |

**Scoring rubric (for authenticity_score):**

| Factor | Weight | What it checks |
|---|---|---|
| Detail (location, time, action, person) | 25% | Specific and concrete information |
| Evidence (first-hand, clear, media) | 25% | Quality of supporting evidence |
| Consistency (no contradictions) | 15% | Aligned fields, no exaggeration |
| Risk flags (rumours, missing data, ragebait) | −5% | Deductions for red flags |

**Formula:** `authenticity = (0.25 × detail) + (0.25 × evidence) + (0.15 × consistency) − (0.05 × risk)`

---

### 6.5 Incident Decisions Table

**File:** `backend/agents/langchain/decider.py` | **Table:** `incident_decisions`

Stores the final decision made by the Decision Agent and any reasoning.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `incident_id` | uuid | PRIMARY KEY, FK | References `incidents.incident_id` |
| `decision` | enum | NOT NULL | Final decision: `publish`, `needs_revision`, `reject` |
| `decision_reason` | text | NULL | LLM-generated explanation for the decision |
| `report_status` | enum | DEFAULT `'unknown'` | Report processing status: `unknown`, `pending`, `confirmed`, `dismissed` |
| `decided_at` | timestamptz | DEFAULT now() | Decision timestamp |

**Decision logic:**

- If `authenticity_score >= 0.7` AND `category` is known → `publish`
- Else if `retry_count < 2` → `needs_revision`
- Else → `reject`

---

### 6.6 Incident Locations Table

**File:** `backend/agents/cleaner/cleaner_agent.py` | **Table:** `incident_locations`

Stores geographic data extracted and geocoded by the Cleaner Agent.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `incident_id` | uuid | PRIMARY KEY, FK | References `incidents.incident_id` |
| `location_text` | text | NULL | Normalised place name (e.g. "Ang Mo Kio MRT", "Tampines Block 542") |
| `latitude` | double precision | NULL | GPS latitude (Singapore range: ~1.1–1.5) |
| `longitude` | double precision | NULL | GPS longitude (Singapore range: ~103.6–104.1) |

**Notes:**
- Set by the Cleaner Agent during text processing
- If geocoding fails, both lat/lng are NULL
- Frontend uses these coordinates to place pins on the map

---

### 6.7 Incident Agent Messages Table

**File:** `backend/agents/langchain/` | **Table:** `incident_agent_messages`

Complete audit log of every agent's work on each incident. Used for transparency and debugging.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | uuid | PRIMARY KEY | Auto-generated message ID |
| `incident_id` | uuid | NOT NULL, FK | References `incidents.incident_id` |
| `agent` | enum | NOT NULL | Which agent created this message: `crawler`, `cleaner`, `classifier`, `decision_agent` |
| `sequence_order` | smallint | NOT NULL | Order in the processing pipeline (1, 2, 3, …) |
| `attempt` | smallint | DEFAULT 1 | Attempt number if the incident was retried |
| `message_type` | text | NOT NULL | `status_update`, `note`, `error`, `output`, etc. |
| `summary` | text | NULL | Short message or note (shown in UI as `note` for backward compatibility) |
| `reasoning` | text | NULL | Detailed reasoning from LLM |
| `llm_raw_output` | text | NULL | Unprocessed LLM response |
| `category_assigned` | text | NULL | Category picked by this agent |
| `category_score` | numeric | NULL | Confidence in the category |
| `authenticity_level` | text | NULL | `high`, `medium`, `low` |
| `authenticity_score` | numeric | NULL | Numeric score (0.0–1.0) |
| `severity_level` | text | NULL | `critical`, `high`, `medium`, `low` |
| `severity_score` | numeric | NULL | Numeric score (0.0–1.0) |
| `decision_made` | text | NULL | Decision output from Decision Agent |
| `decision_instruction` | text | NULL | Instructions based on the decision |
| `decision_reason` | text | NULL | Why this decision was made |
| `classifier_review` | text | NULL | Classifier's review notes |
| `metadata` | jsonb | DEFAULT `{}` | Arbitrary agent-specific data |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | Message creation timestamp |

**Notes:**
- Each row represents one discrete step in processing
- The `incident_full` view aggregates all messages for an incident into one JSONB array
- For backward compatibility, `summary` is aliased as `note` in the view

---

### 6.8 Agent Feedback Table

**File:** `backend/db/feedback.py` | **Table:** `agent_feedback`

Stores inter-agent communication: one agent requesting another to revise work or provide more information.



| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | uuid | PRIMARY KEY | Auto-generated feedback message ID |
| `incident_id` | uuid | NOT NULL, FK | References `incidents.incident_id` |
| `from_agent` | enum | NOT NULL | Sending agent: `crawler`, `cleaner`, `classifier`, `decision_agent` |
| `to_agent` | enum | NOT NULL | Receiving agent |
| `feedback_type` | text | NOT NULL | Code: `location_unclear`, `time_missing`, `source_weak`, `text_too_vague`, `possible_duplicate`, `authenticity_too_low`, `category_conflict`, `severity_unclear`, `source_metadata_missing` |
| `reason` | text | NOT NULL | Human-readable explanation |
| `requested_action` | text | NULL | What the receiving agent should do |
| `context_snapshot` | jsonb | DEFAULT `{}` | Snapshot of incident state when feedback was sent |
| `priority` | text | DEFAULT `'normal'` | Urgency: `low`, `normal`, `high`, `urgent` |
| `resolved` | boolean | DEFAULT false | Has the receiving agent acted on this? |
| `resolved_at` | timestamptz | NULL | When it was resolved |
| `resolved_by` | text | NULL | Which agent or process resolved it |
| `created_at` | timestamptz | DEFAULT now() | Feedback creation timestamp |

**Available functions:**

```python
insert_feedback(data: dict) -> dict
get_feedback_for_incident(incident_id: str) -> list[dict]
get_unresolved_feedback(to_agent: str | None = None) -> list[dict]
mark_feedback_resolved(feedback_id: str) -> dict
```

---

### 6.9 Incident Full View

**File:** `supabase/incident_full.sql` | **View:** `incident_full`

Pre-joined view that combines all related tables for easy querying. Used by the frontend API and reporting.

**Purpose:** Fetch a complete incident record with all analysis, decisions, and messages without requiring multiple joins.

**Source tables joined:**
- `incidents` (core identity and source data)
- `incident_queue` (workflow state)
- `incident_analysis` (classification results)
- `incident_locations` (geographic data)
- `incident_decisions` (final decision)
- `incident_agent_messages` (aggregated as JSONB array)

**Result columns:** All columns from the source tables, plus:
- `agent_messages` (jsonb array) — All messages for this incident, in sequence order

**Usage example:**

```python
# Instead of this:
core = db.query("SELECT * FROM incidents WHERE id = ?", id)
queue = db.query("SELECT * FROM incident_queue WHERE id = ?", id)
analysis = db.query("SELECT * FROM incident_analysis WHERE id = ?", id)

# Use this:
full = db.query("SELECT * FROM incident_full WHERE incident_id = ?", id)
```

---

### 6.10 Deprecated: Mock Official Reports Table

> ⚠️ **Deprecated** — not found in current schema

**Former file:** `backend/db/mock_reports.py` | **Former table:** `mock_official_reports`

This table was used in early prototypes to simulate official police/news records for deduplication. It is no longer present in the current Supabase schema (`supabase/new_tables.sql`).

If you need to use this functionality in the future:
1. Define the table schema in Supabase
2. Restore the Python functions in `backend/db/mock_reports.py`
3. Wire it back into the classifier LLM prompt

---

## 7. API Reference

Base URL (local): `http://127.0.0.1:8000`

---

### `GET /`

Returns API version info and whether the database is connected.

```json
{
  "message": "PettyCrimeSG API is running.",
  "docs": "/docs",
  "database_connected": "True"
}
```

---

### `GET /health`

```json
{ "status": "ok", "database": "connected" }
```

---

### `GET /api/incidents`

Runs the deterministic crawler on `data/sample_posts.json` in memory. No database needed. Good for local testing.

**Query params:** `candidate_only=true`, `limit=50`

---

### `GET /api/db/incidents`

Gets incidents from Supabase. This is what the frontend map calls.

**Query params:** `status=published`, `published_only=true`, `limit=50`

```json
{
  "count": 8,
  "source": "supabase",
  "incidents": [...]
}
```

---

### `GET /api/db/incidents/{incident_id}`

Gets one incident by UUID. Returns 404 if not found.

---

### `GET /api/db/incidents/{incident_id}/feedback`

Gets the full agent conversation log for one incident.

```json
{
  "incident_id": "...",
  "count": 2,
  "feedback": [
    {
      "from_agent": "classifier",
      "to_agent": "crawler",
      "feedback_type": "location_unclear",
      "reason": "...",
      "requested_action": "...",
      "priority": "medium",
      "resolved": false
    }
  ]
}
```

---

### `POST /api/db/incidents`

Saves a new incident. Required body fields: `source_platform`, `raw_text`, `status`.

---

### `POST /api/db/incidents/{incident_id}/feedback`

Sends an agent-to-agent feedback message. Required: `from_agent`, `to_agent`, `feedback_type`, `reason`, `requested_action`, `priority`.

---

### `GET /api/db/official-reports`

Gets all mock official reports. Query param: `limit=100`.

---

### `POST /api/pipeline/run`

Runs the LangGraph pipeline on a list of posts. Posts go through the full graph one at a time.

**Request body:**
```json
{
  "posts": [
    { "post_id": "abc", "raw_text": "Bag stolen at Bedok MRT last night." }
  ]
}
```

**Response:**
```json
{
  "results": [
    {
      "post_id": "abc",
      "decision": "publish",
      "category": "theft",
      "authenticity_score": 0.78,
      "status": "published"
    }
  ]
}
```

If the pipeline fails on a single post, that entry gets an `"error"` field instead. The rest of the posts still run.

---

## 8. Frontend

**Stack:** Next.js 16 (App Router), TypeScript, Tailwind CSS v4, React-Leaflet, Zustand, Framer Motion

**Start:**
```bash
cd frontend
npm install
npm run dev   # → http://localhost:3000
```

---

### 8.1 App Shell

- `app/page.tsx` → renders `<Dashboard />`
- `app/layout.tsx` → sets page metadata and global CSS
- `app/globals.css` → Tailwind base + custom CSS classes for glass panels, pin animations, and map overlays

---

### 8.2 Store (Zustand)

**File:** `src/components/safewatch/store.ts`

Single source of truth for all UI state.

| Field | Type | Description |
|---|---|---|
| `incidents` | `Incident[]` | Current incident list (starts as mock data) |
| `selectedIncidentId` | `string?` | Which incident is open in the detail panel |
| `crimeType` | `CrimeTypeFilter` | Active crime type filter |
| `timeRange` | `TimeRangeFilter` | `24h`, `7d`, `30d`, `90d`, or `all` |
| `severityFilter` | `SeverityFilter` | Severity display mode |
| `mapFlyTo` | `object?` | Coords to animate the map to |
| `sidebarCollapsed` | `bool` | Sidebar open or closed |
| `isLoading` | `bool` | API call in progress |

**`fetchIncidents()`** calls `GET /api/db/incidents?published_only=true&limit=200`. If the API returns real data, it replaces the mock incidents. If the API fails or returns zero rows, mock data stays.

**How database rows map to frontend fields:**

| DB column | Frontend field | Notes |
|---|---|---|
| `incident_id` | `id` | |
| `authenticity_score` | `confidence` | |
| `authenticity_score >= 0.8` | `verified` | True/false badge |
| `raw_text` | `description` | |
| `location_text` | `location.area` | |
| `latitude` | `location.lat` | Defaults to `1.3521` if missing |
| `longitude` | `location.lng` | Defaults to `103.8198` if missing |
| `normalized_time` | `timestamp` | |
| `severity` (float) | `severity` (string) | `≥0.9`=critical, `≥0.7`=high, `≥0.5`=medium, else=low |

**Helper functions:**

```typescript
useFilteredIncidents()   // applies crimeType + timeRange filters
severityCounts(incidents) // returns { critical, high, medium, low }
timeAgo(isoString)        // returns "5 min ago", "2 hrs ago", "3 days ago"
```

---

### 8.3 Map View

**File:** `src/components/safewatch/MapView.tsx`

Built on React-Leaflet. Locked to Singapore's bounding box (`[1.16, 103.6]` → `[1.48, 104.1]`). Zoom: 12–18.

Incidents are grouped by planning area. Each area gets one pin instead of individual markers. Area polygons come from `/data/sg-planning-areas.geojson`.

**Pin colours by incident count:**

| Count | Colour | Hex |
|---|---|---|
| 1 | Cyan | `#06b6d4` |
| 2–3 | Yellow | `#eab308` |
| 4–6 | Orange | `#f97316` |
| 7–9 | Red-orange | `#ef4444` |
| 10+ | Deep red | `#b91c1c` |

- **Hover** a pin → tooltip shows up to 5 incidents in that area
- **Click** a pin → popup with the full list; clicking an incident opens the detail panel
- Incidents with no matching area get a fallback pin at their raw `lat/lng`

**Map styles** (switchable in the app):
- Voyager (default, light)
- Dark Matter
- Positron
- Satellite (ArcGIS)

---

### 8.4 Incident Detail Panel

**File:** `src/components/safewatch/IncidentDetailPanel.tsx`

Slides in from the right when you click an incident. Shows:
- Title, severity badge, verified status
- Location, timestamp, source
- Full description
- Agent analysis: classification confidence, validation, severity reason, pattern notes

---

### 8.5 Severity Sidebar

**File:** `src/components/safewatch/SeveritySidebar.tsx`

Collapsible panel (collapsed on mobile by default). Contains:
- Crime type filter buttons
- Time range filter buttons
- Severity count summary
- Scrollable incident list with colour indicators

---

### 8.6 Mock Data

**File:** `src/components/safewatch/mockData.ts`

55 hardcoded incidents across 15+ Singapore planning areas. Used as the starting state and as a fallback if the backend is unreachable.

3 hardcoded clusters:

| Cluster | Type | Area | Count |
|---|---|---|---|
| `CL_023` | Snatch Theft | Geylang | 5 |
| `CL_019` | Bike Theft | Tampines MRT | 4 |
| `CL_031` | Voyeurism | Yishun Block 743 | 3 |

**Severity colours:**
```
critical → #ef4444  (red)
high     → #f97316  (orange)
medium   → #eab308  (yellow)
low      → #22c55e  (green)
```

---

## 9. Data Schemas

### Frontend `Incident` type

```typescript
interface Incident {
  id: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  location: { area: string; lat: number; lng: number };
  source: string;
  verified: boolean;
  confidence: number;
  timestamp: string;
  cluster_id: string | null;
  agent_analysis: {
    classification: string;
    classification_confidence: number;
    validation: string;
    severity_reason: string;
    pattern: string;
  };
}
```

### Backend `CleanedIncident` (Pydantic)

```python
class CleanedIncident(BaseModel):
    cleaned_content: str
    topic_bucket: Literal["singapore_news", "singapore_viral", "other"]
    location_text: Optional[str]
    latitude: Optional[float]   # 1.1–1.5
    longitude: Optional[float]  # 103.6–104.1
    normalized_time: Optional[str]  # ISO-8601 Singapore time
```

### LangGraph `IncidentState` (TypedDict)

```python
class IncidentState(TypedDict):
    post_id: str
    raw_text: str
    candidate: Optional[bool]
    category: Optional[str]
    authenticity_score: Optional[float]
    decision: Optional[str]
    revision_count: int
    notes: list[str]
```

---

## 10. Agent Feedback Loop

Three feedback channels exist:

```
Classifier → Crawler      ("location unclear, find more details")
Decision   → Classifier   ("re-score this ambiguous incident")
Decision   → Crawler      ("source metadata is missing")
```

**Inside the orchestration pipelines:** Feedback is stored in `state["messages"]` as in-memory dicts with a `feedback_to` field.

**In Supabase:** Feedback is saved to `agent_feedback`. Agents call `get_unresolved_feedback(to_agent="crawler")` to check their inbox, then `mark_feedback_resolved(feedback_id)` when done.

**Via the API:** Any component can send feedback through `POST /api/db/incidents/{id}/feedback`.

**Retry limit:** Max 2 retries per incident. After that, the decision node forces a reject.

---

## 11. Environment Variables

Copy `.env.example` to `.env` and fill in the values.

**Backend:**

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Used by all LLM agents |
| `SUPABASE_URL` | Yes (for DB) | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes (for DB) | Service role key — bypasses row-level security |
| `SUPABASE_ANON_KEY` | Optional | Fallback if service role key is missing |
| `SUPABASE_KEY` | Yes (for crawler) | Used by `reddit_crawler.py` specifically |
| `REDDIT_USER_AGENT` | Optional | Custom User-Agent for Reddit requests |
| `HUGGINGFACEHUB_API_TOKEN` | Optional | Used by the Reddit crawler's classifier model |

Without `SUPABASE_URL` and a key, the backend falls back to `data/sample_posts.json` and the map shows mock data.

**Frontend — Vercel / production:**

Next.js only passes variables to the browser if they start with `NEXT_PUBLIC_`. The backend variables above are server-only. Add these separately in **Vercel → Settings → Environment Variables**:

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Same value as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Same value as `SUPABASE_ANON_KEY` |

Without these, the frontend throws `supabaseUrl is required` at runtime and the page won't load. They are read by `frontend/src/lib/supabase.ts`.

---

## 12. Setup and Running

### Backend

```bash
cd HORNY_APPLE/backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Start the API (run from `HORNY_APPLE/`):

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd HORNY_APPLE/frontend
npm install
npm run dev   # → http://localhost:3000
```

### Run agents manually

```bash
# Keyword crawler — writes to data/incident_drafts.json
python -m backend.agents.crawler.deterministic

# Reddit crawler — scrape and save to Supabase
python -m backend.agents.crawler.reddit_crawler --upload --stats

# Cleaner agent — process one queued incident from Supabase
python -m backend.agents.cleaner.cleaner_agent

# Simple LangGraph pipeline — one hardcoded test post
python -m backend.orchestration

# Full LangGraph pipeline — runs on data/mock_posts.json
python -m backend.agents.crawler.orchestration6_DB
```

### Run the pipeline via the API

```bash
curl -X POST http://127.0.0.1:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{
    "posts": [
      { "post_id": "test_001", "raw_text": "Bag stolen at Bedok MRT last night." }
    ]
  }'
```

### Database setup

1. Create a Supabase project
2. Run `upgrade_migration.sql` in the Supabase SQL editor to create the tables
3. Run `seed_incidents.sql` to add test data
4. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`

---

## 13. Known Issues

| # | Severity | File | Description |
|---|---|---|---|
| 1 | **High** | `langchain/classifier.py` | Vandalism (0.64) and harassment (0.66) scores are hardcoded below the 0.70 publish threshold. These categories can never be published through the `langchain/` pipeline path. |
| 2 | **High** | All orchestration pipelines | The standalone pipelines (`orchestration6_DB.py`, `orchestration7.py`) do not write decisions back to Supabase themselves — only the `langchain/decider.py` path does (via `POST /api/pipeline/run`). |
| 3 | **High** | `langchain/workflow.py` | Not wired to a trigger. The only way to run the graph is via `POST /api/pipeline/run` or the `__main__` block in `workflow.py`. |
| 4 | **Medium** | `deterministic.py` | Crawler always sets `latitude: None` and `longitude: None`. Geocoding only happens if the Cleaner Agent runs separately. |
| 5 | **Medium** | `langchain/cleaner.py` | The graph's cleaner node only strips whitespace. It does not fill in `location_text` or `normalized_time` — those fields don't even exist in `IncidentState`. |
| 6 | **Medium** | `orchestration6_DB.py` | Classifier LLM calls do not set `temperature=0`, so results vary between runs. |
| 7 | **Low** | `frontend/store.ts` | The map always flashes mock data on first load before the real data arrives, even when the backend is available. |
| 8 | **Low** | `db/mock_reports.py` | `find_similar_official_report` uses simple string matching. It misses the same location if described differently (e.g. "Bedok" vs "East Coast"). |
| ~~9~~ | ~~Fixed~~ | ~~`orchestration7.py:571`~~ | ~~Decision node called `model="gpt-5-mini"` which doesn't exist.~~ Fixed — now `"gpt-4o-mini"`. |
| ~~10~~ | ~~Fixed~~ | ~~`frontend/store.ts:207`~~ | ~~TypeScript error: `data as DbRow[]` failed type check.~~ Fixed — now `data as unknown as DbRow[]`. |

---

## 14. Ethics Rules

All agents follow these rules, enforced via LLM system prompts:

1. **Posts are unverified reports, not confirmed crimes.** The system never says someone is guilty.
2. **Confidence scores are always shown.** No incident goes on the map without its `authenticity_score`.
3. **No personal info is published.** Names, usernames, phone numbers, and personal details are removed by the Cleaner Agent.
4. **Only clean summaries are shown publicly.** The raw post text is stored but never displayed to end users.
5. **Low-confidence reports are held or rejected.** Posts below the threshold go to `needs_revision` or `rejected` — not the map.
6. **Max 2 retries.** After 2 revision cycles, an uncertain incident is rejected rather than kept alive.
7. **The map shows patterns, not accusations.** Pins represent community reports, not police records.

---

> **Last synced from supabase/ on:** May 1, 2026
