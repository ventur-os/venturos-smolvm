# VenturOS smolvm Website mount

This repository builds smolvm v1.25.0 with one opt-in virtiofs volume mode:
`HOST:/website-workspaces:override-stat`. It uses the pinned upstream libkrun
bundle and leaves all other volumes unchanged. The [patch](patches/override-stat.patch)
is applied to upstream commit `18a7c09fe334ab64fda0e672f3c98aebbfff64e6`.

Tagged releases contain a Linux x86_64 tarball and its SHA-256. The VenturOS
BYOP host installer pins that digest. The runtime must pass a live devtest guest
write/read test before the host switches to it. Pull requests and tagged builds
run the focused Rust checks and `scripts/website-mount-smoke.py` against the
packaged Linux runtime using an isolated state directory and disposable KVM guest.
The smoke checks opt-in ownership, a read-only control mount, and file persistence
through stop/start. It does not call providers or change existing machines.
