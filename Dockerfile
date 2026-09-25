FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package.json .
COPY ./.next* ./.next
COPY next.config.ts .
COPY tsconfig.json .
COPY next.config.ts .
RUN npm install

# Build the application
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "dev"]
