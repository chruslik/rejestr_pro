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
        # Zrezygnowanie z ponownego kodowania, ponieważ może to powodować błędy.
        # Flask i jsonify powinny to robić poprawnie.
    return response
# ======================================================================

# ----------------------------------------------------------------------
# ENDPOINTY MASZYN
# ----------------------------------------------------------------------

@app.route("/maszyny", methods=["GET"])
def get_maszyny():
    """Pobiera listę wszystkich maszyn."""
    try:
        # Pamiętaj, że maszyny są pobierane w RPC, ale to jest endpoint do listy filtrów
        maszyny = supabase.table("maszyny").select("*").execute()
        
        if maszyny.data:
            return jsonify(maszyny.data)
        return jsonify([])
            
    except Exception as e:
        print("Błąd GET /maszyny:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (GET /maszyny): {str(e)}"}), 500

# ----------------------------------------------------------------------
# ENDPOINTY KLIENTÓW
# ----------------------------------------------------------------------

@app.route("/klienci", methods=["GET"])
def get_klienci():
    """Pobiera listę wszystkich klientów."""
    try:
        # Pamiętaj, że klienci są pobierani w RPC, ale to jest endpoint do listy filtrów
        klienci = supabase.table("klienci").select("*").execute()
        
        if klienci.data:
            return jsonify(klienci.data)
        return jsonify([])
            
    except Exception as e:
        print("Błąd GET /klienci:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (GET /klienci): {str(e)}"}), 500

