from datetime import date, datetime

import pytest
from sqlalchemy import event, select as sqlalchemy_select
from sqlalchemy.exc import IntegrityError
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
    @event.listens_for(test_engine, "connect")
    def enable_test_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
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
        test_client.test_engine = test_engine
        yield test_client
    app.dependency_overrides.clear()
    app.state.skip_startup = False
    test_engine.dispose()


def test_get_members_returns_list(client):
    response = client.get("/api/members")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 5


def test_get_specialties_returns_seeded_reference_data(client):
    response = client.get("/api/specialties")
    assert response.status_code == 200
    assert response.json()[0]["code"] == "01.01.01"


def test_member_filter_returns_matching_record_only(client):
    response = client.get("/api/members", params={"q": "Учёный 1"})
    assert response.status_code == 200
    assert [row["full_name"] for row in response.json()] == ["Учёный 1"]


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


def test_member_crud_get_update_delete(client):
    member_id = client.test_ids["members"][0]
    fetched = client.get(f"/api/members/{member_id}")
    assert fetched.status_code == 200
    assert fetched.json()["member_id"] == member_id

    updated = client.put(f"/api/members/{member_id}", json={
        "full_name": "Обновлённый учёный",
        "degree": "doctor",
        "academic_title": "профессор",
        "specialty_id": client.test_ids["specialty"],
    })
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Обновлённый учёный"

    created = client.post("/api/members", json={
        "full_name": "Удаляемый учёный",
        "degree": "candidate",
        "specialty_id": client.test_ids["specialty"],
    })
    assert created.status_code == 201
    member_id = created.json()["member_id"]
    deleted = client.delete(f"/api/members/{member_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/members/{member_id}").status_code == 404


def test_invalid_member_payload_is_rejected(client):
    response = client.post("/api/members", json={
        "full_name": "X", "degree": "wizard", "specialty_id": -1,
    })
    assert response.status_code == 422


def test_missing_specialty_returns_404_without_creating_member(client):
    before = len(client.get("/api/members").json())
    response = client.post("/api/members", json={
        "full_name": "Некорректная специальность",
        "degree": "doctor",
        "specialty_id": 99999,
    })
    assert response.status_code == 404
    assert len(client.get("/api/members").json()) == before


def test_unknown_member_and_council_return_404(client):
    assert client.get("/api/members/99999").status_code == 404
    assert client.get("/api/councils/99999/members").status_code == 404


def test_meeting_rejects_missing_council_instead_of_database_error(client):
    response = client.post("/api/meetings", json={
        "council_id": 99999,
        "dissertation_id": None,
        "meeting_date": "2026-02-03T10:00:00",
    })
    assert response.status_code == 404
    assert "traceback" not in response.text.lower()


def test_database_foreign_key_failure_rolls_back_transaction(client):
    with Session(client.test_engine) as session:
        before = len(session.exec(sqlalchemy_select(CouncilMember)).all())
        session.add(CouncilMember(
            full_name="Запись с несуществующей специальностью",
            degree="doctor",
            specialty_id=99999,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        after = len(session.exec(sqlalchemy_select(CouncilMember)).all())
    assert after == before


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


def test_attendance_rejects_member_outside_council(client):
    response = client.put(
        f"/api/meetings/{client.test_ids['meeting']}/attendance",
        json={"present_member_ids": [99999]},
    )
    assert response.status_code == 422


def test_protocol_requires_quorum(client):
    response = client.post(
        f"/api/meetings/{client.test_ids['meeting']}/protocol",
        json={"votes": {str(client.test_ids['members'][0]): "for"}, "created_by": 1},
    )
    assert response.status_code == 409


def test_api_does_not_expose_password_hash(client):
    response = client.get("/api/members")
    assert response.status_code == 200
    assert all("password_hash" not in row for row in response.json())
