"""Слой представления: веб-маршруты приложения «АРМ Секретаря Учёного совета».

Запуск:  python app.py          (первый запуск создаёт базу arm.db с демо-данными)
         python app.py --reset  (пересоздать базу с нуля)
"""
import os
import sqlite3
import sys
from datetime import date, datetime
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
import seed
import services
from db import execute, get_db, query, scalar
from services import (COUNCIL_STATUS, DEGREE, DISS_STATUS, MEETING_STATUS, POSITION, RESULT, VOTE,
                      BusinessError)

app = Flask(__name__)
app.secret_key = os.environ.get("ARM_SECRET", "arm-demo-secret-change-me")
app.teardown_appcontext(db.close_db)

WRITE_ROLES = ("secretary", "admin")

BADGES = {
    "submitted": "gray", "accepted": "blue", "scheduled": "amber", "defended": "green", "rejected": "red",
    "planned": "amber", "held": "green", "cancelled": "gray",
    "active": "green", "closed": "gray",
    "granted": "green", "denied": "red", "rework": "amber",
    "for": "green", "against": "red", "abstain": "gray",
}
ACTION_LABELS = {
    "create": "Создание", "update": "Изменение", "delete": "Удаление", "login": "Вход в систему",
    "attendance": "Отметка явки", "protocol": "Оформление протокола",
    "composition_add": "Добавление в состав совета", "composition_remove": "Исключение из состава совета",
}
ENTITY_LABELS = {
    "council_members": "Члены совета", "councils": "Диссоветы", "specialties": "Специальности",
    "candidates": "Соискатели", "dissertations": "Диссертационные дела", "meetings": "Заседания",
    "protocols": "Протоколы", "users": "Пользователи", "council_composition": "Состав совета",
}


# ---------------------------------------------------------------- общие помощники
def can_write():
    return bool(g.get("user")) and g.user["role"] in WRITE_ROLES


def write_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not can_write():
            abort(403)
        return f(*a, **k)
    return wrapper


def get_or_404(sql, args=()):
    row = query(sql, args, one=True)
    if row is None:
        abort(404)
    return row


def fmt_dt(value):
    if not value:
        return "—"
    s = str(value).replace("T", " ")
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return fmt_d(value)


def fmt_d(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


app.jinja_env.filters["dt"] = fmt_dt
app.jinja_env.filters["d"] = fmt_d


@app.before_request
def load_user():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = query(
            """SELECT u.user_id, u.full_name, u.login, r.name AS role, r.title AS role_title
               FROM users u JOIN roles r ON r.role_id = u.role_id
               WHERE u.user_id = ? AND u.is_active = 1""",
            (uid,), one=True,
        )
    if g.user is None and request.endpoint not in ("login", "static"):
        return redirect(url_for("login", next=request.path))


@app.context_processor
def inject_globals():
    return dict(
        can_write=can_write(), DEGREE=DEGREE, POSITION=POSITION, DISS_STATUS=DISS_STATUS,
        MEETING_STATUS=MEETING_STATUS, COUNCIL_STATUS=COUNCIL_STATUS, VOTE=VOTE, RESULT=RESULT,
        badge=lambda code: BADGES.get(code, "gray"),
        nav_active=lambda prefix: (request.endpoint or "").startswith(prefix),
        user=g.get("user"),
    )


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, text="У вашей роли нет прав на это действие."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, text="Такой страницы или записи нет."), 404


def clean(row):
    """Строка БД → словарь значений для формы (None → пустая строка)."""
    return {k: ("" if row[k] is None else row[k]) for k in row.keys()}


def collect(fields):
    return {f["name"]: (request.form.get(f["name"]) or "").strip() for f in fields}


def validate(fields, data):
    errors = {}
    for f in fields:
        v = data[f["name"]]
        if not v:
            if f.get("required", True):
                errors[f["name"]] = "Обязательное поле"
            continue
        try:
            if f["type"] == "date":
                datetime.strptime(v, "%Y-%m-%d")
            elif f["type"] == "datetime-local":
                datetime.strptime(v, "%Y-%m-%dT%H:%M")
        except ValueError:
            errors[f["name"]] = "Неверный формат даты"
        if f["type"] == "select" and v not in {str(o[0]) for o in f["options"]}:
            errors[f["name"]] = "Выберите значение из списка"
    return errors


def handle_form(title, fields, initial, save, back, success, subtitle=None):
    data, errors = dict(initial), {}
    if request.method == "POST":
        data = collect(fields)
        errors = validate(fields, data)
        if not errors:
            try:
                save(data)
                flash(success, "ok")
                return redirect(back)
            except BusinessError as e:
                flash(str(e), "error")
            except sqlite3.IntegrityError:
                flash("Такая запись уже существует (нарушена уникальность данных).", "error")
    return render_template("form.html", title=title, subtitle=subtitle, fields=fields,
                           values=data, errors=errors, back=back)


