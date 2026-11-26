# Local development only. Build upstream source because public image pulls are unavailable.
FROM golang:1.24.2-alpine AS build
RUN apk add --no-cache git
RUN timeout 120 git clone --depth 1 --branch RELEASE.2025-04-22T22-12-26Z https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /out/minio .
FROM alpine:3.21.3
RUN apk add --no-cache ca-certificates && addgroup -g 10001 minio && adduser -D -u 10001 -G minio minio && mkdir /data && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/licenses/minio/LICENSE
COPY --from=build /src/NOTICE /usr/share/licenses/minio/NOTICE
USER 10001:10001
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
