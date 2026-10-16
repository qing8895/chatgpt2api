FROM mcr.microsoft.com/playwright/python:v1.58.0-noble
WORKDIR /solver
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install --no-shell chromium
COPY app.py .
USER pwuser
CMD ["xvfb-run", "-a", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
