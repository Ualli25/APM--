"""Create a small, repeatable demonstration dataset for a fresh database."""
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3

from sqlmodel import Session, select

from app.database.db import DATABASE_URL, engine
from app.database.models import (
    AuditLog, Candidate, Council, CouncilComposition, CouncilMember, Decision,
    Dissertation, Meeting, MeetingAttendance, Protocol, Role, Specialty, User, Vote,
)


def migrate_legacy_database() -> bool:
    """Copy the untouched Flask database into a fresh local SQLModel database."""
    if not DATABASE_URL.startswith("sqlite") or not engine.url.database or engine.url.database == ":memory:":
        return False
    legacy_path = Path(__file__).resolve().parents[2] / "arm.db"
    target_path = Path(engine.url.database).resolve()
    if not legacy_path.is_file() or legacy_path.resolve() == target_path:
        return False

    tables = (
        "roles", "users", "specialties", "council_members", "councils",
        "council_composition", "candidates", "dissertations", "meetings",
        "meeting_attendance", "protocols", "votes", "decisions", "audit_log",
    )
    with sqlite3.connect(target_path) as target, sqlite3.connect(legacy_path) as source:
        target.execute("PRAGMA foreign_keys=ON")
        if target.execute("SELECT COUNT(*) FROM roles").fetchone()[0]:
            return False
        source_tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table not in source_tables:
                continue
            target_columns = [row[1] for row in target.execute(f"PRAGMA table_info({table})")]
            source_columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
            shared_columns = [name for name in target_columns if name in source_columns]
            if not shared_columns:
                continue
            columns = ", ".join(f'"{name}"' for name in shared_columns)
            # These identifiers come from the fixed table allowlist and local SQLite schema; values are never interpolated.
            rows = source.execute(f"SELECT {columns} FROM {table}").fetchall()  # nosec B608
            if rows:
                marks = ", ".join("?" for _ in shared_columns)
                # Identifiers come from the local schemas; row values use SQLite placeholders.
                target.executemany(f"INSERT INTO {table} ({columns}) VALUES ({marks})", rows)  # nosec B608
        target.commit()
    return True


def seed_data() -> None:
    with Session(engine) as session:
        if session.exec(select(Role)).first():
            return

        roles = [Role(name="secretary", title="Секретарь совета"),
                 Role(name="member", title="Член совета"),
                 Role(name="admin", title="Администратор")]
        session.add_all(roles)
        session.flush()
        users = [
            User(full_name="Иванова Анна Петровна", login="secretary", password_hash="demo-only", role_id=roles[0].role_id),
            User(full_name="Смирнов Олег Викторович", login="member", password_hash="demo-only", role_id=roles[1].role_id),
            User(full_name="Администратор системы", login="admin", password_hash="demo-only", role_id=roles[2].role_id),
        ]
        specialties = [
            Specialty(code="05.13.19", name="Методы и системы защиты информации"),
            Specialty(code="05.13.11", name="Математическое и программное обеспечение вычислительных систем"),
            Specialty(code="05.13.01", name="Системный анализ, управление и обработка информации"),
            Specialty(code="05.13.18", name="Математическое моделирование, численные методы"),
        ]
        session.add_all(users + specialties)
        session.flush()

        members = []
        for index in range(1, 10):
            specialty_id = specialties[0].specialty_id if index <= 5 else specialties[1].specialty_id
            members.append(CouncilMember(
                full_name=f"Член совета {index}", degree="doctor",
                academic_title="профессор" if index % 2 else "доцент",
                specialty_id=specialty_id,
                user_id=users[1].user_id if index == 1 else None,
            ))
        for index in range(10, 13):
            members.append(CouncilMember(
                full_name=f"Член совета {index}", degree="candidate",
                academic_title="доцент", specialty_id=specialties[2].specialty_id,
            ))
        councils = [
            Council(number="Д 999.001.02", name="Совет по информационной безопасности", department="Кафедра информационных систем"),
            Council(number="Д 999.002.01", name="Совет по математическому моделированию", department="Кафедра прикладной математики"),
        ]
        candidates = [Candidate(
            full_name=f"Соискатель {index}", degree_sought="candidate",
            specialty_id=specialties[(index - 1) % 2].specialty_id,
            contact_info=f"candidate{index}@example.edu",
        ) for index in range(1, 5)]
        session.add_all(members + councils + candidates)
        session.flush()

        compositions = []
        for index, member in enumerate(members):
            position = "chair" if index == 0 else "secretary" if index == 2 else "member"
            compositions.append(CouncilComposition(
                council_id=councils[0].council_id, member_id=member.member_id,
                position_in_council=position, date_from=date.today() - timedelta(days=500),
            ))
        for index, member in enumerate(members[4:7]):
            compositions.append(CouncilComposition(
                council_id=councils[1].council_id, member_id=member.member_id,
                position_in_council="chair" if index == 0 else "member",
                date_from=date.today() - timedelta(days=400),
            ))
        dissertations = [Dissertation(
            candidate_id=candidates[index].candidate_id,
            council_id=councils[0].council_id,
            specialty_id=specialties[index % 2].specialty_id,
            topic=[
                "Методы защиты информации в распределённых системах",
                "Верификация программного обеспечения встроенных систем",
                "Модели обнаружения аномалий в сетевом трафике",
                "Анализ надёжности информационных систем",
            ][index],
            status="scheduled" if index < 2 else "submitted",
            submitted_at=date.today() - timedelta(days=40 - index),
        ) for index in range(4)]
        session.add_all(compositions + dissertations)
        session.flush()

        meeting_rows = []
        for index in range(3):
            meeting_rows.append(Meeting(
                council_id=councils[0].council_id,
                dissertation_id=dissertations[index].dissertation_id,
                meeting_date=(datetime.now() - timedelta(days=90 - index * 25)).isoformat(timespec="seconds"),
                quorum_required=8, quorum_met=True, status="held",
            ))
        meeting_rows.append(Meeting(
            council_id=councils[0].council_id,
            dissertation_id=dissertations[3].dissertation_id,
            meeting_date=(datetime.now() + timedelta(days=14)).isoformat(timespec="seconds"),
            quorum_required=8, quorum_met=None, status="planned",
        ))
        session.add_all(meeting_rows)
        session.flush()

        for meeting in meeting_rows[:3]:
            for member in members[:9]:
                session.add(MeetingAttendance(
                    meeting_id=meeting.meeting_id, member_id=member.member_id, is_present=True,
                ))
            protocol = Protocol(
                meeting_id=meeting.meeting_id,
                protocol_number=f"2026/{meeting.meeting_id:03d}",
                signed_date=date.today(), created_by=users[0].user_id,
            )
            session.add(protocol)
            session.flush()
            for index, member in enumerate(members[:9]):
                session.add(Vote(
                    protocol_id=protocol.protocol_id, member_id=member.member_id,
                    vote_value="for" if index < 7 else "abstain" if index == 7 else "against",
                ))
            granted = meeting.meeting_id % 2 == 1
            session.add(Decision(
                dissertation_id=meeting.dissertation_id,
                meeting_id=meeting.meeting_id,
                decision_text="Степень присуждена" if granted else "Дело направлено на доработку",
                result="granted" if granted else "rework",
                decision_date=date.today(),
            ))
        for index in range(3):
            session.add(AuditLog(
                user_id=users[0].user_id,
                action="seed", entity="system", entity_id=index + 1,
            ))
        session.commit()
