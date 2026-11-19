"""Бизнес-слой: правила диссертационного совета (кворум, состав, протокол, решение)."""
from datetime import date

from db import execute, get_db, query

# ---- Подписи для кодов (единый источник для интерфейса) ----
DEGREE = {"doctor": "Доктор наук", "candidate": "Кандидат наук"}
DEGREE_SOUGHT = {"candidate": "кандидата наук", "doctor": "доктора наук"}
POSITION = {
    "chair": "Председатель",
    "deputy": "Заместитель председателя",
    "secretary": "Учёный секретарь",
    "member": "Член совета",
}
DISS_STATUS = {
    "submitted": "Подано",
    "accepted": "Принято к рассмотрению",
    "scheduled": "Назначено к защите",
    "defended": "Защищено",
    "rejected": "Отклонено",
}
MEETING_STATUS = {"planned": "Запланировано", "held": "Проведено", "cancelled": "Отменено"}
COUNCIL_STATUS = {"active": "Действует", "closed": "Закрыт"}
VOTE = {"for": "За", "against": "Против", "abstain": "Воздержался"}
RESULT = {"granted": "Степень присуждена", "denied": "В присуждении отказано", "rework": "Отправлено на доработку"}

# ---- Параметры правил ----
QUORUM_NUM, QUORUM_DEN = 2, 3     # кворум: не менее 2/3 состава совета
MIN_SPECIALISTS = 3               # не менее 3 докторов наук по специальности дела
DECISION_NUM, DECISION_DEN = 2, 3  # решение «за»: не менее 2/3 проголосовавших


class BusinessError(Exception):
    """Нарушение бизнес-правила — текст показывается пользователю."""


def ceil_share(n, num, den):
    return (n * num + den - 1) // den if n else 0


def log_action(user_id, action, entity, entity_id=None):
    execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id) VALUES (?,?,?,?)",
        (user_id, action, entity, entity_id),
    )


# ---------------- Состав совета ----------------
def add_to_council(council_id, member_id, position, user_id):
    if position not in POSITION:
        raise BusinessError("Недопустимая должность в совете")
    if position in ("chair", "secretary"):
        busy = query(
            "SELECT 1 FROM council_composition WHERE council_id=? AND position_in_council=? AND date_to IS NULL",
            (council_id, position),
            one=True,
        )
        if busy:
            raise BusinessError(f"В совете уже назначен: {POSITION[position].lower()}")
    exists = query(
        "SELECT 1 FROM council_composition WHERE council_id=? AND member_id=? AND date_to IS NULL",
        (council_id, member_id),
        one=True,
    )
    if exists:
        raise BusinessError("Этот человек уже входит в состав совета")
    cid = execute(
        "INSERT INTO council_composition (council_id, member_id, position_in_council, date_from) VALUES (?,?,?,?)",
        (council_id, member_id, position, date.today().isoformat()),
    )
    log_action(user_id, "composition_add", "council_composition", cid)


def remove_from_council(council_id, member_id, user_id):
    execute(
        "DELETE FROM council_composition WHERE council_id=? AND member_id=?",
        (council_id, member_id),
    )
    log_action(user_id, "composition_remove", "councils", council_id)


# ---------------- Заседания и явка ----------------
def _check_dissertation_belongs(council_id, dissertation_id):
    if not dissertation_id:
        return
    row = query("SELECT council_id FROM dissertations WHERE dissertation_id=?", (dissertation_id,), one=True)
    if not row:
        raise BusinessError("Диссертационное дело не найдено")
    if row["council_id"] != council_id:
        raise BusinessError("Это дело закреплено за другим советом — выберите дело выбранного совета")


def ensure_attendance(meeting_id):
    """Создать строки явки для всех действующих членов совета (новые — «отсутствует»)."""
    m = query("SELECT council_id FROM meetings WHERE meeting_id=?", (meeting_id,), one=True)
    conn = get_db()
    conn.execute(
        """INSERT OR IGNORE INTO meeting_attendance (meeting_id, member_id, is_present)
           SELECT ?, member_id, 0 FROM council_composition
           WHERE council_id=? AND date_to IS NULL""",
        (meeting_id, m["council_id"]),
    )
    conn.commit()


def create_meeting(council_id, dissertation_id, meeting_date, user_id):
    n = query(
        "SELECT COUNT(*) c FROM council_composition WHERE council_id=? AND date_to IS NULL",
        (council_id,),
        one=True,
    )["c"]
    if n == 0:
        raise BusinessError("В составе совета нет членов — сначала добавьте их на странице совета")
    _check_dissertation_belongs(council_id, dissertation_id)
    mid = execute(
        "INSERT INTO meetings (council_id, dissertation_id, meeting_date, quorum_required, status) VALUES (?,?,?,?, 'planned')",
        (council_id, dissertation_id or None, meeting_date, ceil_share(n, QUORUM_NUM, QUORUM_DEN)),
    )
    ensure_attendance(mid)
    log_action(user_id, "create", "meetings", mid)
    return mid


