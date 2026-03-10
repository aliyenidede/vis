FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY src/ src/
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/output

CMD ["python", "-m", "vis.scheduler"]
