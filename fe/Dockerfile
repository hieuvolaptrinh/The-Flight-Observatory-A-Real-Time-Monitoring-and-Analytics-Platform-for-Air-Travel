FROM node:22-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:2002/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN npm run build

EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
