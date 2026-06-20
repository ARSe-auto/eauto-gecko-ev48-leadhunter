FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501
# $PORT lo inyecta el host (Render/Railway/Fly); 8501 por defecto en local.
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
