CREATE TABLE zakupy (
    id SERIAL PRIMARY KEY,
    produkt VARCHAR(100),
    dostawca VARCHAR(100),
    ilosc INT,
    cena FLOAT DEFAULT (random() * 50 + 50),  -- losowa cena dla testów
    data_zamowienia DATE
);
