import psycopg2
import pandas as pd

DB_CONFIG = {
    "dbname": "hurtownia",
    "user": "postgres",
    "password": "admin",  # Zmień jeśli masz inne hasło
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
    produkt = produkt.lower()
    if "256" in produkt:
        return 256
    elif "512" in produkt:
        return 512
    elif "1 tb" in produkt or "1tb" in produkt:
        return 1024
    else:
        return None
