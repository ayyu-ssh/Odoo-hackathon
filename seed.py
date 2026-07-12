from sqlalchemy.orm import Session
from datetime import datetime, date
from app.db import SessionLocal, Base, engine
from app.models import User, Department, AssetCategory, Asset, UserRole, UserStatus, AssetStatus
from app.auth import get_password_hash

def seed_db():
    print("Beginning database seeding...")
    
    # Ensure tables are created
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Create Users
        admin = db.query(User).filter(User.email == "admin@assetflow.com").first()
        if not admin:
            admin = User(
                name="System Admin",
                email="admin@assetflow.com",
                hashed_password=get_password_hash("admin123"),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE
            )
            db.add(admin)
            db.flush()
            print("Created Admin user: admin@assetflow.com")
            
        manager = db.query(User).filter(User.email == "manager@assetflow.com").first()
        if not manager:
            manager = User(
                name="Asset Manager",
                email="manager@assetflow.com",
                hashed_password=get_password_hash("manager123"),
                role=UserRole.ASSET_MANAGER,
                status=UserStatus.ACTIVE
            )
            db.add(manager)
            db.flush()
            print("Created Asset Manager user: manager@assetflow.com")

        head_it = db.query(User).filter(User.email == "head_it@assetflow.com").first()
        if not head_it:
            head_it = User(
                name="Head of IT",
                email="head_it@assetflow.com",
                hashed_password=get_password_hash("head123"),
                role=UserRole.DEPARTMENT_HEAD,
                status=UserStatus.ACTIVE
            )
            db.add(head_it)
            db.flush()
            print("Created Dept Head: head_it@assetflow.com")

        priya = db.query(User).filter(User.email == "priya@assetflow.com").first()
        if not priya:
            priya = User(
                name="Priya Sharma",
                email="priya@assetflow.com",
                hashed_password=get_password_hash("employee123"),
                role=UserRole.EMPLOYEE,
                status=UserStatus.ACTIVE
            )
            db.add(priya)
            db.flush()
            print("Created Employee: priya@assetflow.com")

        raj = db.query(User).filter(User.email == "raj@assetflow.com").first()
        if not raj:
            raj = User(
                name="Raj Patel",
                email="raj@assetflow.com",
                hashed_password=get_password_hash("employee123"),
                role=UserRole.EMPLOYEE,
                status=UserStatus.ACTIVE
            )
            db.add(raj)
            db.flush()
            print("Created Employee: raj@assetflow.com")

        # 2. Create Departments
        it_dept = db.query(Department).filter(Department.name == "IT Infrastructure").first()
        if not it_dept:
            it_dept = Department(
                name="IT Infrastructure",
                head_id=head_it.id,
                status=UserStatus.ACTIVE
            )
            db.add(it_dept)
            db.flush()
            print("Created Department: IT Infrastructure")

        ops_dept = db.query(Department).filter(Department.name == "Operations").first()
        if not ops_dept:
            ops_dept = Department(
                name="Operations",
                parent_id=it_dept.id if it_dept else None,
                status=UserStatus.ACTIVE
            )
            db.add(ops_dept)
            db.flush()
            print("Created Department: Operations (Child of IT)")

        # Link departments back to users
        if head_it and it_dept:
            head_it.department_id = it_dept.id
        if priya and it_dept:
            priya.department_id = it_dept.id
        if raj and ops_dept:
            raj.department_id = ops_dept.id

        # 3. Create Categories
        electronics = db.query(AssetCategory).filter(AssetCategory.name == "Electronics").first()
        if not electronics:
            electronics = AssetCategory(
                name="Electronics",
                fields_schema={"warranty_period_months": "int", "brand": "str"}
            )
            db.add(electronics)
            db.flush()
            print("Created Category: Electronics")

        furniture = db.query(AssetCategory).filter(AssetCategory.name == "Furniture").first()
        if not furniture:
            furniture = AssetCategory(
                name="Furniture",
                fields_schema={"material": "str"}
            )
            db.add(furniture)
            db.flush()
            print("Created Category: Furniture")

        vehicles = db.query(AssetCategory).filter(AssetCategory.name == "Vehicles").first()
        if not vehicles:
            vehicles = AssetCategory(
                name="Vehicles",
                fields_schema={"license_plate": "str", "fuel_type": "str"}
            )
            db.add(vehicles)
            db.flush()
            print("Created Category: Vehicles")

        # 4. Create Assets
        asset_laptop = db.query(Asset).filter(Asset.serial_number == "SN-MBP-9923").first()
        if not asset_laptop and electronics:
            asset_laptop = Asset(
                name="MacBook Pro 16-inch",
                category_id=electronics.id,
                asset_tag="AF-0001",
                serial_number="SN-MBP-9923",
                acquisition_date=date(2025, 6, 15),
                acquisition_cost=2499.99,
                condition="Excellent",
                location="IT Lab Room 102",
                is_shared_bookable=False,
                status=AssetStatus.AVAILABLE,
                category_attributes={"warranty_period_months": 24, "brand": "Apple"}
            )
            db.add(asset_laptop)
            print("Created Asset: MacBook Pro 16-inch (AF-0001)")

        asset_room = db.query(Asset).filter(Asset.serial_number == "SN-CONF-B2").first()
        if not asset_room and furniture:
            asset_room = Asset(
                name="Conference Room B2",
                category_id=furniture.id,
                asset_tag="AF-0002",
                serial_number="SN-CONF-B2",
                acquisition_date=date(2024, 1, 10),
                acquisition_cost=5000.00,
                condition="Good",
                location="Ground Floor Main Block",
                is_shared_bookable=True,
                status=AssetStatus.AVAILABLE,
                category_attributes={"material": "Glass and Mahogany"}
            )
            db.add(asset_room)
            print("Created Asset: Conference Room B2 (AF-0002 - Shared/Bookable)")

        db.commit()
        print("Database seeding completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
