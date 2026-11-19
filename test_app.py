"""Автотест основных сценариев. Запуск: python test_app.py"""
import os
import tempfile
import importlib.util

tmp = tempfile.mkdtemp()
os.environ["ARM_DB"] = os.path.join(tmp, "test.db")

legacy_app_path = os.path.join(os.path.dirname(__file__), "app.py")
legacy_spec = importlib.util.spec_from_file_location("legacy_flask_app", legacy_app_path)
appmod = importlib.util.module_from_spec(legacy_spec)
legacy_spec.loader.exec_module(appmod)
from db import query  # noqa: E402

appmod.ensure_db(reset=True)
app = appmod.app
app.config["TESTING"] = True

failed = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        failed.append(name)


def login(client, user, pwd):
    return client.post("/login", data={"login": user, "password": pwd}, follow_redirects=True)


def html(r):
    return r.get_data(as_text=True)


sec = app.test_client()
# --- без входа редирект на логин
r = sec.get("/members")
check("без входа -> редирект на /login", r.status_code == 302 and "/login" in r.headers["Location"])
r = login(sec, "secretary", "wrong")
check("неверный пароль отклонён", "Неверный логин или пароль" in html(r))
r = login(sec, "secretary", "secretary123")
check("вход секретаря", r.status_code == 200 and "Ближайшие заседания" in html(r))

# --- все GET-страницы открываются
for url in ["/", "/councils", "/councils/1", "/councils/new", "/members", "/members/new", "/members/1/edit",
            "/candidates", "/candidates/new", "/dissertations", "/dissertations/new", "/dissertations/1/edit",
            "/meetings", "/meetings/new", "/meetings/1", "/meetings/2", "/protocols/1", "/specialties",
            "/specialties/new", "/audit", "/members?q=смирнов", "/dissertations?status=scheduled"]:
    r = sec.get(url)
    check(f"GET {url} -> 200", r.status_code == 200)

check("поиск по ФИО без учёта регистра кириллицы", "Смирнов" in html(sec.get("/members?q=смирнов")) and "Кузнецова" not in html(sec.get("/members?q=смирнов")))

# --- CREATE / UPDATE / DELETE члена совета
r = sec.post("/members/new", data={"full_name": "Тестов Тест Тестович", "degree": "doctor", "academic_title": "", "specialty_id": "1"}, follow_redirects=True)
check("создание члена совета", "Тестов Тест Тестович" in html(r))
mid = query("SELECT member_id FROM council_members WHERE full_name='Тестов Тест Тестович'", one=True) if False else None
with app.app_context():
    mid = query("SELECT member_id FROM council_members WHERE full_name='Тестов Тест Тестович'", one=True)["member_id"]
r = sec.post(f"/members/{mid}/edit", data={"full_name": "Тестов Изменённый", "degree": "candidate", "academic_title": "доцент", "specialty_id": "2"}, follow_redirects=True)
check("изменение члена совета", "Тестов Изменённый" in html(r))
r = sec.post("/members/new", data={"full_name": "", "degree": "doctor", "specialty_id": "1"})
check("валидация: пустое ФИО не сохраняется", "Обязательное поле" in html(r))
r = sec.post(f"/members/{mid}/delete", follow_redirects=True)
check("удаление члена совета", "Запись удалена" in html(r) and "Тестов Изменённый" not in html(r))
r = sec.post("/members/1/delete", follow_redirects=True)
check("нельзя удалить члена совета, который в составе (целостность)", "Нельзя удалить" in html(r))
r = sec.post("/specialties/1/delete", follow_redirects=True)
check("нельзя удалить используемую специальность", "Нельзя удалить" in html(r))

# --- совет: состав и бизнес-правила
r = sec.post("/councils/new", data={"number": "Д 777.000.01", "name": "Тестовый совет", "department": "Каф.", "status": "active"}, follow_redirects=True)
check("создание совета", "Тестовый совет" in html(r))
with app.app_context():
    cid = query("SELECT council_id FROM councils WHERE number='Д 777.000.01'", one=True)["council_id"]
r = sec.post(f"/councils/{cid}/members/add", data={"member_id": "1", "position": "chair"}, follow_redirects=True)
check("добавление председателя", "добавлен в состав" in html(r))
r = sec.post(f"/councils/{cid}/members/add", data={"member_id": "2", "position": "chair"}, follow_redirects=True)
check("правило: второй председатель запрещён", "уже назначен" in html(r))
r = sec.post(f"/councils/{cid}/members/add", data={"member_id": "1", "position": "member"}, follow_redirects=True)
check("правило: дубликат в составе запрещён", "уже входит" in html(r))
r = sec.post("/meetings/new", data={"council_id": "2", "dissertation_id": "1", "meeting_date": "2026-11-01T10:00"}, follow_redirects=True)
check("правило: дело другого совета нельзя поставить на заседание", "закреплено за другим советом" in html(r))
r = sec.post(f"/councils/{cid}/delete", follow_redirects=True)
check("удаление пустого совета", "Запись удалена" in html(r))

