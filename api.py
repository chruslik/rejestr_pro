from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from supabase import create_client, Client
import os
import traceback
from dotenv import load_dotenv
from postgrest.exceptions import APIError

app = Flask(__name__)
CORS(app)

# ======================================================================
# KONFIGURACJA DLA UTF-8
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

# ======================================================================
# GLOBALNA KOREKTA KODOWANIA
# ======================================================================
@app.after_request
def add_charset_header(response):
    r"""
    Dodaje lub poprawia nagłówek Content-Type,
    gwarantując, że zawsze zawiera charset=utf-8 dla odpowiedzi JSON.
    """
    if response.content_type == 'application/json':
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.data = response.get_data(as_text=True).encode('utf8')
    return response
# ======================================================================


@app.route("/")
def index():
    """Sprawdzenie statusu API."""
    return {"status": "ok", "message": "API działa"}

# ----------------------------------------------------------------------
# ENDPOINTY NAPRAW (CRUD)
# ----------------------------------------------------------------------

def _formatuj_naprawe(n):
    """Pomocnicza funkcja do formatowania pojedynczej naprawy."""
    maszyna_dane = n.get("maszyny", {})
    
    if isinstance(maszyna_dane, list) and maszyna_dane:
        maszyna_dane = maszyna_dane[0]

    return {
        "id": n["id"],
        "klient_id": n["klient_id"], 
        "marka": maszyna_dane.get("marka"),
        "klasa": maszyna_dane.get("klasa"),
        "ns": n.get("maszyna_ns"),
        "status": n["status"],
        "data_przyjecia": n["data_przyjecia"],
        "data_zakonczenia": n.get("data_zakonczenia"),
        "opis_usterki": n.get("opis_usterki"),
        "opis_naprawy": n.get("opis_naprawy"),
        "posrednik_id": n.get("posrednik_id"),
        "rozliczone": n.get("rozliczone", False)
    }

# POPRAWIONA FUNKCJA Z OBSŁUGĄ RELACJI:

@app.route("/naprawy", methods=["GET"])
def get_naprawy():
    # ... (pobranie parametrów) ...
    
    try:
        zapytanie_select = r"""
            *,
            maszyny!naprawy_maszyna_ns_fkey(ns, klasa, marka)
        """
        
        query_builder = supabase.table("naprawy").select(zapytanie_select)
        
        # ... (poprawione filtry klient_id i maszyna_ns) ...

        # 3. Dynamiczne dodawanie filtrów (Kluczowa zmiana dla relacji!)
        
        if klient_filter:
            query_builder = query_builder.ilike('klient_id', f'%{klient_filter}%') 

        if ns_filter:
            query_builder = query_builder.eq('maszyna_ns', ns_filter)
            
        # POPRAWKA DLA MARKI I KLASY (filtry na relacji):
        # Format: .eq('nazwa_relacji.nazwa_pola', wartość)
        
        if marka_filter:
            print(f"DEBUG SERWERA: Filtr marka (relacja) = {marka_filter}")
            # Użycie .ilike jest lepsze dla tekstu
            query_builder = query_builder.ilike('maszyny.marka', f'%{marka_filter}%') 
            
        if klasa_filter:
            print(f"DEBUG SERWERA: Filtr klasa (relacja) = {klasa_filter}")
            query_builder = query_builder.ilike('maszyny.klasa', f'%{klasa_filter}%')

        if status_filter:
            query_builder = query_builder.eq('status', status_filter)
            
        if usterka_filter:
            query_builder = query_builder.ilike('opis_usterki', f'%{usterka_filter}%')


        # 4. Wykonanie i zwrócenie danych
        naprawy_resp = query_builder.order("id", desc=True).execute()
        # ... (dalsza część funkcji) ...
        
    except Exception as e:
        print("BŁĄD KRYTYCZNY W /naprawy (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


@app.route("/naprawy", methods=["POST"])
def dodaj_naprawe():
    """Dodaje nową naprawę, uwzględniając wszystkie pola z schematu."""
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

@app.route("/naprawy/<int:naprawa_id>", methods=["PUT"])
def update_naprawa(naprawa_id):
    """Aktualizuje naprawę, akceptując częściową aktualizację danych."""
    data = request.get_json()

    pola_do_aktualizacji = {}
    
    # Lista wszystkich pól do aktualizacji (kluczowych do filtrowania danych) 
    pola_naprawy = ["status", "data_zakonczenia", "opis_usterki", "opis_naprawy", 
                    "posrednik_id", "rozliczone", "klient_id", "maszyna_ns", "data_przyjecia"]

    for pole in pola_naprawy:
        # Sprawdzamy, czy pole istnieje w przychodzącym JSON, 
        # co umożliwia aktualizację tylko jednego pola (np. 'rozliczone')
        if pole in data:
            pola_do_aktualizacji[pole] = data[pole]

    if not pola_do_aktualizacji:
        # Ten błąd jest często zwracany, gdy żądanie jest puste lub nie zawiera znanych pól
        return jsonify({"error": "Brak danych do aktualizacji"}), 400

    try:
        # Wykonaj aktualizację tylko dla przekazanych pól
        result = supabase.table("naprawy").update(pola_do_aktualizacji).eq("id", naprawa_id).execute()

        if result.data:
            return jsonify({"message": f"Zaktualizowano naprawę o ID: {naprawa_id}"})
        else:
            # Pusta lista danych zwrotnych może oznaczać, że ID nie zostało znalezione
            return jsonify({"error": "Nie znaleziono naprawy o podanym ID lub brak zmian."}), 404
            
    except Exception as e:
        # Wypisanie pełnego błędu jest kluczowe dla serwera Render
        print("Błąd w update_naprawa (PUT):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (PUT /naprawy): {str(e)}"}), 500
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ENDPOINTY MASZYN
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

