# Production Keycloak for IronVision AI: optimized build (Postgres + health) so the container runs `start --optimized`.
# Secrets/DB credentials are runtime env only – never baked into the image.
ARG KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:26.8.1
FROM ${KEYCLOAK_IMAGE} AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=false
RUN /opt/keycloak/bin/kc.sh build

FROM ${KEYCLOAK_IMAGE}
COPY --from=builder /opt/keycloak/ /opt/keycloak/
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized"]
