# ----------- 0. IMPORTS ----------------------------------------------------
import datetime as dt
from pathlib import Path
import requests, pandas as pd
from sqlalchemy import create_engine

# ----------- PARAMÈTRES ----------------------------------------------------
TERM_FIELD = "Terme"         # champ terme
DEF_FIELD  = "Def"          # champ définition
CARD_QUERY = ""              # filtre deck:..., tag:..., etc.

# ----------- DOSSIERS / FICHIERS ------------------------------------------
BASE_DIR = Path.home() / "Documents" / "japanese" / "data"
BASE_DIR.mkdir(parents=True, exist_ok=True)

today = dt.date.today().isoformat()
today_iso = dt.date.today().isoformat()

csv_terms = BASE_DIR / f"anki_terms_{today}.csv"
csv_today  = BASE_DIR / f"stats_today_{today_iso}.csv"
csv_byday  = BASE_DIR / f"stats_by_day_{today_iso}.csv"
csv_crev   = BASE_DIR / f"card_reviews_{today_iso}.csv"
csv_rpc    = BASE_DIR / f"reviews_per_card_{today_iso}.csv"

db_terms = BASE_DIR / "anki_terms.db"
db_stats   = BASE_DIR / "anki_stats.db"

eng_terms = create_engine(f"sqlite:///{db_terms}")
eng_stats = create_engine(f"sqlite:///{db_stats}")

# ----------- FONCTION API ANKICONNECT --------------------------------------
def invoke(action: str, **params):
    resp = requests.post(
        "http://localhost:8765",
        json={"action": action, "version": 6, "params": params},
        timeout=15
    ).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect error {action}: {resp['error']}")
    return resp["result"]



# ----------- 1. Sélection des cartes --------------------------------------
card_ids = invoke("findCards", query=CARD_QUERY)



# ----------- 2. cardsInfo (lots de 500) -----------------------------------
cards = []
for i in range(0, len(card_ids), 500):
    cards += invoke("cardsInfo", cards=card_ids[i:i+500])



# ----------- 3. notesInfo pour les tags (1 seul appel) --------------------
note_ids   = list({c["note"] for c in cards})
notes_info = invoke("notesInfo", notes=note_ids)          # rapide et natif
tags_by_id = {n["noteId"]: " ".join(n["tags"]) for n in notes_info}



# ----------- 4. Construction des lignes ----------------------------------
rows_terms, rows_stats = [], []

# 0) getCardsInfo
for c in cards:
    f = c["fields"]
    note_id = c["note"]

    # --- Contenu (TERME + DEFINITION) ---
    rows_terms.append({
        "card_id":    c["cardId"],
        "note_id":    note_id,
        "deck":       c["deckName"],
        "term":       f.get(TERM_FIELD, {}).get("value"),
        "definition": f.get(DEF_FIELD, {}).get("value"),
        "model":      c["modelName"],
        "interval":   c["interval"],
        "ord":        c["ord"],
        "type":       c["type"],
        "queue":      c["queue"],
        "due":        c["due"],
        "reps":       c["reps"],
        "lapses":     c["lapses"],
        "tags":       tags_by_id.get(note_id, ""),
    })
df_terms = pd.DataFrame(rows_terms)


# 1) getNumCardsReviewedToday  (kpi du jour)
num_today = invoke("getNumCardsReviewedToday")
df_today = pd.DataFrame([{
    "date": today_iso,
    "reviews": num_today
}])


# 2) getNumCardsReviewedByDay  (historique assiduité)
by_day = invoke("getNumCardsReviewedByDay")          # list[date, n]
df_by_day = pd.DataFrame(by_day, columns=["date", "reviews"])


# 3) cardReviews  (historique complet de revues)
#    Ici startID = 0  →  tout récupérer une fois ; ensuite, stocke le max(id)
logs = invoke("cardReviews", deck="", startID=0)
cols = ["rev_time_ms", "card_id", "usn",
        "ease", "new_ivl", "prev_ivl", "factor",
        "duration_ms", "rev_type"]
df_reviews = pd.DataFrame(logs, columns=cols)
df_reviews["rev_time"] = pd.to_datetime(df_reviews["rev_time_ms"], unit="ms")


# 4) getReviewsOfCards  (toutes les revues, groupées par carte)
reviews_dict = invoke("getReviewsOfCards", cards=card_ids)
rows_rpc = []
for cid, entries in reviews_dict.items():
    for e in entries:
        rows_rpc.append({
            "card_id":   int(cid),
            "rev_time":  pd.to_datetime(e["id"], unit="ms"),
            "usn":       e["usn"],
            "ease":      e["ease"],
            "new_ivl":   e["ivl"],
            "prev_ivl":  e["lastIvl"],
            "factor":    e["factor"],
            "duration_ms": e["time"],
            "rev_type":  e["type"],
        })
df_rpc = pd.DataFrame(rows_rpc)




# ----------- 5. Sauvegarde -------------------------------------------------

#0) terms
df_terms.to_sql("anki_terms", eng_terms, if_exists="replace", index=False)
df_terms.to_csv(csv_terms, index=False, encoding="utf-8-sig")

# 1) today
df_today.to_csv(csv_today, index=False)
df_today.to_sql("stats_today", eng_stats, if_exists="replace", index=False)

# 2) by day
df_by_day.to_csv(csv_byday, index=False)
df_by_day.to_sql("stats_by_day", eng_stats, if_exists="replace", index=False)

# 3) cardReviews
df_reviews.to_csv(csv_crev, index=False)
df_reviews.to_sql("card_reviews", eng_stats, if_exists="replace", index=False)

# 4) reviews per card
df_rpc.to_csv(csv_rpc, index=False)
df_rpc.to_sql("reviews_per_card", eng_stats, if_exists="replace", index=False)


print(
    f"✅ {len(df_terms):,} cartes → {csv_terms.name} & anki_terms.db\n"
    f"✅ Stats OK :\n"
    f"  • {csv_today.name}  ({len(df_today)} ligne)\n"
    f"  • {csv_byday.name}  ({len(df_by_day)} jours)\n"
    f"  • {csv_crev.name}   ({len(df_reviews):,} revues)\n"
    f"  • {csv_rpc.name}    ({len(df_rpc):,} revues détaillées)"
)
