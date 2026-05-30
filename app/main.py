from fastapi import FastAPI
from app.api.routes import health, customers, imports

app = FastAPI(
    title="Partner Customer Import API",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(customers.router, prefix="/customers", tags=["customers"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])