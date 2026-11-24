import os
import signal
import stat
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
START_ALL = REPO_ROOT / "start_all.sh"


def _make_exe(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_start_all_launches_bridge_and_cleans_up(tmp_path):
    """start_all.sh must run self-contained without GEMMA_TALK_DIR, launch bridge, and clean up on SIGTERM."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _make_exe(bin_dir / "curl", "#!/usr/bin/env bash\nexit 0\n")
    _make_exe(bin_dir / "open", "#!/usr/bin/env bash\nexit 0\n")
    _make_exe(bin_dir / "npm", "#!/usr/bin/env bash\nexec sleep 30\n")

    webots_stub = tmp_path / "webots"
    _make_exe(webots_stub, "#!/usr/bin/env bash\nexec sleep 30\n")

    bridge_marker = tmp_path / "bridge_started.txt"
    bridge_pid_file = tmp_path / "bridge.pid"
    fake_python = tmp_path / "fake_python3"
    _make_exe(
        fake_python,
        f"""#!/usr/bin/env bash
echo "$@" > "{bridge_marker}"
echo $$ > "{bridge_pid_file}"
echo "fake bridge started"
exec sleep 30
""",
    )

    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["WEBOTS_APP"] = str(webots_stub)
    env["GEMMA_LOG_DIR"] = str(log_dir)
    env["GEMMA_PYTHON_BIN"] = str(fake_python)

    proc = subprocess.Popen(
        ["bash", str(START_ALL)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not bridge_marker.exists():
            if proc.poll() is not None:
                break
            time.sleep(0.05)

        assert bridge_marker.exists(), "start_all.sh never launched gemma_talk_bridge.py"
        assert "gemma_talk_bridge.py" in bridge_marker.read_text(encoding="utf-8")

        bridge_pid = int(bridge_pid_file.read_text(encoding="utf-8").strip())
        log_files = list(log_dir.glob("*bridge*.log")) if log_dir.exists() else []
        assert log_files, "Expected a bridge log file to be created"

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

        time.sleep(0.2)
        try:
            os.kill(bridge_pid, 0)
            still_alive = True
        except OSError:
            still_alive = False
        assert not still_alive, f"Bridge PID {bridge_pid} was not cleaned up on SIGTERM"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_start_all_fails_loudly_if_bridge_dies_on_startup(tmp_path):
    """start_all.sh must fail loudly (non-zero exit) if gemma_talk_bridge.py dies on startup."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _make_exe(bin_dir / "curl", "#!/usr/bin/env bash\nexit 0\n")
    _make_exe(bin_dir / "open", "#!/usr/bin/env bash\nexit 0\n")
    _make_exe(bin_dir / "npm", "#!/usr/bin/env bash\nexec sleep 30\n")

    webots_stub = tmp_path / "webots"
    _make_exe(webots_stub, "#!/usr/bin/env bash\nexec sleep 30\n")

    fake_python = tmp_path / "fake_python3"
    _make_exe(
        fake_python,
        "#!/usr/bin/env bash\necho 'boom: missing dependency' >&2\nexit 1\n",
    )

    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["WEBOTS_APP"] = str(webots_stub)
    env["GEMMA_LOG_DIR"] = str(log_dir)
    env["GEMMA_PYTHON_BIN"] = str(fake_python)

    result = subprocess.run(
        ["bash", str(START_ALL)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0, "start_all.sh should exit non-zero when bridge dies on startup"
    assert "bridge" in result.stdout.lower()
