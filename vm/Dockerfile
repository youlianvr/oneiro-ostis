# Oneiro's isolated environment: office work with no desktop.
#
# This is a process sandbox inside Docker Desktop's WSL2 VM, not a separate
# machine: it shares that kernel. The job code mounts no host directory — sources
# go in and results come out with `docker cp` — so the environment cannot reach
# the owner's files. The GUI agent (screen, click, typing) is out of scope and
# recorded as a development direction; see docs/READY-2026-10-12.md, work W1.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer libreoffice-calc libreoffice-impress \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# The container idles and the suite is driven with `docker exec --convert-to`, so
# there is no server and no port: `--network none` at run time costs it nothing.
WORKDIR /work
CMD ["sleep", "infinity"]
