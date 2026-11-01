# Если Docker Hub недоступен, подставьте зеркало: docker build --build-arg BASE_IMAGE=<зеркало>/python:3.13-slim .
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pravo_mcp.py server_http.py ./
ENV PORT=8080
EXPOSE 8080
USER nobody
CMD ["python", "server_http.py"]
