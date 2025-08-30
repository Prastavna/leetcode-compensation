<p align="center">
<img src="./assets/leetcomp_banner.png">
<sub>https://prastavna.github.io/leetcode-compensation</sub>
</p>

<p align="center">
<a href="https://github.com/prastavna/leetcode-compensation/actions/workflows/data-refresh.yaml"><img src="https://github.com/prastavna/leetcode-compensation/actions/workflows/data-refresh.yaml/badge.svg" alt="automatic-data-update"/ ></a>
<a href="https://github.com/prastavna/leetcode-compensation/actions/workflows/manual-cleanup.yaml"><img src="https://github.com/prastavna/leetcode-compensation/actions/workflows/manual-cleanup.yaml/badge.svg" alt="manual-cleanup"/ ></a>
<a href="https://github.com/prastavna/leetcode-compensation/actions/workflows/pages/pages-build-deployment"><img src="https://github.com/prastavna/leetcode-compensation/actions/workflows/pages/pages-build-deployment/badge.svg" alt="pages-build-deployment" /></a>
</p>

**[LeetCode Compensation](https://prastavna.github.io/leetcode-compensation)** is a tool that helps you find **Software Engineer Salary in India** by:
- Fetching compensation data from Leetcode forums using GraphQL API
- Automated weekly updates through GitHub Actions
- Using LLMs (GitHub Models) for parsing and sanitizing structured data from posts
- Intelligent data processing with mapping and aggregation
- Automatic cleanup to maintain data quality and file sizes

> [!WARNING]
> A 5-day data refresh delay allows the votes to accumulate, after that posts with negative votes are dropped.

> [!NOTE]
> This project started as a fork of [LeetCode Compensation](https://github.com/kuutsav/leetcode-compensation)

## Getting Started

### Prerequisites

Install [uv](https://github.com/astral-sh/uv) - a fast Python package manager:

```shell
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

### Setup

1. **Clone the repository:**
   ```shell
   git clone https://github.com/prastavna/leetcode-compensation.git
   cd leetcode-compensation
   ```

2. **Navigate to the leetcomp directory:**
   ```shell
   cd leetcomp
   ```

3. **Install dependencies:**
   ```shell
   uv sync  # Creates virtual environment and installs dependencies
   ```

4. **Set up environment variables:**
   ```shell
   # Copy the sample environment file
   cp ../.env.sample ../.env
   
   # Edit .env and add your GitHub token
   GITHUB_TOKEN=your_github_token_here
   ```

## Usage

### Complete Data Pipeline

Run the complete data processing pipeline (recommended):

```shell
cd leetcomp
uv run python main.py
```

This executes:
1. **Step 1**: Refresh posts from LeetCode
2. **Step 2**: Parse compensation data using LLMs
3. **Step 3**: Clean up raw posts file (keeps latest 100)

### Individual Components

You can also run individual components:

```shell
cd leetcomp

# Refresh posts from LeetCode
uv run python refresh.py

# Parse compensation data
uv run python parse.py

# Clean up specific posts by ID
uv run python clean.py "12345,67890,11111"
```

### Utility Functions

The project provides reusable utility functions:

```python
from utils import jsonl_to_json, LeetCodeFetcher, get_existing_ids

# Convert JSONL to JSON with mapping
jsonl_to_json("input.jsonl", "output.json")

# Use LeetCode API client
fetcher = LeetCodeFetcher()
posts = fetcher.fetch_posts_list()

# Get existing post IDs
ids = get_existing_ids("data.jsonl")
```

## Project Structure

```
leetcomp/
├── utils/
│   ├── config.py              # Configuration management
│   ├── helpers.py             # Core utility functions
│   ├── data_processing.py     # Data manipulation utilities
│   └── leetcode_api.py        # LeetCode API and parsing
├── queries/                   # GraphQL query files
├── main.py                    # Complete pipeline orchestrator
├── refresh.py                 # LeetCode data fetching
├── parse.py                   # Compensation data parsing
└── clean.py                   # Post cleanup functionality
```

## GitHub Actions

### Automatic Data Refresh
- **Schedule**: Runs twice weekly (Wednesday & Saturday at 10 PM UTC)
- **Manual trigger**: Can be triggered manually from GitHub Actions
- **Process**: Complete pipeline with automatic PR creation and merge

### Manual Cleanup
- **Trigger**: Manual workflow dispatch
- **Input**: Comma-separated post IDs to remove
- **Options**: Optional full data refresh after cleanup
- **Use case**: Remove problematic or duplicate posts

## Configuration

The project uses `config.toml` for configuration:

```toml
[app]
data_dir = "../data"
date_fmt = "%Y-%m-%d %H:%M:%S"
lag_days = 7
leetcode_graphql_url = "https://leetcode.com/graphql"
max_fetch_recs = 10000
max_recs = 10000
n_api_retries = 3

[parsing]
max_base_offer = 120
max_total_offer = 200
min_base_offer = 2
min_total_offer = 3
```

## Features

### Data Processing
- [x] **Automated data fetching** from LeetCode forums via GraphQL API
- [x] **LLM-powered parsing** using GitHub Models (GPT-4o-mini)
- [x] **Smart data validation** with Pydantic models
- [x] **Intelligent mapping** for companies, roles, and locations
- [x] **Automatic cleanup** to maintain data quality and file sizes
- [x] **Lag period filtering** to allow vote accumulation
- [x] **Duplicate detection** and prevention

### Web Interface
- [x] **Sort by Compensation and YoE**
- [x] **Pagination** for large datasets
- [x] **Advanced filters** for YoE, Compensation ranges
- [x] **Search functionality** for Companies and Locations
- [x] **Responsive design** for mobile and desktop

### Automation
- [x] **Scheduled updates** via GitHub Actions (bi-weekly)
- [x] **Manual cleanup workflows** for data maintenance
- [x] **Automatic PR creation** and merging
- [x] **Error handling** and retry mechanisms

## Roadmap

### Upcoming Features
- [ ] **Data export** - CSV/Excel export functionality

## Development

### Running Tests

```shell
cd leetcomp
uv run python -m pytest  # Run tests (when available)
```

### Code Quality

The project uses modern Python tooling:
- **uv** for fast dependency management
- **Pydantic** for data validation
- **Type hints** throughout the codebase
- **Modular architecture** for maintainability

### Adding New Features

1. **Utility functions** go in `utils/` directory
2. **Data processing** functions in `utils/data_processing.py`
3. **API interactions** in `utils/leetcode_api.py`
4. **Configuration** changes in `config.toml`

## Troubleshooting

### Common Issues

**GitHub Token Error:**
```
Error: OpenAI parsing error: ...
```
- Ensure your `GITHUB_TOKEN` is set correctly
- Token needs access to GitHub Models

**Import Errors:**
```
ImportError: attempted relative import with no known parent package
```
- Run commands from the `leetcomp/` directory
- Use `uv run python` instead of direct `python`

**File Not Found:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'queries/...'
```
- Ensure you're running from the `leetcomp/` directory
- Check that GraphQL query files exist

## Contributing

We welcome contributions! Please:

1. **Read** [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
2. **Fork** the repository
3. **Create** a feature branch
4. **Test** your changes thoroughly
5. **Submit** a pull request with clear description

### Areas for Contribution
- **Data quality improvements** - Better parsing and validation
- **Web interface enhancements** - New filters, visualizations
- **Performance optimizations** - Faster data processing
- **Documentation** - Improve guides and examples
- **Testing** - Add comprehensive test coverage

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Original project by [kuutsav](https://github.com/kuutsav/leetcode-compensation)
- LeetCode community for compensation data
- GitHub Models for LLM parsing capabilities
