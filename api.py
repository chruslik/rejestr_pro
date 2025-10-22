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
    return response
# ======================================================================

@app.route("/")
def index():
    """Sprawdzenie statusu API."""
    return {"status": "ok", "message": "API działa"}

# ----------------------------------------------------------------------
# ENDPOINTY MASZYN
# ----------------------------------------------------------------------

@app.route("/maszyny", methods=["GET"])
def get_maszyny():
    """Pobiera listę wszystkich maszyn (do filtrów)."""
    try:
        maszyny = supabase.table("maszyny").select("*").execute()
        
        if maszyny.data:
            return jsonify(maszyny.data)
        return jsonify([])
            
    except Exception as e:
        print("Błąd GET /maszyny:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (GET /maszyny): {str(e)}"}), 500

@app.route("/maszyny/<string:maszyna_ns_str>", methods=["GET"])
def get_maszyna_by_id(maszyna_ns_str):
    """Pobiera pojedynczą maszynę po numerze seryjnym (maszyna_ns) - case-insensitive."""
    try:
        # 🟢 POPRAWKA: Używamy ilike do wyszukiwania bez wrażliwości na wielkość liter
        # Używamy limit(1) zamiast single(), aby uniknąć wyjątku, gdy brak wyniku
        maszyna_resp = supabase.table("maszyny").select("*").ilike("maszyna_ns", maszyna_ns_str).limit(1).execute()
        
        maszyna_data = maszyna_resp.data[0] if maszyna_resp.data else None
        
        if not maszyna_data:
            return jsonify({"error": "Maszyna nie została znaleziona"}), 404
        
        # Zwracamy znaleziony rekord z oryginalną wielkością liter z bazy
        return jsonify(maszyna_data)
        
    except Exception as e:
        # Obsługa błędu gdy nie znajduje rekordu (404)
        if "No rows returned from the query" in str(e) or (hasattr(e, 'code') and e.code == 'PGRST116'):
            return jsonify({"error": "Maszyna nie została znaleziona"}), 404
            
        print(f"Błąd w /maszyny/{maszyna_ns_str} (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

@app.route("/maszyny", methods=["POST"])
def upsert_maszyna():
    """
    Dodaje lub aktualizuje maszynę (UPSERT) na podstawie maszyna_ns.
    Zachowuje wielkość liter zapisaną przez klienta.
    """
    try:
        data = request.get_json()
        
        # Wymagane pola
        if 'maszyna_ns' not in data or not data['maszyna_ns']:
            return jsonify({"error": "Pole 'maszyna_ns' jest wymagane."}), 400
        
        # 🟢 UWAGA: UPSERT jest case-sensitive na kluczu `maszyna_ns`, chyba że użyjesz citext w bazie.
        # Wysłany NS (np. AB60D) zostanie użyty do zapisu lub aktualizacji
        result = supabase.table("maszyny").upsert(
            data,
            on_conflict="maszyna_ns" 
        ).execute()
        
        if result.data:
            # Zwracamy zaktualizowany lub dodany rekord
            return jsonify(result.data[0]), 200
        else:
            return jsonify({"error": "Błąd podczas dodawania/aktualizacji maszyny."}), 500

    except Exception as e:
        print("Błąd POST /maszyny (UPSERT):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (POST /maszyny): {str(e)}"}), 500

# ----------------------------------------------------------------------
# ENDPOINTY KLIENTÓW
# ----------------------------------------------------------------------

@app.route("/klienci", methods=["GET"])
def get_klienci():
    """Pobiera listę wszystkich klientów."""
    try:
        klienci = supabase.table("klienci").select("*").execute()
        
        if klienci.data:
            return jsonify(klienci.data)
        return jsonify([])
            
    except Exception as e:
        print("Błąd GET /klienci:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (GET /klienci): {str(e)}"}), 500

