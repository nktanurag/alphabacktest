# One image serves the API and the built frontend.

FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/alphabacktest backend/alphabacktest
COPY backend/docqa backend/docqa
COPY --from=frontend /build/frontend/dist frontend/dist
RUN useradd --create-home app && chown -R app /app
USER app
WORKDIR /app/backend
ENV PORT=8080
EXPOSE 8080
# Hosts such as Render set PORT; the default suits local `docker run -p 8080:8080`.
CMD ["sh", "-c", "uvicorn alphabacktest.api:app --host 0.0.0.0 --port ${PORT}"]
