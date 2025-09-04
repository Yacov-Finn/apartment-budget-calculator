# -*- coding: utf-8 -*-
# streamlit_budget_calculator_app.py
# מחולל תקציב לרכישת דירה מקבלן – לפי המפרט שהועבר
# הפעלה:  streamlit run streamlit_budget_calculator_app.py

import streamlit as st
from dataclasses import dataclass
from typing import List, Tuple, Dict
import math

st.set_page_config(page_title="מחשבון תקציב רכישת דירה", page_icon="🏠", layout="wide")

# ==== RTL styling ====
st.markdown(
    """
    <style>
    html, body, [class*="css"]  { direction: rtl; text-align: right; }
    .big-number { font-size: 1.4rem; font-weight: 700; }
    .muted { color: #666; }
    .ok { color: #0a8; }
    .warn { color: #c76f00; }
    .bad { color: #c00; }
    .card { padding: 1rem; border: 1px solid #eee; border-radius: 12px; background: #fff; }
    .small { font-size: 0.9rem; }
    .pill { display:inline-block; padding: .2rem .6rem; border-radius:999px; border:1px solid #ddd; margin-left:.4rem; }
    </style>
    """,
    unsafe_allow_html=True
)

# ==== Constants & Helpers ====

VAT_DEFAULT = 0.18  # 18% מע״מ בישראל נכון ל-2025
CONSULTANT_MIN = 7_500  # מינימום יועץ משכנתאות
CONTRACTOR_LAWYER_FLAT = 5_500  # שכ״ט עו״ד קבלן

# מדרגות מס רכישה – דירה יחידה (מקפיאים עד 15.01.2028 לפי פרסומים עדכניים)
# מקור (לרפרנס ידני): קול-זכות ונבו/רשות המסים
SINGLE_HOME_BRACKETS = [
    (0, 1_978_745, 0.00),
    (1_978_745, 2_347_040, 0.035),
    (2_347_040, 6_055_070, 0.05),
    (6_055_070, 20_183_565, 0.08),
    (20_183_565, float("inf"), 0.10),
]

# מדרגות מס רכישה – דירה נוספת / לא תושב
INVESTOR_BRACKETS = [
    (0, 6_055_070, 0.08),
    (6_055_070, float("inf"), 0.10),
]

# מדרגות מס רכישה – לעולה חדש (מעודכן מאוג׳ 2024)
# (דירה יחידה בלבד, לפי העדכונים. יש לעדכן מול רו״ח/עו״ד בכל שימוש אמיתי)
OLIM_BRACKETS = [
    (0, 1_978_745, 0.00),
    (1_978_745, 6_055_070, 0.005),
    (6_055_070, 20_183_565, 0.08),
    (20_183_565, float("inf"), 0.10),
]

@dataclass
class BuyerProfile:
    is_israeli: bool
    is_single_home: bool
    is_oleh: bool


def calc_progressive_tax(amount: float, brackets: List[Tuple[float, float, float]]) -> float:
    """חשב מס פרוגרסיבי לפי מדרגות (from, to, rate)."""
    tax = 0.0
    for lower, upper, rate in brackets:
        if amount <= lower:
            break
        taxable = min(amount, upper) - lower
        if taxable > 0:
            tax += taxable * rate
    return max(0.0, tax)


def calc_purchase_tax(price: float, profile: BuyerProfile) -> Tuple[float, str]:
    """
    מס רכישה לפי סוג רוכש:
    - דירה יחידה לתושב ישראלי → מדרגות SINGLE_HOME_BRACKETS
    - עולה חדש (דירה יחידה) → OLIM_BRACKETS
    - כל השאר (משקיע / לא תושב / לא דירה יחידה) → INVESTOR_BRACKETS
    """
    if profile.is_oleh and profile.is_single_home:
        brackets = OLIM_BRACKETS
        kind = "עולה חדש – דירה יחידה"
    elif profile.is_israeli and profile.is_single_home:
        brackets = SINGLE_HOME_BRACKETS
        kind = "תושב ישראל – דירה יחידה"
    else:
        brackets = INVESTOR_BRACKETS
        kind = "דירה נוספת / לא תושב"

    tax = calc_progressive_tax(price, brackets)
    return tax, kind


def rule_of_thumb_monthly(mortgage_amount: float, years: int) -> float:
    """
    אומדנים לכל מיליון ש״ח:
    - 30 שנה ≈ 5,550 ש״ח למיליון
    - 20 שנה ≈ 6,700 ש״ח למיליון
    """
    per_million = 5550 if years == 30 else 6700
    return (mortgage_amount / 1_000_000) * per_million