@app.route("/klienci/<string:klient_id_str>", methods=["GET"])
def get_klient_by_id(klient_id_str):
    """
    Pobiera pojedynczego klienta po ID, używając bezwrażliwego na wielkość liter wyszukiwania (ILIKE).
    """
    try:
        # 🟢 POPRAWKA: Używamy ilike do wyszukiwania bez wrażliwości na wielkość liter
        klient_resp = supabase.table("klienci").select("*").ilike("klient_id", klient_id_str).limit(1).execute()
        
        klient_data = klient_resp.data[0] if klient_resp.data else None
        
        if not klient_data:
            return jsonify({"error": "Klient nie został znaleziony"}), 404
            
        # Zwracamy znaleziony rekord z oryginalną wielkością liter z bazy
        return jsonify(klient_data), 200
        
    except Exception as e:
        # Obsługa błędu gdy nie znajduje rekordu (404)
        if "No rows returned from the query" in str(e) or (hasattr(e, 'code') and e.code == 'PGRST116'):
            return jsonify({"error": "Klient nie został znaleziony"}), 404
            
        print(f"Błąd w /klienci/{klient_id_str} (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


@app.route("/klienci", methods=["POST"])
def dodaj_klienta():
    """Dodaje nowego klienta, zachowując wielkość liter."""
    try:
        data = request.get_json()
        
        if 'klient_id' not in data or not data['klient_id']:
            return jsonify({"error": "Pole 'klient_id' jest wymagane."}), 400
        
        # Zapisujemy ID klienta z wielkością liter wysłaną przez klienta (np. "Seco")
        result = supabase.table("klienci").insert(data).execute()
        
        return jsonify({"message": f"Dodano klienta: {data['klient_id']}"}), 201

    except APIError as ae:
        if 'duplicate key value violates unique constraint' in str(ae):
            return jsonify({"error": "Klient o podanym ID lub innej unikalnej wartości już istnieje."}), 409
        print("Błąd POST /klienci (APIError):", traceback.format_exc())
        return jsonify({"error": f"Błąd Supabase: {str(ae)}"}), 500
    except Exception as e:
        print("Błąd POST /klienci:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

# ----------------------------------------------------------------------
# ENDPOINTY NAPRAW (CRUD)
# ----------------------------------------------------------------------

# === FUNKCJA FORMATUJĄCA DANE (Bez zmian) ===
def _formatuj_naprawe(naprawa):
    """
    Formatowanie danych naprawy dla front-endu.
    Oczekuje płaskich kolumn od RPC, w tym 'maszyna_marka' i 'maszyna_klasa'.
    """
    marka = naprawa.get('maszyna_marka', 'Brak') 
    klasa = naprawa.get('maszyna_klasa', 'Brak')
    
    return {
        'id': naprawa.get('id'),
        # ZACHOWUJEMY WIELKOŚĆ LITER Z BAZY
        'klient_id': naprawa.get('klient_id', 'Brak'), 
        'maszyna_ns': naprawa.get('maszyna_ns', 'Brak'),
        
        'marka': marka, 
        'klasa': klasa,
        
        'data_przyjecia': naprawa.get('data_przyjecia'),
        'data_zakonczenia': naprawa.get('data_zakonczenia'),
        'status': naprawa.get('status'),
        'opis_usterki': naprawa.get('opis_usterki'),
        'opis_naprawy': naprawa.get('opis_naprawy'),
        'posrednik_id': naprawa.get('posrednik_id'),
        'rozliczone': naprawa.get('rozliczone'),
    }

# ==========================================

@app.route("/naprawy", methods=["GET"])
def get_naprawy():
    """Pobiera naprawy z filtrowaniem przez RPC."""
    try:
        # Wartości filtrów są wysyłane jako case-sensitive,
        # ale funkcja SQL musi użyć ILIKE, aby działało bezwrażliwie.
        klient_filter = request.args.get('_klient_id')
        ns_filter = request.args.get('_maszyna_ns')
        marka_filter = request.args.get('_marka') 
        klasa_filter = request.args.get('_klasa')
        status_filter = request.args.get('_status')
        usterka_filter = request.args.get('_opis_usterki')
        
        params = {
            "_klient_id": klient_filter,
            "_maszyna_ns": ns_filter,
            "_marka": marka_filter,
            "_klasa": klasa_filter,
            "_status": status_filter,
            # Usterka jest domyślnie normalizowana do małych liter na frontendzie
            "_opis_usterki": usterka_filter
        }
        
        params_rpc = {k: v for k, v in params.items() if v}
        
        print(f"DEBUG API: Wywołanie RPC z filtrami: {params_rpc}")
        
        naprawy_resp = supabase.rpc(
            'get_naprawy_z_filtrami', 
            params=params_rpc
        ).execute()

        naprawy = naprawy_resp.data

        wynik = [_formatuj_naprawe(n) for n in naprawy]
        return jsonify(wynik)
        
    except Exception as e:
        print("BŁĄD KRYTYCZNY W /naprawy (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: Błąd wewnętrzny. {str(e)}"}), 500

@app.route("/naprawy/<int:naprawa_id>", methods=["GET"])
def get_naprawa_by_id(naprawa_id):
    """Pobiera pojedynczą naprawę po ID (dla edycji)."""
    try:
        naprawa_resp = supabase.table("naprawy").select(
            "*, maszyny(marka, klasa)" 
        ).eq("id", naprawa_id).single().execute()
        
        naprawa_data = naprawa_resp.data
        
        if not naprawa_data:
            return jsonify({"error": "Naprawa nie została znaleziona"}), 404
        
        maszyna_dane = naprawa_data.pop("maszyny", {})
        
        wynik = {
            **naprawa_data, 
            # ZACHOWUJEMY WIELKOŚĆ LITER Z BAZY
            "marka": maszyna_dane.get("marka", "Brak"),
            "klasa": maszyna_dane.get("klasa", "Brak"),
        }
        
        return jsonify(wynik)
        
    except Exception as e:
        if "No rows returned from the query" in str(e) or (hasattr(e, 'code') and e.code == 'PGRST116'):
            return jsonify({"error": "Naprawa nie została znaleziona"}), 404
            
        print(f"Błąd w /naprawy/{naprawa_id} (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

@app.route("/naprawy", methods=["POST"])
def dodaj_naprawe():
    """Dodaje nową naprawę, zachowując wielkość liter dla ID, NS, Marki, Klasy."""
    data = request.get_json()
    try:
        # Dane są już oczyszczone i sformatowane z zachowaniem wielkości liter na frontendzie
        result = supabase.table("naprawy").insert(data).execute()
        
        if result.data:
            return jsonify(result.data[0]), 201
        else:
            return jsonify({"error": "Błąd podczas dodawania naprawy."}), 500

    except Exception as e:
        print("Błąd w dodaj_naprawe (POST):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (POST /naprawy): {str(e)}"}), 500

@app.route("/naprawy/<int:naprawa_id>", methods=["DELETE"])
def delete_naprawa(naprawa_id):
    """Usuwa naprawę."""
    try:
        result = supabase.table("naprawy").delete().eq("id", naprawa_id).execute()
        
        if result.data:
            return jsonify({"message": f"Usunięto naprawę o ID: {naprawa_id}"})
        else:
            return jsonify({"error": "Nie znaleziono naprawy o podanym ID."}), 404
            
    except Exception as e:
        print("Błąd w delete_naprawa (DELETE):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (DELETE /naprawy): {str(e)}"}), 500


