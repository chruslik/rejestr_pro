from flask import Flask, request, jsonify, make_response # Dodano make_response
from flask_cors import CORS
from supabase import create_client, Client
import os
import traceback
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

# ======================================================================
# KONFIGURACJA DLA UTF-8
# ======================================================================
# 1. Wyłącza konwersję na ASCII w jsonify (powinien działać, ale dla pewności zostawiamy)
app.config['JSON_AS_ASCII'] = False 
# 2. Ustawia domyślny charset (też może być nadpisywany przez serwer)
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

# ======================================================================
# GLOBALNA KOREKTA KODOWANIA (OSTATECZNA PRÓBA)
# Wymusza nagłówek i ponowne kodowanie danych, aby pozbyć się \uXXXX.
# ======================================================================
@app.after_request
def add_charset_header(response):
    # Używamy r""" """ dla bezpiecznego komentarza wieloliniowego
    r"""
    Dodaje lub poprawia nagłówek Content-Type,
    gwarantując, że zawsze zawiera charset=utf-8 dla odpowiedzi JSON.
    Ponownie koduje dane, aby usunąć sekwencje \uXXXX.
    """
    if response.content_type == 'application/json':
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        # To jest kluczowe: pobiera dane jako tekst (dekoduje \uXXXX),
        # a następnie ponownie koduje do UTF-8, wysyłając poprawne znaki.
        response.data = response.get_data(as_text=True).encode('utf8')
    return response
# ======================================================================


@app.route("/")
def index():
    """Sprawdzenie statusu API."""
    return {"status": "ok", "message": "API działa"}

# ----------------------------------------------------------------------

