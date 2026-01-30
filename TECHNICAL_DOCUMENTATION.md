# JobTracker - Technical Documentation

## Overview

JobTracker is an ETL pipeline and API for synchronizing U.S. Bureau of Labor Statistics (BLS) and O*NET occupational data into a Typesense search database, with both REST API and MCP (Model Context Protocol) interfaces.

### Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   BLS OEWS API  │     │  O*NET Web API  │
│  (wages/employ) │     │    (skills)     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
        ┌────────────▼────────────┐
        │   Python ETL Pipeline   │
        │   (src/pipeline.py)     │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │      Typesense DB       │
        │   (Search Database)     │
        └────────────┬────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐   ┌──────────▼──────────┐
│   REST API      │   │    MCP Server       │
│   (FastAPI)     │   │  (AI Integration)   │
└─────────────────┘   └─────────────────────┘
```

---

## 1. Data Sources

### 1.1 BLS OEWS (Occupational Employment and Wage Statistics)

**Base URL:** `https://api.bls.gov/publicAPI/v2/`

**Bulk Downloads:** `https://www.bls.gov/oes/special-requests/`

**Data Provided:**
- Employment counts by occupation
- Mean, median, and percentile wages
- Hourly and annual wage figures
- National, state, and metro area breakdowns

**Update Frequency:** Annual (May reference period, released following year)

**Rate Limits (API v2):**
- 500 queries/day
- 50 series/query
- 20 years of data

### 1.2 O*NET (Occupational Information Network)

**Base URL:** `https://services.onetcenter.org/ws/`

**Data Provided:**
- Skills, knowledge, and abilities
- Technology skills and tools
- Work tasks and activities
- Education requirements
- Job zone classifications
- Bright outlook designations

**Update Frequency:** Quarterly

**Rate Limits:** Reasonable use policy (0.2s delay recommended)

---

## 2. Database Schema

### 2.1 Typesense Collections

#### `occupations` Collection

Primary collection for occupation data with merged BLS and O*NET information.

```json
{
    "name": "occupations",
    "fields": [
        {"name": "soc_code", "type": "string", "facet": true},
        {"name": "onet_code", "type": "string", "facet": true},
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string", "optional": true},
        {"name": "occupation_group", "type": "string", "facet": true},

        {"name": "national_employment", "type": "int32", "optional": true},
        {"name": "national_mean_wage", "type": "float", "optional": true},
        {"name": "national_median_wage", "type": "float", "optional": true},
        {"name": "wage_pct_10", "type": "float", "optional": true},
        {"name": "wage_pct_90", "type": "float", "optional": true},

        {"name": "job_zone", "type": "int32", "facet": true, "optional": true},
        {"name": "education_level", "type": "string", "facet": true, "optional": true},
        {"name": "bright_outlook", "type": "bool", "facet": true, "optional": true},

        {"name": "skills", "type": "object[]", "optional": true},
        {"name": "technology_skills", "type": "string[]", "facet": true, "optional": true},
        {"name": "skill_names", "type": "string[]", "facet": true, "optional": true},

        {"name": "last_updated", "type": "int64"}
    ],
    "default_sorting_field": "national_employment"
}
```

#### `occupation_wages_by_location` Collection

Geographic wage breakdowns.

```json
{
    "name": "occupation_wages_by_location",
    "fields": [
        {"name": "soc_code", "type": "string", "facet": true},
        {"name": "occupation_title", "type": "string"},
        {"name": "area_type", "type": "string", "facet": true},
        {"name": "area_code", "type": "string", "facet": true},
        {"name": "area_title", "type": "string"},
        {"name": "state_code", "type": "string", "facet": true, "optional": true},

        {"name": "employment", "type": "int32", "optional": true},
        {"name": "location_quotient", "type": "float", "optional": true},
        {"name": "annual_median_wage", "type": "float", "optional": true},

        {"name": "data_year", "type": "int32", "facet": true},
        {"name": "last_updated", "type": "int64"}
    ],
    "default_sorting_field": "employment"
}
```

#### `skills` Collection

Aggregated skills across occupations.

