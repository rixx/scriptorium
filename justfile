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

# Check for outdated dependencies
[group('development')]
[script('python3')]
deps-outdated:
    import json, subprocess, tomllib
    from packaging.requirements import Requirement

    result = subprocess.run(['uv', 'pip', 'list', '--outdated', '--format=json'], capture_output=True, text=True)
    outdated = {p['name'].lower(): p for p in json.loads(result.stdout)}
    deps = tomllib.load(open('pyproject.toml', 'rb')).get('project', {}).get('dependencies', [])
    direct = {Requirement(d).name.lower() for d in deps}

    for name in sorted(outdated.keys() & direct):
        p = outdated[name]
        print(f"{p['name']}: {p['version']} → {p['latest_version']}")

# Bump a dependency version
[group('development')]
[script('python3')]
deps-bump package version:
    import subprocess, tomllib
    from pathlib import Path
    from packaging.requirements import Requirement

    p = Path('pyproject.toml')
    deps = tomllib.load(open('pyproject.toml', 'rb')).get('project', {}).get('dependencies', [])
    old = next((d for d in deps if Requirement(d).name.lower() == '{{ package }}'.lower()), None)
    if old:
        p.write_text(p.read_text().replace(old, f'{Requirement(old).name}~={{ version }}'))
    subprocess.run(['uv', 'lock', '--upgrade-package', '{{ package }}'])

# Remove Python caches, build artifacts, and coverage reports
[group('development')]
clean:
    -find . -type d -name __pycache__ -exec rm -rf {} +
    -find . -type f -name "*.pyc" -delete
    -find . -type d -name "*.egg-info" -exec rm -rf {} +
    -rm -rf .pytest_cache .coverage htmlcov dist build
