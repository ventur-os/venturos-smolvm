#!/usr/bin/env python3
"""Check a packaged Linux runtime using only a disposable, offline guest."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="smolvm-website-smoke-") as directory:
        root = Path(directory)
        home, website, control = (root / name for name in ("home", "website", "control"))
        for path in (home, website, control):
            path.mkdir()
        os.setxattr(website, "user.containers.override_stat", b"31000:31000:0755")
        (control / "sentinel").write_text("read-only")
        env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
               "XDG_CACHE_HOME": str(home / "cache"), "XDG_CONFIG_HOME": str(home / "config")}

        def run(*args):
            result = subprocess.run([str(binary), *args], env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}")
            return result.stdout.strip()

        assert run("--version") == "smolvm 1.25.0"
        assert json.loads(run("machine", "list", "--json")) == []
        for command in ("create", "update"):
            assert "override-stat" in run("machine", command, "--help")
        name = "website-mount-smoke"
        run("machine", "create", "--name", name, "--cpus", "1", "--mem", "512",
            "--storage", "1", "--overlay", "1", "--volume", f"{website}:/website-workspaces:override-stat",
            "--volume", f"{control}:/control:ro")
        try:
            run("machine", "start", "--name", name)
            assert run("machine", "exec", "--name", name, "--", "stat", "-c", "%u:%g:%a",
                       "/website-workspaces") == "31000:31000:755"
            run("machine", "exec", "--name", name, "--user", "31000:31000", "--", "sh", "-c",
                "printf persisted > /website-workspaces/proof")
            assert (website / "proof").read_text() == "persisted"
            assert os.getxattr(website / "proof", "user.containers.override_stat") == b"31000:31000:0644"
            run("machine", "exec", "--name", name, "--", "sh", "-c",
                "set -e; test \"$(cat /control/sentinel)\" = read-only; "
                "if touch /control/forbidden; then exit 1; fi")
            assert not (control / "forbidden").exists()
            run("machine", "exec", "--name", name, "--", "sh", "-c",
                "printf overlay-persisted > /workspace/proof")
            run("machine", "stop", "--name", name)
            run("machine", "update", "--name", name, "--mem", "512")
            run("machine", "start", "--name", name)
            assert run("machine", "exec", "--name", name, "--", "cat",
                       "/website-workspaces/proof") == "persisted"
            assert run("machine", "exec", "--name", name, "--", "stat", "-c", "%u:%g:%a",
                       "/website-workspaces/proof") == "31000:31000:644"
            assert run("machine", "exec", "--name", name, "--", "cat", "/workspace/proof") == "overlay-persisted"
        finally:
            run("machine", "stop", "--name", name)
            run("machine", "delete", "--force", "--name", name)
        assert json.loads(run("machine", "list", "--json")) == []
        print("Packaged Website ownership, read-only mount, and stop/start persistence verified")


if __name__ == "__main__":
    main()
