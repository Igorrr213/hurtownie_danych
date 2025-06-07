import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from db import get_zakupy, dodaj_zakup, pojemnosc_dysku_gb, wyczysc_baze
from forecast import prognozuj
import datetime

# ✅ Jednorazowy reset bazy na start sesji
if "inicjalizacja" not in st.session_state:
    wyczysc_baze()
    st.session_state["inicjalizacja"] = True

if "symulacja_data" not in st.session_state:
    st.session_state["symulacja_data"] = datetime.date.today()

if "historia_zuzycia" not in st.session_state:
    st.session_state["historia_zuzycia"] = pd.DataFrame(columns=["data", "zuzycie_tb"])

def losowa_cena_bazowa(produkt, data):
    base = {"Dysk 256 GB": 60, "Dysk 512 GB": 100, "Dysk 1 TB": 180}
    seed = int(data.strftime("%Y%m")) + sum(ord(c) for c in produkt)
    np.random.seed(seed)
    zmiennosc = np.random.normal(1.0, 0.1)
    return round(base.get(produkt, 100) * zmiennosc, 2)

def przesun_symulacje_o_miesiac():
    data = st.session_state["symulacja_data"]
    month = data.month + 1
    year = data.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    st.session_state["symulacja_data"] = datetime.date(year, month, 1)

st.set_page_config(layout="wide")
st.title("📦 Optymalizacja zakupów dysków")
st.markdown(f"📅 **Aktualna data symulacji:** `{st.session_state['symulacja_data']}`")

if st.button("⏭ Symuluj miesiąc bez zakupu"):
    przesun_symulacje_o_miesiac()
    st.rerun()

st.sidebar.header("📝 Dodaj nowe zamówienia")
produkty = st.sidebar.multiselect("Produkty", ["Dysk 256 GB", "Dysk 512 GB", "Dysk 1 TB"])

if produkty:
    with st.sidebar.form("form_zamowienia"):
        ilosci = {}
        for p in produkty:
            ilosci[p] = st.number_input(f"Ilość {p}", min_value=1, step=1, key=p)
            cena_sym = losowa_cena_bazowa(p, st.session_state["symulacja_data"])
            st.markdown(f"📦 {p} — cena symulowana: **{cena_sym:.2f} PLN**")
        if st.form_submit_button("Zapisz zamówienia"):
            for p in produkty:
                cena_sym = losowa_cena_bazowa(p, st.session_state["symulacja_data"])
                dodaj_zakup(p, int(ilosci[p]), cena_sym, st.session_state["symulacja_data"])
            st.success("✅ Zamówienia zostały dodane.")
            przesun_symulacje_o_miesiac()
            st.rerun()

df = get_zakupy()

if df.empty:
    st.warning("Brak danych zakupowych.")
