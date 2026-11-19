"""Meeting, attendance, quorum and decision endpoints."""
from datetime import date, datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.database.db import get_session
from app.database.models import (
    Council, CouncilComposition, CouncilMember, Dissertation, Meeting, MeetingAttendance,
    Protocol, Vote, Decision, User,
)

router = APIRouter(prefix="/api/meetings", tags=["Заседания"])


class MeetingCreate(BaseModel):
    council_id: int
    dissertation_id: Optional[int] = None
    meeting_date: datetime
    status: str = "planned"


class MeetingOut(MeetingCreate):
    model_config = ConfigDict(from_attributes=True)
    meeting_id: int
    quorum_required: int
    quorum_met: Optional[bool]


class AttendanceInput(BaseModel):
    present_member_ids: list[int] = Field(default_factory=list)


class QuorumOut(BaseModel):
    meeting_id: int
    quorum_met: bool
    present_count: int
    council_size: int
    required_count: int
    profile_doctors_present: int
    profile_doctors_required: int = 3
    reasons: list[str]


class ProtocolInput(BaseModel):
    votes: dict[int, str]
    created_by: int = 1
    signed_date: date = Field(default_factory=date.today)


class DecisionOut(BaseModel):
    protocol_id: int
    protocol_number: str
    granted: bool
    votes_for: int
    votes_against: int
    abstentions: int
    decision_id: int
    result: str


@router.get("", response_model=list[MeetingOut])
def list_meetings(session: Session = Depends(get_session)):
    return session.exec(select(Meeting).order_by(Meeting.meeting_date.desc())).all()


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate, session: Session = Depends(get_session)):
    if session.get(Council, payload.council_id) is None:
        raise HTTPException(status_code=404, detail="Совет не найден")
    if payload.dissertation_id is not None and session.get(Dissertation, payload.dissertation_id) is None:
        raise HTTPException(status_code=404, detail="Диссертационное дело не найдено")
    meeting = Meeting(
        council_id=payload.council_id,
        dissertation_id=payload.dissertation_id,
        meeting_date=payload.meeting_date.isoformat(timespec="seconds"),
        status=payload.status,
    )
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def _quorum(session: Session, meeting: Meeting) -> QuorumOut:
    members = session.exec(select(CouncilComposition).where(
        CouncilComposition.council_id == meeting.council_id,
        CouncilComposition.date_to.is_(None),
    )).all()
    member_ids = {item.member_id for item in members}
    present = session.exec(select(MeetingAttendance).where(
        MeetingAttendance.meeting_id == meeting.meeting_id,
        MeetingAttendance.is_present.is_(True),
    )).all()
    present_ids = {item.member_id for item in present}
    present_ids &= member_ids
    required = ceil(len(member_ids) * 2 / 3) if member_ids else 0
    dissertation = session.get(Dissertation, meeting.dissertation_id) if meeting.dissertation_id else None
    profile_doctors = 0
    if dissertation:
        for member_id in present_ids:
            member = session.get(CouncilMember, member_id)
            if member and member.degree == "doctor" and member.specialty_id == dissertation.specialty_id:
                profile_doctors += 1
    reasons = []
    if len(present_ids) < required:
        reasons.append(f"Нужно не менее {required} членов совета, присутствуют {len(present_ids)}")
    if profile_doctors < 3:
        reasons.append(f"Нужно не менее 3 профильных докторов наук, присутствуют {profile_doctors}")
    return QuorumOut(
        meeting_id=meeting.meeting_id,
        quorum_met=not reasons,
        present_count=len(present_ids),
        council_size=len(member_ids),
        required_count=required,
        profile_doctors_present=profile_doctors,
        reasons=reasons,
    )


@router.get("/{meeting_id}/quorum", response_model=QuorumOut)
def check_quorum(meeting_id: int, session: Session = Depends(get_session)):
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    return _quorum(session, meeting)


