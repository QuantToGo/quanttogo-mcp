FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

COPY dist/ ./dist/
COPY server.json ./
COPY README.md ./

EXPOSE 80

CMD ["node", "dist/index.js"]
