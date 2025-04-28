import streamlit as st

# Page configuration must be the first Streamlit command
st.set_page_config(
    page_title="Hildegard - Suggeritore di Canti",
    page_icon="🎵",
    layout="centered"
)

# Importazioni e funzioni di base
import pandas as pd
import requests
from datetime import datetime, timedelta
import os
import json

# Add thefuzz import for fuzzy matching (senza messaggi di errore visibili)
try:
    from thefuzz import process as fuzzy_process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    
# Import gspread and service_account (senza messaggi di errore visibili)
try:
    import gspread
    from google.oauth2 import service_account
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    
# Funzione per convertire la data in formato italiano
def format_date_italian(date):
    return date.strftime("%d/%m/%Y") # Format as dd/mm/yyyy

# Function to get fuzzy matches for a search term
def get_fuzzy_matches(search_term, title_list, limit=5, score_cutoff=50):
    """Get fuzzy matches for a search term from a list of titles"""
    if not FUZZY_AVAILABLE:
        # If thefuzz is not available, fall back to substring matching
        return [(title, 100) for title in title_list if search_term.lower() in title.lower()][:limit]
    
    # Use thefuzz to get matches with scores
    matches = fuzzy_process.extractBests(
        search_term, 
        title_list, 
        score_cutoff=score_cutoff,
        limit=limit
    )
    return matches

