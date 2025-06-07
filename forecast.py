from prophet import Prophet
import pandas as pd

def prognozuj(df, okres=6):
    df = df.rename(columns={"data_zamowienia": "ds", "ilosc": "y"})
    model = Prophet()
    model.fit(df)
    future = model.make_future_dataframe(periods=okres, freq='M')
    forecast = model.predict(future)
    return forecast[['ds', 'yhat']]
