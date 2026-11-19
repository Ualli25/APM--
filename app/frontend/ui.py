"""Streamlit client for the Academic Council Secretary REST API."""
import os
from datetime import date, datetime, time

import requests
import streamlit as st

API = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="АРМ секретаря совета", page_icon="🎓", layout="wide")
st.title("АРМ секретаря Учёного совета")
st.caption("Учёт состава совета, соискателей, диссертаций и заседаний")


def api(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API}{path}", timeout=8, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None
    except requests.RequestException as exc:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
        st.error(f"Не удалось обратиться к серверу: {detail}")
        return None


def show_table(path: str, empty: str = "Записей пока нет"):
    rows = api("GET", path)
    if rows is None:
        return []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info(empty)
    return rows


section = st.sidebar.radio(
    "Раздел",
    ["Обзор", "Члены совета", "Советы", "Соискатели", "Диссертации", "Заседания"],
)

if section == "Обзор":
    left, right = st.columns(2)
    with left:
        st.subheader("Советы")
        councils = show_table("/api/councils")
        st.metric("Всего советов", len(councils))
    with right:
        st.subheader("Ближайшие заседания")
        meetings = show_table("/api/meetings")
        st.metric("Всего заседаний", len(meetings))
    st.info("Подробная интерактивная документация API доступна по адресу сервера /docs.")

elif section == "Члены совета":
    st.subheader("Состав членов совета")
    show_table("/api/members")
    specialties = api("GET", "/api/specialties") or []
    with st.expander("Добавить члена совета"):
        if specialties:
            with st.form("create_member"):
                full_name = st.text_input("ФИО")
                degree = st.selectbox("Учёная степень", ["doctor", "candidate"], format_func=lambda v: {"doctor": "Доктор наук", "candidate": "Кандидат наук"}[v])
                title = st.text_input("Учёное звание")
                spec = st.selectbox("Специальность", specialties, format_func=lambda v: f"{v['code']} — {v['name']}")
                if st.form_submit_button("Сохранить"):
                    result = api("POST", "/api/members", json={"full_name": full_name, "degree": degree, "academic_title": title or None, "specialty_id": spec["specialty_id"]})
                    if result:
                        st.success("Член совета добавлен")
                        st.rerun()
        else:
            st.warning("Сначала добавьте специальности через API /docs.")

elif section == "Советы":
    st.subheader("Диссертационные советы")
    show_table("/api/councils")
    with st.form("create_council"):
        number = st.text_input("Номер совета")
        name = st.text_input("Название")
        department = st.text_input("Подразделение")
        if st.form_submit_button("Создать совет"):
            result = api("POST", "/api/councils", json={"number": number, "name": name, "department": department})
            if result:
                st.success("Совет создан")
                st.rerun()

elif section == "Соискатели":
    st.subheader("Соискатели")
    show_table("/api/candidates")
    specialties = api("GET", "/api/specialties") or []
    if specialties:
        with st.form("create_candidate"):
            full_name = st.text_input("ФИО")
            degree = st.selectbox("Искомая степень", ["candidate", "doctor"], format_func=lambda v: {"doctor": "Доктор наук", "candidate": "Кандидат наук"}[v])
            contact = st.text_input("Контакт")
            spec = st.selectbox("Специальность", specialties, format_func=lambda v: f"{v['code']} — {v['name']}")
            if st.form_submit_button("Добавить соискателя"):
                result = api("POST", "/api/candidates", json={"full_name": full_name, "degree_sought": degree, "specialty_id": spec["specialty_id"], "contact_info": contact or None})
                if result:
                    st.success("Соискатель добавлен")
                    st.rerun()

