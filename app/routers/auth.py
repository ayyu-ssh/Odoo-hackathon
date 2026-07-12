from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, UserRole, UserStatus
from app.schemas import UserCreate, UserResponse, Token, LoginRequest
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.crud import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """Signup screen - creates a standard Employee account (no self-promoting)."""
    # Verify unique email
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email is already registered"
        )
    
    # Hash password securely
    hashed_pwd = get_password_hash(user_in.password)
    
    # Create the user profile
    db_user = User(
        name=user_in.name,
        email=user_in.email,
        hashed_password=hashed_pwd,
        role=UserRole.EMPLOYEE,  # Enforce non-elevated signup role
        status=UserStatus.ACTIVE,
        department_id=user_in.department_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    log_activity(db, db_user.id, "USER_SIGNUP", {"email": db_user.email})
    return db_user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    """Authenticate via email/password (OAuth2 compatible form-data for Swagger UI)."""
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Account is deactivated"
        )
        
    access_token = create_access_token(data={"sub": user.email})
    log_activity(db, user.id, "USER_LOGIN")
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.post("/login/json", response_model=Token)
def login_json(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate via JSON payload."""
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Account is deactivated"
        )
        
    access_token = create_access_token(data={"sub": user.email})
    log_activity(db, user.id, "USER_LOGIN")
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """Retrieve details of currently authenticated user session."""
    return current_user