```json
{
    "name": "skills",
    "fields": [
        {"name": "skill_id", "type": "string"},
        {"name": "skill_name", "type": "string"},
        {"name": "skill_type", "type": "string", "facet": true},
        {"name": "description", "type": "string"},
        {"name": "category", "type": "string", "facet": true},
        {"name": "related_occupations", "type": "object[]"},
        {"name": "occupation_count", "type": "int32"},
        {"name": "avg_importance", "type": "float"},
        {"name": "last_updated", "type": "int64"}
    ],
    "default_sorting_field": "occupation_count"
}
```

---

## 3. Python SDK

### 3.1 BLS Client (`src/bls_client.py`)

```python
from src.bls_client import BLSClient

client = BLSClient()

# Get all occupations with national data
df = client.get_all_occupations()

# Get specific occupation
occ = client.get_occupation_by_soc("15-1252")

# Get state-level wages
state_wages = client.get_wages_by_state("15-1252")

# Search by title
results = client.search_occupations("software")
```

### 3.2 O*NET Client (`src/onet_client.py`)

```python
from src.onet_client import ONetClient

client = ONetClient()

# Get complete occupation data
details = client.get_complete_occupation("15-1252.00")

# Get specific data types
skills = client.get_skills("15-1252.00")
tech_skills = client.get_technology_skills("15-1252.00")

# Search occupations
results = client.search_occupations("data analyst")
```

### 3.3 Pipeline (`src/pipeline.py`)

```python
from src.pipeline import OccupationalDataPipeline

pipeline = OccupationalDataPipeline()

# Full data refresh
results = pipeline.run_full_refresh(
    drop_existing=False,
    include_onet=True,
    include_location_wages=True,
)

# Check for updates
pipeline.check_and_update_oews()

# Update O*NET data only
pipeline.update_onet_data()
```

### 3.4 Typesense Loader (`src/typesense_loader.py`)

```python
from src.typesense_loader import TypesenseLoader

loader = TypesenseLoader()

# Search occupations
results = loader.search_occupations(
    query="software developer",
    filter_by="job_zone:>=4",
    sort_by="national_median_wage:desc",
)

# Get specific document
doc = loader.get_document("occupations", "15-1252")

# Search wages by location
wages = loader.search_wages_by_location(
    soc_code="15-1252",
    area_type="state",
)
```

---

## 4. REST API

### 4.1 Base Configuration

- **Default Port:** 8000
- **Documentation:** `/docs` (Swagger UI), `/redoc` (ReDoc)
- **Health Check:** `/health`

### 4.2 Occupation Endpoints

#### Search Occupations
```http
GET /occupations?q=software&job_zone=4&min_wage=100000
```

Parameters:
- `q`: Search query (default: "*")
- `job_zone`: Filter by job zone (1-5)
- `education_level`: Filter by education requirement
- `bright_outlook`: Filter by bright outlook (true/false)
- `min_wage`: Minimum annual median wage
- `technology`: Filter by technology skill
- `sort_by`: Sort field (default: "national_employment:desc")
- `per_page`: Results per page (1-100)
- `page`: Page number

#### Get Occupation Details
```http
GET /occupations/15-1252
```

Returns complete occupation data including skills, wages, and employment.

#### Get Occupation Skills
```http
GET /occupations/15-1252/skills?skill_type=skill&min_importance=3.5
```

#### Compare Occupations
```http
GET /occupations/compare/15-1252/15-2051
```

### 4.3 Wage Endpoints

#### Search Wages by Location
```http
GET /wages?soc_code=15-1252&area_type=state&sort_by=annual_median_wage:desc
```

#### Get Top Paying Occupations
```http
GET /wages/top-paying?state_code=CA&limit=25
```

#### Compare States
```http
GET /wages/compare-states/15-1252?states=CA,TX,NY,WA
```

### 4.4 Skills Endpoints

#### Search Skills
```http
GET /skills?q=programming&skill_type=skill
```

#### Skill Gap Analysis
```http
GET /skills/gap-analysis?from_soc_code=13-2011&to_soc_code=15-2051
```

---

## 5. MCP Server

### 5.1 Available Tools

