set shell := ["bash", "-euo", "pipefail", "-c"]
set quiet

_ := require("uv")
python := "uv run python"
uv_dev := "uv run"
src_dir := "src"

[private]
default:
    just --list

# Install dependencies to the locked versions (use --extras to include e.g. dev)
[group('development')]
install *args:
    uv sync {{ args }}

# Upgrade locked dependencies to their latest compatible versions
[group('development')]
upgrade *args:
    uv lock --upgrade
    uv sync {{ args }}

# Run the development server or other commands, e.g. `just run migrate`
[group('development')]
[working-directory("src")]
run *args="runserver":
    {{ python }} manage.py {{ args }}

# Deploy in production: pull, sync deps to the lock, migrate, collectstatic, restart (run as root)
[group('deployment')]
deploy:
    runuser -u books -- git pull
    runuser -u books -- uv sync --frozen
    runuser -u books -- just run migrate
    runuser -u books -- just run collectstatic --no-input
    systemctl restart books

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

# Run the test suite
[group('tests')]
[positional-arguments]
test *args:
    {{ uv_dev }} pytest --cov=src --cov-report=term-missing:skip-covered --cov-config=pyproject.toml "$@"

# Run tests in parallel (requires pytest-xdist)
[group('tests')]
[positional-arguments]
test-parallel n="auto" *args:
    shift; just test -n {{ n }} "$@"

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