def format_ils(x: float) -> str:
    return f"₪{x:,.0f}".replace(",", ",")


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


# ==== Sidebar – קלטים כלליים ====

with st.sidebar:
    st.header("הגדרות כלליות")
    vat = st.number_input("מע״מ באחוזים", min_value=0.0, max_value=0.5, value=VAT_DEFAULT, step=0.01, format="%.2f")
    st.caption("מע״מ ברירת מחדל 18% (נכון ל-2025). ניתן לשנות לפי הצורך.")

    st.markdown("---")
    st.subheader("פרטי רוכש")
    is_israeli = st.checkbox("אני אזרח/ת ישראל", value=True)
    is_single_home = st.checkbox("זו דירתי היחידה (או אמכור דירה קיימת במועד החוקי)", value=True)
    is_oleh = st.checkbox("אני עולה/עולה חדש/ה", value=False)
    profile = BuyerProfile(is_israeli=is_israeli, is_single_home=is_single_home, is_oleh=is_oleh)

    st.markdown("---")
    st.subheader("רכיב שדרוגים (ניתן לשינוי)")
    default_upgrades: Dict[str, Dict[str, float]] = {
        "מזגנים (לפי חדרים)": {"qty": 0.0, "unit_cost": 6_000.0},
        "רשתות לחלונות (יח׳)": {"qty": 0.0, "unit_cost": 300.0},
        "מקלחונים (יח׳)": {"qty": 0.0, "unit_cost": 1_800.0},
        "שדרוג מטבח": {"qty": 1.0, "unit_cost": 50_000.0},
        "גופי תאורה": {"qty": 1.0, "unit_cost": 5_000.0},
        "הוספת שקעים (יח׳)": {"qty": 0.0, "unit_cost": 500.0},
        "שדרוג ריצוף": {"qty": 1.0, "unit_cost": 12_000.0},
        "הזזת קירות/שינויים": {"qty": 1.0, "unit_cost": 8_000.0},
    }
    # עריכה דינמית:
    st.caption("הערכות סדר גודל – שנו כמו שתרצו. המחירים אינם מחייבים.")
    for k in list(default_upgrades.keys()):
        cols = st.columns([2,1,1])
        with cols[0]:
            st.write(k)
        with cols[1]:
            default_upgrades[k]["qty"] = st.number_input(f"כמות – {k}", min_value=0.0, value=float(default_upgrades[k]["qty"]), step=1.0, key=f"qty_{k}")
        with cols[2]:
            default_upgrades[k]["unit_cost"] = st.number_input(f"עלו׳ יחידה – {k}", min_value=0.0, value=float(default_upgrades[k]["unit_cost"]), step=500.0, key=f"cost_{k}")

# ==== Main – תהליך רב שלבי ====

st.title("🏠 מחשבון תקציב לרכישת דירה מקבלן")
st.caption("תוצאה מיידית לכל שאלה ובסוף סיכום מלא של הון עצמי, מס רכישה, משכנתא והחזר חודשי (20/30 שנה).")

tab1, tab2, tab3, tab4 = st.tabs(["פרטי העסקה", "עמלות ועלויות נוספות", "משכנתא", "סיכום"])

