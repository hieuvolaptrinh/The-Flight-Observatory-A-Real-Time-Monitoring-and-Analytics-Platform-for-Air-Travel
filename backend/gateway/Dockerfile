FROM nginx:stable-alpine

ENV FRONTEND_ORIGIN=http://localhost:3000

COPY default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1
