#!/usr/bin/env python3
"""Check the packaged runtime's virtio-net TCP relay capacity with a disposable guest.

The guest holds more connections open than the old fixed 256-relay table allowed,
to a listener on the host's loopback reached through the guest gateway. Flows past
the table capacity are refused by the userspace stack, so the host-accepted count
equals the effective capacity.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading

FLOWS = 600
GUEST_SCRIPT = r"""
set -u
gateway=$(awk '$2 == "00000000" { print $3; exit }' /proc/net/route)
set -- $(echo "$gateway" | sed 's/\(..\)\(..\)\(..\)\(..\)/\4 \3 \2 \1/')
host=$(printf '%d.%d.%d.%d' "0x$1" "0x$2" "0x$3" "0x$4")
rm -f /tmp/hold /tmp/refused
mkfifo /tmp/hold
: > /tmp/refused
sleep 300 > /tmp/hold 2>/dev/null &
holder=$!
i=0
while [ "$i" -lt FLOWS ]; do
  nc "$host" PORT < /tmp/hold > /dev/null 2>> /tmp/refused &
  i=$((i + 1))
done
sleep 10
remote="$gateway:$(printf '%04X' PORT)"
established=$(awk -v remote="$remote" '$3 == remote && $4 == "01"' /proc/net/tcp | wc -l)
refused=$(grep -c 'refused' /tmp/refused || true)
killall nc 2>/dev/null || true
kill "$holder" 2>/dev/null || true
echo "established=$established refused=$refused"
"""


class Listener:
    def __init__(self):
        self.socket = socket.create_server(("127.0.0.1", 0), backlog=4096)
        self.port = self.socket.getsockname()[1]
        self.accepted = []
        self.stopped = False
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stopped:
            try:
                connection, _ = self.socket.accept()
            except OSError:
                return
            self.accepted.append(connection)

    def reset(self):
        for connection in self.accepted:
            connection.close()
        self.accepted = []

    def close(self):
        self.stopped = True
        self.socket.close()
        self.reset()


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="smolvm-relay-smoke-") as directory:
        home = Path(directory) / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
               "XDG_CACHE_HOME": str(home / "cache"), "XDG_CONFIG_HOME": str(home / "config"),
               "DOCKER_CONFIG": str(home / ".docker"), "SMOLVM_LIB_DIR": str(binary.parent / "lib"),
               "SMOLVM_AGENT_ROOTFS": str(binary.parent / "agent-rootfs")}
        for name in ("SMOLVM_DATA_DIR", "SMOLVM_TCP_RELAY_CAPACITY", "SMOLVM_PUBLISH_ADDR",
                     "SMOLVM_EGRESS_FLOOR", "SMOLVM_EGRESS_ALLOW_PRIVATE"):
            env.pop(name, None)

        def run(*args, extra=None):
            result = subprocess.run([str(binary), *args], env={**env, **(extra or {})}, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}")
            return result.stdout.strip()

        assert run("--version") == "smolvm 1.25.0"
        assert json.loads(run("machine", "list", "--json")) == []
        listener = Listener()
        script = (GUEST_SCRIPT.replace("FLOWS", str(FLOWS))
                  .replace("PORT", str(listener.port)))
        name = "tcp-relay-capacity-smoke"
        run("machine", "create", "--name", name, "--cpus", "2", "--mem", "1024",
            "--image", str(binary.parent / "agent-rootfs"), "--storage", "1", "--overlay", "1",
            "--net", "--net-backend", "virtio-net")
        try:
            # (relay capacity env, expected concurrent flows the host accepts)
            for capacity, expected in ((None, 512), ("2048", FLOWS)):
                extra = {} if capacity is None else {"SMOLVM_TCP_RELAY_CAPACITY": capacity}
                run("machine", "start", "--name", name, extra=extra)
                guest = run("machine", "exec", "--name", name, "--", "sh", "-c", script)
                accepted = len(listener.accepted)
                print(f"capacity={capacity or 'default'} host_accepted={accepted} guest {guest}")
                assert accepted == expected, (capacity, accepted, guest)
                assert guest == f"established={expected} refused={FLOWS - expected}", (capacity, guest)
                run("machine", "stop", "--name", name)
                listener.reset()
        finally:
            listener.close()
            subprocess.run([str(binary), "machine", "stop", "--name", name], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run("machine", "delete", "--force", "--name", name)
        assert json.loads(run("machine", "list", "--json")) == []
        print(f"Packaged virtio-net relay: default 512 and configured {FLOWS} concurrent flows verified")


if __name__ == "__main__":
    main()
