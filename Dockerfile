FROM debian:bookworm-slim AS builder


RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*


ADD https://cdn.sema4.ai/action-server/releases/latest/linux64/action-server /usr/local/bin/action-server
RUN chmod +x /usr/local/bin/action-server

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y \
    procps \
    openssl \
    ca-certificates \
    supervisor \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxkbcommon0 \
    libasound2 \
    libcups2 \
    libdrm2 \
    libxshmfence1 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*


COPY --from=builder /usr/local/bin/action-server /usr/local/bin/action-server


RUN useradd -m as-user


RUN mkdir -p /action-server/datadir /action-server/actions \
    && chown -R as-user:as-user /action-server

WORKDIR /action-server/actions


RUN mkdir -p /action-server/actions/uploaded_files \
    && chown -R as-user:as-user /action-server/actions/uploaded_files

# Ensure files copied into the image are writable by the unprivileged user
# and create an output directory for logs and screenshots.
RUN mkdir -p /action-server/actions/output \
    && chown -R as-user:as-user /action-server/actions \
    && chown -R as-user:as-user /action-server/actions/uploaded_files

COPY . .

COPY scripts/start-action-server.sh /usr/local/bin/start-action-server.sh
COPY docker/supervisor/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/supervisor/action-server.conf /etc/supervisor/conf.d/action-server.conf
RUN chmod +x /usr/local/bin/start-action-server.sh


USER as-user
RUN action-server import --datadir=/action-server/datadir

USER as-user


ENV HOME=/home/as-user

EXPOSE 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