@app.route("/maszyny/<string:ns>", methods=["GET"])
def get_maszyna_by_ns(ns):
    """Pobiera szczegóły maszyny po numerze seryjnym (ns)."""
    try:
        maszyna_resp = supabase.table("maszyny").select("*").eq("ns", ns).single().execute()
        
        if maszyna_resp.data:
            return jsonify(maszyna_resp.data)
        else:
            return jsonify({"error": "Nie znaleziono maszyny"}), 404
    except Exception as e:
        if "No rows returned from the query" in str(e):
             return jsonify({"error": "Nie znaleziono maszyny"}), 404
        print(f"Błąd w /maszyny/{ns} (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

@app.route("/maszyny", methods=["POST"])
def dodaj_lub_pobierz_maszyne():
    """Dodaje nową maszynę lub pobiera istniejącą i aktualizuje dane (klucz ns)."""
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

        # Payload używany zarówno do wstawienia, jak i do aktualizacji
        payload = {
            "ns": ns,
            "marka": marka,
            "klasa": klasa,
            "opis": opis
        }

        if existing.data:
            # Maszyna istnieje, aktualizuj dane (POST jest używany jako UPSERT)
            update_resp = supabase.table("maszyny").update(payload).eq("ns", ns).execute()
            if update_resp.data:
                return jsonify({"ns": existing.data[0]["ns"]})
            else:
                return jsonify({"error": "Brak danych zwrotnych po aktualizacji maszyny"}), 500
                
        else:
            # Maszyna nie istnieje, wstaw nową
            insert = supabase.table("maszyny").insert(payload).execute()
            if insert.data:
                 return jsonify({"ns": insert.data[0]["ns"]})
            else:
                 return jsonify({"error": "Brak danych zwrotnych po wstawieniu maszyny"}), 500

    except Exception as e:
        print("Błąd w dodaj_lub_pobierz_maszyne:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ENDPOINTY KLIENTÓW
# ----------------------------------------------------------------------

@app.route("/klienci/<string:klient_id_str>", methods=["GET"])
def get_klient_by_id(klient_id_str):
    """Pobiera dane pojedynczego klienta po jego ID. Używane do walidacji w aplikacji desktopowej."""
    try:
        # Używamy .single().execute() - klient_resp.data będzie słownikiem lub None/Error
        klient_resp = supabase.table("klienci").select("*").eq("klient_id", klient_id_str).single().execute()
        
        # Jeśli się udało (kod 200), zwróć dane. klient_resp.data jest już słownikiem.
        # Usuwamy [0]
        return jsonify(klient_resp.data)

    # Poprawna obsługa błędu, gdy Supabase .single() nie znajdzie rekordu
    except APIError as e:
        # Kod PGRST116 oznacza "The result contains 0 rows"
        if e.code == 'PGRST116':
            return jsonify({"error": "Nie znaleziono klienta"}), 404 # ZWRACAMY 404
        
        # Obsługa innych błędów API Supabase
        print(f"Błąd Supabase (APIError) w get_klient_by_id: {e}")
        return jsonify({"error": f"Błąd bazy danych: {e.message}"}), 500

    except Exception as e:
        # Obsługa nieznanych błędów serwera
        print("BŁĄD W get_klient_by_id:")
        print(traceback.format_exc()) # Teraz zobaczysz pełny ślad błędu w logach Render
        return jsonify({"error": "Wewnętrzny błąd serwera. Sprawdź logi serwera."}), 500


@app.route("/klienci", methods=["GET", "POST"])
def dodaj_lub_pobierz_klienta():
    """
    Obsługuje POST (dodanie nowego klienta) oraz GET (pobranie listy wszystkich klientów).
    """
    
    if request.method == "GET":
        # ----------------------------------------------------
        # NOWA LOGIKA: POBIERANIE LISTY WSZYSTKICH KLIENTÓW (Fix dla 405)
        # ----------------------------------------------------
        try:
            # Zmieniłem to na prostsze zapytanie bez .single(), by uniknąć 406
            klienci = supabase.table("klienci").select("*").execute()
            
            # W Supabase .execute() zwraca pełną strukturę; dane są w .data
            if klienci.data:
                return jsonify(klienci.data)
            else:
                return jsonify([]), 200 # Zwracamy pustą listę, a nie błąd
                
        except Exception as e:
            print("Błąd GET /klienci:", e)
            return jsonify({"error": "Błąd pobierania listy klientów"}), 500

    
    elif request.method == "POST":
        # ----------------------------------------------------
        # ISTNIEJĄCA LOGIKA: DODAWANIE NOWEGO KLIENTA
        # ----------------------------------------------------
        try:
            data = request.get_json()
            nazwa = data.get("nazwa")
            klient_id = data.get("klient_id") 
            
            if not nazwa or not klient_id:
                  return jsonify({"error": "Brak wymaganego pola 'nazwa' lub 'klient_id'"}), 400

            # Wyszukiwanie po nazwie
            existing = supabase.table("klienci") \
                .select("klient_id") \
                .eq("nazwa", nazwa) \
                .limit(1) \
                .execute()

            if existing.data:
                # Klient istnieje, zwróć jego ID
                return jsonify({"klient_id": existing.data[0]["klient_id"]})

            # Jeśli klient nie istnieje, wstaw nowego
            insert_data = {
                "klient_id": klient_id, 
                "nazwa": nazwa,
                "adres": data.get("adres"),
                "osoba": data.get("osoba"),
                "telefon": data.get("telefon"),
                "NIP": data.get("NIP")
            }
            
            insert_data = {k: v for k, v in insert_data.items() if v is not None}

            insert = supabase.table("klienci").insert(insert_data).execute()

            if insert.data:
                return jsonify({"klient_id": insert.data[0]["klient_id"]})
            else:
                return jsonify({"error": "Brak danych zwrotnych po wstawieniu klienta"}), 500
                
        except Exception as e:
            # Pamiętaj o traceback w produkcji, ale użyj prostszego komunikatu dla klienta
            print("Błąd w dodaj_lub_pobierz_klienta (POST):", e)
            return jsonify({"error": f"Błąd serwera podczas dodawania klienta: {str(e)}"}), 500

@app.route("/klienci/<string:klient_id_str>", methods=["PUT"])
def update_klient(klient_id_str):
    """Aktualizuje dane klienta, uwzględniając wszystkie pola z schematu."""
    data = request.get_json()

    pola_do_aktualizacji = {}
    
    # Lista wszystkich pól do aktualizacji (oprócz klient_id, które jest PK)
    pola_klienta = ["nazwa", "adres", "osoba", "telefon", "NIP"]

    for pole in pola_klienta:
        if pole in data:
            pola_do_aktualizacji[pole] = data[pole]

    if not pola_do_aktualizacji:
         return jsonify({"error": "Brak danych do aktualizacji"}), 400

    try:
        # klient_id jest traktowane jako string (TEXT)
        result = supabase.table("klienci").update(pola_do_aktualizacji).eq("klient_id", klient_id_str).execute()

        if result.data:
            return jsonify({"message": f"Zaktualizowano klienta o ID: {klient_id_str}"})
        else:
            return jsonify({"error": "Nie znaleziono klienta"}), 404
    except Exception as e:
        print("Błąd w update_klient:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
