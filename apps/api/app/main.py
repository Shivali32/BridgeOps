from fastapi import FastAPI

app = FastAPI(
    title="BridgOps API",
    description="Retail Integration and Workflow Platform",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "bridgops-api",
    }