# JobTracker - BLS Jobs Data API & MCP Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A comprehensive open-source API and MCP (Model Context Protocol) tool for accessing U.S. Bureau of Labor Statistics (BLS) occupational data, wages, and O*NET skills information. Designed to help students plan careers by connecting job skills to education and microcredentialing opportunities.

## Features

- **800+ Occupations**: Complete employment and wage data from BLS OEWS
- **Skills & Competencies**: O*NET skills, knowledge, abilities, and technology requirements
- **Geographic Data**: Wages broken down by state and metropolitan area
- **Career Tools**: Occupation comparison and skill gap analysis
- **AI Integration**: MCP server for seamless AI assistant integration
- **Portable Deployment**: Docker-based for easy deployment anywhere

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/rahepler2/JobTracker.git
cd JobTracker

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see API Registration below)

# Start the services
docker-compose up -d

# Load initial data (first time only)
docker-compose --profile loader run data-loader

# API is now available at http://localhost:8000
# Typesense admin at http://localhost:8108
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Typesense (using Docker)
docker run -d -p 8108:8108 \
    -v typesense-data:/data \
    typesense/typesense:27.1 \
    --data-dir /data \
    --api-key=your-api-key \
    --enable-cors

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Load data
python -m scripts.initial_load

# Start the API
python -m api.main
```

## API Registration (Required)

### BLS API Key (Free)
1. Register at https://data.bls.gov/registrationEngine/
2. Add to `.env`: `BLS_API_KEY=your_key`

### O*NET Credentials (Free)
1. Register at https://services.onetcenter.org/developer/
2. Add to `.env`:
   ```
   ONET_USERNAME=your_email
   ONET_APP_KEY=your_key
   ```

## API Endpoints

### Occupations
| Endpoint | Description |
|----------|-------------|
| `GET /occupations` | Search occupations by title, skills, or keywords |
| `GET /occupations/{soc_code}` | Get detailed occupation info |
| `GET /occupations/{soc_code}/skills` | Get skills for an occupation |
| `GET /occupations/compare/{soc1}/{soc2}` | Compare two occupations |

### Wages
| Endpoint | Description |
|----------|-------------|
| `GET /wages` | Search wage data by location |
| `GET /wages/by-occupation/{soc_code}` | Wages across all locations |
| `GET /wages/by-state/{state_code}` | All occupations in a state |
| `GET /wages/top-paying` | Highest paying occupations |

### Skills
| Endpoint | Description |
|----------|-------------|
| `GET /skills` | Search skills/knowledge/abilities |
| `GET /skills/{skill_id}` | Get skill details |
| `GET /skills/gap-analysis` | Analyze skill gaps between careers |

### Full API documentation available at `/docs` when running.

## MCP Server

The MCP server enables AI assistants to query occupational data directly.

### Available Tools

- `search_occupations` - Search for jobs by title, skills, or requirements
- `get_occupation_details` - Get complete occupation information
- `get_wages_by_location` - Compare wages across locations
- `search_skills` - Find skills and related occupations
- `analyze_skill_gap` - Plan career transitions
- `compare_occupations` - Side-by-side comparison
- `get_top_paying_occupations` - Find highest paying jobs
- `find_occupations_by_skill` - Jobs requiring specific skills

### Configure with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jobtracker": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/JobTracker",
      "env": {
        "TYPESENSE_HOST": "localhost",
        "TYPESENSE_PORT": "8108",
        "TYPESENSE_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Project Structure

```
JobTracker/
├── src/                    # Core library
│   ├── bls_client.py      # BLS OEWS API client
│   ├── onet_client.py     # O*NET API client
│   ├── typesense_loader.py # Typesense operations
│   ├── data_transformer.py # Data transformation
│   └── pipeline.py        # ETL orchestration
├── api/                    # REST API
│   ├── main.py            # FastAPI application
│   ├── models.py          # Pydantic models
│   └── routers/           # API endpoints
├── mcp_server/            # MCP server
│   └── server.py          # MCP implementation
├── scripts/               # Utility scripts
│   └── initial_load.py    # Data loading script
├── config/                # Configuration
│   └── settings.yaml      # Default settings
├── tests/                 # Test suite
├── Dockerfile             # API container
├── docker-compose.yml     # Full stack deployment
└── requirements.txt       # Python dependencies
```

## Data Sources

### BLS OEWS (Occupational Employment and Wage Statistics)
- Employment counts by occupation
- Mean and median wages
- Wage percentiles (10th, 25th, 75th, 90th)
- State and metropolitan area breakdowns

### O*NET (Occupational Information Network)
- Skills, knowledge, and abilities
- Technology skills and tools
- Work tasks and activities
- Education and experience requirements
- Job zone classifications
- Bright outlook indicators

## Use Cases

### Career Exploration
```python
# Find careers in technology with high wages
GET /occupations?q=software&min_wage=100000&bright_outlook=true
```

### Education Planning
```python
# What skills do I need for data science?
GET /occupations/15-2051/skills
```

### Career Transition
```python
# How do I move from accounting to data analysis?
GET /skills/gap-analysis?from_soc_code=13-2011&to_soc_code=15-2051
```

### Geographic Comparison
```python
# Where are software developers paid the most?
GET /wages/by-occupation/15-1252?area_type=state
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BLS_API_KEY` | BLS API registration key | Recommended |
| `ONET_USERNAME` | O*NET registered email | For skills data |
| `ONET_APP_KEY` | O*NET application key | For skills data |
| `TYPESENSE_HOST` | Typesense server host | Yes |
| `TYPESENSE_PORT` | Typesense server port | Yes |
| `TYPESENSE_API_KEY` | Typesense admin API key | Yes |

## Deployment Options

### Docker Compose (Recommended)
Complete stack with Typesense and API.

### Kubernetes
Use the provided Docker images with your K8s cluster.

### Azure
- Deploy Typesense on Azure VM or AKS
- Run API as Azure Container Instance or App Service
- Use Azure Functions for scheduled data updates

### AWS
- Typesense on EC2 or ECS
- API on ECS, EKS, or Lambda
- EventBridge for scheduled updates

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest`
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [U.S. Bureau of Labor Statistics](https://www.bls.gov/) for OEWS data
- [O*NET](https://www.onetonline.org/) for occupational information
- [Typesense](https://typesense.org/) for the search engine
- [FastAPI](https://fastapi.tiangolo.com/) for the API framework
