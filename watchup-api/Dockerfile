FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN groupadd --gid 2001 watchup \
    && useradd --uid 2001 --gid watchup --no-create-home --shell /usr/sbin/nologin watchup

ENV APP_ENV=production \
    WATCHUP_EVENT_STORE=postgres \
    WATCHUP_API_HOST=0.0.0.0 \
    PYTHONDONTWRITEBYTECODE=1
USER watchup
CMD ["python", "app.py"]
