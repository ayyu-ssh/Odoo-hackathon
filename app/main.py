from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import Base, engine
from app.routers import (
    auth,
    departments,
    categories,
    employees,
    assets,
    allocations,
    bookings,
    maintenance,
    audits,
    reports,
    dashboard,
    notifications
)

# Initialize database tables on startup (perfect for prototype auto-generation)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AssetFlow API",
    description="Enterprise Asset & Resource Management System API",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under v1 API namespace
app.include_router(auth.router, prefix="/api/v1")
app.include_router(departments.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(employees.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(allocations.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")
app.include_router(maintenance.router, prefix="/api/v1")
app.include_router(audits.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "name": "AssetFlow Backend API",
        "status": "healthy",
        "docs_url": "/docs"
    }
