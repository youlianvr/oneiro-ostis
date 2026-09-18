FROM oneiro-base:latest AS base

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
RUN ./scripts/install_cxx_problem_solver.sh

FROM devdeps AS builder
COPY . .
RUN --mount=type=cache,target=/ccache/ cmake --preset release && cmake --build --preset release

# Gathering all artifacts together
FROM base AS final

COPY --from=builder /example-app/scripts /example-app/scripts
COPY --from=builder /example-app/install /example-app/install
COPY --from=builder /example-app/build/Release/extensions /example-app/build/Release/extensions
COPY --from=builder /example-app/.venv /example-app/.venv

WORKDIR /example-app

EXPOSE 8090

ENTRYPOINT ["/usr/bin/tini", "--", "/example-app/scripts/docker_entrypoint.sh"]
