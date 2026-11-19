"""Regenerate the ER diagram PNG with Pillow (no external services required)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("er_diagram.png")
W, H = 2400, 1420
image = Image.new("RGB", (W, H), "#f5f7fb")
draw = ImageDraw.Draw(image)
font_path = Path("C:/Windows/Fonts/arial.ttf")
title_font = ImageFont.truetype(str(font_path), 44)
head_font = ImageFont.truetype(str(font_path), 27)
body_font = ImageFont.truetype(str(font_path), 20)
small_font = ImageFont.truetype(str(font_path), 17)

draw.text((60, 25), "ER-диаграмма — АРМ секретаря Учёного совета", font=title_font, fill="#17324d")
draw.text((62, 82), "Первичные ключи (PK), внешние ключи (FK) и основные связи", font=small_font, fill="#53677c")

boxes = {
    "ROLES": (50, 150, "Роли (roles)", ["PK role_id", "name, title"]),
    "USERS": (50, 390, "Пользователи (users)", ["PK user_id", "FK role_id → roles", "full_name, login, password_hash"]),
    "AUDIT": (50, 630, "Журнал (audit_log)", ["PK log_id", "FK user_id → users", "action, entity, created_at"]),
    "SPECIALTIES": (50, 870, "Специальности (specialties)", ["PK specialty_id", "code, name"]),
    "MEMBERS": (50, 1110, "Члены совета (council_members)", ["PK member_id", "FK specialty_id, user_id", "full_name, degree, academic_title"]),
    "COUNCILS": (830, 150, "Советы (councils)", ["PK council_id", "number, name, department, status"]),
    "COMPOSITION": (830, 390, "Состав совета (council_composition)", ["PK id", "FK council_id → councils", "FK member_id → council_members"]),
    "CANDIDATES": (830, 630, "Соискатели (candidates)", ["PK candidate_id", "FK specialty_id → specialties", "full_name, degree_sought, contact_info"]),
    "DISSERTATIONS": (830, 870, "Диссертации (dissertations)", ["PK dissertation_id", "FK candidate_id, council_id, specialty_id", "topic, status, submitted_at"]),
    "MEETINGS": (830, 1110, "Заседания (meetings)", ["PK meeting_id", "FK council_id, dissertation_id", "meeting_date, quorum_met, status"]),
    "ATTENDANCE": (1610, 150, "Явка (meeting_attendance)", ["PK id", "FK meeting_id → meetings", "FK member_id → council_members"]),
    "PROTOCOLS": (1610, 390, "Протоколы (protocols)", ["PK protocol_id", "FK meeting_id, created_by", "protocol_number, signed_date"]),
    "VOTES": (1610, 630, "Голоса (votes)", ["PK vote_id", "FK protocol_id, member_id", "vote_value"]),
    "DECISIONS": (1610, 870, "Решения (decisions)", ["PK decision_id", "FK meeting_id, dissertation_id", "decision_text, result, decision_date"]),
}
box_w, box_h = 700, 185
centers = {}

# Connectors are drawn before the entity boxes, so they remain behind the text.
edges = [
    ("ROLES", "USERS"), ("USERS", "AUDIT"),
    ("SPECIALTIES", "MEMBERS"), ("COUNCILS", "COMPOSITION"),
    ("MEMBERS", "COMPOSITION"), ("SPECIALTIES", "CANDIDATES"),
    ("CANDIDATES", "DISSERTATIONS"), ("COUNCILS", "DISSERTATIONS"),
    ("DISSERTATIONS", "MEETINGS"), ("COUNCILS", "MEETINGS"),
    ("MEETINGS", "ATTENDANCE"), ("MEMBERS", "ATTENDANCE"),
    ("MEETINGS", "PROTOCOLS"), ("USERS", "PROTOCOLS"),
    ("PROTOCOLS", "VOTES"), ("MEMBERS", "VOTES"),
    ("MEETINGS", "DECISIONS"), ("DISSERTATIONS", "DECISIONS"),
]
for key, (x, y, _title, _fields) in boxes.items():
    centers[key] = (x + box_w // 2, y + box_h // 2)
for source, target in edges:
    sx, sy = centers[source]
    tx, ty = centers[target]
    dx, dy = tx - sx, ty - sy
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    source_scale = min((box_w / 2) / abs(dx) if dx else float("inf"), (box_h / 2) / abs(dy) if dy else float("inf"))
    target_scale = source_scale
    start = (sx + dx * source_scale, sy + dy * source_scale)
    end = (tx - dx * target_scale, ty - dy * target_scale)
    draw.line((*start, *end), fill="#86a7c7", width=3)
    ax, ay = end[0] - ux * 16, end[1] - uy * 16
    draw.polygon([end, (ax + px * 8, ay + py * 8), (ax - px * 8, ay - py * 8)], fill="#527b9f")

for key, (x, y, title, fields) in boxes.items():
    draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=18, fill="white", outline="#31658a", width=3)
    draw.rounded_rectangle((x, y, x + box_w, y + 48), radius=18, fill="#e5eff8", outline="#31658a", width=2)
    draw.rectangle((x, y + 30, x + box_w, y + 48), fill="#e5eff8")
    draw.text((x + 17, y + 8), title, font=head_font, fill="#163b59")
    for index, line in enumerate(fields):
        draw.text((x + 19, y + 58 + index * 32), line, font=body_font, fill="#293b4a")

image.save(OUT, optimize=True)
print(OUT.name)
