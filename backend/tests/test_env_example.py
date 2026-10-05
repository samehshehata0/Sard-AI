import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def example_names() -> set[str]:
    names = set()
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line.split("=")[0].strip())
    return names


def test_every_setting_the_backend_reads_from_the_environment_is_in_env_example():
    read = set()
    for path in (ROOT / "backend" / "app" / "core" / "config.py", ROOT / "backend" / "run.py"):
        read |= set(re.findall(r'os\.getenv\(\s*"([A-Z0-9_]+)"', path.read_text(encoding="utf-8")))
    assert read, "found no settings to check"
    assert sorted(read - example_names()) == []


def test_every_environment_variable_the_web_app_reads_is_in_env_example():
    read = set()
    for path in (ROOT / "src").rglob("*.ts*"):
        read |= set(re.findall(r"process\.env\.([A-Z0-9_]+)", path.read_text(encoding="utf-8")))
    # Set by Node and Next.js themselves, not by us.
    read -= {"NODE_ENV", "NEXT_RUNTIME", "NEXT_PHASE", "CI", "VERCEL_ENV"}
    assert read, "found no variables to check"
    assert sorted(read - example_names()) == []


def test_compose_runs_the_whole_stack_and_the_worker_is_not_switched_off():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ("mongo:", "backend:", "frontend:"):
        assert f"\n  {service}" in compose
    assert "JOB_WORKER_ENABLED" not in compose or 'JOB_WORKER_ENABLED: "false"' not in compose
    assert "PYTHON_BACKEND_URL: http://backend:8000" in compose
    assert "BACKEND_HOST: 0.0.0.0" in compose  # the published port must reach the API inside the container
    assert "mongodb://mongo:27017" in compose
