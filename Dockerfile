# Dùng Python base image
FROM python:3.11-slim

# Tạo thư mục app
WORKDIR /app

# Cài đặt các dependencies của hệ thống
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements trước (tối ưu cache build)
COPY requirements.txt .

# Cài dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code
COPY . .

# Thiết lập biến môi trường
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Khai báo cổng (không thực sự cần thiết cho worker nhưng là thói quen tốt)
EXPOSE 8000

# Khởi chạy bot
CMD ["python3", "telegram_bot.py"]

