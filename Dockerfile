FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY api ./api
COPY helpers ./helpers
COPY datasets ./datasets
COPY *.db ./
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT} api.index:app"]
