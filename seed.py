"""Демонстрационные данные — чтобы приложение сразу выглядело «живым»."""
from werkzeug.security import generate_password_hash

import services
from db import execute, scalar


def run():
    # Роли и пользователи
    roles = {}
    for name, title in [("secretary", "Секретарь совета"), ("member", "Член совета"), ("admin", "Администратор")]:
        roles[name] = execute("INSERT INTO roles (name, title) VALUES (?,?)", (name, title))

    sec = execute(
        "INSERT INTO users (full_name, login, password_hash, role_id) VALUES (?,?,?,?)",
        ("Иванова Анна Петровна", "secretary", generate_password_hash("secretary123"), roles["secretary"]),
    )
    execute(
        "INSERT INTO users (full_name, login, password_hash, role_id) VALUES (?,?,?,?)",
        ("Администратор системы", "admin", generate_password_hash("admin123"), roles["admin"]),
    )
    member_user = execute(
        "INSERT INTO users (full_name, login, password_hash, role_id) VALUES (?,?,?,?)",
        ("Смирнов Олег Викторович", "member", generate_password_hash("member123"), roles["member"]),
    )

    # Специальности
    spec = {}
    for code, name in [
        ("05.13.19", "Методы и системы защиты информации"),
        ("05.13.11", "Математическое и программное обеспечение вычислительных систем"),
        ("05.13.01", "Системный анализ, управление и обработка информации"),
        ("05.13.18", "Математическое моделирование, численные методы"),
    ]:
        spec[code] = execute("INSERT INTO specialties (code, name) VALUES (?,?)", (code, name))

    # Члены совета
    people = [
        ("Смирнов Олег Викторович", "doctor", "профессор", "05.13.19", member_user),
        ("Кузнецова Мария Сергеевна", "doctor", "профессор", "05.13.19", None),
        ("Нурпеисов Бауыржан Касымович", "doctor", "профессор", "05.13.19", None),
        ("Абенова Айгерим Тулегеновна", "doctor", "доцент", "05.13.19", None),
        ("Егоров Дмитрий Алексеевич", "doctor", "профессор", "05.13.11", None),
        ("Ким Виктор Сергеевич", "doctor", "профессор", "05.13.11", None),
        ("Оспанова Дина Маратовна", "candidate", "доцент", "05.13.01", None),
        ("Тихонов Павел Андреевич", "candidate", "доцент", "05.13.19", None),
    ]
    m = []
    for name, deg, title, code, uid in people:
        m.append(
            execute(
                "INSERT INTO council_members (full_name, degree, academic_title, specialty_id, user_id) VALUES (?,?,?,?,?)",
                (name, deg, title, spec[code], uid),
            )
        )

    # Советы и их состав
    c1 = execute(
        "INSERT INTO councils (number, name, department, status) VALUES (?,?,?,?)",
        ("Д 999.001.02", "Совет по информационной безопасности и программному обеспечению",
         "Кафедра информационных систем", "active"),
    )
    c2 = execute(
        "INSERT INTO councils (number, name, department, status) VALUES (?,?,?,?)",
        ("Д 999.002.01", "Совет по математическому моделированию", "Кафедра прикладной математики", "active"),
    )
    positions = ["chair", "member", "secretary", "member", "deputy", "member", "member", "member"]
    for mid, pos in zip(m, positions):
        services.add_to_council(c1, mid, pos, sec)
    services.add_to_council(c2, m[4], "chair", sec)
    services.add_to_council(c2, m[5], "member", sec)
    services.add_to_council(c2, m[6], "secretary", sec)

    # Соискатели и диссертационные дела
    def cand(name, degree, code, contact):
        return execute(
            "INSERT INTO candidates (full_name, degree_sought, specialty_id, contact_info) VALUES (?,?,?,?)",
            (name, degree, spec[code], contact),
        )

    def diss(cid, council, code, topic, status, day):
        return execute(
            "INSERT INTO dissertations (candidate_id, council_id, specialty_id, topic, status, submitted_at) VALUES (?,?,?,?,?,?)",
            (cid, council, spec[code], topic, status, day),
        )

    k1 = cand("Соколов Иван Николаевич", "candidate", "05.13.19", "sokolov@example.edu")
    k2 = cand("Жумабаева Алия Ерлановна", "candidate", "05.13.11", "+7 700 000-00-01")
    k3 = cand("Петренко Артём Игоревич", "candidate", "05.13.19", "petrenko@example.edu")
    k4 = cand("Алиев Ренат Маратович", "candidate", "05.13.19", "aliev@example.edu")

    d1 = diss(k1, c1, "05.13.19", "Методы защиты информации в распределённых системах", "scheduled", "2026-08-20")
    diss(k2, c1, "05.13.11", "Верификация программного обеспечения встроенных систем", "accepted", "2026-09-05")
    diss(k3, c1, "05.13.19", "Модели обнаружения аномалий в сетевом трафике", "submitted", "2026-10-01")
    d4 = diss(k4, c1, "05.13.19", "Анализ уязвимостей веб-приложений методами динамического тестирования", "scheduled", "2026-06-10")

    # Прошедшее заседание с протоколом (оформляется через те же бизнес-правила)
    past = services.create_meeting(c1, d4, "2026-09-12T11:00", sec)
    services.save_attendance(past, [x for x in m if x != m[6]], sec)
    votes = {x: "for" for x in m if x != m[6]}
    votes[m[7]] = "abstain"
    services.register_protocol(past, votes, sec, signed_date="2026-09-12")

    # Будущее заседание — для демонстрации проверки кворума
    services.create_meeting(c1, d1, "2026-10-28T10:00", sec)

    assert scalar("SELECT COUNT(*) FROM protocols") == 1
