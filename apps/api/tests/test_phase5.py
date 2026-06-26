"""Phase 5 — model registry (§12), permissions (§11), tmux command builder (§10)."""


def test_model_registry_defaults():
    from app import model_registry

    assert model_registry.default_model("claude") == "claude-opus-4-8"
    assert model_registry.default_model("codex") == "gpt-5.5"
    assert model_registry.is_known("claude", "claude-sonnet-4-6")
    assert not model_registry.is_known("codex", "nope")


def test_models_endpoint(client):
    d = client.get("/models?brain=claude").json()
    assert d["default"] == "claude-opus-4-8"
    assert any(m["id"] == "claude-fable-5" for m in d["models"])
    allm = client.get("/models").json()
    assert "claude" in allm and "codex" in allm


def test_permission_flags():
    from app.services import permissions

    assert permissions.claude_flags("auto") == ["--permission-mode", "auto"]
    assert permissions.claude_flags("locked") == ["--permission-mode", "dontAsk"]
    assert permissions.codex_flags("auto") == [
        "--sandbox", "workspace-write", "--ask-for-approval", "on-request",
    ]
    assert permissions.codex_flags("locked") == [
        "--sandbox", "read-only", "--ask-for-approval", "never",
    ]
    assert permissions.flags_for("claude", "safe") == ["--permission-mode", "default"]


def test_permission_presets_endpoint(client):
    d = client.get("/permission-presets").json()
    assert d["default"] == "auto"
    assert any(p["key"] == "auto" for p in d["presets"])


def test_get_set_agent_permissions(client):
    got = client.get("/agents/claude/permissions").json()
    assert got["preset"] == "auto" and got["flags"] == ["--permission-mode", "auto"]

    upd = client.put(
        "/agents/codex/permissions",
        json={"preset": "locked", "allow": ["Read"], "deny": ["Bash(rm -rf *)"]},
    ).json()
    assert upd["preset"] == "locked"
    assert upd["flags"] == ["--sandbox", "read-only", "--ask-for-approval", "never"]

    again = client.get("/agents/codex/permissions").json()
    assert again["preset"] == "locked" and again["allow"] == ["Read"]


def test_tmux_command_builder():
    from app.services import cli_exec

    cmd = cli_exec.build_new_window_command(
        7, "claude", "claude-opus-4-8", "auto", "/mnt/k/runs/7/run.log"
    )
    assert cmd[:5] == ["tmux", "new-window", "-d", "-t", "asv2"]
    assert "run-7" in cmd
    shell = cmd[-1]
    assert "claude --model claude-opus-4-8 --permission-mode auto" in shell
    assert "tee" in shell and "run.log" in shell

    cmd2 = cli_exec.build_new_window_command(8, "codex", "gpt-5.5", "auto", "/tmp/8.log")
    assert (
        "codex --model gpt-5.5 --sandbox workspace-write --ask-for-approval on-request"
        in cmd2[-1]
    )
    assert cli_exec.kill_window_command(7) == ["tmux", "kill-window", "-t", "asv2:run-7"]
