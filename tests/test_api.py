from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database.db import get_session
from app.database.models import (
    Candidate, Council, CouncilComposition, CouncilMember, Dissertation,
    Meeting, Specialty, User, Role,
)
from app.main import app


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        role = Role(name="secretary", title="Секретарь")
        specialty = Specialty(code="01.01.01", name="Информационные системы")
        session.add_all([role, specialty])
        session.flush()
        user = User(full_name="Тестовый секретарь", login="test", password_hash="test", role_id=role.role_id)
        council = Council(number="Т 001", name="Тестовый совет", department="Кафедра")
        session.add_all([user, council])
        session.flush()
        members = []
        for index in range(5):
            member = CouncilMember(
                full_name=f"Учёный {index + 1}",
                degree="doctor" if index < 3 else "candidate",
                specialty_id=specialty.specialty_id,
            )
            members.append(member)
            session.add(member)
        session.flush()
        for member in members:
            session.add(CouncilComposition(
                council_id=council.council_id,
                member_id=member.member_id,
                position_in_council="member",
                date_from=date.today(),
            ))
        candidate = Candidate(full_name="Соискатель Тест", degree_sought="candidate", specialty_id=specialty.specialty_id)
        session.add(candidate)
        session.flush()
        dissertation = Dissertation(
            candidate_id=candidate.candidate_id,
            council_id=council.council_id,
            specialty_id=specialty.specialty_id,
            topic="Проверка тестового REST API",
            submitted_at=date.today(),
        )
        session.add(dissertation)
        session.flush()
        meeting = Meeting(
            council_id=council.council_id,
            dissertation_id=dissertation.dissertation_id,
            meeting_date="2026-01-01T10:00:00",
        )
        session.add(meeting)
        session.commit()
        test_ids = {
            "specialty": specialty.specialty_id,
            "council": council.council_id,
            "meeting": meeting.meeting_id,
            "members": [member.member_id for member in members],
        }

    def override_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.state.skip_startup = True
    with TestClient(app) as test_client:
        test_client.test_ids = test_ids
        yield test_client
    app.dependency_overrides.clear()
    app.state.skip_startup = False
    test_engine.dispose()


def test_get_members_returns_list(client):
    response = client.get("/api/members")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 5


def test_post_member_creates_record(client):
    response = client.post("/api/members", json={
        "full_name": "Новый учёный",
        "degree": "doctor",
        "academic_title": "профессор",
        "specialty_id": client.test_ids["specialty"],
    })
    assert response.status_code == 201
    assert response.json()["full_name"] == "Новый учёный"
    assert response.json()["member_id"] > 0


def test_attendance_calculates_quorum_and_protocol(client):
    meeting_id = client.test_ids["meeting"]
    member_ids = client.test_ids["members"]
    response = client.put(f"/api/meetings/{meeting_id}/attendance", json={"present_member_ids": member_ids[:4]})
    assert response.status_code == 200
    assert response.json()["quorum_met"] is True
    votes = {str(member_id): "for" for member_id in member_ids[:4]}
    protocol = client.post(f"/api/meetings/{meeting_id}/protocol", json={"votes": votes, "created_by": 1})
    assert protocol.status_code == 201
    assert protocol.json()["result"] == "granted"
