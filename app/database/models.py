"""SQLModel entities for the Academic Council Secretary information system."""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    role_id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    title: str
    users: list["User"] = Relationship(back_populates="role")


class User(SQLModel, table=True):
    __tablename__ = "users"
    user_id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    login: str = Field(index=True, unique=True)
    password_hash: str
    role_id: int = Field(foreign_key="roles.role_id")
    is_active: bool = True
    role: Optional[Role] = Relationship(back_populates="users")


class Specialty(SQLModel, table=True):
    __tablename__ = "specialties"
    specialty_id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    council_members: list["CouncilMember"] = Relationship(back_populates="specialty")
    candidates: list["Candidate"] = Relationship(back_populates="specialty")


class CouncilMember(SQLModel, table=True):
    __tablename__ = "council_members"
    member_id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True)
    degree: str
    academic_title: Optional[str] = None
    specialty_id: int = Field(foreign_key="specialties.specialty_id")
    user_id: Optional[int] = Field(default=None, foreign_key="users.user_id", unique=True)
    specialty: Optional[Specialty] = Relationship(back_populates="council_members")
    composition: list["CouncilComposition"] = Relationship(back_populates="member")


class Council(SQLModel, table=True):
    __tablename__ = "councils"
    council_id: Optional[int] = Field(default=None, primary_key=True)
    number: str = Field(index=True, unique=True)
    name: str
    department: str
    status: str = "active"
    composition: list["CouncilComposition"] = Relationship(back_populates="council")
    dissertations: list["Dissertation"] = Relationship(back_populates="council")
    meetings: list["Meeting"] = Relationship(back_populates="council")


class CouncilComposition(SQLModel, table=True):
    __tablename__ = "council_composition"
    id: Optional[int] = Field(default=None, primary_key=True)
    council_id: int = Field(foreign_key="councils.council_id", index=True)
    member_id: int = Field(foreign_key="council_members.member_id", index=True)
    position_in_council: str = "member"
    date_from: date = Field(default_factory=date.today)
    date_to: Optional[date] = None
    council: Optional[Council] = Relationship(back_populates="composition")
    member: Optional[CouncilMember] = Relationship(back_populates="composition")


class Candidate(SQLModel, table=True):
    __tablename__ = "candidates"
    candidate_id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True)
    degree_sought: str
    specialty_id: int = Field(foreign_key="specialties.specialty_id")
    contact_info: Optional[str] = None
    specialty: Optional[Specialty] = Relationship(back_populates="candidates")
    dissertations: list["Dissertation"] = Relationship(back_populates="candidate")


class Dissertation(SQLModel, table=True):
    __tablename__ = "dissertations"
    dissertation_id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidates.candidate_id", index=True)
    council_id: int = Field(foreign_key="councils.council_id", index=True)
    specialty_id: int = Field(foreign_key="specialties.specialty_id")
    topic: str
    status: str = "submitted"
    submitted_at: date = Field(default_factory=date.today)
    candidate: Optional[Candidate] = Relationship(back_populates="dissertations")
    council: Optional[Council] = Relationship(back_populates="dissertations")
    meetings: list["Meeting"] = Relationship(back_populates="dissertation")


class Meeting(SQLModel, table=True):
    __tablename__ = "meetings"
    meeting_id: Optional[int] = Field(default=None, primary_key=True)
    council_id: int = Field(foreign_key="councils.council_id", index=True)
    dissertation_id: Optional[int] = Field(default=None, foreign_key="dissertations.dissertation_id")
    meeting_date: str
    quorum_required: int = 0
    quorum_met: Optional[bool] = None
    status: str = "planned"
    council: Optional[Council] = Relationship(back_populates="meetings")
    dissertation: Optional[Dissertation] = Relationship(back_populates="meetings")
    attendance: list["MeetingAttendance"] = Relationship(back_populates="meeting")


class MeetingAttendance(SQLModel, table=True):
    __tablename__ = "meeting_attendance"
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.meeting_id", index=True)
    member_id: int = Field(foreign_key="council_members.member_id")
    is_present: bool = False
    meeting: Optional[Meeting] = Relationship(back_populates="attendance")


class Protocol(SQLModel, table=True):
    __tablename__ = "protocols"
    protocol_id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.meeting_id", unique=True)
    protocol_number: str
    signed_date: Optional[date] = None
    file_path: Optional[str] = None
    created_by: int = Field(foreign_key="users.user_id")


class Vote(SQLModel, table=True):
    __tablename__ = "votes"
    vote_id: Optional[int] = Field(default=None, primary_key=True)
    protocol_id: int = Field(foreign_key="protocols.protocol_id", index=True)
    member_id: int = Field(foreign_key="council_members.member_id")
    vote_value: str


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"
    decision_id: Optional[int] = Field(default=None, primary_key=True)
    dissertation_id: int = Field(foreign_key="dissertations.dissertation_id")
    meeting_id: int = Field(foreign_key="meetings.meeting_id", unique=True)
    decision_text: str
    result: str
    decision_date: date = Field(default_factory=date.today)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    log_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.user_id")
    action: str
    entity: str
    entity_id: Optional[int] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
