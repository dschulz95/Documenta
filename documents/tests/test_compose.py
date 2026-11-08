"""Behavior of the document stack's Compose configuration (spec: document-deployment, document-access)."""

import json
import re

import pytest

from conftest import STACK_DIR, VALID_ENV

REQUIRED_VARIABLES = [
    "DOCS_ROOT",
    "DOCS_HOST",
    "POSTGRES_PASSWORD",
    "NEXTCLOUD_ADMIN_USER",
    "NEXTCLOUD_ADMIN_PASSWORD",
]


@pytest.mark.parametrize("missing", REQUIRED_VARIABLES)
def test_missing_required_value_fails_and_names_it(compose_config, missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}

    result = compose_config(env)

    assert result.returncode != 0
    assert missing in result.stderr


def test_production_publishes_no_ports(compose_config):
    services = compose_config().model["services"]

    published = {name: svc["ports"] for name, svc in services.items() if svc.get("ports")}
    assert published == {}


def test_database_and_redis_are_only_on_the_internal_network(compose_config):
    model = compose_config().model
    networks, services = model["networks"], model["services"]

    assert networks["data"].get("internal") is True
    assert set(services["db"]["networks"]) == {"data"}
    assert set(services["redis"]["networks"]) == {"data"}
    assert set(services["nextcloud"]["networks"]) == {"web", "data"}


def test_web_network_has_a_fixed_subnet(compose_config):
    web = compose_config().model["networks"]["web"]

    subnets = [cfg["subnet"] for cfg in web["ipam"]["config"]]
    assert subnets == ["172.30.10.0/24"]


def _mounts(service: dict) -> dict:
    """Map container path -> (type, source) for a resolved service."""
    return {m["target"]: (m["type"], m.get("source")) for m in service.get("volumes", [])}


def test_nextcloud_keeps_files_config_and_apps_in_host_folders_under_docs_root(compose_config):
    mounts = _mounts(compose_config().model["services"]["nextcloud"])
    root = VALID_ENV["DOCS_ROOT"]

    assert mounts["/var/www/html/data"] == ("bind", f"{root}/data")
    assert mounts["/var/www/html/config"] == ("bind", f"{root}/config")
    assert mounts["/var/www/html/custom_apps"] == ("bind", f"{root}/custom_apps")


def test_nextcloud_code_and_database_use_named_volumes(compose_config):
    services = compose_config().model["services"]

    assert _mounts(services["nextcloud"])["/var/www/html"] == ("volume", "docs-html")
    assert _mounts(services["db"])["/var/lib/postgresql/data"] == ("volume", "docs-db")


def test_every_service_has_a_healthcheck(compose_config):
    services = compose_config().model["services"]

    without = [name for name, svc in services.items() if not svc.get("healthcheck", {}).get("test")]
    assert without == []


def test_nextcloud_starts_only_after_database_and_redis_are_healthy(compose_config):
    depends_on = compose_config().model["services"]["nextcloud"]["depends_on"]

    assert depends_on["db"]["condition"] == "service_healthy"
    assert depends_on["redis"]["condition"] == "service_healthy"


def test_cron_runs_nextcloud_background_jobs_with_the_same_image_and_files(compose_config):
    services = compose_config().model["services"]
    nextcloud, cron = services["nextcloud"], services["cron"]

    assert cron["image"] == nextcloud["image"]
    assert cron["entrypoint"] == ["/cron.sh"]
    assert _mounts(cron) == _mounts(nextcloud)
    assert set(cron["networks"]) == {"web", "data"}
    assert cron["depends_on"]["nextcloud"]["condition"] == "service_healthy"


def test_tailscale_sidecar_gives_the_stack_its_own_tagged_tailnet_node(compose_config):
    services = compose_config().model["services"]
    ts = services["tailscale"]
    env = ts["environment"]

    assert ts["image"] == "tailscale/tailscale:v1.104.4"
    assert env["TS_USERSPACE"] == "true"
    assert env["TS_SERVE_CONFIG"] == "/config/serve.json"
    assert "--advertise-tags=tag:docs" in env["TS_EXTRA_ARGS"].split()
    assert env["TS_STATE_DIR"] == "/var/lib/tailscale"
    mounts = _mounts(ts)
    assert mounts["/var/lib/tailscale"] == ("volume", "docs-ts")
    assert mounts["/config"][0] == "bind" and mounts["/config"][1].replace("\\", "/").endswith("/documents/tailscale")
    assert set(ts["networks"]) == {"web"}
    assert ts["depends_on"]["nextcloud"]["condition"] == "service_healthy"


