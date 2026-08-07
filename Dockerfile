FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion/ ingestion/
COPY extraction/ extraction/
COPY graph/ graph/
COPY retrieval/ retrieval/
COPY agents/ agents/
COPY finance/ finance/
COPY social/ social/

EXPOSE 8000

CMD ["uvicorn", "ingestion.main:app", "--host", "0.0.0.0", "--port", "8000"]