# Function to connect to Google Sheets
@st.cache_resource(ttl=3600, show_spinner=False)  # Cache for 1 hour, no spinner
def connect_to_gsheets():
    # Indica all'utente cosa sta avvenendo
    st.session_state.connection_message = "Connessione al database in corso..."
    
    try:
        # Utilizza direttamente i secrets di Streamlit
        if "gcp_service_account" in st.secrets:
            credentials = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=[
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive.file",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
            
            # Connessione a Google Sheets
            client = gspread.authorize(credentials)
            sheet_name = "hildegard_form_manual_suggestions"
            
            try:
                # Prima tenta di aprire il foglio esistente
                spreadsheet = client.open(sheet_name)
            except Exception as e:
                # Se non esiste, mostra messaggio ma non fallire silenziosamente
                st.session_state.connection_error = f"Errore: Il foglio '{sheet_name}' non è accessibile. Verificare che esista o che l'account di servizio abbia i permessi necessari."
                return "SIMULATION_MODE"
            
            # Memorizza in session state per accessi futuri più rapidi
            st.session_state.gs_client = spreadsheet
            
            try:
                # Tenta di accedere ai fogli specifici
                existing_sheet = spreadsheet.worksheet("existing_songs")
                new_sheet = spreadsheet.worksheet("new_songs")
                st.session_state.existing_songs_sheet = existing_sheet
                st.session_state.new_songs_sheet = new_sheet
            except Exception as e:
                st.session_state.connection_message = "Creazione dei fogli di lavoro in corso..."
                # Se i fogli specifici non esistono, creali
                try:
                    st.session_state.existing_songs_sheet = spreadsheet.add_worksheet(
                        title="existing_songs", 
                        rows="1000", 
                        cols="10"
                    )
                    st.session_state.new_songs_sheet = spreadsheet.add_worksheet(
                        title="new_songs", 
                        rows="1000", 
                        cols="10"
                    )
                    st.session_state.connection_message = "Fogli di lavoro creati con successo!"
                except Exception as e:
                    # Fallback al primo foglio
                    st.session_state.connection_error = f"Errore nella creazione dei fogli di lavoro: {str(e)}"
                    return "SIMULATION_MODE"
            
            return {
                "spreadsheet": spreadsheet,
                "existing_songs_sheet": st.session_state.existing_songs_sheet,
                "new_songs_sheet": st.session_state.new_songs_sheet
            }
        else:
            # Secrets non configurati
            st.session_state.connection_error = "Le credenziali di servizio non sono configurate nei secrets di Streamlit."
            return "SIMULATION_MODE"
            
    except Exception as e:
        # Errore di connessione - mostra messaggio esplicito
        st.session_state.connection_error = f"Errore di connessione: {str(e)}"
        return "SIMULATION_MODE"
        
# Function to load song data
@st.cache_data(ttl=3600, show_spinner=False)  # Cache for 1 hour, no spinner
def load_songs_data():
    try:
        # First try to load from GitHub
        try:
            csv_url = "https://raw.githubusercontent.com/dennisangemi/hildegard/refs/heads/main/data/anagrafica_canti.csv"
            df = pd.read_csv(csv_url)
            return df
        except:
            # If GitHub loading fails, try local file
            if os.path.exists("sample_canti.csv"):
                df = pd.read_csv("sample_canti.csv")
                return df
            else:
                # Return an empty dataframe with the required columns
                return pd.DataFrame(columns=["titolo", "autore", "url", "link_youtube"])
    except Exception:
        # Return an empty dataframe with the required columns
        return pd.DataFrame(columns=["titolo", "id_canti", "autore", "url", "link_youtube"])
        
# Carica dati canti in silenzio
songs_df = load_songs_data()

# Converti in liste per la selezione
existing_song_titles_list = list(songs_df["titolo"].unique()) if not songs_df.empty else []
existing_song_titles_set = set(existing_song_titles_list)

# Precarica la connessione a Google Sheets per velocizzare il form
try:
    sheets_connection = connect_to_gsheets()
except Exception:
    # Silenziosamente fallisce, riproveremo quando necessario
    pass

# Title and description
st.title("Suggeritore di Canti per Hildegard")
st.markdown("""Compila questo modulo per suggerire un canto liturgico da utilizzare su [Hildegard](https://hildegard.it/). 

Segui i passaggi e inserisci le informazioni richieste: il sistema ti aiuterà a evitare duplicati e a fornire tutti i dettagli utili.
""")

# Aggiungo informazioni su Hildegard in una sezione espandibile
with st.expander("Informazioni su Hildegard"):
    st.markdown("""**Cos'è Hildegard?** Un suggeritore automatico che aiuta a selezionare i canti più adatti per la liturgia domenicale,
    basandosi sul confronto dei testi con le letture del giorno.
    
    **Come funziona?** L'algoritmo analizza le letture della domenica e confronta il testo con una vasta raccolta di canti 
    liturgici per suggerirti quelli più pertinenti.
    
    **Come contribuire?** Attraverso questo modulo puoi suggerire canti che ritieni adatti per specifiche liturgie, contribuendo 
    così a migliorare le raccomandazioni di Hildegard.
    
    Per maggiori informazioni visita [il sito ufficiale di Hildegard](https://hildegard.it/).
    """)

# Initialize session state variables if they don't exist
if 'selected_song_title' not in st.session_state:
    st.session_state.selected_song_title = None # The final chosen title
if 'is_new_song' not in st.session_state:
    st.session_state.is_new_song = False
if 'author' not in st.session_state:
    st.session_state.author = ""
if 'text_link' not in st.session_state:
    st.session_state.text_link = ""
if 'audio_link' not in st.session_state:
    st.session_state.audio_link = ""
if 'notes' not in st.session_state:
    st.session_state.notes = ""
if 'adequacy_percentage' not in st.session_state:
    st.session_state.adequacy_percentage = 50 # Default value
if 'form_submitted' not in st.session_state:
    st.session_state.form_submitted = False
if 'submission_success' not in st.session_state:
    st.session_state.submission_success = False  # Nuovo flag per tracciare il successo dell'invio
if 'new_song_title' not in st.session_state:
    st.session_state.new_song_title = ""
# Initialize song list in session state for dropdown
if 'song_list' not in st.session_state:
    st.session_state.song_list = existing_song_titles_list
# Add a step tracker for multi-page form
if 'current_step' not in st.session_state:
    st.session_state.current_step = 1

# --- Multi-step Form Logic ---
st.header("Suggerisci un Canto")

# Progress bar to show form completion status
step_text = {
    1: "Data della liturgia", 
    2: "Cerca canto", 
    3: "Seleziona canto", 
    4: "Completa e invia"
}
st.progress((st.session_state.current_step - 1) / 3)  # Progress from 0 to 1 in 4 steps
st.write(f"**Passo {st.session_state.current_step}/4: {step_text[st.session_state.current_step]}**")

# Buttons for navigation
def go_to_next_step():
    st.session_state.current_step += 1

def go_to_prev_step():
    st.session_state.current_step -= 1

# Content for STEP 1 - Date selection
if st.session_state.current_step == 1:
    st.markdown("Seleziona la data della liturgia per cui vuoi suggerire un canto.")
    
    # Selettore calendario con formato italiano
    selected_date = st.date_input(
        "Data della liturgia",
        format="DD/MM/YYYY",
        help="Seleziona la data della liturgia per cui suggerisci il canto (formato gg/mm/aaaa)"
    )
    
    # Store date in session state
    if selected_date:
        st.session_state.selected_date = selected_date
    
    # Navigation buttons
    col1, col2 = st.columns([1, 5])
    with col2:
        next_button = st.button("Avanti →", on_click=go_to_next_step, disabled=not selected_date)

# Content for STEP 2 - Free text search for songs
elif st.session_state.current_step == 2:
    st.markdown("Inserisci il titolo del canto che vuoi suggerire.")
    
    # Initialize a separate session state variable for storing the search value
    if 'search_term_value' not in st.session_state:
        st.session_state.search_term_value = ""
    
    # Use a text input for searching/entering song title
    search_term = st.text_input(
        "Titolo del canto",
        value=st.session_state.search_term_value,  # Use our separate storage variable
        help="Inserisci il titolo del canto che vuoi suggerire",
        key="search_input"  # Changed key to avoid conflict
    )
    
    # Store search term in our separate storage variable (not directly in widget's state)
    if search_term != st.session_state.search_term_value:
        st.session_state.search_term_value = search_term
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        st.button("← Indietro", on_click=go_to_prev_step)
    with col2:
        next_button = st.button("Avanti →", on_click=go_to_next_step, disabled=not search_term)

# Content for STEP 3 - Select from dropdown or add new
elif st.session_state.current_step == 3:
    st.markdown("Seleziona un canto esistente o aggiungi un nuovo canto.")
    
    # Filter song list based on search term from step 2, using fuzzy matching
    search_term = st.session_state.search_term_value  # Use our separate storage variable
    
    if search_term:
        # Get fuzzy matches with scores (limit top 10, minimum score 50)
        fuzzy_matches = get_fuzzy_matches(search_term, st.session_state.song_list, limit=10, score_cutoff=50)
        # Extract just the song titles
        filtered_songs = [match[0] for match in fuzzy_matches]
        
    else:
        filtered_songs = []
    
    # Create display options with filtered songs + always add "Add new" option
    add_new_option = f"➕ Aggiungi \"{search_term}\" come nuovo canto"
    # Add an empty option at the beginning for "no selection"
    display_options = [""] + filtered_songs + [add_new_option]
    
    # Function to handle selection change
    def handle_song_selection():
        selected_value = st.session_state.song_selection
        
        # Handle empty selection
        if not selected_value:
            st.session_state.is_new_song = False
            st.session_state.selected_song_title = None
            return
        
        if selected_value == add_new_option:
            st.session_state.is_new_song = True
            st.session_state.selected_song_title = search_term
            st.session_state.new_song_title = search_term
        else:  # An existing song was selected
            st.session_state.is_new_song = False
            st.session_state.selected_song_title = selected_value
    
    # Display the selectbox with our filtered+add new options
    st.selectbox(
        "Seleziona un canto",
        options=display_options,
        index=0,  # No default selection 
        key="song_selection",
        on_change=handle_song_selection,
        placeholder="Seleziona un canto o aggiungi nuovo..."
    )
    
    # Additional info based on selection
    if st.session_state.selected_song_title:
        if st.session_state.is_new_song:
            st.success(f"Stai aggiungendo un nuovo canto: **{st.session_state.selected_song_title}**")
        else:
            st.info(f"Hai selezionato un canto esistente: **{st.session_state.selected_song_title}**")
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        st.button("← Indietro", on_click=go_to_prev_step)
    with col2:
        next_button = st.button("Avanti →", on_click=go_to_next_step, disabled=not st.session_state.selected_song_title)

# Content for STEP 4 - Final details and submission
elif st.session_state.current_step == 4:
    # Controllo se abbiamo già inviato con successo
    if st.session_state.submission_success:
        # Mostra solo il messaggio di conferma con dettagli del suggerimento
        st.success("✅ Grazie! Il tuo suggerimento è stato inviato con successo.")
        
        # Mostra un riepilogo del suggerimento inviato
        st.info(f"""
        **Riepilogo del suggerimento inviato:**
        - Data liturgia: {st.session_state.selected_date.strftime('%d/%m/%Y')}
        - Canto: {st.session_state.selected_song_title} ({'Nuovo' if st.session_state.is_new_song else 'Esistente'})
        """)
        
        # Pulsante per inviare un nuovo suggerimento
        if st.button("Invia un nuovo suggerimento"):
            # Reset delle variabili di sessione
            st.session_state.song_title_input = ""
            st.session_state.selected_song_title = None
            st.session_state.is_new_song = False
            st.session_state.author = ""
            st.session_state.text_link = ""
            st.session_state.audio_link = ""
            st.session_state.notes = ""
            st.session_state.adequacy_percentage = 50
            st.session_state.form_submitted = False
            st.session_state.submission_success = False
            st.session_state.current_step = 1
            st.rerun()
            
    # Altrimenti, mostra il form normalmente
    elif st.session_state.is_new_song:
        st.markdown(f"### Aggiungi dettagli per il nuovo canto: {st.session_state.selected_song_title}")
        
        # Mostra eventuali messaggi di connessione
        if 'connection_message' in st.session_state:
            st.info(st.session_state.connection_message)
            
        if 'connection_error' in st.session_state:
            st.error(st.session_state.connection_error)
            
        with st.form(key="new_song_submission_form"):
            # Fields for new song
            st.session_state.author = st.text_input(
                "Autore*",
                value=st.session_state.author,
                help="Inserisci il nome dell'autore del canto. Campo obbligatorio."
            )
            
            st.session_state.text_link = st.text_input(
                "Link al testo",
                value=st.session_state.text_link,
                help="Se disponibile, inserisci il link al testo del canto."
            )
            
            st.session_state.audio_link = st.text_input(
                "Link all'audio",
                value=st.session_state.audio_link,
                help="Se disponibile, inserisci il link a una registrazione audio o video del canto."
            )
            
            st.session_state.adequacy_percentage = st.slider(
                "Percentuale di adeguatezza*",
                min_value=0,
                max_value=100,
                value=st.session_state.adequacy_percentage,
                step=5,
                format="%d%%",
                help="Quanto pensi che questo canto sia adatto alla liturgia selezionata?"
            )
            
            # Notes field is required for new songs
            st.session_state.notes = st.text_area(
                "Motivazione / Note aggiuntive*",
                value=st.session_state.notes,
                help="Spiega brevemente perché suggerisci questo canto per la liturgia scelta. Campo obbligatorio."
            )
            
            # Display a summary before submission
            st.info(f"""
            **Riepilogo:**
            - Data liturgia: {st.session_state.selected_date.strftime('%d/%m/%Y')}
            - Canto: {st.session_state.selected_song_title} (Nuovo)
            """)
            
            # Form submission
            col1, col2 = st.columns([1, 2])
            with col1:
                back_1 = st.form_submit_button("← Indietro")
                if back_1:
                    st.session_state.go_back = True
            with col2:
                submitted = st.form_submit_button("Invia suggerimento")
                if submitted:
                    st.session_state.form_submitted = True  # IMPORTANTE - imposta il flag quando il pulsante viene premuto
            
    else:
        st.markdown(f"### Aggiungi una motivazione per: {st.session_state.selected_song_title}")
        
        # Mostra eventuali messaggi di connessione
        if 'connection_message' in st.session_state:
            st.info(st.session_state.connection_message)
            
        if 'connection_error' in st.session_state:
            st.error(st.session_state.connection_error)
            
        with st.form(key="existing_song_submission_form"):
            st.session_state.adequacy_percentage = st.slider(
                "Percentuale di adeguatezza*",
                min_value=0,
                max_value=100,
                value=st.session_state.adequacy_percentage,
                step=5,
                format="%d%%",
                help="Quanto pensi che questo canto sia adatto alla liturgia selezionata?"
            )
            
            # Notes field is optional for existing songs
            st.session_state.notes = st.text_area(
                "Motivazione / Note aggiuntive",
                value=st.session_state.notes,
                help="Spiega brevemente perché suggerisci questo canto per la liturgia scelta."
            )
            
            # Display a summary before submission
            st.info(f"""
            **Riepilogo:**
            - Data liturgia: {st.session_state.selected_date.strftime('%d/%m/%Y')}
            - Canto: {st.session_state.selected_song_title} (Esistente)
            """)
            
            # Form submission
            col1, col2 = st.columns([1, 2])
            with col1:
                back_2 = st.form_submit_button("← Indietro")
                if back_2:
                    st.session_state.go_back = True
            with col2:
                submitted = st.form_submit_button("Invia suggerimento")
                if submitted:
                    st.session_state.form_submitted = True  # IMPORTANTE - imposta il flag quando il pulsante viene premuto
    
    # Handle back button (outside the form)
    if 'go_back' in st.session_state and st.session_state.go_back:
        st.session_state.go_back = False  # Reset the flag
        go_to_prev_step()
        st.rerun()

# Visualizza i messaggi di stato della connessione
# Non mostrare più pannelli laterali con messaggi di debug
# if 'connection_message' in st.session_state and not st.session_state.submission_success:
#     st.sidebar.info(st.session_state.connection_message)
    
# if 'connection_error' in st.session_state:
#     st.sidebar.error(st.session_state.connection_error)

# Visualizza le informazioni di debug in una sezione espandibile
# if 'debug_info' in st.session_state:
#     with st.expander("Informazioni di debug"):
#         st.text(st.session_state.debug_info)

# Handle form submission logic (same as before)
if st.session_state.form_submitted:
    # Validation
    validation_error = False
    
    # Validate based on whether it's a new or existing song
    if st.session_state.is_new_song:
        # Validate required fields for new song
        if not st.session_state.author.strip():
            st.error("Per favore, inserisci l'autore del nuovo canto.")
            validation_error = True
        if not st.session_state.notes.strip():
            st.error("Per favore, inserisci una motivazione per il nuovo canto.")
            validation_error = True
    
    # Continue with existing submission logic
    if not validation_error:
        with st.spinner("Invio in corso..."):
            # Retrieve values from session state for submission
            final_song_title = st.session_state.selected_song_title
            is_new = st.session_state.is_new_song
            final_author_input = st.session_state.author.strip()
            final_text_link_input = st.session_state.text_link.strip()
            final_audio_link_input = st.session_state.audio_link.strip()
            final_notes = st.session_state.notes.strip()
            final_adequacy = st.session_state.adequacy_percentage
            
            # Initialize fields that might be blanked or fetched
            song_id = ""
            final_author_for_sheet = ""
            final_text_link_for_sheet = ""
            final_audio_link_for_sheet = ""
            tipo_suggerimento = ""

            # --- Logic to determine final values based on is_new ---
            if not is_new:
                tipo_suggerimento = "Esistente"
                try:
                    if not songs_df.empty and final_song_title in existing_song_titles_set:
                        if 'id_canti' in songs_df.columns:
                            song_info = songs_df[songs_df["titolo"] == final_song_title].iloc[0]
                            song_id = song_info.get('id_canti', "") 
                            if pd.isna(song_id):
                                song_id = ""
                except Exception:
                    song_id = ""
            else:
                tipo_suggerimento = "Nuovo"
                song_id = ""
                final_author_for_sheet = final_author_input
                final_text_link_for_sheet = final_text_link_input
                final_audio_link_for_sheet = final_audio_link_input

            # Connect to Google Sheets - nuova implementazione corretta
            try:
                # Utilizza direttamente i secrets di Streamlit invece del file creds.json
                if "gcp_service_account" in st.secrets:
                    credentials = service_account.Credentials.from_service_account_info(
                        st.secrets["gcp_service_account"], 
                        scopes=[
                            "https://spreadsheets.google.com/feeds",
                            "https://www.googleapis.com/auth/spreadsheets",
                            "https://www.googleapis.com/auth/drive.file",
                            "https://www.googleapis.com/auth/drive"
                        ]
                    )
                    
                    client = gspread.authorize(credentials)
                    spreadsheet = client.open("hildegard_form_manual_suggestions")
                    
                    # Ottieni i fogli di lavoro
                    try:
                        existing_songs_sheet = spreadsheet.worksheet("existing_songs")
                        new_songs_sheet = spreadsheet.worksheet("new_songs")
                    except gspread.exceptions.WorksheetNotFound:
                        # Crea i fogli se non esistono
                        try:
                            existing_songs_sheet = spreadsheet.add_worksheet("existing_songs", 1000, 10)
                            new_songs_sheet = spreadsheet.add_worksheet("new_songs", 1000, 10)
                        except Exception:
                            # Usa il primo foglio come fallback
                            existing_songs_sheet = spreadsheet.get_worksheet(0)
                            new_songs_sheet = spreadsheet.get_worksheet(0)
                            
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    selected_date_str = st.session_state.selected_date.strftime("%Y-%m-%d")
                    
                    # Prepare data row based on song type
                    if not is_new:
                        row_to_submit = [
                            timestamp,
                            selected_date_str,  
                            str(song_id),
                            final_song_title,
                            f"{final_adequacy}%",
                            final_notes
                        ]
                        # Invia i dati
                        existing_songs_sheet.append_row(row_to_submit)
                    else:
                        row_to_submit = [
                            timestamp,
                            selected_date_str,
                            final_song_title,
                            final_author_for_sheet,
                            final_text_link_for_sheet,
                            final_audio_link_for_sheet,
                            final_notes,
                            f"{final_adequacy}%",
                            tipo_suggerimento
                        ]
                        # Invia i dati
                        new_songs_sheet.append_row(row_to_submit)
                        
                    # Imposta il flag di successo dell'invio
                    st.session_state.submission_success = True
                    
                    # Salva i dati inviati in session_state per mostrarli nella schermata di conferma
                    st.session_state.submitted_data = {
                        "song_title": final_song_title,
                        "song_type": "Nuovo" if is_new else "Esistente",
                        "date": st.session_state.selected_date,
                        "adequacy": final_adequacy,
                        "notes": final_notes
                    }
                    if is_new:
                        st.session_state.submitted_data["author"] = final_author_input
                        st.session_state.submitted_data["text_link"] = final_text_link_input
                        st.session_state.submitted_data["audio_link"] = final_audio_link_input
                    
                    # Ricarica la pagina per mostrare la schermata di conferma
                    st.session_state.form_submitted = False
                    st.rerun()
                    
                else:
                    st.error("Le credenziali di servizio non sono configurate nei secrets di Streamlit.")
                    st.session_state.form_submitted = False
                    
            except Exception as e:
                st.error("Si è verificato un errore durante l'invio del suggerimento. Riprova tra qualche istante.")
                st.session_state.form_submitted = False

    else:
        # If validation failed, reset submission flag to allow correction
        st.session_state.form_submitted = False