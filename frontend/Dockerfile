FROM node:20-alpine as builder

WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps
COPY . .
ARG REACT_APP_API_URL=http://localhost:8000/api/v1
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

# Production: serve with nginx
FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