elif section == "Диссертации":
    st.subheader("Диссертационные дела")
    show_table("/api/dissertations")
    candidates = api("GET", "/api/candidates") or []
    councils = api("GET", "/api/councils") or []
    specialties = api("GET", "/api/specialties") or []
    if candidates and councils and specialties:
        with st.form("create_dissertation"):
            candidate = st.selectbox("Соискатель", candidates, format_func=lambda v: v["full_name"])
            council = st.selectbox("Совет", councils, format_func=lambda v: f"{v['number']} — {v['name']}")
            specialty = st.selectbox("Специальность", specialties, format_func=lambda v: f"{v['code']} — {v['name']}")
            topic = st.text_input("Тема диссертации")
            submitted = st.date_input("Дата подачи", value=date.today())
            if st.form_submit_button("Зарегистрировать дело"):
                result = api("POST", "/api/dissertations", json={"candidate_id": candidate["candidate_id"], "council_id": council["council_id"], "specialty_id": specialty["specialty_id"], "topic": topic, "submitted_at": submitted.isoformat()})
                if result:
                    st.success("Диссертационное дело зарегистрировано")
                    st.rerun()

elif section == "Заседания":
    st.subheader("Заседания")
    meetings = show_table("/api/meetings")
    councils = api("GET", "/api/councils") or []
    dissertations = api("GET", "/api/dissertations") or []
    with st.expander("Запланировать заседание"):
        if councils:
            with st.form("create_meeting"):
                council = st.selectbox("Совет", councils, format_func=lambda v: f"{v['number']} — {v['name']}")
                dissertation = st.selectbox("Диссертационное дело", [None] + dissertations, format_func=lambda v: "Без привязки" if v is None else f"#{v['dissertation_id']} — {v['topic']}")
                meeting_day = st.date_input("Дата", value=date.today())
                meeting_time = st.time_input("Время", value=time(10, 0))
                if st.form_submit_button("Создать заседание"):
                    result = api("POST", "/api/meetings", json={"council_id": council["council_id"], "dissertation_id": dissertation["dissertation_id"] if dissertation else None, "meeting_date": datetime.combine(meeting_day, meeting_time).isoformat()})
                    if result:
                        st.success("Заседание создано")
                        st.rerun()

    if meetings:
        chosen = st.selectbox("Работа с заседанием", meetings, format_func=lambda v: f"#{v['meeting_id']} — {v['meeting_date']}")
        council_members = api("GET", f"/api/councils/{chosen['council_id']}/members") or []
        with st.form(f"attendance_{chosen['meeting_id']}"):
            present = st.multiselect("Присутствующие члены совета", council_members, format_func=lambda v: f"{v['member_id']} — {v['full_name']} ({v['degree']})")
            if st.form_submit_button("Сохранить явку и проверить кворум"):
                result = api("PUT", f"/api/meetings/{chosen['meeting_id']}/attendance", json={"present_member_ids": [person["member_id"] for person in present]})
                if result:
                    st.success("Кворум есть" if result["quorum_met"] else "Кворума нет")
                    st.json(result)
        if st.button("Проверить текущий кворум", key=f"quorum_{chosen['meeting_id']}"):
            result = api("GET", f"/api/meetings/{chosen['meeting_id']}/quorum")
            if result:
                st.success("Кворум есть" if result["quorum_met"] else "Кворума нет")
                st.json(result)
        with st.form(f"protocol_{chosen['meeting_id']}"):
            voters = st.multiselect("Члены совета, присутствующие на голосовании", council_members, format_func=lambda v: f"{v['member_id']} — {v['full_name']}", key=f"voters_{chosen['meeting_id']}")
            votes = {person["member_id"]: st.selectbox(f"Голос: {person['full_name']}", ["for", "against", "abstain"], format_func=lambda v: {"for": "За", "against": "Против", "abstain": "Воздержался"}[v], key=f"vote_{chosen['meeting_id']}_{person['member_id']}") for person in voters}
            if st.form_submit_button("Оформить протокол и решение"):
                result = api("POST", f"/api/meetings/{chosen['meeting_id']}/protocol", json={"votes": votes, "created_by": 1})
                if result:
                    st.success("Протокол и решение сохранены")
                    st.json(result)