def test_tailscale_serves_https_to_nextcloud_without_funnel():
    serve = json.loads((STACK_DIR / "tailscale" / "serve.json").read_text(encoding="utf-8"))
    site = "${TS_CERT_DOMAIN}:443"

    assert serve["TCP"]["443"]["HTTPS"] is True
    assert serve["Web"][site]["Handlers"] == {"/": {"Proxy": "http://nextcloud:80"}}
    assert serve.get("AllowFunnel", {}).get(site, False) is False
    assert list(serve.get("AllowFunnel", {}).values()) in ([], [False])


def test_nextcloud_generates_https_links_for_the_tailnet_host_and_trusts_only_the_web_subnet(compose_config):
    env = compose_config().model["services"]["nextcloud"]["environment"]
    host = VALID_ENV["DOCS_HOST"]

    assert env["OVERWRITEPROTOCOL"] == "https"
    assert env["OVERWRITECLIURL"] == f"https://{host}"
    assert env["TRUSTED_PROXIES"] == "172.30.10.0/24"


def test_nextcloud_keeps_checking_the_host_name_itself(compose_config):
    # OVERWRITEHOST would replace every request's host name and disable Nextcloud's
    # trusted-domain check. Tailscale forwards the real host name, so it is not needed.
    for files in (["docker-compose.yml"], DEV_FILES):
        env = compose_config(files=files).model["services"]["nextcloud"]["environment"]
        assert "OVERWRITEHOST" not in env, files


MIB = 1024 * 1024
MEMORY_LIMITS = {  # design D9
    "nextcloud": 768 * MIB,
    "cron": 640 * MIB,  # above cron's PHP_MEMORY_LIMIT (512M), so PHP fails cleanly before the kernel kills it
    "db": 256 * MIB,
    "redis": 96 * MIB,
    "tailscale": 128 * MIB,
}


def test_every_container_has_its_memory_limit(compose_config):
    services = compose_config().model["services"]

    limits = {name: int(svc.get("mem_limit", 0)) for name, svc in services.items()}
    assert limits == MEMORY_LIMITS


def test_every_container_restarts_after_a_crash_or_reboot(compose_config):
    services = compose_config().model["services"]

    assert {name: svc.get("restart") for name, svc in services.items()} == {name: "unless-stopped" for name in services}


def test_redis_is_a_bounded_cache_without_persistence(compose_config):
    args = compose_config().model["services"]["redis"]["command"]
    options = dict(zip(args[1::2], args[2::2]))  # ["redis-server", "--opt", "value", ...]

    assert args[0] == "redis-server"
    assert options == {"--maxmemory": "64mb", "--maxmemory-policy": "allkeys-lru", "--save": "", "--appendonly": "no"}


def test_nextcloud_accepts_large_uploads_and_has_enough_php_memory(compose_config):
    env = compose_config().model["services"]["nextcloud"]["environment"]

    assert env["PHP_UPLOAD_LIMIT"] == "16G"
    assert env["PHP_MEMORY_LIMIT"] == "512M"


DEV_FILES = ["docker-compose.yml", "docker-compose.dev.yml"]


def test_dev_override_publishes_nextcloud_on_localhost_8081_over_http(compose_config):
    services = compose_config(files=DEV_FILES).model["services"]
    nextcloud = services["nextcloud"]

    ports = [(p["host_ip"], p["published"], p["target"]) for p in nextcloud["ports"]]
    assert ports == [("127.0.0.1", "8081", 80)]
    assert nextcloud["environment"]["OVERWRITEPROTOCOL"] == "http"
    assert "127.0.0.1" in nextcloud["environment"]["NEXTCLOUD_TRUSTED_DOMAINS"].split()
    assert [name for name, svc in services.items() if svc.get("ports") and name != "nextcloud"] == []


def test_dev_override_generates_links_for_localhost_and_runs_without_tailscale(compose_config):
    services = compose_config(files=DEV_FILES).model["services"]
    env = services["nextcloud"]["environment"]

    assert env["OVERWRITECLIURL"] == "http://127.0.0.1:8081"
    assert "tailscale" not in services


def test_dev_port_can_be_changed(compose_config):
    env = dict(VALID_ENV, DOCS_DEV_PORT="9090")

    nextcloud = compose_config(env, files=DEV_FILES).model["services"]["nextcloud"]

    assert [p["published"] for p in nextcloud["ports"]] == ["9090"]


def _example_env() -> dict:
    text = (STACK_DIR / ".env.example").read_text(encoding="utf-8")
    pairs = (line.split("=", 1) for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def test_env_example_lists_every_variable_the_compose_files_use():
    used = set()
    for name in DEV_FILES:
        text = (STACK_DIR / name).read_text(encoding="utf-8")
        used |= set(re.findall(r"\$\{([A-Z0-9_]+)", text))

    assert used - set(_example_env()) == set()


def test_env_example_filled_in_resolves(compose_config):
    filled = {k: (v or f"filled-{k.lower()}") for k, v in _example_env().items()}

    assert compose_config(filled).returncode == 0