def update_meeting(meeting_id, dissertation_id, meeting_date, status, user_id):
    m = query("SELECT * FROM meetings WHERE meeting_id=?", (meeting_id,), one=True)
    if m["status"] == "held":
        raise BusinessError("Проведённое заседание изменять нельзя")
    _check_dissertation_belongs(m["council_id"], dissertation_id)
    execute(
        "UPDATE meetings SET dissertation_id=?, meeting_date=?, status=? WHERE meeting_id=?",
        (dissertation_id or None, meeting_date, status, meeting_id),
    )
    log_action(user_id, "update", "meetings", meeting_id)


def attendance_list(meeting_id):
    return query(
        """SELECT a.member_id, a.is_present, cm.full_name, cm.degree, cm.academic_title,
                  cm.specialty_id, s.code AS spec_code, cc.position_in_council
           FROM meeting_attendance a
           JOIN meetings m ON m.meeting_id = a.meeting_id
           JOIN council_composition cc ON cc.council_id = m.council_id
                AND cc.member_id = a.member_id AND cc.date_to IS NULL
           JOIN council_members cm ON cm.member_id = a.member_id
           JOIN specialties s ON s.specialty_id = cm.specialty_id
           WHERE a.meeting_id = ?
           ORDER BY CASE cc.position_in_council WHEN 'chair' THEN 0 WHEN 'deputy' THEN 1
                    WHEN 'secretary' THEN 2 ELSE 3 END, cm.full_name""",
        (meeting_id,),
    )


def evaluate_quorum(meeting_id):
    """Главное бизнес-правило системы: есть ли кворум на заседании."""
    m = query(
        """SELECT m.*, d.specialty_id AS diss_specialty, s.code AS diss_spec_code
           FROM meetings m
           LEFT JOIN dissertations d ON d.dissertation_id = m.dissertation_id
           LEFT JOIN specialties s ON s.specialty_id = d.specialty_id
           WHERE m.meeting_id = ?""",
        (meeting_id,),
        one=True,
    )
    rows = attendance_list(meeting_id)
    total = len(rows)
    required = ceil_share(total, QUORUM_NUM, QUORUM_DEN)
    present = [r for r in rows if r["is_present"]]
    specialists = None
    if m["diss_specialty"]:
        specialists = [r for r in present if r["degree"] == "doctor" and r["specialty_id"] == m["diss_specialty"]]
    reasons = []
    if total == 0:
        reasons.append("В составе совета нет действующих членов")
    if len(present) < required:
        reasons.append(f"Присутствует {len(present)} из {required} необходимых членов совета")
    if specialists is not None and len(specialists) < MIN_SPECIALISTS:
        reasons.append(
            f"Докторов наук по специальности {m['diss_spec_code']}: {len(specialists)} из {MIN_SPECIALISTS} необходимых"
        )
    return {
        "ok": not reasons,
        "total": total,
        "required": required,
        "present_count": len(present),
        "present": present,
        "has_specialty": specialists is not None,
        "spec_code": m["diss_spec_code"],
        "specialists_count": len(specialists) if specialists is not None else 0,
        "min_specialists": MIN_SPECIALISTS,
        "reasons": reasons,
    }


def has_protocol(meeting_id):
    return query("SELECT protocol_id FROM protocols WHERE meeting_id=?", (meeting_id,), one=True)


def save_attendance(meeting_id, present_ids, user_id):
    if has_protocol(meeting_id):
        raise BusinessError("Протокол уже оформлен — явку менять нельзя")
    m = query("SELECT * FROM meetings WHERE meeting_id=?", (meeting_id,), one=True)
    if m["status"] == "cancelled":
        raise BusinessError("Заседание отменено")
    ensure_attendance(meeting_id)
    valid = {r["member_id"] for r in attendance_list(meeting_id)}
    chosen = {int(i) for i in present_ids if str(i).isdigit()} & valid
    conn = get_db()
    with conn:
        conn.execute("UPDATE meeting_attendance SET is_present=0 WHERE meeting_id=?", (meeting_id,))
        for mid in chosen:
            conn.execute(
                "UPDATE meeting_attendance SET is_present=1 WHERE meeting_id=? AND member_id=?",
                (meeting_id, mid),
            )
    q = evaluate_quorum(meeting_id)
    execute(
        "UPDATE meetings SET quorum_required=?, quorum_met=? WHERE meeting_id=?",
        (q["required"], 1 if q["ok"] else 0, meeting_id),
    )
    log_action(user_id, "attendance", "meetings", meeting_id)
    return q


