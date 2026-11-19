"""CRUD endpoints for the system's reference and case data."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field as SchemaField
from sqlmodel import Session, select

from app.database.db import get_session
from app.database.models import Candidate, Council, CouncilComposition, CouncilMember, Dissertation, Specialty

router = APIRouter(prefix="/api", tags=["Справочники и дела"])


class SpecialtyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    specialty_id: int
    code: str
    name: str


class MemberCreate(BaseModel):
    full_name: str = SchemaField(min_length=3, max_length=200)
    degree: str = SchemaField(pattern="^(doctor|candidate)$")
    academic_title: Optional[str] = None
    specialty_id: int


class MemberOut(MemberCreate):
    model_config = ConfigDict(from_attributes=True)
    member_id: int


class CandidateCreate(BaseModel):
    full_name: str = SchemaField(min_length=3, max_length=200)
    degree_sought: str = SchemaField(pattern="^(doctor|candidate)$")
    specialty_id: int
    contact_info: Optional[str] = None


class CandidateOut(CandidateCreate):
    model_config = ConfigDict(from_attributes=True)
    candidate_id: int


class CouncilCreate(BaseModel):
    number: str = SchemaField(min_length=3, max_length=40)
    name: str = SchemaField(min_length=3, max_length=240)
    department: str = SchemaField(min_length=2, max_length=240)
    status: str = "active"


class CouncilOut(CouncilCreate):
    model_config = ConfigDict(from_attributes=True)
    council_id: int


class DissertationCreate(BaseModel):
    candidate_id: int
    council_id: int
    specialty_id: int
    topic: str = SchemaField(min_length=8, max_length=500)
    status: str = "submitted"
    submitted_at: date = SchemaField(default_factory=date.today)


class DissertationOut(DissertationCreate):
    model_config = ConfigDict(from_attributes=True)
    dissertation_id: int


def _ensure_specialty(session: Session, specialty_id: int) -> None:
    if session.get(Specialty, specialty_id) is None:
        raise HTTPException(status_code=404, detail="Специальность не найдена")


@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(session: Session = Depends(get_session)):
    return session.exec(select(Specialty).order_by(Specialty.code)).all()


@router.get("/members", response_model=list[MemberOut])
def list_members(q: Optional[str] = None, session: Session = Depends(get_session)):
    statement = select(CouncilMember).order_by(CouncilMember.full_name)
    if q:
        statement = statement.where(CouncilMember.full_name.contains(q))
    return session.exec(statement).all()


@router.get("/members/{member_id}", response_model=MemberOut)
def get_member(member_id: int, session: Session = Depends(get_session)):
    member = session.get(CouncilMember, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Член совета не найден")
    return member


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreate, session: Session = Depends(get_session)):
    _ensure_specialty(session, payload.specialty_id)
    member = CouncilMember.model_validate(payload)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.put("/members/{member_id}", response_model=MemberOut)
def update_member(member_id: int, payload: MemberCreate, session: Session = Depends(get_session)):
    member = session.get(CouncilMember, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Член совета не найден")
    _ensure_specialty(session, payload.specialty_id)
    for field, value in payload.model_dump().items():
        setattr(member, field, value)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: int, session: Session = Depends(get_session)):
    member = session.get(CouncilMember, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Член совета не найден")
    session.delete(member)
    session.commit()


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(session: Session = Depends(get_session)):
    return session.exec(select(Candidate).order_by(Candidate.full_name)).all()


@router.post("/candidates", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(payload: CandidateCreate, session: Session = Depends(get_session)):
    _ensure_specialty(session, payload.specialty_id)
    candidate = Candidate.model_validate(payload)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


@router.get("/councils", response_model=list[CouncilOut])
def list_councils(session: Session = Depends(get_session)):
    return session.exec(select(Council).order_by(Council.number)).all()


@router.post("/councils", response_model=CouncilOut, status_code=status.HTTP_201_CREATED)
def create_council(payload: CouncilCreate, session: Session = Depends(get_session)):
    council = Council.model_validate(payload)
    session.add(council)
    session.commit()
    session.refresh(council)
    return council


@router.get("/councils/{council_id}/members", response_model=list[MemberOut])
def list_council_members(council_id: int, session: Session = Depends(get_session)):
    if session.get(Council, council_id) is None:
        raise HTTPException(status_code=404, detail="Совет не найден")
    composition = session.exec(select(CouncilComposition).where(
        CouncilComposition.council_id == council_id,
        CouncilComposition.date_to.is_(None),
    )).all()
    member_ids = [row.member_id for row in composition]
    return session.exec(select(CouncilMember).where(CouncilMember.member_id.in_(member_ids)).order_by(CouncilMember.full_name)).all() if member_ids else []


@router.get("/dissertations", response_model=list[DissertationOut])
def list_dissertations(session: Session = Depends(get_session)):
    return session.exec(select(Dissertation).order_by(Dissertation.submitted_at.desc())).all()


@router.post("/dissertations", response_model=DissertationOut, status_code=status.HTTP_201_CREATED)
def create_dissertation(payload: DissertationCreate, session: Session = Depends(get_session)):
    for model, record_id, label in (
        (Candidate, payload.candidate_id, "Соискатель"),
        (Council, payload.council_id, "Совет"),
        (Specialty, payload.specialty_id, "Специальность"),
    ):
        if session.get(model, record_id) is None:
            raise HTTPException(status_code=404, detail=f"{label} не найдена")
    dissertation = Dissertation.model_validate(payload)
    session.add(dissertation)
    session.commit()
    session.refresh(dissertation)
    return dissertation
