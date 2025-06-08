import psycopg2
import pandas as pd
import numpy as np
from psycopg2.extensions import register_adapter, AsIs

# Rejestracja adapterów dla typów numpy
def adapt_numpy_float64(numpy_float):
    return AsIs(float(numpy_float))

def adapt_numpy_int64(numpy_int):
    return AsIs(int(numpy_int))

register_adapter(np.float64, adapt_numpy_float64)
register_adapter(np.float32, adapt_numpy_float64)
register_adapter(np.int64, adapt_numpy_int64)
register_adapter(np.int32, adapt_numpy_int64)

DB_CONFIG = {
    "dbname": "hurtownia",
    "user": "postgres",
    "password": "test123",  # Zmień jeśli masz inne hasło
    "host": "localhost",
    "port": 5432
}

def wyczysc_baze():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("DELETE FROM zakupy")
    conn.commit()
    cur.close()
    conn.close()

def get_zakupy():
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT * FROM zakupy ORDER BY data_zamowienia", conn)
    conn.close()
    return df

def dodaj_zakup(produkt, ilosc, cena, data_zamowienia):
    # Konwersja typów numpy do natywnych typów Pythona
    if isinstance(ilosc, (np.integer, np.int64, np.int32)):
        ilosc = int(ilosc)
    if isinstance(cena, (np.floating, np.float64, np.float32)):
        cena = float(cena)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO zakupy (produkt, ilosc, cena, data_zamowienia) VALUES (%s, %s, %s, %s)",
        (produkt, ilosc, cena, data_zamowienia)
    )
    conn.commit()
    cur.close()
    conn.close()

def pojemnosc_dysku_gb(produkt):
    produkt = produkt.lower().replace(" ", "")
    if "256" in produkt:
        return 256
    elif "512" in produkt:
        return 512
    elif "1tb" in produkt or "1 tb" in produkt:
        return 1024
    else:
        return None
