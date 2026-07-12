<<<<<<< HEAD
# AssetFlow - Enterprise Asset & Resource Management System

**AssetFlow** is a modular ERP backend designed to help organizations simplify, digitize, and automate how they track physical assets (equipment, laptops, vehicles) and manage bookings for shared spaces (rooms, vehicles) or equipment.

The backend is built with a clean, modular architecture using **FastAPI**, **PostgreSQL**, and **SQLAlchemy** (v2+).

---

## Features Implemented

1. **Authentication & Sign Up**: Role-based access control (Admin, Asset Manager, Department Head, Employee) using JWT and native `bcrypt` cryptography. Signups default to a non-elevated `EMPLOYEE` role.
2. **Dashboard & Operational Snapshots**: Scoped operational KPIs (Assets Available/Allocated, Active Bookings, Active Maintenance, Pending Transfers) and highlights overdue returns.
3. **Organization Setup**: Hierarchical department management, category-specific metadata definitions, and employee directories.
4. **Asset Directory**: General asset registry supporting serial tags, location tracking, and auto-generated asset tags (e.g. `AF-0001`, `AF-0002`).
5. **Asset Allocation & Conflicts**: Restricts asset allocations to prevent double-allocations. If already held, returns the current holder's info and prompts a direct **Transfer Workflow** instead.
6. **Resource Bookings**: Overlap-validated calendar booking system for shared bookable spaces (e.g., rooms) or equipment.
7. **Maintenance & Repairs Ticket System**: Lifecycle state machines (Pending -> Approved/Rejected -> Assigned -> In Progress -> Resolved) that automatically update asset statuses (e.g. to `UNDER_MAINTENANCE` and back to `AVAILABLE`).
8. **Structured Auditing Cycles**: Scope-based audit creation (by department/location), auditor assignments, discrepancy flag triggers, and auto-updating assets (e.g., marking missing ones as `LOST` on cycle close).
9. **Reports & Analytics**: Asset utilization, maintenance frequency logs, department allocations, and CSV downloads.
10. **System Logs & Alerts**: Admin audit trail and user inbox notification alerts.

---

## Directory Structure

```text
├── app/
│   ├── routers/            # API Route controllers for each feature module
│   │   ├── auth.py
│   │   ├── departments.py
│   │   ├── categories.py
│   │   ├── employees.py
│   │   ├── assets.py
│   │   ├── allocations.py
│   │   ├── bookings.py
│   │   ├── maintenance.py
│   │   ├── audits.py
│   │   ├── reports.py
│   │   ├── dashboard.py
│   │   └── notifications.py
│   ├── config.py           # Environment variables parser (pydantic/dotenv)
│   ├── db.py               # DB engine config, pool pre-ping, & session
│   ├── models.py           # SQLAlchemy declarative database schemas & relationships
│   ├── schemas.py          # Pydantic v2 schemas for request validation & responses
│   ├── auth.py             # Auth check helpers & native bcrypt crypto algorithms
│   ├── crud.py             # Activity logs and notification DB operations
│   └── main.py             # FastAPI bootstrap loader
├── tests/
│   └── test_api.py         # Integration test suite using TestClient
├── .env                    # Local database & JWT credentials (do not commit)
├── .gitignore              # Standard git exclusions
├── seed.py                 # Automatic database seeding script with mockup data
├── pyproject.toml          # Project metadata and dependencies list
└── README.md               # Documentation guide
```

---

## Quick Start Setup

### 1. Database Setup
Ensure you have a running PostgreSQL instance. It is highly recommended to create a dedicated database user for AssetFlow:
```sql
-- Connect to your PostgreSQL instance and create a dedicated user & database:
CREATE USER assetflow_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE assetflow_db OWNER assetflow_user;
```

If the database user is not a superuser or the database owner, you may need to explicitly grant it privileges on the public schema (particularly in PostgreSQL 15+):
```sql
GRANT ALL ON SCHEMA public TO assetflow_user;
```

### 2. Environment Configurations
Create a `.env` file in the root directory:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=assetflow_db
DB_USER=<db_username>
DB_PASSWORD=<db_password>

# Optionals
SECRET_KEY=your-secure-jwt-key
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 3. Dependencies Installation
Install dependencies in the virtual environment:
```powershell
uv pip install -e .
# Or standard pip install:
pip install -e .
```

### 4. Seed the Database
Run the seeding script to populate initial categories, departments, assets, and role accounts:
```powershell
python seed.py
```
*Creates initial user roles (Passwords: `admin123`, `manager123`, `head123`, `employee123`):*
- Admin: `admin@assetflow.com`
- Manager: `manager@assetflow.com`
- Department Head: `head_it@assetflow.com`
- Employee: `priya@assetflow.com` & `raj@assetflow.com`

---

## Running the Application

Start the FastAPI application:
```powershell
uvicorn app.main:app --reload
```

- **Interactive API Documentation**: Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser.
- **Alternative Redoc API Documentation**: Go to [http://localhost:8000/redoc](http://localhost:8000/redoc).

---

## Running Verification Tests
To run the automated integration test suite:
```powershell
pytest tests/
```
=======
# Oddo-hackathon
>>>>>>> db4667d603b6c1e4b6075598b2cf132435886046
