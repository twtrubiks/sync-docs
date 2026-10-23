"""
clear_ws_connections 管理指令測試（真實 Redis）

驗證 --list / --user-id / --all 三種模式的輸出與刪除行為，
包含 HASH（field 級 TTL）與遷移期殘留的舊格式 SET。
"""

import io

import pytest
import redis
from django.core.management import call_command

from docs_app.redis_pool import _get_host_port

USER_A = 999911  # 避免與其他測試的 user id 衝突
USER_B = 999912
KEY_A = f"ws:connections:user:{USER_A}"
KEY_B = f"ws:connections:user:{USER_B}"


@pytest.fixture
def redis_client():
    host, port = _get_host_port()
    r = redis.Redis(host=host, port=port, decode_responses=True)
    r.delete(KEY_A, KEY_B)
    yield r
    r.delete(KEY_A, KEY_B)
    r.close()


@pytest.fixture
def no_connection_keys(redis_client):
    """清空所有連線記錄，讓「找不到記錄」與 --all 的計數可預期"""
    for key in redis_client.scan_iter(match="ws:connections:user:*"):
        redis_client.delete(key)
    return redis_client


def run_command(*args):
    out = io.StringIO()
    call_command("clear_ws_connections", *args, stdout=out)
    return out.getvalue()


def test_without_option_prints_usage_hint(redis_client):
    redis_client.hset(KEY_A, "chan_a", 1)

    output = run_command()

    assert "Please specify --user-id, --all, or --list" in output
    assert redis_client.exists(KEY_A), "未指定模式時不應刪除任何記錄"


def test_list_without_records(no_connection_keys):
    assert run_command("--list").strip() == "No connection records found."


def test_list_shows_channels_and_field_ttl(redis_client):
    redis_client.hset(KEY_A, mapping={"chan_ttl": 1, "chan_forever": 1})
    redis_client.hexpire(KEY_A, 300, "chan_ttl")
    # 遷移期殘留的舊格式（SET）：HTTL 不適用，應顯示 legacy 提示而非崩潰
    redis_client.sadd(KEY_B, "legacy_chan")

    output = run_command("--list")

    assert "Found 2 connection key(s):" in output
    assert f"User {USER_A}:" in output
    assert f"User {USER_B}:" in output
    assert "Connections (2):" in output
    assert "Connections (1): ['legacy_chan']" in output
    ttl_line = next(line for line in output.splitlines() if "chan_ttl: TTL" in line)
    seconds = int(ttl_line.split("TTL ")[1].split(" seconds")[0])
    assert 0 < seconds <= 300
    assert "chan_forever: TTL no expiry" in output
    assert "legacy_chan: TTL n/a (legacy set format)" in output
    # --list 只讀不刪
    assert redis_client.hlen(KEY_A) == 2
    assert redis_client.scard(KEY_B) == 1


def test_list_sorts_keys(redis_client):
    redis_client.hset(KEY_B, "chan_b", 1)
    redis_client.hset(KEY_A, "chan_a", 1)

    output = run_command("--list")

    assert output.index(f"User {USER_A}:") < output.index(f"User {USER_B}:")


def test_clear_user_deletes_only_that_user(redis_client):
    redis_client.hset(KEY_A, mapping={"chan_1": 1, "chan_2": 1})
    redis_client.hset(KEY_B, "chan_other", 1)

    output = run_command(f"--user-id={USER_A}")

    assert f"Cleared 2 connection(s) for user {USER_A}" in output
    assert not redis_client.exists(KEY_A)
    assert redis_client.hkeys(KEY_B) == ["chan_other"]


def test_clear_user_counts_legacy_set_members(redis_client):
    redis_client.sadd(KEY_A, "legacy_1", "legacy_2", "legacy_3")

    output = run_command(f"--user-id={USER_A}")

    assert f"Cleared 3 connection(s) for user {USER_A}" in output
    assert not redis_client.exists(KEY_A)


def test_clear_user_without_records(redis_client):
    output = run_command(f"--user-id={USER_A}")

    assert f"No connections found for user {USER_A}" in output


def test_clear_all_deletes_every_connection_key(no_connection_keys):
    r = no_connection_keys
    r.hset(KEY_A, mapping={"chan_1": 1, "chan_2": 1})
    r.sadd(KEY_B, "legacy_1")
    r.set("unrelated:key", "keep")

    try:
        output = run_command("--all")

        assert "Cleared 3 connection(s) across 2 user(s)" in output
        assert not r.exists(KEY_A)
        assert not r.exists(KEY_B)
        assert r.get("unrelated:key") == "keep", "只能刪除 ws:connections:user:* 的記錄"
    finally:
        r.delete("unrelated:key")


def test_clear_all_without_records(no_connection_keys):
    assert run_command("--all").strip() == "No connection records to clear."