@app.route("/naprawy", methods=["GET"])
def get_naprawy():
    """
    Pobiera wszystkie naprawy, łącząc dane z tabel klienci i maszyny.
    """
    try:
        zapytanie = r"""
            *,
            klienci!naprawy_klient_id_fkey(klient_id, nazwa),
            maszyny!naprawy_maszyna_ns_fkey(ns, klasa, marka)
        """
        
        naprawy_resp = supabase.table("naprawy").select(zapytanie).order("id", desc=True).execute()
        naprawy = naprawy_resp.data

        wynik = []
        for n in naprawy:
            klient_dane = n.get("klienci", {})
            maszyna_dane = n.get("maszyny", {})
            
            if isinstance(klient_dane, list) and klient_dane:
                klient_dane = klient_dane[0]
            if isinstance(maszyna_dane, list) and maszyna_dane:
                maszyna_dane = maszyna_dane[0]

            wynik.append({
                "id": n["id"],
                "klient_id": n["klient_id"],
                "klient_nazwa": klient_dane.get("nazwa"),
                "posrednik_id": n.get("posrednik_id"),
                "marka": maszyna_dane.get("marka"),
                "klasa": maszyna_dane.get("klasa"),
                "ns": n.get("maszyna_ns"),
                "status": n["status"],
                "data_przyjecia": n["data_przyjecia"],
                "data_zakonczenia": n.get("data_zakonczenia"),
                "opis_usterki": n.get("opis_usterki"),
                "opis_naprawy": n.get("opis_naprawy"),
                "rozliczone": n.get("rozliczone", False)
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

        wymagane_pola = ["klient_id", "maszyna_ns", "data_przyjecia", "status"]
        if not all(dane.get(pole) for pole in wymagane_pola):
             return jsonify({"error": f"Brak wymaganych danych: {', '.join(wymagane_pola)}"}), 400

        dane_do_wstawienia = {
            "klient_id": dane["klient_id"],
            "maszyna_ns": dane["maszyna_ns"],
            "data_przyjecia": dane["data_przyjecia"],
            "data_zakonczenia": dane.get("data_zakonczenia"),
            "status": dane["status"],
            "opis_usterki": dane.get("opis_usterki"),
            "opis_naprawy": dane.get("opis_naprawy"),
            "posrednik_id": dane.get("posrednik_id"),
            "rozliczone": dane.get("rozliczone", False)
        }

        insert_resp = supabase.table("naprawy").insert(dane_do_wstawienia).execute()

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
    """Usuwa naprawę na podstawie ID."""
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

    pola_do_aktualizacji = {}
    if "status" in data:
        pola_do_aktualizacji["status"] = data["status"]
    if "data_zakonczenia" in data:
        pola_do_aktualizacji["data_zakonczenia"] = data["data_zakonczenia"]
    if "opis_usterki" in data:
        pola_do_aktualizacji["opis_usterki"] = data["opis_usterki"]
    if "opis_naprawy" in data:
        pola_do_aktualizacji["opis_naprawy"] = data["opis_naprawy"]
    if "posrednik_id" in data:
        pola_do_aktualizacji["posrednik_id"] = data["posrednik_id"]
    if "rozliczone" in data:
        pola_do_aktualizacji["rozliczone"] = data["rozliczone"]
    if "klient_id" in data:
        pola_do_aktualizacji["klient_id"] = data["klient_id"]
    if "maszyna_ns" in data:
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
    """Pobiera wszystkie maszyny."""
    try:
        maszyny_resp = supabase.table("maszyny").select("*").execute()
        return jsonify(maszyny_resp.data)
    except Exception as e:
        print("Błąd w get_maszyny:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/maszyny", methods=["POST"])
def dodaj_lub_pobierz_maszyne():
    """Dodaje nową maszynę lub pobiera istniejącą (klucz ns)."""
    try:
        data = request.get_json()
        marka = data.get("marka")
        klasa = data.get("klasa")
        ns = data.get("ns")
        opis = data.get("opis")

        if not ns:
             return jsonify({"error": "Brak wymaganego pola 'ns' (numer seryjny)"}), 400

        existing = supabase.table("maszyny") \
            .select("ns") \
            .eq("ns", ns) \
            .limit(1) \
            .execute()

        if existing.data:
            return jsonify({"ns": existing.data[0]["ns"]})

        insert = supabase.table("maszyny").insert({
            "ns": ns,
            "marka": marka,
            "klasa": klasa,
            "opis": opis
        }).execute()

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
    """Pobiera wszystkich klientów."""
    try:
        klienci_resp = supabase.table("klienci").select("*").execute()
        return jsonify(klienci_resp.data)
    except Exception as e:
        print("Błąd w get_klienci:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/klienci", methods=["POST"])
def dodaj_klienta():
    """Dodaje nowego klienta lub pobiera istniejącego."""
    try:
        data = request.get_json()
        nazwa = data.get("nazwa")
        adres = data.get("adres")
        osoba = data.get("osoba")
        telefon = data.get("telefon")

        if not nazwa:
            return jsonify({"error": "Brak nazwy klienta"}), 400

        existing = supabase.table("klienci") \
            .select("klient_id") \
            .eq("nazwa", nazwa) \
            .limit(1) \
            .execute()

        if existing.data:
            return jsonify({"klient_id": existing.data[0]["klient_id"]})

        insert = supabase.table("klienci").insert({
            "nazwa": nazwa,
            "adres": adres,
            "osoba": osoba,
            "telefon": telefon
        }).execute()

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
    """Pobiera dane do słowników."""
    try:
        marki = supabase.table("maszyny").select("marka").execute()
        klasy = supabase.table("maszyny").select("klasa").execute()
        usterki = supabase.table("naprawy").select("opis_usterki").execute()
        klienci = supabase.table("klienci").select("nazwa").execute()
        numery_seryjne = supabase.table("maszyny").select("ns").execute()

        return jsonify({
            "marki": sorted(list(set([row["marka"] for row in marki.data if row["marka"]]))),
            "klasy": sorted(list(set([row["klasa"] for row in klasy.data if row["klasa"]]))),
            "usterki": sorted(list(set([row["opis_usterki"] for row in usterki.data if row["opis_usterki"]]))),
            "klienci": [row["nazwa"] for row in klienci.data],
            "numery_seryjne": [row["ns"] for row in numery_seryjne.data]
        })
    except Exception as e:
        print("Błąd w /slowniki:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
