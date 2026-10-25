FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY shared ./shared
COPY services ./services
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
ENV PYTHONUNBUFFERED=1
ENV SERVICE=personnel
CMD ["sh", "-c", "SERVICE=$SERVICE alembic upgrade head && uvicorn services.$SERVICE.app:app --host 0.0.0.0 --port 8000"]
