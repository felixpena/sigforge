FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

RUN rm -rf node_modules/.vite && npm run build

EXPOSE 3000

CMD ["npx", "serve", "-s", "dist", "-l", "3000"]
