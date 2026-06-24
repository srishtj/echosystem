from fastapi import FastAPI

app = FastAPI(title="EchoSystem-AI Ingestion")

@app.get("/health")

def health():
    return {"status": "ok"}