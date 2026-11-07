from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DEFAULT_SETTINGS, User
from app.schemas import LoginIn, SignupIn, TokenOut, UserOut
from app.security import create_token, current_user, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/signup", response_model=TokenOut)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name, password_hash=hash_password(body.password),
                settings=dict(DEFAULT_SETTINGS))
    db.add(user)
    db.commit()
    return TokenOut(token=create_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(user)
    db.commit()
