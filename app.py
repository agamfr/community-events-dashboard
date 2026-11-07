
import streamlit as st
import pandas as pd
import math

st.set_page_config(
    page_title="ניהול אירועים קהילתיים",
    page_icon="📊",
    layout="wide"
)

st.title("📊 דשבורד ניהול אירועים קהילתיים")
st.write("מערכת לחישוב משאבים ולניהול לוגיסטי")

st.info("הנתונים כרגע להדגמה בלבד")

# נתוני הרשמה לדוגמה
data = pd.DataFrame({
    "שכונה": ["א", "ב", "ג", "ד"],
    "משתתפים": [35, 28, 42, 15],
    "זקוקים להסעה": [30, 20, 35, 10]
})

# חישובים בפייתון
total_people = int(data["משתתפים"].sum())
total_transport = int(data["זקוקים להסעה"].sum())

bus_capacity = st.number_input(
    "כמה מקומות יש בכל אוטובוס?",
    min_value=1,
    value=50
)

buses_needed = math.ceil(total_transport / bus_capacity)

# הצגת מדדים
col1, col2, col3 = st.columns(3)

col1.metric("👥 סך משתתפים", total_people)
col2.metric("🚌 זקוקים להסעה", total_transport)
col3.metric("🚍 אוטובוסים נדרשים", buses_needed)

st.subheader("📍 חלוקת משתתפים לפי שכונה")
st.bar_chart(data.set_index("שכונה")["משתתפים"])

st.subheader("🚌 ביקוש להסעות לפי שכונה")
st.bar_chart(data.set_index("שכונה")["זקוקים להסעה"])

st.subheader("📋 טבלת נתונים")
st.dataframe(data, use_container_width=True)
