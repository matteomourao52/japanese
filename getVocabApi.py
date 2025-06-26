import requests, pandas as pd
from sqlalchemy import create_engine
from pathlib import Path
import datetime as dt

BASE_DIR = Path.home() / "Documents" / "japanese" / "data"
BASE_DIR.mkdir(parents=True, exist_ok=True)
BASE = "https://jlpt-vocab-api.vercel.app"

DB_PATH  = BASE_DIR / "jlpt_vocab.db"
CSV_PATH = BASE_DIR / f"jlpt_vocab_{dt.date.today()}.csv"

engine = create_engine(f"sqlite:///{DB_PATH}")

def fetch_level(lvl: int) -> pd.DataFrame:
    url = f"{BASE}/api/words/all?level={lvl}"
    data  = requests.get(url, timeout=30).json()
    words = data["words"] if isinstance(data, dict) else data
    df = pd.DataFrame(words)
    df["level"] = f"N{lvl}"
    return df

frames = [fetch_level(lvl) for lvl in range(1, 6)]
df_all = pd.concat(frames, ignore_index=True)

df_all.to_sql("jlpt_vocab", engine, if_exists="replace", index=False)
df_all.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

print("Vocabulaire JLPT synchronisé :", len(df_all), "entrées")