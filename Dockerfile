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


COPY . .


USER as-user
RUN action-server import --datadir=/action-server/datadir


USER as-user


ENV HOME=/home/as-user

EXPOSE 8080

CMD ["action-server", "start", "--address", "0.0.0.0", "--port", "8080", "--datadir=/action-server/datadir", "--actions-sync=false", "--min-processes", "1", "--max-processes", "3", "--reuse-processes", "--full-openapi-spec"]