# ---------------- Протокол и решение ----------------
def register_protocol(meeting_id, votes, user_id, signed_date=None):
    """Оформить протокол: проверяет кворум, фиксирует голоса, решение и статус дела — одной транзакцией."""
    m = query(
        """SELECT m.*, d.dissertation_id AS did, d.specialty_id AS dspec, cand.full_name AS candidate,
                  cand.degree_sought, s.code AS spec_code
           FROM meetings m
           LEFT JOIN dissertations d ON d.dissertation_id = m.dissertation_id
           LEFT JOIN candidates cand ON cand.candidate_id = d.candidate_id
           LEFT JOIN specialties s ON s.specialty_id = d.specialty_id
           WHERE m.meeting_id = ?""",
        (meeting_id,),
        one=True,
    )
    if m is None:
        raise BusinessError("Заседание не найдено")
    if m["status"] == "cancelled":
        raise BusinessError("Заседание отменено")
    if has_protocol(meeting_id):
        raise BusinessError("Протокол по этому заседанию уже оформлен")
    if not m["did"]:
        raise BusinessError("Протокол оформляется по диссертационному делу — выберите дело в заседании")

    q = evaluate_quorum(meeting_id)
    if not q["ok"]:
        raise BusinessError("Кворум не достигнут. " + "; ".join(q["reasons"]) + ".")

    present_ids = {r["member_id"] for r in q["present"]}
    clean = {}
    for mid in present_ids:
        v = votes.get(mid)
        if v not in VOTE:
            raise BusinessError("Укажите голос каждого присутствующего члена совета")
        clean[mid] = v

    n_for = sum(1 for v in clean.values() if v == "for")
    n_against = sum(1 for v in clean.values() if v == "against")
    n_abstain = sum(1 for v in clean.values() if v == "abstain")
    granted = n_for > 0 and n_for * DECISION_DEN >= len(clean) * DECISION_NUM
    result = "granted" if granted else "denied"

    when = signed_date or date.today().isoformat()
    number = f"П-{meeting_id:03d}/{m['meeting_date'][:4]}"
    text = (
        f"По результатам голосования: «за» — {n_for}, «против» — {n_against}, «воздержались» — {n_abstain}. "
        + (
            f"Присудить {m['candidate']} учёную степень {DEGREE_SOUGHT[m['degree_sought']]} по специальности {m['spec_code']}."
            if granted
            else f"Отказать {m['candidate']} в присуждении учёной степени {DEGREE_SOUGHT[m['degree_sought']]}."
        )
    )

    conn = get_db()
    with conn:  # единая транзакция: либо всё сохранится, либо ничего
        cur = conn.execute(
            "INSERT INTO protocols (meeting_id, protocol_number, signed_date, created_by) VALUES (?,?,?,?)",
            (meeting_id, number, when, user_id),
        )
        pid = cur.lastrowid
        for mid, v in clean.items():
            conn.execute(
                "INSERT INTO votes (protocol_id, member_id, vote_value) VALUES (?,?,?)", (pid, mid, v)
            )
        conn.execute(
            "INSERT INTO decisions (dissertation_id, meeting_id, decision_text, result, decision_date) VALUES (?,?,?,?,?)",
            (m["did"], meeting_id, text, result, when),
        )
        conn.execute("UPDATE meetings SET status='held', quorum_met=1 WHERE meeting_id=?", (meeting_id,))
        conn.execute(
            "UPDATE dissertations SET status=? WHERE dissertation_id=?",
            ("defended" if granted else "rejected", m["did"]),
        )
    log_action(user_id, "protocol", "protocols", pid)
    return pid


def get_protocol_bundle(protocol_id):
    p = query(
        """SELECT p.*, m.meeting_date, m.meeting_id, c.number AS council_number, c.name AS council_name,
                  c.department, d.topic, cand.full_name AS candidate, cand.degree_sought,
                  s.code AS spec_code, s.name AS spec_name, u.full_name AS created_by_name
           FROM protocols p
           JOIN meetings m ON m.meeting_id = p.meeting_id
           JOIN councils c ON c.council_id = m.council_id
           LEFT JOIN dissertations d ON d.dissertation_id = m.dissertation_id
           LEFT JOIN candidates cand ON cand.candidate_id = d.candidate_id
           LEFT JOIN specialties s ON s.specialty_id = d.specialty_id
           JOIN users u ON u.user_id = p.created_by
           WHERE p.protocol_id = ?""",
        (protocol_id,),
        one=True,
    )
    if p is None:
        return None
    votes = query(
        """SELECT v.vote_value, cm.full_name, cm.degree, cm.academic_title
           FROM votes v JOIN council_members cm ON cm.member_id = v.member_id
           WHERE v.protocol_id = ? ORDER BY cm.full_name""",
        (protocol_id,),
    )
    decision = query("SELECT * FROM decisions WHERE meeting_id=?", (p["meeting_id"],), one=True)
    return {"p": p, "votes": votes, "decision": decision}
