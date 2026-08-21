# Environment

Everything runs in the **IIC-OSIC-TOOLS** container
([repo](https://github.com/iic-jku/iic-osic-tools) ·
[Docker Hub](https://hub.docker.com/r/hpretl/iic-osic-tools)), maintained by the
Department for Integrated Circuits at Johannes Kepler University. It ships the
sky130A PDK plus Verilator, cocotb, Yosys, xschem, ngspice, magic, KLayout, and
netgen, so there is no venv and no per-tool install.

**Pinned to the tag in [`versions.env`](../versions.env).** Never `latest`. The
helper repo is checked out at the *same* tag — the start scripts and the image
are versioned together, and bumping one without the other is the failure the pin
exists to prevent.

This file covers only what cannot be automated: the one-time, `sudo`-requiring
host bootstrap. Everything downstream of "Docker works on this host" is a make
target, because a step that can be run wrong or skipped eventually will be.

---

## Once per machine

Three steps, all needing `sudo` or a restart. Nothing here is repo-specific.

**1. Linux environment.** On Windows, WSL2 with any Ubuntu. The host distro is
not a project dependency — no EDA tool is ever installed outside the container —
so its version does not matter.

```powershell
wsl --install -d Ubuntu
wsl --set-default Ubuntu
```

**2. Docker.** Install Docker Engine *inside* the distro rather than relying on
Docker Desktop's WSL integration; the integration shim is coupled to the distro's
rootfs layout and fails on newer releases. Native Engine also removes a
filesystem hop on every container I/O.

Follow [Docker's Ubuntu install docs](https://docs.docker.com/engine/install/ubuntu/).
If `apt update` 404s on `download.docker.com`, your Ubuntu codename has no
directory in Docker's repo — substitute `noble` in the `deb` line. The
packages are compatible; only the repo path differs.

Then, so `docker` works without `sudo` (running the start scripts as root makes
the container write root-owned files into your designs directory):

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

`wsl --shutdown` from PowerShell, reopen, and confirm:

```bash
docker run hello-world
```

`make` is the entry point for everything below and is not installed by default:

```bash
sudo apt install make
```

That, `git`, and `docker` are the *only* things this project puts on the host.
No EDA tool is ever installed outside the container.

**3. Clone on the Linux filesystem.** Under `~`, never `/mnt/c`. Windows-side
paths go through a translation layer that adds per-syscall latency (brutal for
the hundred-thousand-file LibreLane runs), mishandles the symlink forest
`open_pdks` builds under `sky130A/libs.tech/`, and does not preserve permission
bits. Reach the files from Windows at `\\wsl$\Ubuntu\home\<user>\...` when you
need to.

```bash
mkdir -p ~/github && cd ~/github
git clone <this repo>
```

Clone *only* this repo. `make` clones `iic-osic-tools` beside it, at the pinned
tag — see below. That checkout is read-only to us: we run its scripts and never
edit them, and make will not move its working tree either.

---

## Everything after that

```bash
make doctor       # is this host ready? names what is missing if not
make container    # clone helpers at the pin, then start the container
make shell        # bash inside it, at this design
```

`make container` is the only supported way in, and it does three things you would
otherwise do by hand and eventually get wrong:

| It does | Instead of | Because |
|---|---|---|
| Clones `iic-osic-tools` to `../iic-osic-tools` at `OSIC_TOOLS_TAG` if absent, and verifies the tag if present | you cloning it and remembering the tag | a `git pull` in that directory six months from now silently moves you off the pin, and nothing tells you. Make never writes to an existing checkout — if it has drifted, it stops and prints the command for you to run |
| Runs the upstream `start_vnc.sh` | a hand-rolled `docker run` | the script does uid/gid mapping, podman/rootless detection, port binding, and container reuse. A hand-rolled `docker run` produces a *different* environment from the one this doc describes |
| Reuses the running container if there is one | restarting it | `start_vnc.sh` prompts you to **stop** a running container, which is not what you want from `make shell` |

`DESIGNS` defaults to this repo's parent directory, so `~/github` is bind-mounted
to `/foss/designs` and this repo appears at `/foss/designs/SAR-ASIC`. Sibling
repos are visible too. Export `DESIGNS` yourself only if you run the start
scripts by hand; make passes it either way.

Once inside, `make check-tools` confirms the installed native tools match
`versions.env`. See [tool-versions.md](tool-versions.md).

---

## Do you actually need the container?

For the digital half, no.

`model`, `lint`, `format`, and `verify` run against whatever is on `PATH` —
Verilator, Yosys, Verible, and the `requirements.txt` Python stack. They never
reference the container or the helper repo. CI proves this: it runs them on a
bare GitHub runner with no Docker at all.

Only `container` and `shell` reach for it. So:

| Working on | Needs the container |
|---|---|
| RTL, cocotb, golden models, lint, CI | **No.** Verilator + Python is enough |
| Schematics, ngspice, Magic, DRC/LVS, the PDK | Yes |

A contributor doing RTL and simulation never installs Docker, never clones
`iic-osic-tools`, and is never blocked by either. The cost of skipping it is
that your tool versions are then whatever you installed rather than what
`versions.env` pins — `make check-tools` tells you if that matters.

This is deliberate, and it is the answer to "what if upstream restructures":
the coupling is one edge in the build graph, reached by two targets, pinned to a
tag that upstream cannot change underneath us. Do not add `doctor` or
`osic-tools` as a prerequisite of any digital target.

`OSIC_TOOLS_DIR` defaults to a sibling checkout but is an override —
`make container OSIC_TOOLS_DIR=/somewhere/else` — so the sibling layout is a
default, not an assumption. If the start script is missing from wherever it
points, `make container` says so and names the override instead of failing in
upstream's shell code.

---

## PDK selection

The image defaults to **`PDK=ihp-sg13g2`**, not sky130A. It also derives
`PDKPATH`, `STD_CELL_LIBRARY`, `SPICE_USERINIT_DIR`, and `KLAYOUT_PATH` from
`PDK` *before* sourcing any file of ours, so setting `PDK` on its own leaves
four variables pointing into the IHP tree. Get this wrong and magic, ngspice,
and KLayout load the wrong technology and produce wrong results with no error.

All five settings live in [`pdk.env`](../pdk.env), in this repo, under git:

```bash
make designinit
```

That writes a three-line shim to `$DESIGNS/.designinit` — the one path the
container sources at shell start — which does nothing but source `pdk.env`.
The indirection is the point:

| | Where | Consequence |
|---|---|---|
| Settings | `pdk.env`, in the repo | Version-controlled, reviewable, present for anyone who clones |
| Hook | `$DESIGNS/.designinit` | Written once, contains no settings, never edited again |

Change the PDK config by editing `pdk.env` and committing it, like any other
file. The out-of-repo file does not change.

`make designinit` is idempotent, and it will not overwrite a `.designinit` it
did not write — the designs directory is shared with sibling projects, so
anything unrecognised is left alone and the line to add is printed instead.
`make doctor` fails if the shim is missing, so the container cannot be started
onto the wrong PDK.

`pdk.env` is sourced by every shell in the container, so it is POSIX `sh` and
must not fail: a syntax error there breaks every terminal.

---

## Getting in

| How | For |
|---|---|
| `http://localhost` (password `abc123`) | xschem, magic, KLayout, GTKWave — anything GUI |
| `make shell` | CLI work in the *same running* container |
| VS Code + WSL extension, editing `~/github/SAR-ASIC` | RTL, tests, models, git |

There is deliberately no `.devcontainer/`. VNC plus VS Code over WSL covers both
jobs, and a devcontainer image is a separate tag namespace — a third version to
keep in sync with the two that already have to match.

`make shell` is a wrapper. The underlying command, worth knowing for a second
terminal or when make is unavailable:

```bash
docker exec -it iic-osic-tools_xvnc_uid_$(id -u) bash
```

Add `-w /foss/designs/SAR-ASIC` to land in this repo rather than `/foss/designs`.
The container name encodes your uid because the start scripts run the container
as you, not as root.

The host directory and `/foss/designs/SAR-ASIC` are the same bytes. Edit on the
host, run tools in the container, no syncing.

First run pulls ~20 GB and needs ~60 GB free. XQuartz is macOS-only and is not
needed on Windows or Linux — VNC mode runs its own X server inside the container.

Verify the mount took:

```bash
echo $PDK $PDK_ROOT     # sky130A /foss/pdks
ls /foss/designs        # this repo should be here
```

An empty `/foss/designs` means `DESIGNS` was wrong when the container started.
`make doctor` catches that case before it happens.

---

## Smoke test

One-time, at M0. Exercises magic, netgen, the sky130A tech files, and the mount
together:

```bash
cd /foss/designs
git clone https://github.com/mattvenn/tt06-analog-relax-osc
cd tt06-analog-relax-osc/mag && make clean lvs
```

An LVS match means the environment is real. Fix any failure here before touching
the design — debugging your own layout and a broken tech setup simultaneously is
miserable.

---

## Do not install into a running container

Anything `pip install`ed or `apt install`ed inside vanishes on restart and is not
in anyone else's environment or in CI. If something genuinely is missing, add a
thin `FROM hpretl/iic-osic-tools:<tag>` layer and commit it. Check the
[tool list](https://github.com/iic-jku/iic-osic-tools#3-installed-tools) first —
gdsfactory, gdspy, pygmid, pyuvm, spicebind, cace, and chipify are already there.

---

## Bumping the pin

Change `OSIC_TOOLS_TAG` in `versions.env` — one number, one place. Then:

`make container` then stops, because the helper checkout disagrees with the pin:

```
iic-osic-tools is at 2026.07, but versions.env pins 2026.11.
    git -C ../iic-osic-tools fetch --tags && git -C ../iic-osic-tools checkout 2026.11
```

Run that yourself, then `make container` again to pull the new image. The
deliberate friction is the point: the image and the start scripts move together,
never independently. Re-run the smoke test after any bump.
