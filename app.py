
import streamlit as st
import pandas as pd
import math
import json
import requests
import re
st.set_page_config(
    page_title="ניהול אירוע קהילתי",
    page_icon="🚌",
    layout="wide"
)

# הגנה על הדשבורד באמצעות סיסמה
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 כניסה למערכת ניהול האירוע")

    password = st.text_input(
        "הכניסי את סיסמת המארגנים",
        type="password"
    )

    if st.button("כניסה"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("סיסמה שגויה")

    st.stop()

st.title("📊 מערכת ניהול אירוע קהילתי")



BUS_CAPACITY = 50
MIN_NEW_BUS_PASSENGERS = 10
NEIGHBORHOODS = ["א", "ב", "ג", "ד"]

# מרחקים דמיוניים בין שכונות
DISTANCES = {
    "א": {"א": 0, "ב": 2, "ג": 5, "ד": 8},
    "ב": {"א": 2, "ב": 0, "ג": 3, "ד": 6},
    "ג": {"א": 5, "ב": 3, "ג": 0, "ד": 3},
    "ד": {"א": 8, "ב": 6, "ג": 3, "ד": 0},
}


# טעינת הרשמות מ-Google Sheets
SHEETS_URL = st.secrets["SHEETS_URL"]
API_TOKEN = st.secrets["API_TOKEN"]

try:
    response = requests.post(SHEETS_URL, json={"token": API_TOKEN}, timeout=30)
    response.raise_for_status()
    sheet_data = response.json()
    if not sheet_data.get("success"):
        st.error("שגיאה בטעינת ההרשמות מ-Google Sheets")
        st.stop()
    registrations = sheet_data.get("registrations", [])
except (requests.RequestException, ValueError) as exc:
    st.error("לא ניתן להתחבר ל-Google Sheets. בדקי את כתובת השירות ואת הפריסה.")
    st.stop()


def field(row, phrase, default=""):
    """Find the first populated matching field, including duplicate headers with (2), (3)..."""
    for key, value in row.items():
        if phrase in str(key) and value is not None and str(value).strip():
            return str(value).strip()
    return default


def participant_field(row, phrase, number, default=""):
    # Exact participant index, including repeated Form section headers
    pattern = re.compile(r"\[משתתף\s*" + str(number) + r"\]")
    for key, value in row.items():
        if phrase in str(key) and pattern.search(str(key)) and value is not None and str(value).strip():
            return str(value).strip()
    return default


def parse_count(value):
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def normalize_neighborhood(value):
    text = str(value).strip()
    if text in NEIGHBORHOODS:
        return text
    match = re.search(r"שכונה\s*([אבגד])", text)
    return match.group(1) if match else text


families = []
for index, row in enumerate(registrations, start=1):
    raw_count = field(row, "מספר המשתתפים הכולל")
    count = parse_count(raw_count)
    if count is None:
        st.warning(f"הרשמה {index}: לא זוהה מספר משתתפים. יש לבדוק את התשובה בטופס.")
        count = 0

  
    neighborhood = normalize_neighborhood(row.get("כתובת", ""))

    transport_answer = field(row, "אופן הגעה לאירוע")
    # Unknown transport answers are NOT treated as requiring a bus.
    needs_transport = "הסעה" in transport_answer and "לא" not in transport_answer

    members = []
    for number in range(1, count + 1):
        members.append({
            "name": f"משתתף {number}",
            "meal": participant_field(row, "העדפת תזונה עיקרית", number),
            "allergy": participant_field(row, "פירוט המגבלה או האלרגיה", number),
        })

    families.append({
        "id": str(index).zfill(3),
        "contact": field(row, "שם מלא איש הקשר המרכזי"),
        "email": field(row, "כתובת דואר אלקטרוני"),
        "neighborhood": neighborhood,
        "transport": needs_transport,
        "transport_answer": transport_answer,
        "members": members,
        "expected_count": count,
        "original_answers": row,
    })

st.success(f"נטענו {len(families)} משפחות מ-Google Sheets")


def validate_family(family):
    issues = []
    if not family.get("email") or "@" not in family["email"]:
        issues.append("כתובת אימייל חסרה או לא תקינה")
    if family["expected_count"] != len(family["members"]) or not family["members"]:
        issues.append("מספר המשתתפים חסר או אינו תואם")
    if family["neighborhood"] not in NEIGHBORHOODS:
        issues.append("שכונה לא מזוהה")
    if not family["transport_answer"]:
        issues.append("חסרה תשובה על אופן ההגעה")
    # Missing meal/allergy details should be reviewed, but should not block bus assignment.
    return issues


def assign_buses(families, capacity):
    buses = []
    assignments = {}
    waiting = []

    eligible = [
        f for f in families
        if f["transport"] and not validate_family(f)
    ]

    eligible.sort(
        key=lambda f: len(f["members"]),
        reverse=True
    )

    def add_bus(neighborhood):
        bus = {
            "number": len(buses) + 1,
            "pickup": neighborhood,
            "remaining": capacity,
            "families": []
        }
        buses.append(bus)
        return bus

    def place_family(family, bus):
        size = len(family["members"])
        bus["remaining"] -= size
        bus["families"].append(family["id"])

        assignments[family["id"]] = {
            "status": "שובץ",
            "bus": bus["number"],
            "pickup": bus["pickup"]
        }

    # אוטובוס בסיסי לכל שכונה עם ביקוש להסעה
    for neighborhood in NEIGHBORHOODS:
        if any(
            f["neighborhood"] == neighborhood
            for f in eligible
        ):
            add_bus(neighborhood)

    # שלב ראשון: שיבוץ בשכונת המגורים
    for family in eligible:
        size = len(family["members"])
        home = family["neighborhood"]

        if size > capacity:
            assignments[family["id"]] = {
                "status": "דורש טיפול ידני",
                "bus": None,
                "pickup": None
            }
            continue

        own_bus = next(
            (b for b in buses if b["pickup"] == home),
            None
        )

        if own_bus and own_bus["remaining"] >= size:
            place_family(family, own_bus)
        else:
            waiting.append(family)

    # שלב שני: שימוש במקומות פנויים בשכונות אחרות
    still_waiting = []

    for family in waiting:
        size = len(family["members"])
        home = family["neighborhood"]

        candidates = [
            b for b in buses
            if b["remaining"] >= size
        ]

        if candidates:
            chosen = min(
                candidates,
                key=lambda b: (
                    DISTANCES[home][b["pickup"]],
                    b["remaining"] - size
                )
            )
            place_family(family, chosen)
        else:
            still_waiting.append(family)

    # שלב שלישי: הקצאת אוטובוסים נוספים מתוך הארבעה
    while still_waiting and len(buses) < 4:
        overflow = {
            n: sum(
                len(f["members"])
                for f in still_waiting
                if f["neighborhood"] == n
            )
            for n in NEIGHBORHOODS
        }

        pickup = max(overflow, key=overflow.get)
        new_bus = add_bus(pickup)

        for family in still_waiting[:]:
            if (
                family["neighborhood"] == pickup
                and len(family["members"]) <= new_bus["remaining"]
            ):
                place_family(family, new_bus)
                still_waiting.remove(family)

    # משפחות שלא נמצא להן מקום
    for family in still_waiting:
        assignments[family["id"]] = {
            "status": "ממתין לשיבוץ",
            "bus": None,
            "pickup": None
        }

    return buses, assignments








capacity = st.sidebar.number_input(
    "מקומות בכל אוטובוס",
    min_value=1,
    value=BUS_CAPACITY
)

buses, assignments = assign_buses(families, capacity)

total_people = sum(len(f["members"]) for f in families)
transport_people = sum(
    len(f["members"]) for f in families if f["transport"]
)
all_members = [
    member
    for family in families
    for member in family["members"]
]

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 סיכום",
    "👨‍👩‍👧‍👦 משפחות",
    "🚌 אוטובוסים",
    "📩 הכנה למיילים",
])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("משפחות", len(families))
    c2.metric("משתתפים", total_people)
    c3.metric("זקוקים להסעה", transport_people)
    c4.metric("אוטובוסים", len(buses))

    neighborhood_counts = pd.Series(
        [f["neighborhood"] for f in families]
    ).value_counts().reindex(
        NEIGHBORHOODS, fill_value=0
    )

    st.subheader("הרשמות לפי שכונה")
    st.bar_chart(neighborhood_counts)

    meal_counts = pd.Series(
        [m["meal"] for m in all_members]
    ).value_counts()

    st.subheader("סוגי ארוחות")
    st.bar_chart(meal_counts)

    allergies = [
        m["allergy"] for m in all_members
        if m["allergy"] and m["allergy"] != "אין"
    ]

    st.subheader("אלרגיות שדווחו")
    if allergies:
        st.dataframe(
            pd.Series(allergies).value_counts(),
            use_container_width=True
        )
    else:
        st.info("לא נמצאו פירוטי אלרגיות בשדות שנקראו; יש לבדוק גם את התשובות המקוריות")