@app.route("/klienci", methods=["POST"])
def dodaj_klienta():
    """Dodaje nowego klienta."""
    try:
        data = request.get_json()
        
        # Wymagane pola
        if 'klient_id' not in data or not data['klient_id']:
            return jsonify({"error": "Pole 'id' jest wymagane."}), 400
            
        # Pamiętaj, że ID klienta to klucz główny (PRIMARY KEY), musi być unikalne.
        # Supabase zgłosi błąd, jeśli ID już istnieje.
        
        result = supabase.table("klienci").insert(data).execute()
        return jsonify({"message": f"Dodano klienta: {data['klient_id']}"}), 201

    except APIError as ae:
        # Błąd unikalności
        if 'duplicate key value violates unique constraint' in str(ae):
            return jsonify({"error": "Klient o podanym ID już istnieje."}), 409
        print("Błąd POST /klienci (APIError):", traceback.format_exc())
        return jsonify({"error": f"Błąd Supabase: {str(ae)}"}), 500
    except Exception as e:
        print("Błąd POST /klienci:", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

@app.route("/")
def index():
    """Sprawdzenie statusu API."""
    return {"status": "ok", "message": "API działa"}

# ----------------------------------------------------------------------
# ENDPOINTY NAPRAW (CRUD)
# ----------------------------------------------------------------------

# === WYMAGANA FUNKCJA FORMATUJĄCA DANE ===
# Ta funkcja musi być jedyną definicją formatującą naprawy!
def _formatuj_naprawe(naprawa):
    """
    Formatowanie danych naprawy dla front-endu.
    Oczekuje płaskich kolumn od RPC, w tym 'maszyna_marka' i 'maszyna_klasa'.
    """
    # Używamy płaskich kolumn z RPC (zdefiniowanych w SQL jako aliasy)
    marka = naprawa.get('maszyna_marka', 'Brak') 
    klasa = naprawa.get('maszyna_klasa', 'Brak')
    
    return {
        'id': naprawa.get('id'),
        'klient_id': naprawa.get('klient_id', 'Brak'), 
        'maszyna_ns': naprawa.get('maszyna_ns', 'Brak'),
        
        'marka': marka, # Wstawiamy pola relacji na tym samym poziomie
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
    """
    Pobiera naprawy, używając funkcji RPC w Supabase (get_naprawy_z_filtrami)
    do bezpiecznego i stabilnego filtrowania, w tym na relacjach.
    """
    try:
        # 1. POPRAWIONO POBIERANIE PARAMETRÓW Z QUERY STRING
        # Klucze z request.args.get() MUSZĄ być takie same jak te wysyłane przez front-end.
        # Z Twojego front-endu wysyłasz klucze z podkreśleniem (np. '_klient_id')
        klient_filter = request.args.get('_klient_id')
        ns_filter = request.args.get('_maszyna_ns')
        marka_filter = request.args.get('_marka') 
        klasa_filter = request.args.get('_klasa')
        status_filter = request.args.get('_status')
        usterka_filter = request.args.get('_opis_usterki')
        
        # 2. Definicja argumentów dla funkcji RPC (Nazwy muszą pasować do SQL!)
        params = {
            "_klient_id": klient_filter,
            "_maszyna_ns": ns_filter,
            "_marka": marka_filter,
            "_klasa": klasa_filter,
            "_status": status_filter,
            "_opis_usterki": usterka_filter
        }
        
        # Usuwamy puste wartości (None lub "")
        params_rpc = {k: v for k, v in params.items() if v}
        
        print(f"DEBUG API: Wywołanie RPC z filtrami: {params_rpc}")
        
        # 3. Wywołanie funkcji RPC
        naprawy_resp = supabase.rpc(
            'get_naprawy_z_filtrami', 
            params=params_rpc
        ).execute()

        naprawy = naprawy_resp.data

        # 4. Formatowanie i zwrócenie danych
        wynik = [_formatuj_naprawe(n) for n in naprawy]
        return jsonify(wynik)
        
    except Exception as e:
        print("BŁĄD KRYTYCZNY W /naprawy (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: Błąd wewnętrzny. {str(e)}"}), 500

@app.route("/naprawy/<int:naprawa_id>", methods=["GET"])
def get_naprawa_by_id(naprawa_id):
    """
    Pobiera pojedynczą naprawę po ID, zwracając spłaszczone dane z marką i klasą.
    Naprawia błąd 405 podczas próby edycji.
    """
    try:
        # Pobieramy naprawę i łączymy z maszyną w jednym zapytaniu Supabase,
        # co jest wydajniejsze niż łączenie danych ręcznie.
        # Używamy select z relacją ('maszyny(marka,klasa)').
        naprawa_resp = supabase.table("naprawy").select(
            "*, maszyny(marka, klasa)" 
        ).eq("id", naprawa_id).single().execute()
        
        naprawa_data = naprawa_resp.data
        
        if not naprawa_data:
            return jsonify({"error": "Naprawa nie została znaleziona"}), 404
        
        # Wyodrębnienie danych maszyny
        maszyna_dane = naprawa_data.pop("maszyny", {})
        
        # Formatowanie wyniku, aby był płaski, jak oczekuje front-end (dla edycji)
        wynik = {
            **naprawa_data, # Kopiowanie wszystkich pól z tabeli naprawy
            "marka": maszyna_dane.get("marka", "Brak"),
            "klasa": maszyna_dane.get("klasa", "Brak"),
        }
        
        return jsonify(wynik)
        
    except Exception as e:
        # Obsługa błędu gdy single() nie znajduje rekordu
        if "No rows returned from the query" in str(e) or (hasattr(e, 'code') and e.code == 'PGRST116'):
            return jsonify({"error": "Naprawa nie została znaleziona"}), 404
            
        print(f"Błąd w /naprawy/{naprawa_id} (GET):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500

@app.route("/naprawy/<int:naprawa_id>", methods=["POST"])
# ... (rest of the endpoints: dodaj_naprawe, delete_naprawa, update_naprawa, maszyny, klienci) ...

@app.route("/naprawy/<int:naprawa_id>", methods=["PUT"])
def update_naprawa(naprawa_id):
    """Aktualizuje naprawę, akceptując częściową aktualizację danych."""
    data = request.get_json()

    pola_do_aktualizacji = {}
    
    # Lista wszystkich pól do aktualizacji (kluczowych do filtrowania danych) 
    pola_naprawy = ["status", "data_zakonczenia", "opis_usterki", "opis_naprawy", 
                    "posrednik_id", "rozliczone", "klient_id", "maszyna_ns", "data_przyjecia"]

    for pole in pola_naprawy:
        if pole in data:
            pola_do_aktualizacji[pole] = data[pole]

    if not pola_do_aktualizacji:
        return jsonify({"error": "Brak danych do aktualizacji"}), 400

    try:
        # Wykonaj aktualizację tylko dla przekazanych pól
        result = supabase.table("naprawy").update(pola_do_aktualizacji).eq("id", naprawa_id).execute()

        if result.data:
            return jsonify({"message": f"Zaktualizowano naprawę o ID: {naprawa_id}"})
        else:
            return jsonify({"error": "Nie znaleziono naprawy o podanym ID lub brak zmian."}), 404
            
    except Exception as e:
        print("Błąd w update_naprawa (PUT):", traceback.format_exc())
        return jsonify({"error": f"Błąd serwera (PUT /naprawy): {str(e)}"}), 500
        
# ... (pozostały kod endpointów /maszyny i /klienci jest poprawny) ...
# Pamiętaj o usunięciu duplikatu funkcji _formatuj_naprawe z oryginalnego kodu!

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
