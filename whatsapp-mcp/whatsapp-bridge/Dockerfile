FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -trimpath -ldflags='-s -w' -o /out/whatsapp-bridge .

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 bridge \
    && useradd --uid 10001 --gid bridge --home-dir /app --no-create-home --shell /usr/sbin/nologin bridge \
    && mkdir -p /app/store /app/media/outbox /run/secrets \
    && chown -R bridge:bridge /app
WORKDIR /app
COPY --from=build /out/whatsapp-bridge /usr/local/bin/whatsapp-bridge
ENV HOME=/app WHATSAPP_MEDIA_ROOTS=/app/media/outbox
USER bridge:bridge
ENTRYPOINT ["/usr/local/bin/whatsapp-bridge"]
