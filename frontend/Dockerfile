FROM node:18-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG BACKEND_URL=http://superscrape-backend:8001
ENV BACKEND_URL=${BACKEND_URL}

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
