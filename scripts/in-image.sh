#!/bin/sh
# Run one command inside the pinned tool image, with its tool paths and this
# repository's PDK selection already in place.
#
# Contract: invoke it through a shell -- the tree carries this file without an
# executable bit, as it does every script here -- and from the repository root,
# with the image already built. The tree is mounted where the image's own
# designs directory expects it, so the command sees the same paths the
# container does and writes its output back into the checkout. A tool the
# image is supposed to have but has not is a failure here rather than a skip.
set -eu

[ "$#" -gt 0 ] || { echo "usage: $0 <command> [args...]" >&2; exit 2; }

# The mount point is the repository's own directory name, which is what the
# container's designs directory is bound to and therefore what every path
# inside it starts with.
name=$(basename "$PWD")

exec docker run --rm --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -e SAR_REQUIRE_TOOLS=1 \
  -v "$PWD:/foss/designs/$name" -w "/foss/designs/$name" \
  --entrypoint /bin/bash "$(make -s image-name)" -c '
    # The image sets its own paths from scripts that read unset variables, so
    # the strictness this script keeps for itself stops at its boundary.
    set -e
    for f in /dockerstartup/scripts/env.sh /headless/.bashrc; do
      [ -f "$f" ] && . "$f" || true
    done
    . ./pdk.env
    exec "$@"' bash "$@"
