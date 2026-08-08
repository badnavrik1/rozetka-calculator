# -*- coding: utf-8 -*-
"""
Rozetka Pricing Calculator
Калькулятор розрахунку оптимальної ціни продажу для маркетплейсу Rozetka
з урахуванням прогресивної шкали комісій, еквайрингу, накладеного платежу,
курсу валют та аналізу конкурентів.

Запуск:
    pip install streamlit pandas
    streamlit run app.py
"""

import streamlit as st
import pandas as pd

# ============================================================
# КОНФІГУРАЦІЯ СТОРІНКИ
# ============================================================
st.set_page_config(
    page_title="Rozetka Калькулятор ціни",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# БАЗА ДАНИХ КОМІСІЙ ROZETKA (ОРІЄНТОВНА, РЕДАГОВАНА)
# ------------------------------------------------------------
# УВАГА: офіційні тарифи Rozetka не публікуються у відкритому
# доступі й видаються індивідуально менеджером маркетплейсу
# після реєстрації продавця (залежать від категорії та ціни).
# Наведені нижче значення — типовий приклад прогресивної шкали
# (нижча ціна -> вищий %, вища ціна -> нижчий %).
# Обов'язково скоригуйте діапазони й відсотки під ваш кабінет
# продавця у вкладці "⚙️ Налаштування комісій" -- зміни
# зберігаються протягом сесії і одразу впливають на розрахунок.
# ============================================================

DEFAULT_COMMISSIONS = {
    "Кава": [
        (0, 300, 15.0),
        (300, 700, 12.0),
        (700, 1500, 9.0),
        (1500, 10_000_000, 7.0),
    ],
    "Харчові продукти": [
        (0, 200, 14.0),
        (200, 500, 11.0),
        (500, 1200, 8.0),
        (1200, 10_000_000, 6.0),
    ],
    "Краса та здоров'я": [
        (0, 300, 20.0),
        (300, 800, 17.0),
        (800, 2000, 14.0),
        (2000, 10_000_000, 11.0),
    ],
    "Косметика та парфумерія": [
        (0, 300, 22.0),
        (300, 900, 18.0),
        (900, 2500, 15.0),
        (2500, 10_000_000, 12.0),
    ],
    "Парфумерія": [
        (0, 500, 20.0),
        (500, 1500, 16.0),
        (1500, 4000, 13.0),
        (4000, 10_000_000, 10.0),
    ],
    "БАДи": [
        (0, 300, 19.0),
        (300, 800, 16.0),
        (800, 2000, 13.0),
        (2000, 10_000_000, 10.0),
    ],
    "Побутова хімія": [
        (0, 200, 13.0),
        (200, 500, 10.0),
        (500, 1200, 8.0),
        (1200, 10_000_000, 6.0),
    ],
}

CURRENCIES = ["UAH", "USD", "EUR"]

# ============================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# ============================================================

def commissions_to_df(tiers):
    return pd.DataFrame(tiers, columns=["Від (грн)", "До (грн)", "Комісія (%)"])


def df_to_commissions(df):
    tiers = []
    for _, row in df.iterrows():
        try:
            lo = float(row["Від (грн)"])
            hi = float(row["До (грн)"])
            pct = float(row["Комісія (%)"])
        except (ValueError, TypeError):
            continue
        if hi > lo:
            tiers.append((lo, hi, pct))
    tiers.sort(key=lambda t: t[0])
    return tiers


def get_commission_pct(price, tiers):
    """Знаходить % комісії Rozetka для заданої ціни продажу за шкалою діапазонів."""
    if not tiers:
        return 0.0
    for lo, hi, pct in tiers:
        if lo <= price < hi:
            return pct
    # якщо ціна вища за останній діапазон - беремо ставку останнього діапазону
    return tiers[-1][2]


def solve_price(base_cost_target, tiers, acquiring_pct, cod_pct, max_iter=200, tol=0.001):
    """
    Стабільний ітеративний підбір фінальної ціни продажу методом нерухомої
    точки (fixed-point iteration). Це виключає циклічні помилки Excel,
    оскільки цикл детермінований, обмежений max_iter та завжди завершується.

    base_cost_target -- сума, яку продавець повинен отримати "на руки"
                         після вирахування комісії Rozetka, еквайрингу
                         та накладеного платежу (собівартість + фікс.
                         витрати + бажаний прибуток).
    """
    price = base_cost_target  # початкове наближення
    for _ in range(max_iter):
        commission_pct = get_commission_pct(price, tiers)
        total_deduction_pct = commission_pct + acquiring_pct + cod_pct
        # захист від некоректних даних (сума комісій >= 100%)
        if total_deduction_pct >= 99.9:
            total_deduction_pct = 99.9
        new_price = base_cost_target / (1 - total_deduction_pct / 100)
        if abs(new_price - price) < tol:
            price = new_price
            break
        price = new_price
    commission_pct_final = get_commission_pct(price, tiers)
    return price, commission_pct_final


def full_calculation(cost_uah, fixed_costs, markup_pct, tiers, acquiring_pct, cod_pct):
    total_cost = cost_uah + fixed_costs
    target_take_home = total_cost * (1 + markup_pct / 100)  # собівартість + фікс.витрати + бажаний прибуток

    price, commission_pct = solve_price(target_take_home, tiers, acquiring_pct, cod_pct)

    commission_uah = price * commission_pct / 100
    acquiring_uah = price * acquiring_pct / 100
    cod_uah = price * cod_pct / 100
    total_fees = commission_uah + acquiring_uah + cod_uah

    net_profit = price - total_cost - total_fees
    profitability_on_cost = (net_profit / total_cost * 100) if total_cost > 0 else 0
    margin_on_price = (net_profit / price * 100) if price > 0 else 0

    return {
        "total_cost": total_cost,
        "price": price,
        "commission_pct": commission_pct,
        "commission_uah": commission_uah,
        "acquiring_uah": acquiring_uah,
        "cod_uah": cod_uah,
        "total_fees": total_fees,
        "net_profit": net_profit,
        "profitability_on_cost": profitability_on_cost,
        "margin_on_price": margin_on_price,
    }


def profit_at_price(fixed_price, total_cost, tiers, acquiring_pct, cod_pct):
    """Розраховує прибуток, якщо ціна продажу задана вручну (напр. ціна конкурента)."""
    commission_pct = get_commission_pct(fixed_price, tiers)
    commission_uah = fixed_price * commission_pct / 100
    acquiring_uah = fixed_price * acquiring_pct / 100
    cod_uah = fixed_price * cod_pct / 100
    total_fees = commission_uah + acquiring_uah + cod_uah
    net_profit = fixed_price - total_cost - total_fees
    profitability_on_cost = (net_profit / total_cost * 100) if total_cost > 0 else 0
    margin_on_price = (net_profit / fixed_price * 100) if fixed_price > 0 else 0
    return {
        "price": fixed_price,
        "commission_pct": commission_pct,
        "commission_uah": commission_uah,
        "acquiring_uah": acquiring_uah,
        "cod_uah": cod_uah,
        "total_fees": total_fees,
        "net_profit": net_profit,
        "profitability_on_cost": profitability_on_cost,
        "margin_on_price": margin_on_price,
    }


def fmt(v):
    return f"{v:,.2f}".replace(",", " ")


# ============================================================
# STATE INIT
# ============================================================
if "commissions" not in st.session_state:
    st.session_state.commissions = {
        cat: list(tiers) for cat, tiers in DEFAULT_COMMISSIONS.items()
    }

# ============================================================
# SIDEBAR — ВХІДНІ ПАРАМЕТРИ
# ============================================================
st.sidebar.title("🧮 Параметри розрахунку")

st.sidebar.subheader("1. Собівартість товару")
currency = st.sidebar.selectbox("Валюта собівартості", CURRENCIES, index=0)

exchange_rate = 1.0
if currency != "UAH":
    exchange_rate = st.sidebar.number_input(
        f"Курс {currency} → UAH",
        min_value=0.01,
        value=41.5 if currency == "USD" else 45.0,
        step=0.01,
        format="%.2f",
    )

cost_value = st.sidebar.number_input(
    f"Собівартість товару, {currency}",
    min_value=0.0,
    value=10.0 if currency != "UAH" else 400.0,
    step=1.0,
)

cost_uah = cost_value * exchange_rate

st.sidebar.subheader("2. Категорія та націнка")
category = st.sidebar.selectbox("Категорія товару", list(st.session_state.commissions.keys()))
markup_pct = st.sidebar.number_input("Бажана націнка, %", min_value=0.0, value=15.0, step=1.0)

st.sidebar.subheader("3. Інші витрати та комісії")
fixed_costs = st.sidebar.number_input(
    "Фіксовані витрати на одиницю, грн (доставка, упаковка тощо)",
    min_value=0.0, value=30.0, step=1.0,
)
acquiring_pct = st.sidebar.number_input("Еквайринг, %", min_value=0.0, value=1.5, step=0.1)
cod_pct = st.sidebar.number_input("Комісія за накладений платіж, %", min_value=0.0, value=2.0, step=0.1)

# ============================================================
# ОСНОВНИЙ РОЗРАХУНОК
# ============================================================
tiers = st.session_state.commissions[category]
result = full_calculation(cost_uah, fixed_costs, markup_pct, tiers, acquiring_pct, cod_pct)
price_in_source_currency = result["price"] / exchange_rate if exchange_rate else result["price"]

# ============================================================
# ГОЛОВНИЙ ЕКРАН
# ============================================================
st.title("🧮 Rozetka — Калькулятор ціни продажу")
st.caption(
    "Швидкий та стабільний розрахунок оптимальної ціни продажу з урахуванням "
    "прогресивної шкали комісій Rozetka, еквайрингу та накладеного платежу. "
    "Без циклічних помилок Excel — розрахунок виконується детермінованим "
    "ітеративним методом нерухомої точки."
)

tab_calc, tab_competitors, tab_commissions = st.tabs(
    ["📊 Розрахунок ціни", "🏁 Аналіз конкурентів", "⚙️ Налаштування комісій"]
)

# ------------------------------------------------------------
# TAB 1: РОЗРАХУНОК ЦІНИ
# ------------------------------------------------------------
with tab_calc:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Оптимальна ціна продажу", f"{fmt(result['price'])} грн")
    col2.metric(
        f"Ціна у валюті ({currency})",
        f"{fmt(price_in_source_currency)} {currency}" if currency != "UAH" else "—",
    )
    col3.metric("Чистий прибуток", f"{fmt(result['net_profit'])} грн")
    col4.metric("Рентабельність (від собівартості)", f"{result['profitability_on_cost']:.1f}%")

    st.divider()

    st.subheader("Детальний звіт")
    report_df = pd.DataFrame(
        {
            "Показник": [
                "Собівартість (грн)",
                "Фіксовані витрати (грн)",
                "Разом витрат без комісій (грн)",
                "Категорія",
                "Знайдений % комісії Rozetka (за шкалою)",
                "Сума комісії Rozetka (грн)",
                "Еквайринг (грн)",
                "Накладений платіж, комісія (грн)",
                "Загальна сума комісій/зборів (грн)",
                "Оптимальна ціна продажу (грн)",
                f"Оптимальна ціна продажу ({currency})" if currency != "UAH" else "Оптимальна ціна продажу (UAH)",
                "Чистий прибуток (грн)",
                "Рентабельність від собівартості (%)",
                "Маржа від ціни продажу (%)",
            ],
            "Значення": [
                fmt(cost_uah),
                fmt(fixed_costs),
                fmt(result["total_cost"]),
                category,
                f"{result['commission_pct']:.2f}%",
                fmt(result["commission_uah"]),
                fmt(result["acquiring_uah"]),
                fmt(result["cod_uah"]),
                fmt(result["total_fees"]),
                fmt(result["price"]),
                fmt(price_in_source_currency) if currency != "UAH" else fmt(result["price"]),
                fmt(result["net_profit"]),
                f"{result['profitability_on_cost']:.2f}%",
                f"{result['margin_on_price']:.2f}%",
            ],
        }
    )
    st.dataframe(report_df, use_container_width=True, hide_index=True)

    with st.expander("ℹ️ Як саме рахує калькулятор (логіка без циклічних помилок)"):
        st.markdown(
            """
            1. Обчислюється базова сума, яку продавець хоче отримати «на руки»:
               `(Собівартість + Фіксовані витрати) × (1 + Націнка / 100)`
            2. Оскільки % комісії Rozetka залежить від фінальної ціни продажу
               (а фінальна ціна залежить від %), калькулятор використовує
               **ітераційний метод нерухомої точки**: бере наближену ціну,
               знаходить для неї % комісії за шкалою діапазонів, перераховує
               ціну заново — і так до моменту, коли ціна перестає змінюватися
               (з точністю до 0.001 грн, максимум 200 ітерацій).
               Це гарантує коректний результат без «зависань» чи посилань по колу,
               характерних для Excel.
            3. Фінальна ціна продажу — це та ціна, при якій після вирахування
               комісії Rozetka (за правильним діапазоном), еквайрингу та
               накладеного платежу продавцю залишається саме бажана сума
               (собівартість + фіксовані витрати + прибуток).
            """
        )

# ------------------------------------------------------------
# TAB 2: АНАЛІЗ КОНКУРЕНТІВ
# ------------------------------------------------------------
with tab_competitors:
    st.subheader("Порівняння з цінами конкурентів")
    st.caption(
        "Введіть ціни конкурентів на аналогічний товар, щоб побачити свою позицію "
        "та розрахувати прибуток, якщо ви встановите ціну на рівні або нижче конкурента."
    )

    n_competitors = st.number_input("Кількість конкурентів", min_value=1, max_value=10, value=3, step=1)

    comp_prices = []
    cols = st.columns(min(n_competitors, 5))
    for i in range(n_competitors):
        col = cols[i % len(cols)]
        with col:
            val = st.number_input(f"Конкурент {i + 1}, грн", min_value=0.0, value=0.0, step=1.0, key=f"comp_{i}")
            comp_prices.append(val)

    comp_prices = [p for p in comp_prices if p > 0]

    if comp_prices:
        st.divider()
        min_comp = min(comp_prices)
        avg_comp = sum(comp_prices) / len(comp_prices)
        max_comp = max(comp_prices)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ваша ціна", f"{fmt(result['price'])} грн")
        c2.metric("Мін. у конкурентів", f"{fmt(min_comp)} грн")
        c3.metric("Середня у конкурентів", f"{fmt(avg_comp)} грн")
        c4.metric("Макс. у конкурентів", f"{fmt(max_comp)} грн")

        if result["price"] > min_comp:
            st.warning(
                f"Ваша розрахована ціна вища за найдешевшого конкурента на "
                f"{fmt(result['price'] - min_comp)} грн."
            )
        else:
            st.success("Ваша розрахована ціна вже нижча або дорівнює мінімальній ціні конкурентів.")

        st.subheader("Прибуток за сценаріями ціноутворення")
        scenarios = {
            "Ваша оптимальна ціна": result["price"],
            "На рівні мінімального конкурента": min_comp,
            "На рівні середньої ціни конкурентів": avg_comp,
            "На рівні максимального конкурента": max_comp,
            "На 5% нижче мінімального конкурента": min_comp * 0.95,
        }

        rows = []
        for label, p in scenarios.items():
            r = profit_at_price(p, result["total_cost"], tiers, acquiring_pct, cod_pct)
            rows.append(
                {
                    "Сценарій": label,
                    "Ціна, грн": fmt(r["price"]),
                    "% комісії Rozetka": f"{r['commission_pct']:.2f}%",
                    "Комісія, грн": fmt(r["commission_uah"]),
                    "Всі збори, грн": fmt(r["total_fees"]),
                    "Чистий прибуток, грн": fmt(r["net_profit"]),
                    "Рентабельність, %": f"{r['profitability_on_cost']:.2f}%",
                }
            )
        scen_df = pd.DataFrame(rows)
        st.dataframe(scen_df, use_container_width=True, hide_index=True)
    else:
        st.info("Введіть хоча б одну ціну конкурента вище, щоб побачити порівняння.")

# ------------------------------------------------------------
# TAB 3: НАЛАШТУВАННЯ КОМІСІЙ
# ------------------------------------------------------------
with tab_commissions:
    st.subheader("Редагування шкали комісій Rozetka за категоріями")
    st.warning(
        "Офіційні тарифи Rozetka індивідуальні та надаються менеджером маркетплейсу "
        "після реєстрації продавця — вони не публікуються у фіксованому вигляді у "
        "відкритому доступі. Значення нижче є **орієнтовним прикладом** прогресивної "
        "шкали. Обов'язково внесіть свої реальні ставки з особистого кабінету продавця "
        "(«Мій баланс» → «Комісія по товарам») — зміни застосуються миттєво до розрахунку."
    )

    edit_category = st.selectbox(
        "Оберіть категорію для редагування", list(st.session_state.commissions.keys()), key="edit_cat"
    )

    df = commissions_to_df(st.session_state.commissions[edit_category])
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{edit_category}",
        column_config={
            "Від (грн)": st.column_config.NumberColumn(min_value=0.0, step=10.0),
            "До (грн)": st.column_config.NumberColumn(min_value=0.0, step=10.0),
            "Комісія (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5),
        },
    )

    colA, colB = st.columns(2)
    if colA.button("💾 Зберегти зміни для категорії", type="primary"):
        new_tiers = df_to_commissions(edited_df)
        if new_tiers:
            st.session_state.commissions[edit_category] = new_tiers
            st.success(f"Шкалу комісій для категорії «{edit_category}» оновлено.")
        else:
            st.error("Не вдалося зберегти: перевірте, що діапазони коректні (До > Від).")

    if colB.button("↩️ Скинути до орієнтовних значень за замовчуванням"):
        st.session_state.commissions[edit_category] = list(DEFAULT_COMMISSIONS[edit_category])
        st.success(f"Шкалу комісій для категорії «{edit_category}» скинуто.")

    st.divider()
    st.subheader("Поточна шкала (перевірка)")
    st.dataframe(
        commissions_to_df(st.session_state.commissions[edit_category]),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    "© Rozetka Pricing Calculator · Розрахунки є орієнтовними. "
    "Перевіряйте актуальні тарифи Rozetka у своєму кабінеті продавця."
)
