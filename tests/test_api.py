import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db import Base, get_db
from app.config import DATABASE_URL

# For testing, we can use the same database, but let's test directly using the API endpoints
client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_auth_flow():
    # 1. Test Signup (Role defaults to EMPLOYEE)
    signup_data = {
        "name": "Integration Test User",
        "email": "testuser@assetflow.com",
        "password": "testpassword123",
        "department_id": None
    }
    response = client.post("/api/v1/auth/signup", json=signup_data)
    # If already exists from previous runs, it's fine, we proceed
    assert response.status_code in [201, 400]
    
    # 2. Test Login
    login_data = {
        "username": "testuser@assetflow.com",
        "password": "testpassword123"
    }
    response = client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()
    assert "access_token" in token
    assert token["user"]["role"] == "EMPLOYEE"
    
    # 3. Test profile fetch
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "testuser@assetflow.com"