# --- заседание 2 (будущее): кворум и протокол
r = sec.get("/meetings/2")
check("до отметки явки кворума нет", "Кворума нет" in html(r) and "Оформить протокол нельзя" in html(r))
r = sec.post("/meetings/2/protocol", data={"vote_1": "for"}, follow_redirects=True)
check("протокол без кворума отклоняется сервером", "Кворум не достигнут" in html(r))
# присутствуют 6 из 8, но доктора по 05.13.19 — только 2 (члены 1,2) + остальные не профильные
r = sec.post("/meetings/2/attendance", data={"present": ["1", "2", "5", "6", "7", "8"]}, follow_redirects=True)
check("явка 6/8 есть, но профильных докторов мало -> кворума нет", "Кворума пока нет" in html(r) and "Докторов наук по специальности" in html(r))
r = sec.post("/meetings/2/attendance", data={"present": ["1", "2", "3", "4", "5", "6"]}, follow_redirects=True)
check("явка 6/8 и 4 профильных доктора -> кворум есть", "Кворум есть" in html(r))
check("появилась форма голосования", "Оформить протокол и решение" in html(r))
r = sec.post("/meetings/2/protocol", data={f"vote_{i}": "for" for i in [1, 2, 3, 4, 5]}, follow_redirects=True)
check("нельзя оформить без голоса каждого присутствующего", "Укажите голос каждого" in html(r))
votes = {f"vote_{i}": "for" for i in [1, 2, 3, 4]}
votes.update({"vote_5": "against", "vote_6": "against"})   # 4 из 6 = ровно 2/3 -> присуждено
r = sec.post("/meetings/2/protocol", data=votes, follow_redirects=True)
check("протокол оформлен (4 из 6 «за» = 2/3)", "ПРОТОКОЛ №" in html(r) and "Присудить" in html(r))
with app.app_context():
    d = query("SELECT status FROM dissertations WHERE dissertation_id=1", one=True)["status"]
    mt = query("SELECT status FROM meetings WHERE meeting_id=2", one=True)["status"]
check("статус дела -> defended, заседание -> held", d == "defended" and mt == "held")
r = sec.post("/meetings/2/attendance", data={"present": ["1"]}, follow_redirects=True)
check("после протокола явку менять нельзя", "Протокол уже оформлен" in html(r))
r = sec.post("/meetings/2/protocol", data=votes, follow_redirects=True)
check("повторный протокол запрещён", "уже оформлен" in html(r))
r = sec.post("/meetings/2/delete", follow_redirects=True)
check("заседание с протоколом удалить нельзя", "Нельзя удалить" in html(r))

# --- создание заседания и удаление
r = sec.post("/meetings/new", data={"council_id": "1", "dissertation_id": "2", "meeting_date": "2026-11-05T12:00"}, follow_redirects=True)
check("создание заседания -> страница заседания", "Явка членов совета" in html(r))
with app.app_context():
    nid = query("SELECT MAX(meeting_id) m FROM meetings", one=True)["m"]
r = sec.post(f"/meetings/{nid}/delete", follow_redirects=True)
check("удаление заседания без протокола", "Запись удалена" in html(r))

# --- дела и соискатели
r = sec.post("/candidates/new", data={"full_name": "Новый Соискатель", "degree_sought": "candidate", "specialty_id": "1", "contact_info": ""}, follow_redirects=True)
check("создание соискателя", "Новый Соискатель" in html(r))
with app.app_context():
    kid = query("SELECT candidate_id FROM candidates WHERE full_name='Новый Соискатель'", one=True)["candidate_id"]
r = sec.post("/dissertations/new", data={"candidate_id": str(kid), "council_id": "1", "specialty_id": "1", "topic": "Тест", "status": "submitted", "submitted_at": "2026-10-10"}, follow_redirects=True)
check("регистрация дела", "Дело зарегистрировано" in html(r))
r = sec.post(f"/candidates/{kid}/delete", follow_redirects=True)
check("нельзя удалить соискателя с делом", "Нельзя удалить" in html(r))
r = sec.post("/dissertations/new", data={"candidate_id": str(kid), "council_id": "1", "specialty_id": "1", "topic": "Тест", "status": "submitted", "submitted_at": "32.13.2026"})
check("валидация даты", "Неверный формат даты" in html(r))

# --- печать протокола и журнал
r = sec.get("/protocols/1")
check("печатная форма протокола", "Присутствовали" in html(r) and "Результаты голосования" in html(r))
check("журнал содержит действия", "Оформление протокола" in html(sec.get("/audit")))

# --- роль «член совета»: только просмотр
mem = app.test_client()
login(mem, "member", "member123")
check("член совета видит список", mem.get("/members").status_code == 200)
check("член совета: нет кнопки добавления", "Добавить члена совета" not in html(mem.get("/members")))
check("член совета: POST запрещён (403)", mem.post("/members/new", data={"full_name": "X"}).status_code == 403)
check("член совета: удаление запрещено (403)", mem.post("/members/1/delete").status_code == 403)
check("член совета может открыть протокол", mem.get("/protocols/1").status_code == 200)

# --- безопасность: открытый редирект
r = app.test_client().post("/login?next=//evil.com", data={"login": "secretary", "password": "secretary123"})
check("редирект после входа не уходит на внешний сайт", r.status_code == 302 and "evil.com" not in r.headers["Location"])

print()
print("ПРОВАЛЕНО:" if failed else "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ", failed if failed else "")
raise SystemExit(1 if failed else 0)
