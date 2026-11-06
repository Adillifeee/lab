from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database.db import get_session
from app.database.models import Role, User
from app.security import current_user, issue_token, require_roles, verify_password, hash_password

router = APIRouter(tags=["authentication"])


class LoginInput(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    role: str


@router.post("/auth/login")
def login(data: LoginInput, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == data.username)).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": issue_token(user.username), "token_type": "bearer", "username": user.username}


@router.get("/auth/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session)):
    role = session.get(Role, user.role_id)
    return {"id": user.id, "username": user.username, "role": role.name if role else ""}


@router.get("/roles")
def list_roles(session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))):
    return session.exec(select(Role).order_by(Role.name)).all()


@router.get("/users")
def list_users(session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))):
    users = session.exec(select(User).order_by(User.username)).all()
    return [{"id": u.id, "username": u.username, "role": session.get(Role, u.role_id).name, "is_active": u.is_active} for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))):
    role = session.exec(select(Role).where(Role.name == data.role)).first()
    if not role:
        raise HTTPException(400, "Unknown role")
    if session.exec(select(User).where(User.username == data.username)).first():
        raise HTTPException(409, "Username already exists")
    user = User(username=data.username, password_hash=hash_password(data.password), role_id=role.id)
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"id": user.id, "username": user.username, "role": role.name}