@router.put("/{meeting_id}/attendance", response_model=QuorumOut)
def save_attendance(meeting_id: int, payload: AttendanceInput, session: Session = Depends(get_session)):
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    composition = session.exec(select(CouncilComposition).where(
        CouncilComposition.council_id == meeting.council_id,
        CouncilComposition.date_to.is_(None),
    )).all()
    council_member_ids = {row.member_id for row in composition}
    if not set(payload.present_member_ids) <= council_member_ids:
        raise HTTPException(status_code=422, detail="Явка может быть указана только для членов состава этого совета")
    existing = session.exec(select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)).all()
    for row in existing:
        session.delete(row)
    for row in composition:
        session.add(MeetingAttendance(
            meeting_id=meeting_id,
            member_id=row.member_id,
            is_present=row.member_id in payload.present_member_ids,
        ))
    session.commit()
    result = _quorum(session, meeting)
    meeting.quorum_required = result.required_count
    meeting.quorum_met = result.quorum_met
    session.add(meeting)
    session.commit()
    return result


@router.post("/{meeting_id}/protocol", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create_protocol(meeting_id: int, payload: ProtocolInput, session: Session = Depends(get_session)):
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    quorum = _quorum(session, meeting)
    if not quorum.quorum_met:
        raise HTTPException(status_code=409, detail="Нельзя оформить протокол без кворума")
    if meeting.dissertation_id is None:
        raise HTTPException(status_code=409, detail="К заседанию не привязано диссертационное дело")
    if session.exec(select(Protocol).where(Protocol.meeting_id == meeting_id)).first():
        raise HTTPException(status_code=409, detail="Протокол для заседания уже существует")
    present_ids = {row.member_id for row in session.exec(select(MeetingAttendance).where(
        MeetingAttendance.meeting_id == meeting_id,
        MeetingAttendance.is_present.is_(True),
    )).all()}
    if set(payload.votes) != present_ids:
        raise HTTPException(status_code=422, detail="Нужно указать голос каждого присутствующего члена совета")
    allowed = {"for", "against", "abstain"}
    if set(payload.votes.values()) - allowed:
        raise HTTPException(status_code=422, detail="Допустимые голоса: for, against, abstain")
    if session.get(User, payload.created_by) is None:
        raise HTTPException(status_code=404, detail="Пользователь, оформляющий протокол, не найден")

    protocol_year = datetime.fromisoformat(meeting.meeting_date).year
    protocol_number = f"{protocol_year}/{meeting_id:03d}"
    protocol = Protocol(
        meeting_id=meeting_id,
        protocol_number=protocol_number,
        signed_date=payload.signed_date,
        created_by=payload.created_by,
    )
    session.add(protocol)
    session.flush()
    for member_id, vote_value in payload.votes.items():
        session.add(Vote(protocol_id=protocol.protocol_id, member_id=member_id, vote_value=vote_value))
    votes_for = sum(value == "for" for value in payload.votes.values())
    votes_against = sum(value == "against" for value in payload.votes.values())
    abstentions = sum(value == "abstain" for value in payload.votes.values())
    granted = votes_for >= ceil(len(payload.votes) * 2 / 3)
    result = "granted" if granted else "denied"
    decision = Decision(
        dissertation_id=meeting.dissertation_id,
        meeting_id=meeting_id,
        decision_text="Степень присуждена" if granted else "В присуждении степени отказано",
        result=result,
        decision_date=payload.signed_date,
    )
    session.add(decision)
    dissertation = session.get(Dissertation, meeting.dissertation_id)
    dissertation.status = "defended" if granted else "rejected"
    meeting.status = "held"
    session.add(meeting)
    session.commit()
    session.refresh(protocol)
    session.refresh(decision)
    return DecisionOut(
        protocol_id=protocol.protocol_id,
        protocol_number=protocol.protocol_number,
        granted=granted,
        votes_for=votes_for,
        votes_against=votes_against,
        abstentions=abstentions,
        decision_id=decision.decision_id,
        result=result,
    )