with tab2:
    st.subheader("כרטיסי משפחות")

    for family in families:
        issues = validate_family(family)
        assignment = assignments.get(family["id"])

        with st.expander(
            f'משפחה {family["id"]} — {family["contact"]}'
        ):
            st.write("איש קשר:", family["contact"])
            st.write("אימייל:", family["email"])
            st.write("שכונה:", family["neighborhood"])
            st.write("משתתפים:", len(family["members"]))
            st.write("אופן הגעה:", family["transport_answer"])

            if issues:
                st.error(" | ".join(issues))
            else:
                st.success("ההרשמה עברה בדיקות תקינות")

            st.dataframe(
                pd.DataFrame(family["members"]),
                use_container_width=True
            )

            if assignment:
                st.write("אוטובוס:", assignment["bus"])
                st.write("נקודת איסוף:", assignment["pickup"])

            st.markdown("**תשובות מקוריות מהטופס**")
            st.json(family["original_answers"])

with tab3:
    st.subheader("שיבוץ אוטובוסים")

    for bus in buses:
        used = capacity - bus["remaining"]

        st.markdown(f'### 🚌 אוטובוס {bus["number"]}')
        st.write("נקודת איסוף:", bus["pickup"])
        st.progress(used / capacity)
        st.write(f"{used}/{capacity} מקומות תפוסים")
        st.write("משפחות:", ", ".join(bus["families"]))

    st.caption(
        "השיבוץ הוא הצעה אוטומטית ודורש אישור מארגן."
    )

with tab4:
    st.subheader("הכנת נתונים לשלב שליחת המיילים")

    ready = []
    for family in families:
        issues = validate_family(family)
        assignment = assignments.get(family["id"])

        ready.append({
            "registration_id": family["id"],
            "contact": family["contact"],
            "email": family["email"],
            "members": family["members"],
            "original_answers": family["original_answers"],
            "bus": assignment["bus"] if assignment else None,
            "pickup": assignment["pickup"] if assignment else None,
            "validation_issues": issues,
            "approved": False,
        })

    st.warning(
        "זהו קובץ הכנה בלבד. "
        "אין לשלוח מיילים לפני בדיקה ואישור."
    )

    st.download_button(
        "📥 הורדת קובץ משפחות JSON",
        data=json.dumps(
            ready, ensure_ascii=False, indent=2
        ),
        file_name="families_ready.json",
        mime="application/json"
    )
