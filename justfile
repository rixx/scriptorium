set shell := ["bash", "-euo", "pipefail", "-c"]
set quiet

_ := require("uv")
python := "uv run python"
src_dir := "src"

[private]
default:
    just --list

# Install dependencies (use --extras to include e.g. dev)
[group('development')]
install *args:
    uv lock --upgrade
    uv sync {{ args }}

# Run the development server or other commands, e.g. `just run migrate`
[group('development')]
[working-directory("src")]
run *args="runserver":
    {{ python }} manage.py {{ args }}

# Open Django shell
[group('development')]
[no-exit-message]
[working-directory("src")]
shell *args:
    {{ python }} manage.py shell {{ args }}

# Run ruff format
[group('linting')]
format *args="":
    uvx ruff format {{ src_dir }} {{ args }}

# Run ruff check
[group('linting')]
check *args="":
    uvx ruff check {{ src_dir }} {{ args }}

# Run all formatters and linters (fix mode)
[group('linting')]
fmt: format (check "--fix")

# Run all code quality checks (check-only, for CI)
[group('linting')]
fmt-check: (format "--check") check

# Remove Python caches, build artifacts, and coverage reports
[group('development')]
clean:
    -find . -type d -name __pycache__ -exec rm -rf {} +
    -find . -type f -name "*.pyc" -delete
    -find . -type d -name "*.egg-info" -exec rm -rf {} +
    -rm -rf .pytest_cache .coverage htmlcov dist build
