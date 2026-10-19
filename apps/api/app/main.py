
from fastapi import FastAPI

app = FastAPI(
    title="OpsBridge API",
    description="Enterprise Integration and Workflow Platform",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "opsbridge-api",
    }
