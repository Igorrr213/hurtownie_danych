import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import get_zakupy, dodaj_zakup, pojemnosc_dysku_gb
from forecast import prognozuj
import datetime

st.set_page_config(layout="wide")
st.title("📦 Optymalizacja zakupów dysków")

# Dodawanie nowego zamówienia
st.sidebar.header("📝 Dodaj nowe zamówienie")
with st.sidebar.form("nowe_zamowienie"):
    produkt = st.selectbox("Produkt", ["Dysk 256 GB", "Dysk 512 GB", "Dysk 1 TB"])
    ilosc = st.number_input("Ilość sztuk", min_value=1, step=1)
    cena = st.number_input("Cena za sztukę (PLN)", min_value=1.0, step=1.0)
    data_zamowienia = st.date_input("Data zamówienia", value=datetime.date.today())
    submitted = st.form_submit_button("Zapisz zamówienie")

    if submitted:
        dodaj_zakup(produkt, int(ilosc), float(cena), data_zamowienia)
        st.success("✅ Zamówienie dodane. Prognoza została zaktualizowana.")

# Pobranie danych
df = get_zakupy()

if df.empty:
    st.warning("Brak danych zakupowych.")
else:
    # Przeliczenie danych
    df["pojemnosc_gb"] = df["produkt"].apply(pojemnosc_dysku_gb)
    df = df[df["pojemnosc_gb"].notnull()]
    df["dane_gb"] = df["pojemnosc_gb"] * df["ilosc"]
    df["dane_tb"] = df["dane_gb"] / 1024

    przestrzen = df.groupby("data_zamowienia").agg({"dane_tb": "sum"}).reset_index()
    forecast_space = prognozuj(przestrzen.rename(columns={"dane_tb": "ilosc"}))

    # Wykres przestrzeni
    st.subheader("💾 Wykorzystanie przestrzeni dyskowej (TB)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=przestrzen["data_zamowienia"], y=przestrzen["dane_tb"], name="Zużycie", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=forecast_space["ds"], y=forecast_space["yhat"], name="Prognoza", line=dict(dash='dot')))
    st.plotly_chart(fig, use_container_width=True)

    zapotrzebowanie = int(forecast_space["yhat"].iloc[-1] * 1024)  # z TB na GB
    st.info(f"📊 Przewidywane zapotrzebowanie przestrzeni: **{zapotrzebowanie} GB**")

    # Prognoza cen dla każdego dysku
    produkty = df["produkt"].unique()
    ceny_prognoza = {}
    for produkt in produkty:
        df_cena = df[df["produkt"] == produkt][["data_zamowienia", "cena"]]
        if len(df_cena) > 4:
            forecast_cena = prognozuj(df_cena.rename(columns={"cena": "ilosc"}))
            ceny_prognoza[produkt] = forecast_cena["yhat"].iloc[-1]
        else:
            ceny_prognoza[produkt] = df_cena["cena"].mean()

    # Lista opcji zakupowych
    opcje = []
    for p in produkty:
        size = pojemnosc_dysku_gb(p)
        if size is None or size == 0:
            continue
        cena = ceny_prognoza[p]
        cena_na_gb = cena / size
        opcje.append({
            "produkt": p,
            "cena": round(cena, 2),
            "pojemnosc": size,
            "cena_na_gb": cena_na_gb
        })

    opcje.sort(key=lambda x: x["cena_na_gb"])

    st.subheader("📦 Rekomendacja zakupowa")
    pozostało = zapotrzebowanie
    zakupy = []

    for o in opcje:
        if o["pojemnosc"] == 0:
            continue
        ile = pozostało // o["pojemnosc"]
        if ile > 0:
            zakupy.append({
                "produkt": o["produkt"],
                "ilosc": int(ile),
                "koszt": round(o["cena"] * ile, 2)
            })
            pozostało -= ile * o["pojemnosc"]
        if pozostało <= 0:
            break

    if pozostało > 0 and opcje:
        najlepszy = opcje[0]
        zakupy.append({
            "produkt": najlepszy["produkt"],
            "ilosc": 1,
            "koszt": round(najlepszy["cena"], 2)
        })

    df_zakup = pd.DataFrame(zakupy)
    if not df_zakup.empty:
        df_zakup["łączna_pojemność"] = df_zakup["ilosc"] * df_zakup["produkt"].apply(pojemnosc_dysku_gb)
        st.dataframe(df_zakup)
        st.success(f"💡 Rekomendowany zakup pokrywa {df_zakup['łączna_pojemność'].sum()} GB za {df_zakup['koszt'].sum():.2f} zł")
    else:
        st.info("🔍 Brak wystarczających danych do rekomendacji.")
