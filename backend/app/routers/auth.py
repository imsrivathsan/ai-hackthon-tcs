import secrets
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_PERSONAS = [
    {
        "id": "analyst-001",
        "name": "Sarah Jenkins",
        "email": "analyst@meridian.intel",
        "role": "Senior Brokerage Analyst",
        "firm": "Meridian Commercial Risk",
        "avatar_initials": "SJ",
    },
    {
        "id": "producer-002",
        "name": "Michael Vance",
        "email": "producer@meridian.intel",
        "role": "Commercial Lines Producer",
        "firm": "Meridian Commercial Risk",
        "avatar_initials": "MV",
    },
    {
        "id": "director-003",
        "name": "Elena Rostova",
        "email": "director@meridian.intel",
        "role": "Risk Engineering Director",
        "firm": "Meridian Commercial Risk",
        "avatar_initials": "ER",
    },
]


class LoginRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = "Senior Brokerage Analyst"


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str
    firm: str
    avatar_initials: str


class LoginResponse(BaseModel):
    token: str
    user: UserProfile
    message: str


@router.get("/profiles", summary="Get predefined demo analyst profiles for quick sign-in")
def get_demo_profiles():
    return DEMO_PERSONAS


@router.post("/login", response_model=LoginResponse, summary="Analyst login authentication")
def login(req: LoginRequest):
    if not req.email or not req.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email/username and password are required.",
        )

    # Match predefined persona if available
    persona = next((p for p in DEMO_PERSONAS if p["email"].lower() == req.email.lower()), None)
    if not persona:
        # Generate profile for custom input
        name_part = req.email.split("@")[0].replace(".", " ").title()
        initials = "".join([w[0].upper() for w in name_part.split()[:2]]) or "AN"
        persona = {
            "id": f"analyst-{secrets.token_hex(4)}",
            "name": name_part or "Brokerage Analyst",
            "email": req.email,
            "role": req.role or "Senior Brokerage Analyst",
            "firm": "Meridian Commercial Risk",
            "avatar_initials": initials,
        }

    token = f"meridian_jwt_{secrets.token_hex(16)}"
    return LoginResponse(
        token=token,
        user=UserProfile(**persona),
        message="Authentication successful",
    )
