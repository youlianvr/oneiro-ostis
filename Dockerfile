FROM ubuntu:noble@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15 AS base

# No undeclared locally tagged base image. Ubuntu digest and vendor binary
# hashes are pinned; apt packages still follow this distribution's repository.
RUN apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends -o Acquire::Retries=5 \
      tini curl ca-certificates ccache python3 python3-pip python3-venv cmake build-essential ninja-build
ENV CCACHE_DIR=/ccache
USER root

COPY scripts /example-app/scripts
COPY CMakePresets.json /example-app/CMakePresets.json
COPY CMakeLists.txt /example-app/CMakeLists.txt
COPY requirements.txt /example-app/requirements.txt

FROM base AS devdeps
WORKDIR /example-app

SHELL ["/bin/bash", "-c"]
RUN python3 -m venv /example-app/.venv && \
    source /example-app/.venv/bin/activate && \
    pip3 install --retries 5 -r /example-app/requirements.txt

# Install prebuilt sc-machine binaries (headers kept for our module build).
# Normalize CRLF -> LF: Windows checkouts give shell scripts \r endings.
RUN sed -i 's/\r$//' /example-app/scripts/*.sh && chmod +x /example-app/scripts/*.sh
RUN ./scripts/install_cxx_problem_solver.sh

FROM devdeps AS builder
COPY . .
# COPY . . restores CRLF endings from the Windows host — normalize again,
# the final image takes its scripts from here.
RUN sed -i 's/\r$//' scripts/*.sh && chmod +x scripts/*.sh
RUN --mount=type=cache,target=/ccache/ cmake --preset release && cmake --build --preset release --parallel 2

# Gathering all artifacts together
FROM base AS final

COPY --from=builder /example-app/scripts /example-app/scripts
COPY --from=builder /example-app/install /example-app/install
COPY --from=builder /example-app/build/Release/extensions /example-app/build/Release/extensions
COPY --from=builder /example-app/.venv /example-app/.venv

WORKDIR /example-app

EXPOSE 8090

ENTRYPOINT ["/usr/bin/tini", "--", "/example-app/scripts/docker_entrypoint.sh"]
