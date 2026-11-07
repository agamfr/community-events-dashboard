
import streamlit as st
import pandas as pd
import math
import json
import requests
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


# טעינת משפחות מ-Google Sheets
import requests
import streamlit as st

SHEETS_URL = st.secrets["SHEETS_URL"]
API_TOKEN = st.secrets["API_TOKEN"]


response = requests.post(
    SHEETS_URL,
    json={"token": API_TOKEN},
    timeout=30
)

response.raise_for_status()

sheet_data = response.json()

if not sheet_data.get("success"):
    st.error("לא הצלחנו לטעון את ההרשמות")
    st.stop()

registrations = sheet_data["registrations"]

if registrations:
    st.write("בדיקת שמות עמודות:")
    st.write(list(registrations[0].keys()))

    st.write("בדיקת מספר משתתפים:")
    for row in registrations:
        st.write([
            (key, str(value))
            for key, value in row.items()
            if "משתתפים" in key
        ])

def get_value(row, key, default=""):
    return row.get(key, default)

families = []


for index, row in enumerate(registrations, start=1):
   
    raw_count = next(
        (
            value
            for key, value in row.items()
            if "מספר המשתתפים הכולל" in key
            and str(value).strip()
        ),
        0
    )


    try:
        count = int(float(str(raw_count).strip()))
    except (ValueError, TypeError):
        count = 0

    neighborhood = str(get_value(row, "כתובת", "")).strip()

    transport_answer = str(get_value(
        row, "5. אופן הגעה לאירוע", ""
    )).strip()

    members = []

    for number in range(1, count + 1):
        members.append({
            "name": f"משתתף {number}",
            "meal": get_value(
                row, f"העדפת תזונה עיקרית [משתתף {number}]"
            ),
            "allergy": get_value(
                row, f"פירוט המגבלה או האלרגיה [משתתף {number}]",
                "אין"
            )
        })

    families.append({
        "id": str(index).zfill(3),
        "contact": get_value(
            row, "1. שם מלא איש הקשר המרכזי"
        ),
        "email": get_value(
            row, "3. כתובת דואר אלקטרוני"
        ),
        "neighborhood": neighborhood,
        "transport": transport_answer != "מגיעים עצמאית",
        "members": members,
        "original_answers": row
    })

st.success(f"נטענו {len(families)} משפחות מ-Google Sheets")

def validate_family(family):
    issues = []

    if not family.get("email") or "@" not in family["email"]:
        issues.append("כתובת אימייל חסרה או לא תקינה")

    members = family.get("members", [])
    expected = family.get("original_answers", {}).get(
        "מספר משתתפים"
    )

    if expected != len(members):
        issues.append("מספר המשתתפים אינו תואם לטופס")

    for index, member in enumerate(members, start=1):
        if not member.get("name"):
            issues.append(f"חסר שם למשתתף {index}")
        if not member.get("meal"):
            issues.append(f"חסרה בחירת ארוחה למשתתף {index}")
        if not member.get("allergy"):
            issues.append(f"חסר מידע אלרגיות למשתתף {index}")

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
        if m["allergy"] != "אין"
    ]

    st.subheader("אלרגיות שדווחו")
    if allergies:
        st.dataframe(
            pd.Series(allergies).value_counts(),
            use_container_width=True
        )
    else:
        st.success("לא דווחו אלרגיות")

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
