from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from app.db import get_db
from app.models import User  # Import your User model
from app.schemas import UserCreate, Token, UserResponse  # Import your Pydantic schemas
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.config import settings
from sqlalchemy.future import select

router = APIRouter()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


@router.post("/register")
async def register(user: UserCreate):
    async with get_db() as db:  # Consume the async generator
        result = await db.execute(select(User).where(User.username == user.username))
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")

        hashed_password = pwd_context.hash(user.password)
        new_user = User(username=user.username, hashed_password=hashed_password)
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return {"msg": "User registered successfully"}



@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    async with get_db() as db:  # Consume the async generator
        result = await db.execute(select(User).where(User.username == form_data.username))
        user = result.scalars().first()
        if not user or not pwd_context.verify(form_data.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect username or password")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"sub": user.username, "user_id": user.id}, expires_delta=access_token_expires)
        return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}


@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: int = Depends(get_current_user_id)):
    async with get_db() as db:  # Consume the async generator
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": user.id, "username": user.username}