| Tool | Description |
|------|-------------|
| `search_occupations` | Search by title, skills, or keywords |
| `get_occupation_details` | Complete occupation information |
| `get_wages_by_location` | Geographic wage data |
| `search_skills` | Find skills and related occupations |
| `analyze_skill_gap` | Career transition planning |
| `compare_occupations` | Side-by-side comparison |
| `get_top_paying_occupations` | Highest paying jobs |
| `find_occupations_by_skill` | Jobs requiring specific skills |

### 5.2 Resources

| URI | Description |
|-----|-------------|
| `jobtracker://overview` | Data overview and statistics |
| `jobtracker://job-zones` | Job zone descriptions |

### 5.3 Prompts

| Prompt | Description |
|--------|-------------|
| `career_exploration` | Explore careers by interest |
| `career_transition` | Plan career changes |
| `salary_research` | Research compensation |

---

## 6. Deployment

### 6.1 Docker Compose (Production)

```bash
# Start all services
docker-compose up -d

# Load initial data
docker-compose --profile loader run data-loader

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### 6.2 Docker Compose (Development)

```bash
# Start with hot reload
docker-compose -f docker-compose.dev.yml up

# API available at http://localhost:8000
# Typesense at http://localhost:8108
```

### 6.3 Environment Configuration

```bash
# Required
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_API_KEY=your-key

# Recommended
BLS_API_KEY=your-bls-key

# For O*NET data
ONET_USERNAME=your-email
ONET_APP_KEY=your-key

# API settings
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
```

---

## 7. Data Update Schedule

| Source | Frequency | Recommended Check |
|--------|-----------|-------------------|
| BLS OEWS | Annual (March/April release) | Weekly |
| O*NET | Quarterly | Quarterly |

### Automated Updates

For production deployments, configure scheduled jobs:

```python
# Example: Azure Functions timer trigger
@app.timer_trigger(schedule="0 0 2 15 * *")
async def monthly_check(timer):
    pipeline = OccupationalDataPipeline()
    await pipeline.check_and_update_oews()
```

---

## 8. Monitoring

### 8.1 Health Endpoints

```http
GET /health
# Returns: {"status": "healthy", "typesense_connected": true, "version": "0.1.0"}

GET /status
# Returns: Detailed pipeline and collection statistics

GET /stats
# Returns: Collection document counts
```

### 8.2 Logging

Configure via environment:
```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

---

## 9. Troubleshooting

### Common Issues

| Issue | Cause | Resolution |
|-------|-------|------------|
| Connection refused | Typesense not running | Start Typesense container |
| 401 on O*NET | Invalid credentials | Check ONET_USERNAME and ONET_APP_KEY |
| Empty results | Collections not loaded | Run initial_load.py |
| Rate limit errors | Too many BLS requests | Add BLS_API_KEY, increase delay |

### Data Validation

```python
# Check collection stats
loader = TypesenseLoader()
stats = loader.get_all_stats()
print(stats)

# Verify specific occupation
doc = loader.get_document("occupations", "15-1252")
assert doc is not None
assert doc["national_employment"] > 0
```

---

## 10. API Reference Links

- **BLS OEWS:** https://www.bls.gov/oes/
- **BLS API Registration:** https://data.bls.gov/registrationEngine/
- **O*NET Developer:** https://services.onetcenter.org/developer/
- **Typesense Docs:** https://typesense.org/docs/
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **MCP Specification:** https://modelcontextprotocol.io/

---

## Appendix A: SOC Code Reference

Standard Occupational Classification hierarchy:

| Level | Digits | Example | Description |
|-------|--------|---------|-------------|
| Major Group | 2 | 15-0000 | Computer and Mathematical |
| Minor Group | 3 | 15-1200 | Computer Occupations |
| Broad Occupation | 5 | 15-1250 | Software and Web Developers |
| Detailed Occupation | 6 | 15-1252 | Software Developers |

O*NET adds decimal suffixes: `15-1252.00` (base occupation)

---

## Appendix B: Job Zone Definitions

| Zone | Preparation | Education | Experience |
|------|-------------|-----------|------------|
| 1 | Little/None | HS diploma or less | None |
| 2 | Some | HS diploma | Some helpful |
| 3 | Medium | Vocational/Associate | Required |
| 4 | Considerable | Bachelor's | Considerable |
| 5 | Extensive | Graduate/Professional | Extensive |
