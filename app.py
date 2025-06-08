import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from db import get_zakupy, dodaj_zakup, pojemnosc_dysku_gb, wyczysc_baze
from forecast import prognozuj
import datetime

# ✅ Inicjalizacja sesji
if "inicjalizacja" not in st.session_state:
    wyczysc_baze()
    st.session_state["inicjalizacja"] = True

if "symulacja_data" not in st.session_state:
    st.session_state["symulacja_data"] = datetime.date.today()

if "historia_zuzycia" not in st.session_state:
    st.session_state["historia_zuzycia"] = pd.DataFrame(columns=["data", "zuzycie_tb"])

if "historia_pojemnosci" not in st.session_state:
    st.session_state["historia_pojemnosci"] = pd.DataFrame(columns=["data", "pojemnosc_tb"])


def losowa_cena_bazowa(produkt, data):
    base = {"Dysk 256 GB": 60, "Dysk 512 GB": 100, "Dysk 1 TB": 180}
    seed = int(data.strftime("%Y%m")) + sum(ord(c) for c in produkt)
    np.random.seed(seed)
    zmiennosc = np.random.normal(1.0, 0.1)
    return round(base.get(produkt, 100) * zmiennosc, 2)


def aktywna_pojemnosc_tb(df, data_symulacji):
    data_sym = pd.to_datetime(data_symulacji)
    df = df.copy()
    df["data_wygasniecia"] = df["data_zamowienia"] + pd.DateOffset(months=12)
    return df[df["data_wygasniecia"] > data_sym]["dane_tb"].sum()


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
    # Przetwarzanie danych
    df["data_zamowienia"] = pd.to_datetime(df["data_zamowienia"])
    df["pojemnosc_gb"] = df["produkt"].apply(pojemnosc_dysku_gb)
    df = df[df["pojemnosc_gb"].notnull()]
    df["dane_gb"] = df["pojemnosc_gb"] * df["ilosc"]
    df["dane_tb"] = df["dane_gb"] / 1024
    df["miesiac"] = df["data_zamowienia"].dt.to_period("M").dt.to_timestamp()

    # Aktualizacja historii pojemności (z wygasaniem)
    aktualna_pojemnosc = aktywna_pojemnosc_tb(df, st.session_state["symulacja_data"])
    nowy_wpis = pd.DataFrame([{
        "data": st.session_state["symulacja_data"],
        "pojemnosc_tb": aktualna_pojemnosc
    }])
    st.session_state["historia_pojemnosci"] = pd.concat(
        [st.session_state["historia_pojemnosci"], nowy_wpis]
    ).drop_duplicates("data", keep="last").sort_values("data")

    # Informacje o wygasłych dyskach
    wygasle = df[
        df["data_zamowienia"] + pd.DateOffset(months=12)
        <= pd.to_datetime(st.session_state["symulacja_data"])
        ]
    if not wygasle.empty:
        st.warning(f"⚠️ {wygasle['ilosc'].sum()} dysków wygasło ({-wygasle['dane_tb'].sum():.1f} TB utracone)")

    # Symulacja zużycia
    np.random.seed(int(st.session_state["symulacja_data"].strftime("%Y%m")))
    faktyczne_zuzycie_gb = 500 * np.random.uniform(0.5, 2.0)
    zuzycie_tb = faktyczne_zuzycie_gb / 1024

    nowy_wiersz = pd.DataFrame([{
        "data": st.session_state["symulacja_data"],
        "zuzycie_tb": zuzycie_tb
    }])
    st.session_state["historia_zuzycia"] = pd.concat(
        [st.session_state["historia_zuzycia"], nowy_wiersz]
    ).drop_duplicates("data", keep="last").sort_values("data")

    # Prognoza zużycia
    df_hist_renamed = st.session_state["historia_zuzycia"].rename(columns={"data": "ds", "zuzycie_tb": "y"})
    if df_hist_renamed.dropna().shape[0] >= 2:
        forecast_zuzycie = prognozuj(df_hist_renamed)
    else:
        forecast_zuzycie = pd.DataFrame(columns=["ds", "yhat"])

    # Wykres
    st.subheader("📈 Zużycie i przestrzeń (TB)")
    fig = go.Figure()

    # Aktywna pojemność (z wygasaniem)
    fig.add_trace(go.Scatter(
        x=st.session_state["historia_pojemnosci"]["data"],
        y=st.session_state["historia_pojemnosci"]["pojemnosc_tb"],
        name="Aktywna pojemność",
        mode="lines+markers",
        line=dict(color="green", width=2)
    ))
    # Zajęte miejsce (kumulatywnie)
    fig.add_trace(go.Scatter(
        x=st.session_state["historia_zuzycia"]["data"],
        y=st.session_state["historia_zuzycia"]["zuzycie_tb"].cumsum(),
        name="Zajęte miejsce",
        mode="lines+markers",
        line=dict(color="red", width=2)
    ))
    # Faktyczne zużycie (miesięczne) - kolor błękitny
    fig.add_trace(go.Scatter(
        x=st.session_state["historia_zuzycia"]["data"],
        y=st.session_state["historia_zuzycia"]["zuzycie_tb"],
        name="Faktyczne zużycie",
        mode="lines",
        line=dict(color="#00BFFF", width=1, dash="dash")
    ))
    # Prognoza
    if not forecast_zuzycie.empty:
        fig.add_trace(go.Scatter(
            x=forecast_zuzycie["ds"],
            y=forecast_zuzycie["yhat"],
            name="Prognoza zużycia",
            line=dict(dash="dot", color="orange")
        ))
    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="TB",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig, use_container_width=True)

    # Rekomendacja zakupowa
    prognozowane_zuzycie_tb = forecast_zuzycie["yhat"].iloc[-1] if not forecast_zuzycie.empty else 0
    prognozowane_zuzycie_gb = int(prognozowane_zuzycie_tb * 1024)
    st.info(f"📊 Prognozowane zużycie w kolejnym miesiącu: **{prognozowane_zuzycie_gb} GB**")

    # Analiza cen
    produkty = df["produkt"].unique()
    ceny_prognoza = {}
    for produkt in produkty:
        df_cena = df[df["produkt"] == produkt][["data_zamowienia", "cena"]]
        if len(df_cena) > 4:
            forecast_cena = prognozuj(df_cena.rename(columns={"cena": "ilosc"}))
            ceny_prognoza[produkt] = forecast_cena["yhat"].iloc[-1]
        else:
            ceny_prognoza[produkt] = df_cena["cena"].mean()

    # Generowanie rekomendacji
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

    # Wyświetlanie rekomendacji
    df_zakup = pd.DataFrame(zakupy)
    if not df_zakup.empty:
        df_zakup["łączna_pojemność"] = df_zakup["ilosc"] * df_zakup["produkt"].apply(pojemnosc_dysku_gb)
        df_zakup["koszt"] = df_zakup.apply(
            lambda r: losowa_cena_bazowa(r["produkt"], st.session_state["symulacja_data"]) * r["ilosc"], axis=1)
        st.subheader("📦 Rekomendowany zakup")
        st.dataframe(df_zakup)
        st.success(f"🔧 Pokrycie: {df_zakup['łączna_pojemność'].sum()} GB za {df_zakup['koszt'].sum():.2f} zł")

        # --- DWA PRZYCISKI ---
        aktywna_pojemnosc_gb = st.session_state["historia_pojemnosci"]["pojemnosc_tb"].iloc[-1] * 1024
        zajete_miejsce_gb = st.session_state["historia_zuzycia"]["zuzycie_tb"].cumsum().iloc[-1] * 1024
        brakujaca_pamiec_gb = max(0, int(zajete_miejsce_gb - aktywna_pojemnosc_gb))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🛒 Zamów rekomendację teraz"):
                for _, r in df_zakup.iterrows():
                    cena = losowa_cena_bazowa(r["produkt"], st.session_state["symulacja_data"])
                    dodaj_zakup(r["produkt"], int(r["ilosc"]), cena, st.session_state["symulacja_data"])
                st.success("✅ Zamówienie zrealizowane.")
                przesun_symulacje_o_miesiac()
                st.rerun()
        with col2:
            if st.button(f"🛒 Zamów rekomendację + brakującą pamięć ({brakujaca_pamiec_gb} GB)"):
                for _, r in df_zakup.iterrows():
                    cena = losowa_cena_bazowa(r["produkt"], st.session_state["symulacja_data"])
                    dodaj_zakup(r["produkt"], int(r["ilosc"]), cena, st.session_state["symulacja_data"])
                pozostalo = brakujaca_pamiec_gb
                for o in opcje:
                    ile = pozostalo // o["pojemnosc"]
                    if ile > 0:
                        dodaj_zakup(o["produkt"], int(ile), o["cena"], st.session_state["symulacja_data"])
                        pozostalo -= ile * o["pojemnosc"]
                    if pozostalo <= 0:
                        break
                if pozostalo > 0 and opcje:
                    dodaj_zakup(opcje[0]["produkt"], 1, opcje[0]["cena"], st.session_state["symulacja_data"])
                st.success("✅ Zamówienie zrealizowane (z kompensacją braków).")
                przesun_symulacje_o_miesiac()
                st.rerun()

    # --- ANALIZA CEN Z OSIAMI ---
    st.markdown("---")
    st.subheader("📊 Analiza historycznych cen")

    if produkty.size > 0:
        podsumowanie = []
        for produkt in produkty:
            df_prod = df[df["produkt"] == produkt].copy()
            df_prod["miesiac"] = df_prod["data_zamowienia"].dt.to_period("M").dt.to_timestamp()
            grupy = df_prod.groupby("miesiac")["cena"].mean().reset_index()

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=grupy["miesiac"],
                y=grupy["cena"],
                mode="lines+markers",
                line=dict(color="#1f77b4", width=2)
            ))
            fig.update_layout(
                title=f"Trend cenowy - {produkt}",
                xaxis_title="Miesiąc",
                yaxis_title="Średnia cena (PLN)",
                margin=dict(l=20, r=20, t=40, b=20),
                height=300,
                width=600
            )

            podsumowanie.append({
                "Produkt": produkt,
                "Wykres": fig
            })

        for item in podsumowanie:
            st.plotly_chart(item["Wykres"], use_container_width=True)

        # Tabela podsumowująca
        st.markdown("**📋 Podsumowanie cenowe**")
        df_srednie = pd.DataFrame([{
            "Produkt": p,
            "Średnia cena": df[df["produkt"] == p]["cena"].mean(),
            "Minimalna cena": df[df["produkt"] == p]["cena"].min(),
            "Maksymalna cena": df[df["produkt"] == p]["cena"].max()
        } for p in produkty])
        st.dataframe(df_srednie.style.format({
            "Średnia cena": "{:.2f} PLN",
            "Minimalna cena": "{:.2f} PLN",
            "Maksymalna cena": "{:.2f} PLN"
        }), hide_index=True)
    else:
        st.info("Brak wystarczających danych do analizy cenowej.")
