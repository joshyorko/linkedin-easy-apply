# Native CP312 Bookworm fixture. Start containers with --init and loopback publish.
FROM python@sha256:9bb659dc6d5218917236f3711e866a5634bb4c2f208de9d4533aa4863f57c1d3 AS runtime-base

RUN test "$(dpkg --print-architecture)" = arm64

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl procps libatomic1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -fsSL \
      https://files.pythonhosted.org/packages/82/e6/f55e8b89fbaa3af81f77f6244ff6a4236e85b595acd8e0e2db03faf187d9/actions_runtime-1.1.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
      -o /tmp/actions_runtime-1.1.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
    && echo '6ba7796dc2520fbffe12e9c023efb915144a2dda0b1865e0d12dd1faaf421a7d  /tmp/actions_runtime-1.1.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl' | sha256sum -c - \
    && python -m pip install --no-cache-dir \
      /tmp/actions_runtime-1.1.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
      actions-core==1.1.0 robocorp-browser==2.3.5 psycopg2-binary==2.9.11 \
    && python -m playwright install-deps chromium \
    && rm /tmp/actions_runtime-1.1.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
    && useradd --create-home --uid 10001 action-user \
    && mkdir -p /opt/fixture /opt/application /var/lib/easy-apply/home \
      /var/lib/easy-apply/datadir /var/lib/easy-apply/output \
      /var/lib/easy-apply/browser_context /var/lib/easy-apply/uploaded_files \
    && chown -R 10001:10001 /opt/fixture /opt/application /var/lib/easy-apply

FROM runtime-base AS application
COPY --chown=10001:10001 package.yaml /opt/application/package.yaml
COPY --chown=10001:10001 src /opt/application/src
COPY --chmod=0755 deployment/start.sh /usr/local/bin/start-easy-apply
RUN ln -s /var/lib/easy-apply/output /opt/application/output \
    && ln -s /var/lib/easy-apply/browser_context /opt/application/browser_context \
    && ln -s /var/lib/easy-apply/uploaded_files /opt/application/uploaded_files
ENV HOME=/var/lib/easy-apply/home \
    ACTIONS_HOME=/var/lib/easy-apply/home/.actions \
    SEMA4AI_HOME=/var/lib/easy-apply/home/.actions \
    ROBOCORP_HOME=/var/lib/easy-apply/home/.actions \
    PYTHONPATH=/opt/application/src \
    SEMA4AI_OPTIMIZE_FOR_CONTAINER=1
USER 10001:10001
WORKDIR /opt/application
RUN action-server import --dir /opt/application --datadir /tmp/easy-apply-import \
    && rm -rf /tmp/easy-apply-import
ENTRYPOINT ["/usr/local/bin/start-easy-apply"]

FROM runtime-base AS fixture

COPY --chown=10001:10001 qualification/package.yaml qualification/my_actions.py /opt/fixture/
ENV HOME=/home/action-user \
    ACTIONS_HOME=/home/action-user/.actions \
    SEMA4AI_HOME=/home/action-user/.actions \
    ROBOCORP_HOME=/home/action-user/.actions
USER 10001:10001
WORKDIR /opt/fixture
ENTRYPOINT ["action-server"]
CMD ["--help"]
