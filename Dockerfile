FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8091
# --no-access-log : le middleware maison émet déjà une ligne JSON par requête,
# celle d'uvicorn ferait doublon.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091", "--no-access-log"]
