-- ============================================================
-- АРМ Секретаря Учёного совета — структура БД (SQLite)
-- 14 таблиц. Коды статусов хранятся латиницей, подписи — в приложении.
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE roles (
    role_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,            -- secretary / member / admin
    title     TEXT NOT NULL
);

CREATE TABLE users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT NOT NULL,
    login          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role_id        INTEGER NOT NULL REFERENCES roles(role_id),
    is_active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE specialties (
    specialty_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL
);

CREATE TABLE council_members (
    member_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    degree          TEXT NOT NULL CHECK (degree IN ('doctor','candidate')),
    academic_title  TEXT,
    specialty_id    INTEGER NOT NULL REFERENCES specialties(specialty_id),
    user_id         INTEGER UNIQUE REFERENCES users(user_id)
);

CREATE TABLE councils (
    council_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    number      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    department  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed'))
);

CREATE TABLE council_composition (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id           INTEGER NOT NULL REFERENCES councils(council_id),
    member_id            INTEGER NOT NULL REFERENCES council_members(member_id),
    position_in_council  TEXT NOT NULL DEFAULT 'member'
                         CHECK (position_in_council IN ('chair','deputy','secretary','member')),
    date_from            TEXT NOT NULL,
    date_to              TEXT,
    UNIQUE (council_id, member_id)
);

CREATE TABLE candidates (
    candidate_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT NOT NULL,
    degree_sought  TEXT NOT NULL CHECK (degree_sought IN ('candidate','doctor')),
    specialty_id   INTEGER NOT NULL REFERENCES specialties(specialty_id),
    contact_info   TEXT
);

CREATE TABLE dissertations (
    dissertation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id     INTEGER NOT NULL REFERENCES candidates(candidate_id),
    council_id       INTEGER NOT NULL REFERENCES councils(council_id),
    specialty_id     INTEGER NOT NULL REFERENCES specialties(specialty_id),
    topic            TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'submitted'
                     CHECK (status IN ('submitted','accepted','scheduled','defended','rejected')),
    submitted_at     TEXT NOT NULL
);

CREATE TABLE meetings (
    meeting_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id       INTEGER NOT NULL REFERENCES councils(council_id),
    dissertation_id  INTEGER REFERENCES dissertations(dissertation_id),
    meeting_date     TEXT NOT NULL,
    quorum_required  INTEGER NOT NULL DEFAULT 0,
    quorum_met       INTEGER,
    status           TEXT NOT NULL DEFAULT 'planned'
                     CHECK (status IN ('planned','held','cancelled'))
);

CREATE TABLE meeting_attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(meeting_id),
    member_id   INTEGER NOT NULL REFERENCES council_members(member_id),
    is_present  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (meeting_id, member_id)
);

CREATE TABLE protocols (
    protocol_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id       INTEGER NOT NULL UNIQUE REFERENCES meetings(meeting_id),
    protocol_number  TEXT NOT NULL,
    signed_date      TEXT,
    file_path        TEXT,
    created_by       INTEGER NOT NULL REFERENCES users(user_id)
);

CREATE TABLE votes (
    vote_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol_id  INTEGER NOT NULL REFERENCES protocols(protocol_id),
    member_id    INTEGER NOT NULL REFERENCES council_members(member_id),
    vote_value   TEXT NOT NULL CHECK (vote_value IN ('for','against','abstain')),
    UNIQUE (protocol_id, member_id)
);

CREATE TABLE decisions (
    decision_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    dissertation_id  INTEGER NOT NULL REFERENCES dissertations(dissertation_id),
    meeting_id       INTEGER NOT NULL UNIQUE REFERENCES meetings(meeting_id),
    decision_text    TEXT,
    result           TEXT NOT NULL CHECK (result IN ('granted','denied','rework')),
    decision_date    TEXT NOT NULL
);

CREATE TABLE audit_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(user_id),
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
