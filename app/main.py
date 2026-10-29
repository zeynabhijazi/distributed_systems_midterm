
from fastapi import FastAPI

app = FastAPI(title="Distributed Storage Node")


@app.get("/")
def root():
    return {
        "message": "Storage Node is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "node": "node1"
    }