else:
    df["data_zamowienia"] = pd.to_datetime(df["data_zamowienia"])
    df["pojemnosc_gb"] = df["produkt"].apply(pojemnosc_dysku_gb)
    df = df[df["pojemnosc_gb"].notnull()]
    df["dane_gb"] = df["pojemnosc_gb"] * df["ilosc"]
    df["dane_tb"] = df["dane_gb"] / 1024
    df["miesiac"] = df["data_zamowienia"].dt.to_period("M").dt.to_timestamp()

    calkowita_pojemnosc_tb = df["dane_tb"].sum()

    # 📊 Historia zużycia
    historia = st.session_state["historia_zuzycia"].copy()
    historia["miesiac"] = historia["data"].apply(lambda d: d.replace(day=1))
    zuzycie_miesiac = historia.groupby("miesiac")["zuzycie_tb"].sum().cumsum().reset_index()

    # 📊 Kumulowana pojemność — bazuje na historii zakupów
    pojemnosci = df.groupby("miesiac")["dane_tb"].sum().cumsum().reset_index()
    pojemnosci.columns = ["miesiac", "pojemnosc_tb"]

    pojemnosci["miesiac"] = pd.to_datetime(pojemnosci["miesiac"])
    zuzycie_miesiac["miesiac"] = pd.to_datetime(zuzycie_miesiac["miesiac"])

    # 📉 Oblicz zużycie na podstawie dostępności z poprzedniego miesiąca
    np.random.seed(int(st.session_state["symulacja_data"].strftime("%Y%m")))
    symulacja_dt = pd.to_datetime(st.session_state["symulacja_data"])
    poprzednie_miesiace = pojemnosci[pojemnosci["miesiac"] < symulacja_dt]

    if not zuzycie_miesiac.empty:
        zajete_tb = zuzycie_miesiac["zuzycie_tb"].iloc[-1]
    else:
        zajete_tb = 0

    if not poprzednie_miesiace.empty:
        dostepnosc_poprzednia = poprzednie_miesiace["pojemnosc_tb"].iloc[-1] - zajete_tb
    else:
        dostepnosc_poprzednia = calkowita_pojemnosc_tb

    procent_zuzycia = np.random.uniform(0.3, 0.8)
    zuzycie_tb = dostepnosc_poprzednia * procent_zuzycia

    nowy_wiersz = pd.DataFrame([{
        "data": st.session_state["symulacja_data"],
        "zuzycie_tb": zuzycie_tb
    }])
    st.session_state["historia_zuzycia"] = pd.concat([st.session_state["historia_zuzycia"], nowy_wiersz], ignore_index=True)

    # 📈 Prognoza zużycia
    df_hist = st.session_state["historia_zuzycia"]
    df_hist_renamed = df_hist.rename(columns={"data": "ds", "zuzycie_tb": "y"})
    if df_hist_renamed.dropna().shape[0] >= 2:
        forecast_zuzycie = prognozuj(df_hist_renamed)
    else:
        forecast_zuzycie = pd.DataFrame(columns=["ds", "yhat"])

    # 📊 Wykres
    st.subheader("📈 Zużycie i przestrzeń (TB)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pojemnosci["miesiac"], y=pojemnosci["pojemnosc_tb"], name="Całkowita pojemność", mode="lines"))
    fig.add_trace(go.Scatter(x=df_hist["data"], y=df_hist["zuzycie_tb"].cumsum(), name="Zajęte miejsce", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df_hist["data"], y=df_hist["zuzycie_tb"], name="Faktyczne zużycie", mode="lines"))
    if not forecast_zuzycie.empty:
        fig.add_trace(go.Scatter(x=forecast_zuzycie["ds"], y=forecast_zuzycie["yhat"], name="Prognoza zużycia", line=dict(dash='dot')))
    st.plotly_chart(fig, use_container_width=True)

    # 🧠 Rekomendacja zakupowa
    prognozowane_zuzycie_tb = forecast_zuzycie["yhat"].iloc[-1] if not forecast_zuzycie.empty else 0
    prognozowane_zuzycie_gb = int(prognozowane_zuzycie_tb * 1024)
    st.info(f"📊 Prognozowane zużycie w kolejnym miesiącu: **{prognozowane_zuzycie_gb} GB**")

    produkty = df["produkt"].unique()
    ceny_prognoza = {}
    for produkt in produkty:
        df_cena = df[df["produkt"] == produkt][["data_zamowienia", "cena"]]
        if len(df_cena) > 4:
            forecast_cena = prognozuj(df_cena.rename(columns={"cena": "ilosc"}))
            ceny_prognoza[produkt] = forecast_cena["yhat"].iloc[-1]
        else:
            ceny_prognoza[produkt] = df_cena["cena"].mean()

    opcje = []
    for p in produkty:
        size = pojemnosc_dysku_gb(p)
        if not size:
            continue
        cena = ceny_prognoza[p]
        opcje.append({
            "produkt": p,
            "cena": round(cena, 2),
            "pojemnosc": size,
            "cena_na_gb": cena / size
        })
    opcje.sort(key=lambda x: x["cena_na_gb"])

    pozostalo = prognozowane_zuzycie_gb
    zakupy = []
    for o in opcje:
        ile = pozostalo // o["pojemnosc"]
        if ile > 0:
            zakupy.append({"produkt": o["produkt"], "ilosc": int(ile)})
            pozostalo -= ile * o["pojemnosc"]
        if pozostalo <= 0:
            break
    if pozostalo > 0 and opcje:
        zakupy.append({"produkt": opcje[0]["produkt"], "ilosc": 1})

    df_zakup = pd.DataFrame(zakupy)
    if not df_zakup.empty:
        df_zakup["łączna_pojemność"] = df_zakup["ilosc"] * df_zakup["produkt"].apply(pojemnosc_dysku_gb)
        df_zakup["koszt"] = df_zakup.apply(lambda r: losowa_cena_bazowa(r["produkt"], st.session_state["symulacja_data"]) * r["ilosc"], axis=1)
        st.subheader("📦 Rekomendowany zakup")
        st.dataframe(df_zakup)
        st.success(f"🔧 Pokrycie: {df_zakup['łączna_pojemność'].sum()} GB za {df_zakup['koszt'].sum():.2f} zł")

        if st.button("🛒 Zamów rekomendację teraz"):
            for _, r in df_zakup.iterrows():
                cena = losowa_cena_bazowa(r["produkt"], st.session_state["symulacja_data"])
                dodaj_zakup(r["produkt"], int(r["ilosc"]), cena, st.session_state["symulacja_data"])
            st.success("✅ Zamówienie zrealizowane.")
            przesun_symulacje_o_miesiac()
            st.rerun()