with tab1:
    st.subheader("פרטי העסקה")
    price = st.number_input("מחיר דירה (₪)", min_value=0.0, step=50_000.0, value=2_400_000.0)

    colA, colB = st.columns(2)
    with colA:
        rooms = st.number_input("מספר חדרים", min_value=1, step=1, value=4)
        has_ac = st.checkbox("הדירה מגיעה עם מזגנים", value=False)
        has_screens = st.checkbox("הדירה מגיעה עם רשתות", value=False)
        has_showers = st.checkbox("יש מקלחונים", value=False)

    # הערכת שדרוגים אוטומטית לפי ברירות מחדל
    upgrades_breakdown = {}
    if not has_ac:
        upgrades_breakdown["מזגנים (לפי חדרים)"] = rooms * default_upgrades["מזגנים (לפי חדרים)"]["unit_cost"]
    if not has_screens:
        # הערכת יחידות: חלון לכל חדר + סלון
        est_units = rooms + 1
        upgrades_breakdown["רשתות לחלונות (יח׳)"] = est_units * default_upgrades["רשתות לחלונות (יח׳)"]["unit_cost"]
    if not has_showers:
        # הערכה בסיסית: 2 מקלחונים
        upgrades_breakdown["מקלחונים (יח׳)"] = 2 * default_upgrades["מקלחונים (יח׳)"]["unit_cost"]

    # תוספת לפי רכיבי סל
    for name, cfg in default_upgrades.items():
        if name not in ["מזגנים (לפי חדרים)", "רשתות לחלונות (יח׳)", "מקלחונים (יח׳)"]:
            upgrades_breakdown[name] = cfg["qty"] * cfg["unit_cost"]

    upgrades_sum = sum(upgrades_breakdown.values())

    # מס רכישה
    purchase_tax, tax_kind = calc_purchase_tax(price, profile)

    # הצגה
    st.markdown("### עלויות לפי פרטים שהזנת")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="card"><div class="muted">מס רכישה</div><div class="big-number">{}</div><div class="small">{}</div></div>'.format(format_ils(purchase_tax), tax_kind), unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card"><div class="muted">שדרוגים מוערכים</div><div class="big-number">{}</div><div class="small">מבוסס על העדפותיך לעיל</div></div>'.format(format_ils(upgrades_sum)), unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="card"><div class="muted">מחיר דירה</div><div class="big-number">{}</div><div class="small">ללא עמלות/מסים</div></div>'.format(format_ils(price)), unsafe_allow_html=True)

with tab2:
    st.subheader("עמלות ועלויות נוספות")
    st.caption("טווחים מקובלים – שנה לפי המקרה.")

    col1, col2 = st.columns(2)
    with col1:
        has_broker = st.checkbox("יש דמי תיווך", value=True)
        broker_pct = st.slider("אחוז תיווך", min_value=0.0, max_value=0.03, step=0.005, value=0.02, format="%.3f")
        broker_fee = price * broker_pct if has_broker else 0.0

        has_lawyer = st.checkbox("שכ״ט עו״ד קונה (אחוז מהעסקה)", value=True)
        lawyer_pct = st.slider("אחוז שכ״ט עו״ד", min_value=0.0, max_value=0.02, step=0.0025, value=0.01, format="%.4f")
        lawyer_fee = price * lawyer_pct if has_lawyer else 0.0

        contractor_lawyer_fee = CONTRACTOR_LAWYER_FLAT

    with col2:
        has_consultant = st.checkbox("יועץ משכנתאות", value=True)
        consultant_pct = st.slider("אחוז יועץ (מהמשכנתא)", min_value=0.0, max_value=0.02, step=0.0025, value=0.005, format="%.4f")
        # סכום משכנתא יחושב בטאב משכנתא – כאן נחשב גס לפי LTV בהמשך, אבל נשמור את האחוז לערך הסופי.

    # מע״מ על עמלות רלוונטיות
    broker_vat = broker_fee * vat
    lawyer_vat = lawyer_fee * vat
    contractor_lawyer_vat = contractor_lawyer_fee * vat

    fees_so_far = broker_fee + broker_vat + lawyer_fee + lawyer_vat + contractor_lawyer_fee + contractor_lawyer_vat

    st.markdown("### סיכום עמלות ביניים (ללא יועץ)")
    st.write(f"- תיווך: {format_ils(broker_fee)} + מע״מ {format_ils(broker_vat)}")
    st.write(f"- שכ״ט עו״ד קונה: {format_ils(lawyer_fee)} + מע״מ {format_ils(lawyer_vat)}")
    st.write(f"- שכ״ט עו״ד קבלן (קבוע): {format_ils(contractor_lawyer_fee)} + מע״מ {format_ils(contractor_lawyer_vat)}")
    st.markdown(f"**סך עמלות ביניים:** {format_ils(fees_so_far)}")

