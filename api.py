from flask import Flask, request, jsonify # jsonify jest już importowany
from flask_cors import CORS
from supabase import create_client, Client
import os
import traceback
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

# ======================================================================
# POPRAWKA KODOWANIA UTF-8 DLA POLSKICH ZNAKÓW
# ======================================================================
app.config['JSON_AS_ASCII'] = False 
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8' 
# ======================================================================

load_dotenv()

# Klucze Supabase z Environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")


# Sprawdzenie, czy klucze są dostępne, aby uniknąć błędów
if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError("Brak SUPABASE_URL lub SUPABASE_KEY w zmiennych środowiskowych.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Usunięcie nieużywanego importu psycopg2.extras.RealDictCursor i nieużywanych funkcji
# connect_db z oryginalnego kodu, ponieważ używamy klienta Supabase, a nie bezpośredniego połączenia z PSQL.

@app.route("/")
def index():
    """Sprawdzenie statusu API."""
    return {"status": "ok", "message": "API działa"}

# ----------------------------------------------------------------------

@app.route("/naprawy", methods=["GET"])
def get_naprawy():
    """
    Pobiera wszystkie naprawy, łącząc dane z tabel klienci i maszyny.
    Zamiast wielu zapytań i łączenia w Pythonie, używamy natywnego
    łączenia z Supabase (PostgREST).
    """
    try:
        # POBIERANIE WSZYSTKICH NAPRAW Z JOINAMI
        # '*, klienci(nazwa, klient_id), maszyny(marka, klasa, ns)'
        # uwzględnia wszystkie pola z naprawy (*) i wybrane pola z połączonych tabel.
        # W nowym schemacie:
        # * 'naprawy.klient_id' łączy się z 'klienci.klient_id'
        # * 'naprawy.maszyna_ns' łączy się z 'maszyny.ns'

        zapytanie = """
            *,
            klienci!naprawy_klient_id_fkey(klient_id, nazwa),
            maszyny!naprawy_maszyna_ns_fkey(ns, klasa, marka)
        """
        
        # Sortowanie po ID malejąco i wykonanie zapytania
        naprawy_resp = supabase.table("naprawy").select(zapytanie).order("id", desc=True).execute()
        naprawy = naprawy_resp.data

        wynik = []
        for n in naprawy:
            # Dostęp do połączonych danych: np. n['klienci']['nazwa']
            klient_dane = n.get("klienci", {})
            maszyna_dane = n.get("maszyny", {})
            
            # W Supabase/PostgREST joiny zwracają obiekt lub listę,
            # mimo że w tym przypadku będą to pojedyncze obiekty.
            # Upewniamy się, że to słownik, na wypadek gdyby zwróciło listę.
            if isinstance(klient_dane, list) and klient_dane:
                klient_dane = klient_dane[0]
            if isinstance(maszyna_dane, list) and maszyna_dane:
                maszyna_dane = maszyna_dane[0]

            wynik.append({
                "id": n["id"],
                "klient_id": n["klient_id"], # Nowe pole: klient_id
                "klient_nazwa": klient_dane.get("nazwa"),
                "posrednik_id": n.get("posrednik_id"), # Nowe pole: posrednik_id
                "marka": maszyna_dane.get("marka"),
                "klasa": maszyna_dane.get("klasa"),
                "ns": n.get("maszyna_ns"), # Zmienione na maszyna_ns
                "status": n["status"],
                "data_przyjecia": n["data_przyjecia"],
                "data_zakonczenia": n.get("data_zakonczenia"),
                "opis_usterki": n.get("opis_usterki"), # Zmienione na opis_usterki
                "opis_naprawy": n.get("opis_naprawy"), # Zmienione na opis_naprawy
                "rozliczone": n.get("rozliczone", False) # Nowe pole: rozliczone
            })

        return jsonify(wynik)
    except Exception as e:
        print("Błąd w /naprawy (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------

@app.route("/naprawy", methods=["POST"])
def dodaj_naprawe():
    """Dodaje nową naprawę, uwzględniając nowe nazwy pól i wymagane dane."""
    try:
        dane = request.get_json()

        # Walidacja - uwzględniono nowe wymagane pola i zmienione nazwy
        wymagane_pola = ["klient_id", "maszyna_ns", "data_przyjecia", "status"]
        if not all(dane.get(pole) for pole in wymagane_pola):
             return jsonify({"error": f"Brak wymaganych danych: {', '.join(wymagane_pola)}"}), 400

        # Utworzenie słownika z danymi do wstawienia
        dane_do_wstawienia = {
            "klient_id": dane["klient_id"], # Nowe wymagane pole
            "maszyna_ns": dane["maszyna_ns"], # Zmienione pole
            "data_przyjecia": dane["data_przyjecia"],
            "data_zakonczenia": dane.get("data_zakonczenia"),
            "status": dane["status"],
            "opis_usterki": dane.get("opis_usterki"), # Zmienione pole
            "opis_naprawy": dane.get("opis_naprawy"), # Zmienione pole
            "posrednik_id": dane.get("posrednik_id"), # Nowe pole
            "rozliczone": dane.get("rozliczone", False) # Nowe pole
        }

        # Dodanie naprawy
        insert_resp = supabase.table("naprawy").insert(dane_do_wstawienia).execute()

        # Zwrot id nowo dodanej naprawy
        if insert_resp.data:
            return jsonify({"sukces": True, "id": insert_resp.data[0].get("id")})
        else:
            return jsonify({"sukces": False, "error": "Brak danych zwrotnych po wstawieniu"}), 500

    except Exception as e:
        print("Błąd w /naprawy (POST):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------

@app.route("/naprawy/<int:naprawa_id>", methods=["DELETE"])
def delete_naprawa(naprawa_id):
    """Usuwa naprawę na podstawie ID (bez zmian w logice)."""
    try:
        result = supabase.table("naprawy").delete().eq("id", naprawa_id).execute()

        if result.data:
            return jsonify({"message": f"Usunięto naprawę o ID: {naprawa_id}"})
        else:
            return jsonify({"error": "Nie znaleziono naprawy"}), 404
    except Exception as e:
        print("Błąd w delete_naprawa:", e)
        return jsonify({"error": str(e)}), 500

# ----------------------------------------------------------------------

@app.route("/naprawy/<int:naprawa_id>", methods=["PUT"])
def update_naprawa(naprawa_id):
    """Aktualizuje naprawę, uwzględniając nowe nazwy pól."""
    data = request.get_json()

    # Filtrujemy tylko te pola, które są w nowej tabeli i zostały przekazane
    pola_do_aktualizacji = {}
    if "status" in data:
        pola_do_aktualizacji["status"] = data["status"]
    if "data_zakonczenia" in data:
        pola_do_aktualizacji["data_zakonczenia"] = data["data_zakonczenia"]
    if "opis_usterki" in data: # Nowa nazwa
        pola_do_aktualizacji["opis_usterki"] = data["opis_usterki"]
    if "opis_naprawy" in data: # Nowa nazwa
        pola_do_aktualizacji["opis_naprawy"] = data["opis_naprawy"]
    if "posrednik_id" in data: # Nowe pole
        pola_do_aktualizacji["posrednik_id"] = data["posrednik_id"]
    if "rozliczone" in data: # Nowe pole
        pola_do_aktualizacji["rozliczone"] = data["rozliczone"]
    if "klient_id" in data: # Nowe pole
        pola_do_aktualizacji["klient_id"] = data["klient_id"]
    if "maszyna_ns" in data: # Zmieniona nazwa
        pola_do_aktualizacji["maszyna_ns"] = data["maszyna_ns"]


    if not pola_do_aktualizacji:
         return jsonify({"error": "Brak danych do aktualizacji"}), 400

    try:
        result = supabase.table("naprawy").update(pola_do_aktualizacji).eq("id", naprawa_id).execute()

        if result.data:
            return jsonify({"message": f"Zaktualizowano naprawę o ID: {naprawa_id}"})
        else:
            return jsonify({"error": "Nie znaleziono naprawy"}), 404
    except Exception as e:
        print("Błąd w update_naprawa:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ZMIANY W OBRÓBCE MASZYN
# ----------------------------------------------------------------------

@app.route("/maszyny", methods=["GET"])
def get_maszyny():
    """Pobiera wszystkie maszyny. Oryginalna wersja używała bezpośredniego PSQL - zmieniono na Supabase/PostgREST."""
    try:
        # Tabela maszyny nie ma już kolumny klient_id i id (klucz to ns)
        maszyny_resp = supabase.table("maszyny").select("*").execute()
        return jsonify(maszyny_resp.data)
    except Exception as e:
        print("Błąd w get_maszyny:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/maszyny", methods=["POST"])
def dodaj_lub_pobierz_maszyne():
    """
    Dodaje nową maszynę lub pobiera istniejącą.
    Zmieniono klucz unikalności na 'ns' (numer seryjny), usunięto 'klient_id' z maszyny.
    """
    try:
        data = request.get_json()
        marka = data.get("marka")
        klasa = data.get("klasa")
        ns = data.get("ns") # Zmienione na ns (numer seryjny)
        opis = data.get("opis") # Nowe pole

        if not ns:
             return jsonify({"error": "Brak wymaganego pola 'ns' (numer seryjny)"}), 400

        # Sprawdź czy maszyna już istnieje (teraz tylko po 'ns' - kluczu głównym)
        existing = supabase.table("maszyny") \
            .select("ns") \
            .eq("ns", ns) \
            .limit(1) \
            .execute()

        if existing.data:
            # Zwracamy istniejący ns
            return jsonify({"ns": existing.data[0]["ns"]})

        # Wstaw nową maszynę
        insert = supabase.table("maszyny").insert({
            "ns": ns,
            "marka": marka,
            "klasa": klasa,
            "opis": opis
        }).execute()

        # Zwracamy ns nowo dodanej maszyny
        if insert.data:
             return jsonify({"ns": insert.data[0]["ns"]})
        else:
             return jsonify({"error": "Brak danych zwrotnych po wstawieniu maszyny"}), 500

    except Exception as e:
        print("Błąd w dodaj_lub_pobierz_maszyne:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ZMIANY W OBRÓBCE KLIENTÓW
# ----------------------------------------------------------------------

@app.route("/klienci", methods=["GET"])
def get_klienci():
    """Pobiera wszystkich klientów (nowa funkcja)."""
    try:
        klienci_resp = supabase.table("klienci").select("*").execute()
        return jsonify(klienci_resp.data)
    except Exception as e:
        print("Błąd w get_klienci:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/klienci", methods=["POST"])
def dodaj_klienta():
    """
    Dodaje nowego klienta lub pobiera istniejącego.
    Zmieniono klucz główny na 'klient_id'.
    Rozszerzono o nowe pola: 'adres', 'osoba', 'telefon'.
    """
    try:
        data = request.get_json()
        nazwa = data.get("nazwa")
        adres = data.get("adres")
        osoba = data.get("osoba")
        telefon = data.get("telefon")

        if not nazwa:
            return jsonify({"error": "Brak nazwy klienta"}), 400

        # Sprawdź, czy klient już istnieje (po 'nazwa')
        existing = supabase.table("klienci") \
            .select("klient_id") \
            .eq("nazwa", nazwa) \
            .limit(1) \
            .execute()

        if existing.data:
            # Zmieniono 'id' na 'klient_id'
            return jsonify({"klient_id": existing.data[0]["klient_id"]})

        # Dodaj nowego klienta
        insert = supabase.table("klienci").insert({
            "nazwa": nazwa,
            "adres": adres,
            "osoba": osoba,
            "telefon": telefon
        }).execute()

        # Zmieniono 'id' na 'klient_id'
        if insert.data:
            return jsonify({"klient_id": insert.data[0]["klient_id"]})
        else:
             return jsonify({"error": "Brak danych zwrotnych po wstawieniu klienta"}), 500
    except Exception as e:
        print("Błąd w dodaj_klienta:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ZMIANY W SŁOWNIKACH
# ----------------------------------------------------------------------

@app.route("/slowniki")
def get_slowniki():
    """
    Pobiera dane do słowników, uwzględniając nowe nazwy pól:
    'opis_usterki' zamiast 'usterka', 'ns' zamiast 'numer_seryjny'.
    """
    try:
        marki = supabase.table("maszyny").select("marka").execute()
        klasy = supabase.table("maszyny").select("klasa").execute()
        # Zmieniono 'usterka' na 'opis_usterki'
        usterki = supabase.table("naprawy").select("opis_usterki").execute()
        # Zmieniono 'nazwa' to klucz nazwy klienta
        klienci = supabase.table("klienci").select("nazwa").execute()
        # Zmieniono 'numer_seryjny' na 'ns'
        numery_seryjne = supabase.table("maszyny").select("ns").execute()

        return jsonify({
            "marki": sorted(list(set([row["marka"] for row in marki.data if row["marka"]]))),
            "klasy": sorted(list(set([row["klasa"] for row in klasy.data if row["klasa"]]))),
            # Zmieniono klucz dostępu
            "usterki": sorted(list(set([row["opis_usterki"] for row in usterki.data if row["opis_usterki"]]))),
            "klienci": [row["nazwa"] for row in klienci.data],
            # Zmieniono klucz dostępu
            "numery_seryjne": [row["ns"] for row in numery_seryjne.data]
        })
    except Exception as e:
        print("Błąd w /slowniki:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Użycie debug=True na render.com nie jest zalecane w produkcji
    app.run(host="0.0.0.0", port=port)