def table_page(title, columns, rows, add_url=None, add_label=None, filters=None, subtitle=None, empty=None):
    return render_template(
        "table.html", title=title, subtitle=subtitle, columns=columns, rows=rows, add_url=add_url,
        add_label=add_label, filters=filters, empty=empty,
        has_actions=any(r.get("actions") for r in rows),
    )


def row_actions(edit_ep, del_ep, key, value, confirm_text, extra=None):
    acts = list(extra or [])
    if can_write():
        acts.append({"label": "Изменить", "href": url_for(edit_ep, **{key: value})})
        acts.append({"label": "Удалить", "post": url_for(del_ep, **{key: value}), "confirm": confirm_text})
    return acts


def safe_delete(sql_list, entity, entity_id, back, blocked_text):
    """Удалить запись (и, при необходимости, её дочерние строки) одной транзакцией."""
    conn = get_db()
    try:
        with conn:
            for sql, args in sql_list:
                conn.execute(sql, args)
        services.log_action(g.user["user_id"], "delete", entity, entity_id)
        flash("Запись удалена", "ok")
    except sqlite3.IntegrityError:
        flash(blocked_text, "error")
    return redirect(back)


# ---------------------------------------------------------------- вход / выход
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE login=? AND is_active=1",
                  (request.form.get("login", "").strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = u["user_id"]
            services.log_action(u["user_id"], "login", "users", u["user_id"])
            nxt = request.args.get("next") or ""
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("index")
            return redirect(nxt)
        flash("Неверный логин или пароль", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- главная
@app.route("/")
def index():
    stats = [
        ("Члены совета", scalar("SELECT COUNT(*) FROM council_members"), url_for("members_list")),
        ("Диссоветы", scalar("SELECT COUNT(*) FROM councils WHERE status='active'"), url_for("councils_list")),
        ("Диссертационные дела", scalar("SELECT COUNT(*) FROM dissertations"), url_for("dissertations_list")),
        ("Ближайшие заседания", scalar("SELECT COUNT(*) FROM meetings WHERE status='planned'"), url_for("meetings_list")),
    ]
    upcoming = query(
        """SELECT m.meeting_id, m.meeting_date, c.number, cand.full_name AS candidate, d.topic
           FROM meetings m JOIN councils c ON c.council_id = m.council_id
           LEFT JOIN dissertations d ON d.dissertation_id = m.dissertation_id
           LEFT JOIN candidates cand ON cand.candidate_id = d.candidate_id
           WHERE m.status = 'planned' ORDER BY m.meeting_date LIMIT 5""")
    by_status = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM dissertations GROUP BY status")}
    total_d = sum(by_status.values()) or 1
    pipeline = [(DISS_STATUS[k], by_status.get(k, 0), round(by_status.get(k, 0) * 100 / total_d), k) for k in DISS_STATUS]
    councils = []
    for c in query(
        """SELECT c.council_id, c.number, c.name, COUNT(cc.id) AS n,
                  COALESCE(SUM(CASE WHEN cm.degree='doctor' THEN 1 ELSE 0 END),0) AS doctors
           FROM councils c
           LEFT JOIN council_composition cc ON cc.council_id=c.council_id AND cc.date_to IS NULL
           LEFT JOIN council_members cm ON cm.member_id = cc.member_id
           WHERE c.status='active' GROUP BY c.council_id ORDER BY c.number"""):
        councils.append(dict(c, required=services.ceil_share(c["n"], services.QUORUM_NUM, services.QUORUM_DEN)))
    recent = query(
        """SELECT a.*, u.full_name FROM audit_log a LEFT JOIN users u ON u.user_id=a.user_id
           ORDER BY a.log_id DESC LIMIT 6""")
    return render_template("index.html", stats=stats, upcoming=upcoming, pipeline=pipeline,
                           councils=councils, recent=recent, ACTION_LABELS=ACTION_LABELS, ENTITY_LABELS=ENTITY_LABELS)


# ---------------------------------------------------------------- специальности
SPEC_FIELDS = [
    dict(name="code", label="Шифр", type="text", hint="например, 05.13.19"),
    dict(name="name", label="Наименование", type="text"),
]


@app.route("/specialties")
def specialties_list():
    rows = []
    for s in query("SELECT * FROM specialties ORDER BY code"):
        rows.append({"cells": [s["code"], s["name"]],
                     "actions": row_actions("specialties_edit", "specialties_delete", "spec_id", s["specialty_id"],
                                            f"Удалить специальность {s['code']}?")})
    return table_page("Специальности ВАК", ["Шифр", "Наименование"], rows,
                      add_url=url_for("specialties_new"), add_label="Добавить специальность",
                      subtitle="Справочник научных специальностей: от него зависит расчёт кворума.")


@app.route("/specialties/new", methods=["GET", "POST"])
@write_required
def specialties_new():
    def save(d):
        sid = execute("INSERT INTO specialties (code, name) VALUES (?,?)", (d["code"], d["name"]))
        services.log_action(g.user["user_id"], "create", "specialties", sid)
    return handle_form("Новая специальность", SPEC_FIELDS, {}, save, url_for("specialties_list"), "Специальность добавлена")


@app.route("/specialties/<int:spec_id>/edit", methods=["GET", "POST"])
@write_required
def specialties_edit(spec_id):
    row = get_or_404("SELECT * FROM specialties WHERE specialty_id=?", (spec_id,))

    def save(d):
        execute("UPDATE specialties SET code=?, name=? WHERE specialty_id=?", (d["code"], d["name"], spec_id))
        services.log_action(g.user["user_id"], "update", "specialties", spec_id)
    return handle_form("Изменить специальность", SPEC_FIELDS, clean(row), save, url_for("specialties_list"), "Изменения сохранены")


@app.route("/specialties/<int:spec_id>/delete", methods=["POST"])
@write_required
def specialties_delete(spec_id):
    return safe_delete([("DELETE FROM specialties WHERE specialty_id=?", (spec_id,))], "specialties", spec_id,
                       url_for("specialties_list"),
                       "Нельзя удалить: эта специальность используется у членов совета, соискателей или дел.")


# ---------------------------------------------------------------- члены совета
def spec_options():
    return [(s["specialty_id"], f'{s["code"]} — {s["name"]}') for s in query("SELECT * FROM specialties ORDER BY code")]


def member_fields():
    return [
        dict(name="full_name", label="ФИО", type="text"),
        dict(name="degree", label="Учёная степень", type="select", options=list(DEGREE.items())),
        dict(name="academic_title", label="Учёное звание", type="text", required=False, hint="профессор, доцент и т. п."),
        dict(name="specialty_id", label="Специальность", type="select", options=spec_options()),
    ]


@app.route("/members")
def members_list():
    q = request.args.get("q", "").strip()
    degree = request.args.get("degree", "")
    spec = request.args.get("specialty", "")
    rows = []
    for r in query("""SELECT cm.*, s.code AS spec_code FROM council_members cm
                      JOIN specialties s ON s.specialty_id = cm.specialty_id ORDER BY cm.full_name"""):
        if q and q.casefold() not in r["full_name"].casefold():   # LIKE в SQLite не понимает регистр кириллицы
            continue
        if degree and r["degree"] != degree:
            continue
        if spec and str(r["specialty_id"]) != spec:
            continue
        rows.append({"cells": [r["full_name"], DEGREE[r["degree"]], r["academic_title"] or "—", r["spec_code"]],
                     "actions": row_actions("members_edit", "members_delete", "member_id", r["member_id"],
                                            f"Удалить: {r['full_name']}?")})
    filters = [
        dict(name="q", label="ФИО", type="text", value=q, placeholder="Поиск по ФИО"),
        dict(name="degree", label="Степень", type="select", options=list(DEGREE.items()), value=degree),
        dict(name="specialty", label="Специальность", type="select",
             options=[(s["specialty_id"], s["code"]) for s in query("SELECT * FROM specialties ORDER BY code")], value=spec),
    ]
    return table_page("Члены совета", ["ФИО", "Степень", "Звание", "Специальность"], rows,
                      add_url=url_for("members_new"), add_label="Добавить члена совета", filters=filters,
                      subtitle="Реестр докторов и кандидатов наук, которые могут входить в диссертационные советы.")


@app.route("/members/new", methods=["GET", "POST"])
@write_required
def members_new():
    def save(d):
        mid = execute("INSERT INTO council_members (full_name, degree, academic_title, specialty_id) VALUES (?,?,?,?)",
                      (d["full_name"], d["degree"], d["academic_title"] or None, int(d["specialty_id"])))
        services.log_action(g.user["user_id"], "create", "council_members", mid)
    return handle_form("Новый член совета", member_fields(), {}, save, url_for("members_list"), "Член совета добавлен")


@app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
@write_required
def members_edit(member_id):
    row = get_or_404("SELECT * FROM council_members WHERE member_id=?", (member_id,))

    def save(d):
        execute("UPDATE council_members SET full_name=?, degree=?, academic_title=?, specialty_id=? WHERE member_id=?",
                (d["full_name"], d["degree"], d["academic_title"] or None, int(d["specialty_id"]), member_id))
        services.log_action(g.user["user_id"], "update", "council_members", member_id)
    return handle_form("Изменить данные члена совета", member_fields(), clean(row), save,
                       url_for("members_list"), "Изменения сохранены")


@app.route("/members/<int:member_id>/delete", methods=["POST"])
@write_required
def members_delete(member_id):
    return safe_delete([("DELETE FROM council_members WHERE member_id=?", (member_id,))], "council_members", member_id,
                       url_for("members_list"),
                       "Нельзя удалить: человек входит в состав совета или участвовал в заседаниях. Сначала исключите его из составов.")


# ---------------------------------------------------------------- диссоветы
COUNCIL_FIELDS = [
    dict(name="number", label="Номер совета", type="text", hint="например, Д 999.001.02"),
    dict(name="name", label="Название", type="text"),
    dict(name="department", label="Кафедра / факультет", type="text"),
    dict(name="status", label="Статус", type="select", options=list(COUNCIL_STATUS.items())),
]


@app.route("/councils")
def councils_list():
    rows = []
    for c in query("""SELECT c.*, (SELECT COUNT(*) FROM council_composition cc
                                   WHERE cc.council_id=c.council_id AND cc.date_to IS NULL) AS n
                      FROM councils c ORDER BY c.number"""):
        rows.append({
            "cells": [{"t": c["number"], "href": url_for("councils_detail", council_id=c["council_id"])},
                      c["name"], c["department"], f'{c["n"]} чел.',
                      {"t": COUNCIL_STATUS[c["status"]], "badge": BADGES[c["status"]]}],
            "actions": row_actions("councils_edit", "councils_delete", "council_id", c["council_id"],
                                   f"Удалить совет {c['number']}?",
                                   extra=[{"label": "Открыть", "href": url_for("councils_detail", council_id=c["council_id"])}]),
        })
    return table_page("Диссертационные советы", ["Номер", "Название", "Кафедра", "Состав", "Статус"], rows,
                      add_url=url_for("councils_new"), add_label="Создать совет",
                      subtitle="Откройте совет, чтобы управлять его составом и проверять кворум.")


@app.route("/councils/new", methods=["GET", "POST"])
@write_required
def councils_new():
    def save(d):
        cid = execute("INSERT INTO councils (number, name, department, status) VALUES (?,?,?,?)",
                      (d["number"], d["name"], d["department"], d["status"]))
        services.log_action(g.user["user_id"], "create", "councils", cid)
    return handle_form("Новый диссертационный совет", COUNCIL_FIELDS, {"status": "active"}, save,
                       url_for("councils_list"), "Совет создан")


@app.route("/councils/<int:council_id>/edit", methods=["GET", "POST"])
@write_required
def councils_edit(council_id):
    row = get_or_404("SELECT * FROM councils WHERE council_id=?", (council_id,))

    def save(d):
        execute("UPDATE councils SET number=?, name=?, department=?, status=? WHERE council_id=?",
                (d["number"], d["name"], d["department"], d["status"], council_id))
        services.log_action(g.user["user_id"], "update", "councils", council_id)
    return handle_form("Изменить совет", COUNCIL_FIELDS, clean(row), save, url_for("councils_list"), "Изменения сохранены")


@app.route("/councils/<int:council_id>/delete", methods=["POST"])
@write_required
def councils_delete(council_id):
    return safe_delete(
        [("DELETE FROM council_composition WHERE council_id=?", (council_id,)),
         ("DELETE FROM councils WHERE council_id=?", (council_id,))],
        "councils", council_id, url_for("councils_list"),
        "Нельзя удалить: за советом закреплены диссертационные дела или заседания.")


@app.route("/councils/<int:council_id>")
def councils_detail(council_id):
    c = get_or_404("SELECT * FROM councils WHERE council_id=?", (council_id,))
    comp = query(
        """SELECT cm.member_id, cm.full_name, cm.degree, cm.academic_title, s.code AS spec_code,
                  cc.position_in_council, cc.date_from
           FROM council_composition cc
           JOIN council_members cm ON cm.member_id = cc.member_id
           JOIN specialties s ON s.specialty_id = cm.specialty_id
           WHERE cc.council_id = ? AND cc.date_to IS NULL
           ORDER BY CASE cc.position_in_council WHEN 'chair' THEN 0 WHEN 'deputy' THEN 1
                    WHEN 'secretary' THEN 2 ELSE 3 END, cm.full_name""", (council_id,))
    available = query(
        """SELECT member_id, full_name FROM council_members
           WHERE member_id NOT IN (SELECT member_id FROM council_composition WHERE council_id=? AND date_to IS NULL)
           ORDER BY full_name""", (council_id,))
    diss = query(
        """SELECT d.*, cand.full_name AS candidate FROM dissertations d
           JOIN candidates cand ON cand.candidate_id = d.candidate_id
           WHERE d.council_id=? ORDER BY d.submitted_at DESC""", (council_id,))
    meetings = query("SELECT * FROM meetings WHERE council_id=? ORDER BY meeting_date DESC", (council_id,))
    n = len(comp)
    return render_template(
        "council_detail.html", c=c, comp=comp, available=available, diss=diss, meetings=meetings, n=n,
        required=services.ceil_share(n, services.QUORUM_NUM, services.QUORUM_DEN),
        doctors=sum(1 for r in comp if r["degree"] == "doctor"), min_spec=services.MIN_SPECIALISTS)


@app.route("/councils/<int:council_id>/members/add", methods=["POST"])
@write_required
def council_member_add(council_id):
    get_or_404("SELECT 1 FROM councils WHERE council_id=?", (council_id,))
    try:
        services.add_to_council(council_id, int(request.form.get("member_id", "0") or 0),
                                request.form.get("position", "member"), g.user["user_id"])
        flash("Член совета добавлен в состав", "ok")
    except BusinessError as e:
        flash(str(e), "error")
    except sqlite3.IntegrityError:
        flash("Выберите члена совета из списка", "error")
    return redirect(url_for("councils_detail", council_id=council_id))


@app.route("/councils/<int:council_id>/members/<int:member_id>/remove", methods=["POST"])
@write_required
def council_member_remove(council_id, member_id):
    services.remove_from_council(council_id, member_id, g.user["user_id"])
    flash("Член совета исключён из состава", "ok")
    return redirect(url_for("councils_detail", council_id=council_id))


# ---------------------------------------------------------------- соискатели
def candidate_fields():
    return [
        dict(name="full_name", label="ФИО соискателя", type="text"),
        dict(name="degree_sought", label="Искомая степень", type="select",
             options=[("candidate", "Кандидат наук"), ("doctor", "Доктор наук")]),
        dict(name="specialty_id", label="Специальность", type="select", options=spec_options()),
        dict(name="contact_info", label="Контакты", type="text", required=False, hint="e-mail или телефон"),
    ]


@app.route("/candidates")
def candidates_list():
    rows = []
    for r in query("""SELECT c.*, s.code AS spec_code FROM candidates c
                      JOIN specialties s ON s.specialty_id=c.specialty_id ORDER BY c.full_name"""):
        rows.append({"cells": [r["full_name"], DEGREE[r["degree_sought"]], r["spec_code"], r["contact_info"] or "—"],
                     "actions": row_actions("candidates_edit", "candidates_delete", "cand_id", r["candidate_id"],
                                            f"Удалить соискателя {r['full_name']}?")})
    return table_page("Соискатели", ["ФИО", "Искомая степень", "Специальность", "Контакты"], rows,
                      add_url=url_for("candidates_new"), add_label="Добавить соискателя")


@app.route("/candidates/new", methods=["GET", "POST"])
@write_required
def candidates_new():
    def save(d):
        cid = execute("INSERT INTO candidates (full_name, degree_sought, specialty_id, contact_info) VALUES (?,?,?,?)",
                      (d["full_name"], d["degree_sought"], int(d["specialty_id"]), d["contact_info"] or None))
        services.log_action(g.user["user_id"], "create", "candidates", cid)
    return handle_form("Новый соискатель", candidate_fields(), {}, save, url_for("candidates_list"), "Соискатель добавлен")


@app.route("/candidates/<int:cand_id>/edit", methods=["GET", "POST"])
@write_required
def candidates_edit(cand_id):
    row = get_or_404("SELECT * FROM candidates WHERE candidate_id=?", (cand_id,))

    def save(d):
        execute("UPDATE candidates SET full_name=?, degree_sought=?, specialty_id=?, contact_info=? WHERE candidate_id=?",
                (d["full_name"], d["degree_sought"], int(d["specialty_id"]), d["contact_info"] or None, cand_id))
        services.log_action(g.user["user_id"], "update", "candidates", cand_id)
    return handle_form("Изменить соискателя", candidate_fields(), clean(row), save,
                       url_for("candidates_list"), "Изменения сохранены")


@app.route("/candidates/<int:cand_id>/delete", methods=["POST"])
@write_required
def candidates_delete(cand_id):
    return safe_delete([("DELETE FROM candidates WHERE candidate_id=?", (cand_id,))], "candidates", cand_id,
                       url_for("candidates_list"), "Нельзя удалить: у соискателя есть диссертационное дело.")


# ---------------------------------------------------------------- диссертационные дела
def dissertation_fields():
    return [
        dict(name="candidate_id", label="Соискатель", type="select",
             options=[(c["candidate_id"], c["full_name"]) for c in query("SELECT * FROM candidates ORDER BY full_name")]),
        dict(name="council_id", label="Диссертационный совет", type="select",
             options=[(c["council_id"], f'{c["number"]} — {c["name"]}') for c in
                      query("SELECT * FROM councils WHERE status='active' ORDER BY number")]),
        dict(name="specialty_id", label="Специальность дела", type="select", options=spec_options(),
             hint="по ней проверяется, достаточно ли профильных докторов наук для кворума"),
        dict(name="topic", label="Тема диссертации", type="textarea"),
        dict(name="status", label="Статус", type="select", options=list(DISS_STATUS.items())),
        dict(name="submitted_at", label="Дата подачи", type="date"),
    ]


@app.route("/dissertations")
def dissertations_list():
    status = request.args.get("status", "")
    rows = []
    for r in query("""SELECT d.*, cand.full_name AS candidate, c.number AS council, s.code AS spec_code
                      FROM dissertations d JOIN candidates cand ON cand.candidate_id=d.candidate_id
                      JOIN councils c ON c.council_id=d.council_id
                      JOIN specialties s ON s.specialty_id=d.specialty_id
                      ORDER BY d.submitted_at DESC"""):
        if status and r["status"] != status:
            continue
        rows.append({"cells": [r["candidate"], r["topic"], r["spec_code"], r["council"],
                               {"t": DISS_STATUS[r["status"]], "badge": BADGES[r["status"]]}, fmt_d(r["submitted_at"])],
                     "actions": row_actions("dissertations_edit", "dissertations_delete", "diss_id", r["dissertation_id"],
                                            "Удалить диссертационное дело?")})
    filters = [dict(name="status", label="Статус", type="select", options=list(DISS_STATUS.items()), value=status)]
    return table_page("Диссертационные дела", ["Соискатель", "Тема", "Спец.", "Совет", "Статус", "Подано"], rows,
                      add_url=url_for("dissertations_new"), add_label="Зарегистрировать дело", filters=filters)


def diss_values(d):
    return (int(d["candidate_id"]), int(d["council_id"]), int(d["specialty_id"]), d["topic"], d["status"], d["submitted_at"])


@app.route("/dissertations/new", methods=["GET", "POST"])
@write_required
def dissertations_new():
    def save(d):
        did = execute("""INSERT INTO dissertations (candidate_id, council_id, specialty_id, topic, status, submitted_at)
                         VALUES (?,?,?,?,?,?)""", diss_values(d))
        services.log_action(g.user["user_id"], "create", "dissertations", did)
    return handle_form("Регистрация диссертационного дела", dissertation_fields(),
                       {"status": "submitted", "submitted_at": date.today().isoformat()}, save,
                       url_for("dissertations_list"), "Дело зарегистрировано")


@app.route("/dissertations/<int:diss_id>/edit", methods=["GET", "POST"])
@write_required
def dissertations_edit(diss_id):
    row = get_or_404("SELECT * FROM dissertations WHERE dissertation_id=?", (diss_id,))

    def save(d):
        execute("""UPDATE dissertations SET candidate_id=?, council_id=?, specialty_id=?, topic=?, status=?, submitted_at=?
                   WHERE dissertation_id=?""", diss_values(d) + (diss_id,))
        services.log_action(g.user["user_id"], "update", "dissertations", diss_id)
    return handle_form("Изменить диссертационное дело", dissertation_fields(), clean(row), save,
                       url_for("dissertations_list"), "Изменения сохранены")


@app.route("/dissertations/<int:diss_id>/delete", methods=["POST"])
@write_required
def dissertations_delete(diss_id):
    return safe_delete([("DELETE FROM dissertations WHERE dissertation_id=?", (diss_id,))], "dissertations", diss_id,
                       url_for("dissertations_list"), "Нельзя удалить: по делу назначены заседания или есть решение совета.")


# ---------------------------------------------------------------- заседания
def meeting_diss_options(council_id=None):
    sql = """SELECT d.dissertation_id, d.topic, cand.full_name, c.number FROM dissertations d
             JOIN candidates cand ON cand.candidate_id=d.candidate_id JOIN councils c ON c.council_id=d.council_id"""
    args = ()
    if council_id:
        sql += " WHERE d.council_id=?"
        args = (council_id,)
    return [(r["dissertation_id"], f'{r["full_name"]} — {r["topic"][:60]} ({r["number"]})') for r in query(sql + " ORDER BY cand.full_name", args)]


@app.route("/meetings")
def meetings_list():
    rows = []
    for r in query("""SELECT m.*, c.number, cand.full_name AS candidate, d.topic, p.protocol_id, p.protocol_number
                      FROM meetings m JOIN councils c ON c.council_id=m.council_id
                      LEFT JOIN dissertations d ON d.dissertation_id=m.dissertation_id
                      LEFT JOIN candidates cand ON cand.candidate_id=d.candidate_id
                      LEFT JOIN protocols p ON p.meeting_id=m.meeting_id
                      ORDER BY m.meeting_date DESC"""):
        open_url = url_for("meetings_detail", meeting_id=r["meeting_id"])
        rows.append({
            "cells": [{"t": f'№{r["meeting_id"]}', "href": open_url}, fmt_dt(r["meeting_date"]), r["number"],
                      f'{r["candidate"]} — {r["topic"]}' if r["candidate"] else "Организационное заседание",
                      {"t": MEETING_STATUS[r["status"]], "badge": BADGES[r["status"]]},
                      {"t": r["protocol_number"], "href": url_for("protocol_view", protocol_id=r["protocol_id"])}
                      if r["protocol_id"] else "—"],
            "actions": [{"label": "Открыть", "href": open_url}] + (
                [{"label": "Удалить", "post": url_for("meetings_delete", meeting_id=r["meeting_id"]),
                  "confirm": "Удалить заседание?"}] if can_write() else []),
        })
    return table_page("Заседания", ["№", "Дата и время", "Совет", "Повестка", "Статус", "Протокол"], rows,
                      add_url=url_for("meetings_new"), add_label="Назначить заседание",
                      subtitle="Откройте заседание, чтобы отметить явку, проверить кворум и оформить протокол.")


@app.route("/meetings/new", methods=["GET", "POST"])
@write_required
def meetings_new():
    fields = [
        dict(name="council_id", label="Диссертационный совет", type="select",
             options=[(c["council_id"], f'{c["number"]} — {c["name"]}') for c in
                      query("SELECT * FROM councils WHERE status='active' ORDER BY number")]),
        dict(name="dissertation_id", label="Диссертационное дело", type="select", required=False,
             options=meeting_diss_options(), placeholder="— организационное заседание (без дела) —",
             hint="дело должно быть закреплено за выбранным советом"),
        dict(name="meeting_date", label="Дата и время", type="datetime-local"),
    ]
    created = {}

    def save(d):
        created["id"] = services.create_meeting(int(d["council_id"]), int(d["dissertation_id"] or 0),
                                                d["meeting_date"], g.user["user_id"])

    resp = handle_form("Новое заседание", fields, {}, save, url_for("meetings_list"), "Заседание назначено")
    if created:
        return redirect(url_for("meetings_detail", meeting_id=created["id"]))
    return resp


@app.route("/meetings/<int:meeting_id>/edit", methods=["GET", "POST"])
@write_required
def meetings_edit(meeting_id):
    m = get_or_404("SELECT * FROM meetings WHERE meeting_id=?", (meeting_id,))
    if m["status"] == "held":
        flash("Проведённое заседание изменять нельзя", "error")
        return redirect(url_for("meetings_detail", meeting_id=meeting_id))
    fields = [
        dict(name="dissertation_id", label="Диссертационное дело", type="select", required=False,
             options=meeting_diss_options(m["council_id"]), placeholder="— организационное заседание (без дела) —"),
        dict(name="meeting_date", label="Дата и время", type="datetime-local"),
        dict(name="status", label="Статус", type="select",
             options=[("planned", "Запланировано"), ("cancelled", "Отменено")]),
    ]

    def save(d):
        services.update_meeting(meeting_id, int(d["dissertation_id"] or 0), d["meeting_date"], d["status"], g.user["user_id"])
    return handle_form(f"Изменить заседание №{meeting_id}", fields, clean(m), save,
                       url_for("meetings_detail", meeting_id=meeting_id), "Изменения сохранены")


@app.route("/meetings/<int:meeting_id>/delete", methods=["POST"])
@write_required
def meetings_delete(meeting_id):
    return safe_delete([("DELETE FROM meeting_attendance WHERE meeting_id=?", (meeting_id,)),
                        ("DELETE FROM meetings WHERE meeting_id=?", (meeting_id,))],
                       "meetings", meeting_id, url_for("meetings_list"),
                       "Нельзя удалить: по заседанию уже оформлен протокол.")


@app.route("/meetings/<int:meeting_id>")
def meetings_detail(meeting_id):
    m = get_or_404(
        """SELECT m.*, c.number AS council_number, c.name AS council_name, d.topic, d.specialty_id AS diss_spec,
                  cand.full_name AS candidate, cand.degree_sought, s.code AS spec_code
           FROM meetings m JOIN councils c ON c.council_id=m.council_id
           LEFT JOIN dissertations d ON d.dissertation_id=m.dissertation_id
           LEFT JOIN candidates cand ON cand.candidate_id=d.candidate_id
           LEFT JOIN specialties s ON s.specialty_id=d.specialty_id
           WHERE m.meeting_id=?""", (meeting_id,))
    if m["status"] != "cancelled" and not services.has_protocol(meeting_id):
        services.ensure_attendance(meeting_id)
    att = services.attendance_list(meeting_id)
    q = services.evaluate_quorum(meeting_id)
    proto = services.has_protocol(meeting_id)
    bundle = services.get_protocol_bundle(proto["protocol_id"]) if proto else None
    return render_template("meeting_detail.html", m=m, att=att, q=q, bundle=bundle)


@app.route("/meetings/<int:meeting_id>/attendance", methods=["POST"])
@write_required
def meetings_attendance(meeting_id):
    get_or_404("SELECT 1 FROM meetings WHERE meeting_id=?", (meeting_id,))
    try:
        q = services.save_attendance(meeting_id, request.form.getlist("present"), g.user["user_id"])
        flash("Явка сохранена. " + ("Кворум есть." if q["ok"] else "Кворума пока нет."), "ok" if q["ok"] else "warn")
    except BusinessError as e:
        flash(str(e), "error")
    return redirect(url_for("meetings_detail", meeting_id=meeting_id))


@app.route("/meetings/<int:meeting_id>/protocol", methods=["POST"])
@write_required
def meetings_protocol(meeting_id):
    get_or_404("SELECT 1 FROM meetings WHERE meeting_id=?", (meeting_id,))
    votes = {}
    for key, value in request.form.items():
        if key.startswith("vote_") and key[5:].isdigit():
            votes[int(key[5:])] = value
    try:
        pid = services.register_protocol(meeting_id, votes, g.user["user_id"])
        flash("Протокол оформлен, решение совета зафиксировано, статус дела обновлён.", "ok")
        return redirect(url_for("protocol_view", protocol_id=pid))
    except BusinessError as e:
        flash(str(e), "error")
    return redirect(url_for("meetings_detail", meeting_id=meeting_id))


@app.route("/protocols/<int:protocol_id>")
def protocol_view(protocol_id):
    bundle = services.get_protocol_bundle(protocol_id)
    if bundle is None:
        abort(404)
    attendees = query(
        """SELECT cm.full_name, cm.degree, cm.academic_title, s.code AS spec_code
           FROM meeting_attendance a JOIN council_members cm ON cm.member_id=a.member_id
           JOIN specialties s ON s.specialty_id=cm.specialty_id
           WHERE a.meeting_id=? AND a.is_present=1 ORDER BY cm.full_name""", (bundle["p"]["meeting_id"],))
    return render_template("protocol.html", b=bundle, attendees=attendees)


# ---------------------------------------------------------------- журнал действий
@app.route("/audit")
def audit_view():
    rows = []
    for r in query("""SELECT a.*, u.full_name FROM audit_log a LEFT JOIN users u ON u.user_id=a.user_id
                      ORDER BY a.log_id DESC LIMIT 200"""):
        rows.append({"cells": [fmt_dt(r["created_at"]), r["full_name"] or "—",
                               ACTION_LABELS.get(r["action"], r["action"]),
                               ENTITY_LABELS.get(r["entity"], r["entity"]), r["entity_id"] or "—"],
                     "actions": []})
    return table_page("Журнал действий", ["Время", "Пользователь", "Действие", "Раздел", "ID записи"], rows,
                      subtitle="Протоколирование — сквозная функциональность системы: все изменения данных фиксируются здесь.")


# ---------------------------------------------------------------- запуск
def ensure_db(reset=False):
    if reset and os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    if not os.path.exists(db.DB_PATH):
        db.init_db()
        with app.app_context():
            seed.run()
        print("База данных создана и заполнена демонстрационными данными.")


if __name__ == "__main__":
    ensure_db(reset="--reset" in sys.argv)
    print("Откройте в браузере: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
