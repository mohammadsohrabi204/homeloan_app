FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# کتابخانه‌های سیستمی موردنیاز psycopg2 و Pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# اجرای برنامه با کاربر غیر root (اگر مهاجم کدی اجرا کند، دسترسی root ندارد)
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# مهاجرت دیتابیس + جمع‌آوری فایل‌های استاتیک، سپس اجرای سرور
CMD python manage.py migrate --noinput \
    && python manage.py collectstatic --noinput \
    && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
