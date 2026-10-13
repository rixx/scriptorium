set shell := ["bash", "-euo", "pipefail", "-c"]
set quiet
set fallback
set default-list

python := "uv run python"
uv_dev := "uv run --extra=dev"

# Install dependencies (use --extras to include dev)
[group('dependencies')]
install *args:
    uv sync {{ args }}

# Install all dependencies
[group('dependencies')]
install-all:
    uv sync --all-extras

# Upgrade locked dependencies to their latest compatible versions
[group('dependencies')]
deps-upgrade:
    uv lock --upgrade
    uv sync --all-extras

# Check for outdated dependencies
[group('dependencies')]
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
[group('dependencies')]
[script('python3')]
deps-bump package version:
    import subprocess, tomllib
    from pathlib import Path
    from packaging.requirements import Requirement

    p = Path('pyproject.toml')
    deps = tomllib.load(open('pyproject.toml', 'rb')).get('project', {}).get('dependencies', [])
    old = next((d for d in deps if Requirement(d).name.lower() == '{{ package }}'.lower()), None)
    if old:
        req = Requirement(old)
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        p.write_text(p.read_text().replace(old, f'{req.name}{extras}~={{ version }}'))
    else:
        print("{{ package }} is not a direct dependency; updating the lock only.")
    subprocess.run(['uv', 'lock', '--upgrade-package', '{{ package }}'])

# Run the development server or other commands, e.g. `just run makemigrations`
[group('development')]
[positional-arguments]
[working-directory("src")]
run *args:
    @if [ "$#" -eq 0 ]; then set -- runserver --skip-checks; fi; {{ python }} manage.py "$@"

# Open Django shell
[group('development')]
[no-exit-message]
[positional-arguments]
[working-directory("src")]
shell *args:
    {{ python }} manage.py shell "$@"

# Remove Python caches, build artifacts, and coverage reports
[group('development')]
clean:
    -find . -type d -name __pycache__ -exec rm -rf {} +
    -find . -type f -name "*.pyc" -delete
    -find . -type d -name "*.egg-info" -exec rm -rf {} +
    -rm -rf .pytest_cache .coverage htmlcov dist build

# Run ruff format
[group('linting')]
format *args="":
    {{ uv_dev }} ruff format {{ args }}

# Run ruff check
[group('linting')]
check *args="":
    {{ uv_dev }} ruff check {{ args }}

# Run all formatters and linters
[group('linting')]
fmt: format (check "--fix") && fmt-done

[private]
fmt-done:
    echo '{{ GREEN }}Formatting complete{{ NORMAL }}'

# Run all code quality checks (no fix)
[group('linting')]
fmt-check: (format "--check") check && check-done

[private]
check-done:
    echo '{{ GREEN }}All checks passed{{ NORMAL }}'

# Run periodic tasks (spine colors, thumbnails)
[group('operations')]
[working-directory("src")]
periodic:
    {{ python }} manage.py runperiodic

# Collect static files for production
[group('operations')]
[working-directory("src")]
collectstatic:
    {{ python }} manage.py collectstatic --noinput

# Deploy in production: pull, sync deps to the lock, migrate, collectstatic, restart (run as root)
[group('operations')]
deploy:
    runuser -u books -- git pull
    runuser -u books -- uv sync --frozen
    runuser -u books -- just run migrate
    runuser -u books -- just run collectstatic --no-input
    systemctl restart books

# Run the test suite
[group('tests')]
[positional-arguments]
test *args:
    {{ uv_dev }} pytest --cov=src --cov-report=term-missing:skip-covered --cov-config=pyproject.toml "$@"

# Run tests in parallel (requires pytest-xdist)
[group('tests')]
[positional-arguments]
test-parallel *args:
    just test -n auto "$@"

# Show test coverage report in browser
[group('tests')]
[script('bash')]
test-coverage-report: (test "--cov-report=html")
    set -euo pipefail
    if [ -f "htmlcov/index.html" ]; then
        open htmlcov/index.html 2>/dev/null || \
        xdg-open htmlcov/index.html 2>/dev/null || \
        echo "Coverage report: htmlcov/index.html"
    else
        echo "No coverage report found. Run just test-coverage-report first."
    fi
