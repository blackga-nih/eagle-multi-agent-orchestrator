FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY --from=builder /app/dist ./dist
COPY server.ts ./
EXPOSE 3002
ENV PORT=3002
CMD ["npx", "tsx", "server.ts"]