@app.route("/naprawy/<int:naprawa_id>", methods=["PUT"])
def update_naprawa(naprawa_id):
    """Aktualizuje naprawę, akceptując częściową aktualizację danych."""
    data = request.get_json()

    pola_do_aktualizacji = {}
    
    # Dane te zostaną zapisane z zachowaniem wielkości liter
    pola_naprawy = ["status", "data_zakonczenia", "opis_usterki", "opis_naprawy", 
                    "posrednik_id", "rozliczone", "klient_id", "maszyna_ns", "data_przyjecia"]

    for pole in pola_naprawy:
        if pole in data:
            pola_do_aktualizacji[pole] = data[pole]

    if not pola_do_aktualizacji:
        return jsonify({"error": "Brak danych do aktualizacji"}), 400

    try:
        result = supabase.table("naprawy").update(pola_do_aktualizacji).eq("id", naprawa_id).execute()

        if result.data:
            return jsonify({"message": f"Zaktualizowano naprawę o ID: {naprawa_id}"})
        else:
            return jsonify({"error": "Nie znaleziono naprawy o podanym ID lub brak zmian."}), 404
            
    except Exception as e:
        print("Błąd w update_naprawa (PUT):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (PUT /naprawy): {str(e)}"}), 500

# ======================================================================
# URUCHOMIENIE APLIKACJI
# ======================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
