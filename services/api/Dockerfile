FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt        ./requirements-api.txt
COPY tools/generator/requirements.txt     ./requirements-gen.txt
RUN pip install --no-cache-dir -r requirements-api.txt -r requirements-gen.txt

COPY services/api/app          ./app
COPY tools/generator/generator ./generator

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