with tab3:
    st.subheader("משכנתא")
    # קביעת LTV מותר
    if profile.is_israeli and profile.is_single_home:
        max_ltv = 0.75
    else:
        max_ltv = 0.50

    max_mortgage_allowed = price * max_ltv
    st.markdown(f"**מימון מקסימלי מותר (LTV):** {pct(max_ltv)} → {format_ils(max_mortgage_allowed)}")

    desired_mortgage = st.number_input("גובה משכנתא רצוי (₪)", min_value=0.0, max_value=price, value=float(max_mortgage_allowed), step=50_000.0)
    if desired_mortgage > max_mortgage_allowed:
        st.warning("הסכום שהזנת גבוה מהמותר לפי הכללים – עודכן אוטומטית לסכום המקסימלי.")
        desired_mortgage = max_mortgage_allowed

    # יועץ משכנתאות – חישוב לפי אחוז ומינימום
    if 'consultant_pct' not in st.session_state:
        st.session_state['consultant_pct'] = 0.005
    consultant_fee = 0.0
    if 'has_consultant' in locals():
        if has_consultant:
            consultant_fee = max(desired_mortgage * consultant_pct, CONSULTANT_MIN)
    else:
        # במידה והטאב הזה רץ קודם – ניקח ברירות מחדל
        consultant_fee = max(desired_mortgage * 0.005, CONSULTANT_MIN)

    consultant_vat = consultant_fee * vat

    # תוספים שהצטברו מטאב 2
    total_fees = fees_so_far + consultant_fee + consultant_vat

    st.markdown("### אומדן החזר חודשי לפי כללי אצבע")
    colX, colY = st.columns(2)
    with colX:
        monthly_30 = rule_of_thumb_monthly(desired_mortgage, 30)
        st.markdown(f"<div class='card'><div class='muted'>30 שנה</div><div class='big-number'>{format_ils(monthly_30)}/חודש</div><div class='small'>~5,550 למיל׳</div></div>", unsafe_allow_html=True)
    with colY:
        monthly_20 = rule_of_thumb_monthly(desired_mortgage, 20)
        st.markdown(f"<div class='card'><div class='muted'>20 שנה</div><div class='big-number'>{format_ils(monthly_20)}/חודש</div><div class='small'>~6,700 למיל׳</div></div>", unsafe_allow_html=True)

    st.markdown("### עלויות כוללות עד כה")
    st.write(f"- מס רכישה מוערך: **{format_ils(purchase_tax)}**")
    st.write(f"- שדרוגים: **{format_ils(upgrades_sum)}**")
    st.write(f"- עמלות (כולל מע״מ): **{format_ils(total_fees)}**")

with tab4:
    st.subheader("סיכום כולל והון עצמי נדרש")
    # סיכום כל העלויות
    total_cost = price + purchase_tax + upgrades_sum + total_fees
    equity_required = max(0.0, total_cost - desired_mortgage)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div class='card'><div class='muted'>עלות כוללת (משוערת)</div><div class='big-number'>{format_ils(total_cost)}</div><div class='small'>כולל מס, שדרוגים ועמלות</div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='card'><div class='muted'>גובה המשכנתא</div><div class='big-number'>{format_ils(desired_mortgage)}</div><div class='small'>מגבלת מימון: {pct(max_ltv)}</div></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='card'><div class='muted'>הון עצמי נדרש (משוער)</div><div class='big-number'>{format_ils(equity_required)}</div><div class='small'>עשוי להשתנות לפי תנאי העסקה בפועל</div></div>", unsafe_allow_html=True)

    st.markdown("#### הערות חשובות")
    st.write("- **מדד תשומות הבנייה**: בדירה מקבלן, עד ~40% מיתרת החוב עשוי להיות צמוד למדד בתקופת הבנייה – העלות אינה ניתנת לחיזוי מלא.")
    st.write("- **דירה חלופית**: יש מסלולים המאפשרים מס דירה יחידה אם תמכרו דירה קיימת בפרקי הזמן שבחוק. מומלץ להתייעץ עם איש מקצוע.")
    st.write("- **הכול הערכות** לצורך תכנון: מסים, עלויות ומחירים משתנים. יש לאמת מול רו\"ח/עו\"ד/יועץ לפני החלטה.")

    st.download_button(
        label="📥 הורדת תקציר (CSV)",
        data=(
            "פריט,סכום\n"
            f"מחיר דירה,{int(price)}\n"
            f"מס רכישה,{int(purchase_tax)}\n"
            f"שדרוגים,{int(upgrades_sum)}\n"
            f"עמלות (כולל מע״מ),{int(total_fees)}\n"
            f"גובה משכנתא,{int(desired_mortgage)}\n"
            f"הון עצמי נדרש,{int(equity_required)}\n"
        ).encode("utf-8"),
        file_name="סיכום_רכישת_דירה.csv",
        mime="text/csv"
    )

st.markdown("---")
st.caption("מחשבון הדגמה. אין לראות באמור ייעוץ או התחייבות. בדקו כל נתון מול המקורות הרשמיים והגורמים המקצועיים.")
