# VenturOS smolvm Website mount

This repository builds smolvm v1.17.0 with one opt-in virtiofs volume mode:
`HOST:/website-workspaces:override-stat`. It uses the pinned upstream libkrun
bundle and leaves all other volumes unchanged. The [patch](patches/override-stat.patch)
is applied to upstream commit `d33b5a4adeb844365922cd2a29a89d93a94008ad`.

Tagged releases contain a Linux x86_64 tarball and its SHA-256. The VenturOS
BYOP host installer pins that digest. The runtime must pass a live devtest guest
write/read test before the host switches to it.
