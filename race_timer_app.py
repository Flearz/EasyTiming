import csv
import configparser
import datetime
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import defaultdict
import json
import os
import pathlib # Pour gérer les chemins de manière robuste
import sys # Pour sys.executable et sys.frozen

# Configuration du logging pour la console
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Déterminer le répertoire de base pour les fichiers de données (config, recovery)
if getattr(sys, 'frozen', False):
    BASE_PATH = pathlib.Path(sys.executable).resolve().parent
else:
    BASE_PATH = pathlib.Path(__file__).resolve().parent

RECOVERY_FILE = BASE_PATH / "race_recovery_state.json"
CONFIG_FILENAME = BASE_PATH / "categories.ini" 
LISTE_DEPARTS_FILENAME = BASE_PATH / "liste_departs.csv" # Fichier CSV par défaut pour les participants
RESULTS_DIR = BASE_PATH / "résultats" 


class RaceTimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chronométreur de course")
        self.geometry("800x820") 
        
        self.participants = [] 
        self.filtered_participants_for_chrono = [] 
        self.distances = {'h': {}, 'f': {}}
        self.annees_categories = {} 
        # self.tours_categories = {} # Supprimé

        self.buffer = [] 
        self.rankings = []
        self.current_category = None 
        self._running = False
        self.start_time = None 
        self.race_instance_counter = defaultdict(int)
        self.last_imported_file_path = None 

        # Map pour stocker les ID des timers de feedback pour les labels des popups
        self._feedback_clear_id_map_popup = {}


        restored_from_file = self.attempt_restore_state()
        if not restored_from_file: 
            self.load_config() 
            self._auto_load_initial_participants() 

        self.create_widgets() 
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.update_ui_after_restore_or_init() 

        if self._running and self.start_time: 
            self.update_timer()
        
        if restored_from_file and hasattr(self, 'notebook') and hasattr(self, 'timer_frame'):
            self.notebook.select(self.timer_frame)


    def normalize_category_name_for_display_and_key(self, cat_name):
        if isinstance(cat_name, str):
            return cat_name.strip().capitalize() 
        return "" 

    def show_feedback(self, label_widget, message, color, duration=3000, parent_widget=None):
        _after_method = parent_widget.after if parent_widget else self.after
        _after_cancel_method = parent_widget.after_cancel if parent_widget else self.after_cancel

        feedback_map_attr = '_feedback_clear_id_map_main'
        if parent_widget and parent_widget != self:
            feedback_map_attr = '_feedback_clear_id_map_popup'
        
        if not hasattr(self, feedback_map_attr):
            setattr(self, feedback_map_attr, {})
        
        feedback_map = getattr(self, feedback_map_attr)

        if label_widget in feedback_map and feedback_map[label_widget] is not None:
            try:
                _after_cancel_method(feedback_map[label_widget])
            except (tk.TclError, KeyError): # Timer ID might be invalid or widget destroyed
                pass
        
        label_widget.config(text=message, foreground=color)
        
        try:
            clear_id = _after_method(duration, lambda lw=label_widget: lw.config(text=""))
            feedback_map[label_widget] = clear_id
        except tk.TclError: # Widget might be destroyed before after call
            pass


    def update_ui_after_restore_or_init(self):
        self.filter_participant_treeview() 
        self._populate_all_category_comboboxes() 

        if hasattr(self, 'cat_combo'): 
            if self.current_category and self.current_category in self.cat_combo['values']: 
                self.cat_combo.set(self.current_category) 
            elif self.cat_combo['values']:
                try:
                    self.cat_combo.current(0) # Select first if available
                    if not self.current_category: # If current_category was None, set it to the first one
                         self.current_category = self.cat_combo.get() 
                except tk.TclError: self.cat_combo.set('') # Handle empty list
            else: # No categories available
                self.cat_combo.set('')
                self.current_category = None 
            
            self._update_chrono_tab_for_category()


        if hasattr(self, 'buf_list'): 
            self.buf_list.delete(0, tk.END)
            for i, time_obj in enumerate(self.buffer):
                total_seconds = int(time_obj.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
                self.buf_list.insert(tk.END, f"{i + 1}. {time_str}")
        
        if hasattr(self, 'lbl_time'):
            if self.start_time and self._running:
                 pass # Timer is updated by update_timer()
            elif self.start_time and not self._running: # Race was started but is now stopped
                elapsed = datetime.datetime.now() - self.start_time 
                total_seconds = int(elapsed.total_seconds()) 
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                self.lbl_time.config(text=f"{hours:02}:{minutes:02}:{seconds:02}")
            else: # Not started or reset
                self.lbl_time.config(text="00:00:00")

        if self.current_category and self.participants:
             self.filtered_participants_for_chrono = [p for p in self.participants if p['cat'] == self.current_category]
        else:
             self.filtered_participants_for_chrono = []


    def save_state(self):
        state = {
            'start_time_iso': self.start_time.isoformat() if self.start_time else None,
            'buffer_seconds': [td.total_seconds() for td in self.buffer],
            'rankings': [{'bib': r['bib'], 
                          'time_seconds': r['time'].total_seconds() if r['time'] else None, 
                          'abandon': r['abandon']} for r in self.rankings],
            'current_category': self.current_category, 
            '_running': self._running,
            'race_instance_counter': dict(self.race_instance_counter),
            'last_imported_file_path': self.last_imported_file_path
        }
        try:
            with RECOVERY_FILE.open('w') as f: 
                json.dump(state, f, indent=4)
            logging.info(f"État de la course sauvegardé dans {RECOVERY_FILE}")
        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde de l'état : {e}")

    def _load_participants_from_path_quiet(self, file_path_str, is_auto_load=False): 
        if not file_path_str :
            if not is_auto_load: logging.warning(f"Chemin du fichier participants non fourni.")
            return False
        
        file_path = pathlib.Path(file_path_str) 

        if not file_path.exists():
            if not is_auto_load: 
                logging.warning(f"Chemin du fichier participants non trouvé: {file_path}")
                messagebox.showerror("Erreur Import", f"Fichier non trouvé:\n{file_path}")
            return False
        
        current_participants_before_load = []
        possible_encodings = ('utf-8-sig', 'utf-8', 'cp1252', 'mbcs', 'latin-1')
        # Prioritize semicolon as per user file example and write operations
        common_delimiters = [';', ',']
        loaded_successfully = False
        
        for encoding in possible_encodings:
            if loaded_successfully: break
            sniffed_delimiter = None
            try: 
                with file_path.open('r', encoding=encoding, newline='') as fs:
                    sample = fs.read(2048) 
                    if sample: 
                        dialect = csv.Sniffer().sniff(sample, delimiters=''.join(common_delimiters))
                        sniffed_delimiter = dialect.delimiter
            except Exception: 
                pass 

            delimiters_to_try = [sniffed_delimiter] if sniffed_delimiter else common_delimiters
            
            for delimiter in delimiters_to_try:
                try:
                    temp_participants_this_attempt = []
                    with file_path.open(newline='', encoding=encoding) as fc:
                        reader = csv.DictReader(fc, delimiter=delimiter)
                        if not reader.fieldnames: continue
                        original_fieldnames = reader.fieldnames
                        norm_to_orig_map = { (fn.strip().lower() if fn else ''): fn for fn in original_fieldnames} 
                        
                        bib_key = next((k for k in ['n° dossard', 'n. dossard', 'dossard', 'n','no dossard', 'no. dossard'] if k in norm_to_orig_map), None)
                        nom_key = next((k for k in ['nom'] if k in norm_to_orig_map), None)
                        prenom_key = next((k for k in ['prénom', 'prenom'] if k in norm_to_orig_map), None)
                        sexe_key = next((k for k in ['sexe', 'sex'] if k in norm_to_orig_map), None)
                        cat_key = next((k for k in ['catégorie', 'categorie', 'cat'] if k in norm_to_orig_map), None)

                        bib_h_orig = norm_to_orig_map.get(bib_key) if bib_key else None
                        nom_h_orig = norm_to_orig_map.get(nom_key) if nom_key else None
                        prenom_h_orig = norm_to_orig_map.get(prenom_key) if prenom_key else None
                        sexe_h_orig = norm_to_orig_map.get(sexe_key) if sexe_key else None
                        cat_h_orig = norm_to_orig_map.get(cat_key) if cat_key else None

                        if not all([bib_h_orig, nom_h_orig, prenom_h_orig, sexe_h_orig, cat_h_orig]): 
                            if not is_auto_load: logging.warning(f"Headers manquants pour import ({file_path}) avec enc {encoding} delim '{delimiter}'. Fields: {original_fieldnames}")
                            continue
                        
                        for row_idx, row in enumerate(reader):
                            bib_s = (row.get(bib_h_orig) or '').strip()
                            if not bib_s: 
                                if all(not (row.get(h) or '').strip() for h in [nom_h_orig, prenom_h_orig, sexe_h_orig, cat_h_orig]):
                                    continue 
                            if not bib_s.isdigit(): 
                                if not is_auto_load: logging.warning(f"Dossard non numérique ignoré (ligne {row_idx+2}): '{bib_s}'")
                                continue
                            nom_val = (row.get(nom_h_orig) or '').strip()
                            prenom_val = (row.get(prenom_h_orig) or '').strip()
                            sexe_val = (row.get(sexe_h_orig) or '').strip().lower() 
                            cat_val = self.normalize_category_name_for_display_and_key(row.get(cat_h_orig)) 
                            if not (nom_val and prenom_val and sexe_val and cat_val): 
                                if not is_auto_load: logging.warning(f"Données manquantes pour dossard {bib_s} (ligne {row_idx+2}), ligne ignorée.")
                                continue 
                            temp_participants_this_attempt.append({'bib': int(bib_s), 'nom': nom_val, 'prenom': prenom_val, 'sexe': sexe_val, 'cat': cat_val})
                    
                    if temp_participants_this_attempt or not current_participants_before_load: 
                        current_participants_before_load = temp_participants_this_attempt 
                        loaded_successfully = True; break 
                except Exception as e_inner_load: 
                    if not is_auto_load: logging.debug(f"Erreur interne chargement participants (enc:{encoding}, delim:'{delimiter}'): {e_inner_load}")
            if loaded_successfully: break
        
        if loaded_successfully:
            self.participants = current_participants_before_load 
            self.last_imported_file_path = str(file_path) 
            logging.info(f"{len(self.participants)} participants chargés depuis {file_path}")
            return True
        else:
            if not is_auto_load: 
                logging.error(f"Échec du chargement des participants depuis {file_path}")
                messagebox.showerror("Erreur Import", f"Impossible de lire le fichier {file_path.name}.\nVérifiez le format, le délimiteur (virgule ou point-virgule attendu) et l'encodage.")
            return False


    def _auto_load_initial_participants(self):
        logging.info(f"Tentative de chargement automatique de: {LISTE_DEPARTS_FILENAME}")
        if LISTE_DEPARTS_FILENAME.exists():
            if self._load_participants_from_path_quiet(str(LISTE_DEPARTS_FILENAME), is_auto_load=True):
                logging.info(f"Chargement automatique de {LISTE_DEPARTS_FILENAME} réussi.")
            else:
                logging.warning(f"Échec du chargement automatique de {LISTE_DEPARTS_FILENAME} (fichier existe mais contenu invalide?).")
        else:
            logging.info(f"{LISTE_DEPARTS_FILENAME} non trouvé pour chargement automatique.")


    def attempt_restore_state(self):
        if RECOVERY_FILE.exists(): 
            try:
                if not messagebox.askyesno("Restauration de Session", "État précédent trouvé. Restaurer ?"):
                    try: RECOVERY_FILE.unlink(missing_ok=True); logging.info(f"{RECOVERY_FILE} supprimé (refus restauration).")
                    except Exception: pass
                    return False 
                with RECOVERY_FILE.open('r') as f: state = json.load(f) 
                self.start_time = datetime.datetime.fromisoformat(state['start_time_iso']) if state['start_time_iso'] else None
                self.buffer = [datetime.timedelta(seconds=s) for s in state['buffer_seconds']]
                self.rankings = [{'bib': r['bib'], 'time': datetime.timedelta(seconds=r['time_seconds']) if r['time_seconds'] is not None else None, 'abandon': r['abandon']} for r in state['rankings']]
                self.current_category = self.normalize_category_name_for_display_and_key(state.get('current_category')) 
                self._running = state.get('_running', False)
                self.race_instance_counter = defaultdict(int, state.get('race_instance_counter', {}))
                self.last_imported_file_path = state.get('last_imported_file_path')
                
                self.load_config() 
                
                if self.last_imported_file_path:
                    if not self._load_participants_from_path_quiet(self.last_imported_file_path, is_auto_load=True): 
                         messagebox.showwarning("Info Restauration", "Impossible de recharger la dernière liste de participants. Veuillez l'importer manuellement.")
                         self.participants = [] 
                elif LISTE_DEPARTS_FILENAME.exists(): 
                    logging.info("Aucun chemin de fichier sauvegardé, tentative de chargement de liste_departs.csv pour la restauration.")
                    self._load_participants_from_path_quiet(str(LISTE_DEPARTS_FILENAME), is_auto_load=True)
                else:
                     messagebox.showinfo("Info Restauration", "Aucun fichier de participants à recharger automatiquement. Importez manuellement si nécessaire.")

                logging.info(f"État restauré depuis {RECOVERY_FILE}"); messagebox.showinfo("Restauration Réussie", "État précédent restauré.")
                try: RECOVERY_FILE.unlink(missing_ok=True) 
                except Exception as e: logging.error(f"Err suppression {RECOVERY_FILE}: {e}")
                return True 
            except Exception as e:
                logging.error(f"Err restauration: {e}"); messagebox.showerror("Erreur Restauration", f"Err restauration: {e}")
                try: RECOVERY_FILE.unlink(missing_ok=True)
                except OSError: pass 
                return False 
        return False 

    def on_closing(self):
        if self._running or self.buffer or self.rankings or self.start_time: self.save_state()
        elif RECOVERY_FILE.exists(): 
             try: RECOVERY_FILE.unlink(missing_ok=True); logging.info(f"Nettoyage {RECOVERY_FILE} (fermeture).")
             except Exception as e: logging.error(f"Err nettoyage {RECOVERY_FILE}: {e}")
        self.destroy()

    def load_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str 
        self.distances = {'h': {}, 'f': {}} 
        self.annees_categories = {}
        # self.tours_categories = {} # Supprimé
        
        logging.info(f"Tentative de chargement du fichier de configuration depuis: {CONFIG_FILENAME.resolve()}")
        if getattr(sys, 'frozen', False): 
            logging.info(f"Application is frozen. Base path for config/recovery: {BASE_PATH}")
        else:
            logging.info(f"Application is not frozen. Base path for config/recovery (script dir): {BASE_PATH}")


        if not CONFIG_FILENAME.exists():
            logging.error(f"Fichier de configuration '{CONFIG_FILENAME}' non trouvé à l'emplacement résolu.")
            messagebox.showerror("Erreur Config", f"Fichier '{CONFIG_FILENAME.name}' introuvable à l'emplacement attendu:\n{CONFIG_FILENAME.parent}")
            return

        try:
            read_files = config.read(CONFIG_FILENAME, encoding='utf-8')
            if not read_files: 
                config = configparser.ConfigParser() 
                config.optionxform = str 
                read_files = config.read(CONFIG_FILENAME) 

            if not read_files:
                logging.error(f"Impossible de lire le fichier de configuration '{CONFIG_FILENAME}'.")
                messagebox.showerror("Erreur Config", f"Impossible de lire '{CONFIG_FILENAME.name}'.")
                return
            
            for section_name in config.sections():
                normalized_cat_name = self.normalize_category_name_for_display_and_key(section_name)
                if not normalized_cat_name: continue

                if config.has_option(section_name, 'distance_h'):
                    self.distances['h'][normalized_cat_name] = float(config.get(section_name, 'distance_h'))
                if config.has_option(section_name, 'distance_f'):
                    self.distances['f'][normalized_cat_name] = float(config.get(section_name, 'distance_f'))
                if config.has_option(section_name, 'annees'): 
                    self.annees_categories[normalized_cat_name] = config.get(section_name, 'annees')
                
                # Logic for nb_tours_h and nb_tours_f removed

            logging.info(f"Config loaded successfully from '{CONFIG_FILENAME}'. Distances: {self.distances}, Annees: {self.annees_categories}")
        except Exception as e:
            logging.exception(f"Erreur chargement {CONFIG_FILENAME}"); messagebox.showerror("Erreur config", f"Erreur {CONFIG_FILENAME.name}: {e}")
            self.distances = {'h': {}, 'f': {}}
            self.annees_categories = {}
            # self.tours_categories = {} # Supprimé

    def create_widgets(self):
        main_app_frame = ttk.Frame(self)
        main_app_frame.pack(expand=True, fill='both')
        self.notebook = ttk.Notebook(main_app_frame)
        
        self.inscriptions_frame = ttk.Frame(self.notebook) 
        self.liste_participants_frame = ttk.Frame(self.notebook) 
        self.timer_frame  = ttk.Frame(self.notebook)
        self.export_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.inscriptions_frame, text="Inscriptions") 
        self.notebook.add(self.liste_participants_frame, text="Liste Participants") 
        self.notebook.add(self.timer_frame,  text="Chrono")
        self.notebook.add(self.export_frame, text="Export")
        
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        self.setup_inscriptions_tab() 
        self.setup_liste_participants_tab() 
        self.setup_timer_tab()
        self.setup_export_tab()
        
        current_year = datetime.datetime.now().year
        copyright_label = ttk.Label(main_app_frame, text=f"© Rihen {current_year}", anchor='center')
        copyright_label.pack(side='bottom', fill='x', pady=5)

    def _populate_all_category_comboboxes(self):
        all_config_cats = set()
        all_config_cats.update(self.distances['h'].keys())
        all_config_cats.update(self.distances['f'].keys())
        all_config_cats.update(self.annees_categories.keys())
        # all_config_cats.update(self.tours_categories.keys()) # Supprimé
        defined_categories = sorted(list(all_config_cats))

        if hasattr(self, 'insc_categorie_combo'):
            current_insc_cat = self.insc_categorie_combo.get()
            self.insc_categorie_combo['values'] = defined_categories
            if current_insc_cat and current_insc_cat in defined_categories:
                self.insc_categorie_combo.set(current_insc_cat)
            elif defined_categories:
                 try: self.insc_categorie_combo.current(0)
                 except tk.TclError: self.insc_categorie_combo.set('')
            else:
                self.insc_categorie_combo.set('')
        
        if hasattr(self, 'cat_combo'):
            chrono_cats_display = []
            if self.participants: 
                chrono_cats_display = sorted(list(set(p['cat'] for p in self.participants if p['cat'])))
            elif defined_categories: 
                chrono_cats_display = defined_categories
            
            current_chrono_cat = self.cat_combo.get()
            self.cat_combo['values'] = chrono_cats_display
            
            if self.current_category and self.current_category in chrono_cats_display:
                self.cat_combo.set(self.current_category)
            elif current_chrono_cat and current_chrono_cat in chrono_cats_display: 
                self.cat_combo.set(current_chrono_cat)
            elif chrono_cats_display:
                 try: self.cat_combo.current(0)
                 except tk.TclError: self.cat_combo.set('')
            else:
                self.cat_combo.set('')


    def setup_inscriptions_tab(self):
        form_frame = ttk.LabelFrame(self.inscriptions_frame, text="Ajouter un Participant au CSV", padding=(10,10))
        form_frame.pack(padx=10, pady=10, fill='x', expand=False) 
        ttk.Label(form_frame, text="N° Dossard:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.insc_dossard_entry = ttk.Entry(form_frame, width=10)
        self.insc_dossard_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(form_frame, text="Nom:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.insc_nom_entry = ttk.Entry(form_frame, width=30)
        self.insc_nom_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(form_frame, text="Prénom:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.insc_prenom_entry = ttk.Entry(form_frame, width=30)
        self.insc_prenom_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(form_frame, text="Sexe (h/f):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.insc_sexe_var = tk.StringVar()
        self.insc_sexe_combo = ttk.Combobox(form_frame, textvariable=self.insc_sexe_var, values=['h', 'f'], width=8, state="readonly")
        self.insc_sexe_combo.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.insc_sexe_combo.current(0) 

        cat_insc_frame = ttk.Frame(form_frame)
        cat_insc_frame.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.insc_categorie_combo = ttk.Combobox(cat_insc_frame, width=27, state="readonly") 
        self.insc_categorie_combo.pack(side="left", expand=True, fill="x")
        manage_cat_button = ttk.Button(cat_insc_frame, text="Gérer", command=self._open_manage_categories_popup, width=8)
        manage_cat_button.pack(side="left", padx=(5,0))
        ttk.Label(form_frame, text="Catégorie:").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        
        form_frame.columnconfigure(1, weight=1) 
        self.insc_feedback_label = ttk.Label(self.inscriptions_frame, text="")
        self.insc_feedback_label.pack(pady=5)
        ttk.Button(self.inscriptions_frame, text="Ajouter Participant au CSV", command=self.add_participant_to_csv).pack(pady=10)
        info_label = ttk.Label(self.inscriptions_frame, 
                               text="Note: Après ajout au CSV, la liste des participants est automatiquement rechargée.",
                               wraplength=750, justify='center')
        info_label.pack(pady=10, padx=10)
        self._populate_all_category_comboboxes() 


    def _open_manage_categories_popup(self):
        popup = tk.Toplevel(self)
        popup.title("Gérer les Catégories et Informations")
        popup.geometry("700x400") 
        popup.transient(self)
        popup.grab_set()

        tree_frame = ttk.Frame(popup, padding=(10,10,10,5)) 
        tree_frame.pack(expand=True, fill='both')
        
        cols = ('Catégorie', 'Années', 'Dist. H (m)', 'Dist. F (m)')
        self.cat_popup_tree = ttk.Treeview(tree_frame, columns=cols, show='headings', height=7)
        
        self.cat_popup_tree.heading('Catégorie', text='Catégorie')
        self.cat_popup_tree.column('Catégorie', width=120, anchor='w')
        self.cat_popup_tree.heading('Années', text='Années') 
        self.cat_popup_tree.column('Années', width=200, anchor='w') 
        self.cat_popup_tree.heading('Dist. H (m)', text='Dist. H (m)')
        self.cat_popup_tree.column('Dist. H (m)', width=100, anchor='w')
        self.cat_popup_tree.heading('Dist. F (m)', text='Dist. F (m)')
        self.cat_popup_tree.column('Dist. F (m)', width=100, anchor='w')
        
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cat_popup_tree.yview)
        self.cat_popup_tree.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.pack(side='right', fill='y')
        self.cat_popup_tree.pack(expand=True, fill='both')

        edit_frame = ttk.LabelFrame(popup, text="Ajouter / Modifier Catégorie", padding=10)
        edit_frame.pack(fill='x', padx=10, pady=(5,10)) 

        ttk.Label(edit_frame, text="Nom Catégorie:").grid(row=0, column=0, padx=5, pady=3, sticky='w')
        cat_name_entry_var = tk.StringVar()
        cat_name_entry = ttk.Entry(edit_frame, textvariable=cat_name_entry_var, width=30)
        cat_name_entry.grid(row=0, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(edit_frame, text="Années:").grid(row=0, column=2, padx=5, pady=3, sticky='w') 
        annees_entry_var = tk.StringVar() 
        annees_entry = ttk.Entry(edit_frame, textvariable=annees_entry_var, width=30)
        annees_entry.grid(row=0, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(edit_frame, text="Dist. Hommes (m):").grid(row=1, column=0, padx=5, pady=3, sticky='w')
        dist_h_entry_var = tk.StringVar()
        dist_h_entry = ttk.Entry(edit_frame, textvariable=dist_h_entry_var, width=15)
        dist_h_entry.grid(row=1, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(edit_frame, text="Dist. Femmes (m):").grid(row=1, column=2, padx=5, pady=3, sticky='w') 
        dist_f_entry_var = tk.StringVar()
        dist_f_entry = ttk.Entry(edit_frame, textvariable=dist_f_entry_var, width=15)
        dist_f_entry.grid(row=1, column=3, padx=5, pady=3, sticky='ew')
        
        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(3, weight=1)

        feedback_cat_popup_label = ttk.Label(edit_frame, text="")
        feedback_cat_popup_label.grid(row=2, column=0, columnspan=4, pady=5, sticky='ew') 

        def populate_cat_popup_tree_detailed():
            for i in self.cat_popup_tree.get_children():
                self.cat_popup_tree.delete(i)
            
            all_cats = sorted(list(set(
                list(self.distances['h'].keys()) + 
                list(self.distances['f'].keys()) +
                list(self.annees_categories.keys())
            )))

            for cat_norm in all_cats:
                dist_h = self.distances['h'].get(cat_norm, "")
                dist_f = self.distances['f'].get(cat_norm, "")
                annees_info = self.annees_categories.get(cat_norm, "") 
                
                dist_h_str = f"{int(dist_h)}" if isinstance(dist_h, (int, float)) else ""
                dist_f_str = f"{int(dist_f)}" if isinstance(dist_f, (int, float)) else ""
                
                self.cat_popup_tree.insert('', tk.END, values=(cat_norm, annees_info, dist_h_str, dist_f_str))


        def on_tree_select_popup(event):
            selected_item = self.cat_popup_tree.focus()
            if selected_item:
                values = self.cat_popup_tree.item(selected_item, 'values')
                if len(values) == 4: 
                    cat_name_entry_var.set(values[0])    
                    annees_entry_var.set(values[1])      
                    dist_h_entry_var.set(values[2] if values[2] != "N/A" else "") 
                    dist_f_entry_var.set(values[3] if values[3] != "N/A" else "") 
                else: # Should not happen with corrected populate function
                    cat_name_entry_var.set('')
                    annees_entry_var.set('')
                    dist_h_entry_var.set('')
                    dist_f_entry_var.set('')

        self.cat_popup_tree.bind('<<TreeviewSelect>>', on_tree_select_popup)
        populate_cat_popup_tree_detailed()

        def save_category_action_popup():
            cat_name_raw = cat_name_entry_var.get()
            dist_h_str = dist_h_entry_var.get()
            dist_f_str = dist_f_entry_var.get()
            annees_str = annees_entry_var.get() 
            
            cat_name_normalized = self.normalize_category_name_for_display_and_key(cat_name_raw)

            if not cat_name_normalized:
                self.show_feedback(feedback_cat_popup_label, "Nom de catégorie requis.", "red", parent_widget=popup); return
            
            try:
                dist_h = float(dist_h_str) if dist_h_str else None
                dist_f = float(dist_f_str) if dist_f_str else None
            except ValueError:
                self.show_feedback(feedback_cat_popup_label, "Distances doivent être numériques.", "red", parent_widget=popup); return

            config = configparser.ConfigParser()
            config.optionxform = str 
            if CONFIG_FILENAME.exists():
                config.read(CONFIG_FILENAME, encoding='utf-8')

            section_name = cat_name_normalized 
            if not config.has_section(section_name):
                config.add_section(section_name)
            
            if dist_h is not None: config.set(section_name, 'distance_h', str(dist_h))
            else: config.remove_option(section_name, 'distance_h', fallback=None)
            
            if dist_f is not None: config.set(section_name, 'distance_f', str(dist_f))
            else: config.remove_option(section_name, 'distance_f', fallback=None)
            
            if annees_str: config.set(section_name, 'annees', annees_str) 
            else: config.remove_option(section_name, 'annees', fallback=None)
            
            # Ensure old tour-related keys are removed
            config.remove_option(section_name, 'nb_tours', fallback=None)
            config.remove_option(section_name, 'nb_tours_h', fallback=None)
            config.remove_option(section_name, 'nb_tours_f', fallback=None)
            config.remove_option(section_name, 'age_info', fallback=None) # Also remove old 'age_info' key

            try:
                with CONFIG_FILENAME.open('w', encoding='utf-8') as configfile:
                    config.write(configfile)
                self.show_feedback(feedback_cat_popup_label, f"Catégorie '{cat_name_raw}' enregistrée!", "green", parent_widget=popup)
                logging.info(f"Catégorie '{cat_name_raw}' (normalisée: {cat_name_normalized}) sauvegardée dans {CONFIG_FILENAME}")
                
                self.load_config() 
                self._populate_all_category_comboboxes() 
                self._update_chrono_tab_for_category() 
                populate_cat_popup_tree_detailed() 

                cat_name_entry_var.set(''); dist_h_entry_var.set(''); dist_f_entry_var.set('')
                annees_entry_var.set(''); 
                self.cat_popup_tree.selection_remove(self.cat_popup_tree.focus()) 

            except Exception as e:
                self.show_feedback(feedback_cat_popup_label, f"Erreur sauvegarde: {e}", "red", parent_widget=popup)
                logging.error(f"Erreur sauvegarde {CONFIG_FILENAME}: {e}")

        button_frame_popup = ttk.Frame(popup) 
        button_frame_popup.pack(pady=10)
        ttk.Button(button_frame_popup, text="Enregistrer/Modifier", command=save_category_action_popup).pack(side='left', padx=5)
        ttk.Button(button_frame_popup, text="Fermer", command=popup.destroy).pack(side='left', padx=5)
        
        cat_name_entry.focus()


    def add_participant_to_csv(self):
        dossard_str = self.insc_dossard_entry.get().strip()
        nom = self.insc_nom_entry.get().strip()
        prenom = self.insc_prenom_entry.get().strip()
        sexe = self.insc_sexe_var.get().strip().lower() 
        categorie_selected = self.insc_categorie_combo.get() 

        if not dossard_str or not nom or not prenom or not sexe or not categorie_selected:
            self.show_feedback(self.insc_feedback_label, "Tous les champs sont requis.", "red"); return
        if not dossard_str.isdigit():
            self.show_feedback(self.insc_feedback_label, "Le N° Dossard doit être un nombre.", "red"); return
        
        dossard_to_add = int(dossard_str)

        # Vérifier si le dossard existe déjà dans liste_departs.csv
        if LISTE_DEPARTS_FILENAME.exists():
            try:
                with LISTE_DEPARTS_FILENAME.open('r', newline='', encoding='utf-8-sig') as f_read:
                    reader = csv.reader(f_read, delimiter=',') 
                    header = next(reader, None) 
                    if header: # Check if header exists
                        try:
                            dossard_col_index = header.index('N° Dossard')
                        except ValueError: # If 'N° Dossard' is not in header, assume it's the first column
                            dossard_col_index = 0 
                            logging.warning("En-tête 'N° Dossard' non trouvé dans liste_departs.csv, utilisation de la première colonne pour la vérification des dossards.")
                    else: # No header, assume first column
                        dossard_col_index = 0
                        # Rewind file to read from beginning if there was no header
                        f_read.seek(0)
                        reader = csv.reader(f_read, delimiter=',') # Re-initialize reader

                    for row in reader:
                        if row and len(row) > dossard_col_index and row[dossard_col_index].strip() == dossard_str:
                            messagebox.showwarning("Dossard Existant", f"Le dossard N°{dossard_str} est déjà utilisé. Veuillez en choisir un autre.")
                            self.insc_dossard_entry.focus()
                            return
            except Exception as e:
                logging.error(f"Erreur lors de la vérification du dossard dans {LISTE_DEPARTS_FILENAME}: {e}")
                # Consider not blocking the add if file is unreadable for check, but log it.

        participant_data = [dossard_str, nom, prenom, sexe, categorie_selected] 
        
        file_exists_for_write = LISTE_DEPARTS_FILENAME.exists()
        try:
            with LISTE_DEPARTS_FILENAME.open('a', newline='', encoding='utf-8-sig') as f_append:
                writer = csv.writer(f_append, delimiter=',') 
                if not file_exists_for_write or LISTE_DEPARTS_FILENAME.stat().st_size == 0: 
                    writer.writerow(['N° Dossard', 'Nom', 'Prénom', 'Sexe', 'Catégorie'])
                writer.writerow(participant_data)
            
            self.show_feedback(self.insc_feedback_label, f"Participant {dossard_str} ajouté à {LISTE_DEPARTS_FILENAME.name}!", "green")
            self.insc_dossard_entry.delete(0, tk.END); self.insc_nom_entry.delete(0, tk.END)
            self.insc_prenom_entry.delete(0, tk.END); self.insc_sexe_combo.current(0)
            if self.insc_categorie_combo['values']: self.insc_categorie_combo.current(0)
            else: self.insc_categorie_combo.set('')
            logging.info(f"Participant {dossard_str} ajouté à {LISTE_DEPARTS_FILENAME}")
            
            self._reload_liste_departs_csv(show_success_message=False) 

        except Exception as e:
            self.show_feedback(self.insc_feedback_label, f"Erreur écriture CSV: {e}", "red")
            logging.error(f"Erreur écriture {LISTE_DEPARTS_FILENAME}: {e}")

    def _reload_liste_departs_csv(self, show_success_message=True):
        """Recharge liste_departs.csv et met à jour l'UI."""
        logging.info(f"Rechargement de {LISTE_DEPARTS_FILENAME}...")
        
        # Reset participant-related data before loading, but keep race state if active
        # This is tricky because reloading participants can invalidate current_category if it's not in the new list
        # For now, a full reload implies resetting most things related to participant lists.
        
        # Store current category to try and reselect it after load
        previous_current_category = self.current_category

        self.participants.clear() 
        # Don't clear cat_combo values here, _populate_all_category_comboboxes will do it based on new data.
        # self.current_category = None # Will be reset by _populate or selection
        self.filtered_participants_for_chrono = []
        # _reset_race_state should ideally not be called here if we want to preserve a running race
        # but changing the participant list fundamentally affects a running race.
        # The confirmation in _reload_liste_departs_csv_manual_trigger handles this for manual reloads.
        # For auto-reloads after add/delete, the race state should ideally be preserved if possible,
        # or at least the user warned more explicitly if a race is active.
        # For now, an auto-reload effectively resets the participant-dependent parts of the race.

        if self._load_participants_from_path_quiet(str(LISTE_DEPARTS_FILENAME), is_auto_load=not show_success_message):
            if show_success_message:
                messagebox.showinfo("Rechargement Réussi", f"{len(self.participants)} participants chargés depuis\n{LISTE_DEPARTS_FILENAME.name}")
        else:
            if show_success_message: 
                messagebox.showerror("Erreur Rechargement", f"Impossible de recharger {LISTE_DEPARTS_FILENAME.name}. Vérifiez le fichier.")
        
        # Try to reselect the previously current category if it still exists
        self.current_category = previous_current_category 
        self.update_ui_after_restore_or_init()


    def setup_liste_participants_tab(self): 
        top_frame = ttk.Frame(self.liste_participants_frame)
        top_frame.pack(pady=5, padx=10, fill='x')

        action_button_frame = ttk.Frame(top_frame)
        action_button_frame.pack(side='top', fill='x', pady=(0,5))
        ttk.Button(action_button_frame, text="Recharger Liste (liste_departs.csv)", command=self._reload_liste_departs_csv_manual_trigger).pack(side='left', padx=(0,10))
        ttk.Button(action_button_frame, text="Supprimer Participant(s) Sélectionné(s)", command=self._delete_selected_participants).pack(side='left')

        search_frame = ttk.Frame(top_frame)
        search_frame.pack(side='top', fill='x', pady=(5,0)) 
        ttk.Label(search_frame, text="Rechercher participant:").pack(side='left', padx=(0,5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side='left', expand=True, fill='x')
        self.search_var.trace_add("write", self.filter_participant_treeview) 
        
        tree_container = ttk.Frame(self.liste_participants_frame)
        tree_container.pack(expand=True, fill='both', padx=10, pady=5)

        self.tree = ttk.Treeview(tree_container, columns=('Dossard', 'Nom', 'Prénom', 'Sexe', 'Catégorie'), show='headings', selectmode="extended") 
        self.tree.heading('Dossard', text='Dossard') 
        self.tree.column('Dossard', width=80, anchor='w', minwidth=60)
        self.tree.heading('Nom', text='Nom')
        self.tree.column('Nom', width=150, anchor='w', minwidth=100)
        self.tree.heading('Prénom', text='Prénom')
        self.tree.column('Prénom', width=150, anchor='w', minwidth=100)
        self.tree.heading('Sexe', text='Sexe')
        self.tree.column('Sexe', width=50, anchor='center', minwidth=40)
        self.tree.heading('Catégorie', text='Catégorie')
        self.tree.column('Catégorie', width=100, anchor='w', minwidth=80)
        
        tree_scrollbar_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar_y.set)
        tree_scrollbar_y.pack(side='right', fill='y')
        self.tree.pack(side='left', expand=True, fill='both')

        ttk.Button(self.liste_participants_frame, text="Suivant -> Chrono", command=lambda: self.notebook.select(self.timer_frame)).pack(pady=10)

    def _reload_liste_departs_csv_manual_trigger(self):
        """Triggered by the 'Recharger Liste' button."""
        if self._running or self.rankings or self.buffer:
            if not messagebox.askyesno("Attention", "Données de course en cours. Recharger effacera ces données de course. Continuer ?"): 
                return
        
        # Reset application state related to current race if any
        self.participants.clear()
        if hasattr(self, 'cat_combo'): self.cat_combo['values'] = []; self.cat_combo.set('')
        self.current_category = None; self.filtered_participants_for_chrono = []
        # For a manual reload, we should reset the race state more thoroughly
        self._reset_race_state(clear_instance_counter=True) # Reset instance counter as well

        if self._load_participants_from_path_quiet(str(LISTE_DEPARTS_FILENAME), is_auto_load=False):
            messagebox.showinfo("Rechargement Réussi", f"{len(self.participants)} participants chargés depuis\n{LISTE_DEPARTS_FILENAME.name}")
        # Error message is handled by _load_participants_from_path_quiet if not is_auto_load
        self.update_ui_after_restore_or_init()


    def _delete_selected_participants(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("Aucune Sélection", "Veuillez sélectionner un ou plusieurs participants à supprimer.")
            return

        confirm_msg = "Êtes-vous sûr de vouloir supprimer le(s) participant(s) sélectionné(s) de la liste et du fichier CSV ?"
        if len(selected_items) > 1:
            confirm_msg = f"Êtes-vous sûr de vouloir supprimer les {len(selected_items)} participants sélectionnés de la liste et du fichier CSV ?"
        
        if not messagebox.askyesno("Confirmation Suppression", confirm_msg + "\nCette action est irréversible."):
            return

        bibs_to_delete = set()
        for item_id in selected_items:
            item_values = self.tree.item(item_id, 'values')
            if item_values:
                try:
                    bibs_to_delete.add(int(item_values[0])) 
                except ValueError:
                    logging.warning(f"Valeur de dossard non entière ignorée lors de la suppression : {item_values[0]}")


        if not bibs_to_delete: return

        initial_count = len(self.participants)
        self.participants = [p for p in self.participants if p['bib'] not in bibs_to_delete]
        deleted_count = initial_count - len(self.participants)

        if deleted_count > 0:
            try:
                with LISTE_DEPARTS_FILENAME.open('w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(['N° Dossard', 'Nom', 'Prénom', 'Sexe', 'Catégorie']) 
                    for p_data in self.participants:
                        writer.writerow([p_data['bib'], p_data['nom'], p_data['prenom'], p_data['sexe'], p_data['cat']])
                logging.info(f"{deleted_count} participant(s) supprimé(s) et {LISTE_DEPARTS_FILENAME.name} mis à jour.")
                messagebox.showinfo("Suppression Réussie", f"{deleted_count} participant(s) supprimé(s).\nLe fichier {LISTE_DEPARTS_FILENAME.name} a été mis à jour.")
            except Exception as e:
                logging.error(f"Erreur lors de la réécriture de {LISTE_DEPARTS_FILENAME}: {e}")
                messagebox.showerror("Erreur Fichier", f"Erreur lors de la mise à jour du fichier des départs:\n{e}")
                # Attempt to reload to reflect in-memory state if file write failed
                self._reload_liste_departs_csv(show_success_message=False) 
        else:
            messagebox.showinfo("Info", "Aucun participant correspondant n'a été trouvé dans la liste en mémoire pour suppression.")

        self.update_ui_after_restore_or_init() 


    def filter_participant_treeview(self, *args):
        search_term = self.search_var.get().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for p in self.participants: 
            bib_str = str(p['bib'])
            if (search_term in bib_str or
                search_term in p['nom'].lower() or
                search_term in p['prenom'].lower() or
                (p['cat'] and search_term in p['cat'].lower()) ): 
                self.tree.insert('', tk.END, values=(p['bib'], p['nom'], p['prenom'], p['sexe'], p['cat']))

    def import_participants_manual(self): 
        self._reload_liste_departs_csv_manual_trigger()


    def setup_timer_tab(self):
        main_timer_frame = ttk.Frame(self.timer_frame)
        main_timer_frame.pack(expand=True, fill='both', padx=10, pady=10)
        
        top_section_frame = ttk.Frame(main_timer_frame)
        top_section_frame.pack(pady=5, fill='x')

        cat_dist_frame = ttk.Frame(top_section_frame)
        cat_dist_frame.pack(side='left', expand=True, fill='x')
        ttk.Label(cat_dist_frame, text="Catégorie :").grid(row=0, column=0, padx=(0,5), pady=2, sticky='w')
        self.cat_combo = ttk.Combobox(cat_dist_frame, state='readonly', width=25)
        self.cat_combo.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        self.cat_combo.bind("<<ComboboxSelected>>", self.on_category_selected)
        self.lbl_dist_h = ttk.Label(cat_dist_frame, text="Distance Hommes: N/A")
        self.lbl_dist_h.grid(row=1, column=0, columnspan=2, padx=5, pady=2, sticky='w')
        self.lbl_dist_f = ttk.Label(cat_dist_frame, text="Distance Femmes: N/A")
        self.lbl_dist_f.grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky='w')
        cat_dist_frame.columnconfigure(1, weight=1) 

        show_list_button = ttk.Button(top_section_frame, text="Afficher Liste de Course (Cat. Actuelle)", command=self._show_current_race_list_popup)
        show_list_button.pack(side='right', padx=10, pady=5)


        timer_controls_frame = ttk.Frame(main_timer_frame)
        timer_controls_frame.pack(pady=5, fill='x')
        self.lbl_time = ttk.Label(timer_controls_frame, text="00:00:00", font=('TkDefaultFont', 24))
        self.lbl_time.pack(side='left', padx=10, expand=True) 
        ttk.Button(timer_controls_frame, text="Start", command=self.start_race, width=10).pack(side='left', padx=5)
        ttk.Button(timer_controls_frame, text="Fin Course", command=self.finish_race, width=10).pack(side='left', padx=5) 
        ttk.Button(timer_controls_frame, text="Réinit.", command=self.reset_race_with_confirmation, width=10).pack(side='left', padx=5)
        
        arrival_frame = ttk.Frame(main_timer_frame)
        arrival_frame.pack(pady=5, fill='x')
        ttk.Button(arrival_frame, text="Nouvelle arrivée", command=self.new_arrival).pack(side='left', padx=5)
        ttk.Label(arrival_frame, text="Dossard:").pack(side='left', padx=(10,0))
        self.entry_bib = ttk.Entry(arrival_frame, width=8)
        self.entry_bib.pack(side='left', padx=5); self.entry_bib.bind("<Return>", lambda event: self.assign_arrival()) 
        ttk.Button(arrival_frame, text="Valider Dossard", command=self.assign_arrival).pack(side='left', padx=5)
        ttk.Button(arrival_frame, text="Marquer Abandon", command=lambda: self.assign_arrival(mark_as_abandon=True)).pack(side='left', padx=5)
        self.assign_feedback_label = ttk.Label(arrival_frame, text="", width=40) 
        self.assign_feedback_label.pack(side='left', padx=5, fill='x', expand=True)
        
        buffer_list_frame = ttk.Frame(main_timer_frame)
        buffer_list_frame.pack(pady=5, fill='both', expand=True)
        
        buf_list_sub_frame = ttk.Frame(buffer_list_frame) 
        buf_list_sub_frame.pack(fill='both', expand=True)

        ttk.Label(buffer_list_frame, text="Arrivées en attente (Buffer):").pack(anchor='w') 
        
        self.buf_list = tk.Listbox(buf_list_sub_frame, height=6) 
        self.buf_list.pack(side='left', fill='both', expand=True)
        buf_scrollbar = ttk.Scrollbar(buf_list_sub_frame, orient="vertical", command=self.buf_list.yview)
        self.buf_list.config(yscrollcommand=buf_scrollbar.set)
        buf_scrollbar.pack(side='right', fill='y')
        
        ttk.Button(buffer_list_frame, text="Supprimer Arrivée Sélectionnée", command=self.delete_selected_buffer_time).pack(pady=5, anchor='w', side='bottom')
        
        manual_entry_frame = ttk.LabelFrame(main_timer_frame, text="Ajout Manuel de Résultat")
        manual_entry_frame.pack(pady=10, fill='x', padx=5)
        ttk.Label(manual_entry_frame, text="Dossard:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.manual_bib_entry = ttk.Entry(manual_entry_frame, width=8); self.manual_bib_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(manual_entry_frame, text="Temps (HH:MM:SS):").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.manual_time_entry = ttk.Entry(manual_entry_frame, width=10); self.manual_time_entry.grid(row=0, column=3, padx=5, pady=5, sticky='ew')
        self.manual_abandon_var = tk.BooleanVar()
        ttk.Checkbutton(manual_entry_frame, text="Abandon", variable=self.manual_abandon_var).grid(row=0, column=4, padx=5, pady=5)
        ttk.Button(manual_entry_frame, text="Ajouter Manuel", command=self.add_manual_result).grid(row=0, column=5, padx=5, pady=5)
        self.manual_feedback_label = ttk.Label(manual_entry_frame, text="", width=30) 
        self.manual_feedback_label.grid(row=1, column=0, columnspan=6, sticky='ew', padx=5)
        manual_entry_frame.columnconfigure(1, weight=1); manual_entry_frame.columnconfigure(3, weight=1)

    def _show_current_race_list_popup(self):
        if not self.current_category:
            messagebox.showinfo("Info", "Aucune catégorie sélectionnée pour afficher la liste de course.")
            return
        if not self.filtered_participants_for_chrono:
            messagebox.showinfo("Info", f"Aucun participant pour la catégorie '{self.current_category}'.")
            return

        popup = tk.Toplevel(self)
        popup.title(f"Liste de Course - Catégorie: {self.current_category}")
        popup.geometry("600x400")
        popup.transient(self) 
        popup.grab_set() 

        search_frame_popup = ttk.Frame(popup)
        search_frame_popup.pack(pady=5, padx=10, fill='x')
        ttk.Label(search_frame_popup, text="Rechercher:").pack(side='left', padx=(0,5))
        popup_search_var = tk.StringVar()
        popup_search_entry = ttk.Entry(search_frame_popup, textvariable=popup_search_var, width=30)
        popup_search_entry.pack(side='left', expand=True, fill='x')
        
        popup_tree_frame = ttk.Frame(popup)
        popup_tree_frame.pack(expand=True, fill='both', padx=10, pady=5)

        popup_tree = ttk.Treeview(popup_tree_frame, columns=('Bib', 'Nom', 'Prénom', 'Sexe'), show='headings')
        for col in popup_tree['columns']:
            popup_tree.heading(col, text=col)
            popup_tree.column(col, width=120, anchor='w')
        
        popup_tree_scrollbar = ttk.Scrollbar(popup_tree_frame, orient="vertical", command=popup_tree.yview)
        popup_tree.configure(yscrollcommand=popup_tree_scrollbar.set)
        
        popup_tree.pack(side='left', expand=True, fill='both')
        popup_tree_scrollbar.pack(side='right', fill='y')


        sorted_participants_for_popup = sorted(self.filtered_participants_for_chrono, key=lambda p: p['nom'])

        def populate_popup_tree(filter_term=""):
            for i in popup_tree.get_children():
                popup_tree.delete(i)
            for p in sorted_participants_for_popup:
                bib_str = str(p['bib'])
                if (not filter_term or 
                    filter_term in bib_str or
                    filter_term in p['nom'].lower() or
                    filter_term in p['prenom'].lower()):
                    popup_tree.insert('', tk.END, values=(p['bib'], p['nom'], p['prenom'], p['sexe']))
        
        popup_search_var.trace_add("write", lambda *args: populate_popup_tree(popup_search_var.get().lower()))
        populate_popup_tree() 

        ttk.Button(popup, text="Fermer", command=popup.destroy).pack(pady=10)
        popup_search_entry.focus()


    def setup_export_tab(self):
        ttk.Button(self.export_frame, text="Exporter résultats", command=self.export_results).pack(pady=20)

    def _update_chrono_tab_for_category(self):
        if self.current_category: 
            dist_h = self.distances['h'].get(self.current_category, "N/A") 
            dist_f = self.distances['f'].get(self.current_category, "N/A") 
            dist_h_str = f"{int(dist_h)}m" if isinstance(dist_h, (int, float)) else "N/A"
            dist_f_str = f"{int(dist_f)}m" if isinstance(dist_f, (int, float)) else "N/A"
            if hasattr(self, 'lbl_dist_h'): self.lbl_dist_h.config(text=f"Distance Hommes: {dist_h_str}")
            if hasattr(self, 'lbl_dist_f'): self.lbl_dist_f.config(text=f"Distance Femmes: {dist_f_str}")
            self.filtered_participants_for_chrono = [p for p in self.participants if p['cat'] == self.current_category]
        else:
            if hasattr(self, 'lbl_dist_h'): self.lbl_dist_h.config(text="Distance Hommes: N/A")
            if hasattr(self, 'lbl_dist_f'): self.lbl_dist_f.config(text="Distance Femmes: N/A")
            self.filtered_participants_for_chrono = []
        logging.info(f"Chrono tab updated for category: {self.current_category}. Filtered for chrono: {len(self.filtered_participants_for_chrono)}")

    def on_category_selected(self, event=None): 
        new_category_display = self.cat_combo.get()
        new_category_normalized = self.normalize_category_name_for_display_and_key(new_category_display)

        if not new_category_normalized: 
            if self.current_category and (self._running or self.rankings or self.buffer):
                if not messagebox.askyesno("Attention", f"Désélection catégorie '{self.current_category}' avec données. Effacer ?"):
                    if self.current_category: self.cat_combo.set(self.current_category) 
                    else: self.cat_combo.set('')
                    return
            self.current_category = None
            self._reset_race_state() 
            self._update_chrono_tab_for_category() 
            return

        if new_category_normalized != self.current_category: 
            if self._running or self.rankings or self.buffer: 
                if not messagebox.askyesno("Changement Catégorie", f"Données pour '{self.current_category}'. Changer effacera. Continuer ?"):
                    if self.current_category: self.cat_combo.set(self.current_category) 
                    else: self.cat_combo.set('')
                    return
            self.current_category = new_category_normalized
            self._reset_race_state(clear_instance_counter=False) # Ne pas reset le compteur ici
            self._update_chrono_tab_for_category()

    def start_race(self):
        if not self.current_category: self.show_feedback(self.assign_feedback_label, "Sélectionnez une catégorie", "red"); return
        if not self.filtered_participants_for_chrono and self.participants : messagebox.showwarning("Attention", f"Aucun participant pour '{self.current_category}'.") 
        if self._running: self.show_feedback(self.assign_feedback_label, "Course déjà en cours", "orange"); return
        if self.rankings: 
            if not messagebox.askyesno("Confirmation", f"Résultats existent pour '{self.current_category}'. Relancer effacera. Continuer ?"): return
            self._reset_race_state(clear_instance_counter=True) # Full reset here
        self.start_time = datetime.datetime.now(); self._running = True
        self.update_timer(); logging.info(f"Course démarrée: {self.current_category} à {self.start_time}")
        self.show_feedback(self.assign_feedback_label, f"Course '{self.current_category}' démarrée!", "green")

    def update_timer(self):
        if self._running and self.start_time:
            elapsed = datetime.datetime.now() - self.start_time; total_s = int(elapsed.total_seconds())
            h,rem=divmod(total_s,3600); m,s=divmod(rem,60)
            self.lbl_time.config(text=f"{h:02}:{m:02}:{s:02}"); self.after(1000, self.update_timer) 

    def finish_race(self):
        if not self.start_time: self.show_feedback(self.assign_feedback_label, "Course non démarrée.", "red"); return
        if not self._running: self.show_feedback(self.assign_feedback_label, "Course déjà terminée/réinit.", "orange"); return
        self._running = False; logging.info(f"Course terminée: {self.current_category}")
        self.show_feedback(self.assign_feedback_label, f"Course '{self.current_category}' terminée.", "green")
        self.save_state() 
        if self.rankings and self.current_category:
            try: self.export_results()
            except Exception as e: logging.error(f"Export auto échec: {e}"); messagebox.showerror("Erreur Export Auto", f"Erreur export auto:\n{e}\nExportez manuellement.")

    def _reset_race_state(self, clear_instance_counter=True): 
        self._running = False
        if hasattr(self, 'lbl_time'): self.lbl_time.config(text="00:00:00")
        self.start_time = None; self.buffer.clear()
        if hasattr(self, 'buf_list'): self.buf_list.delete(0, tk.END)
        self.rankings.clear()
        if clear_instance_counter: 
            if self.current_category: # Only clear counter for the *current* category if one is set
                self.race_instance_counter[self.current_category] = 0 
            else: # Or clear all if no specific category context for reset
                self.race_instance_counter.clear()
        if self.current_category: logging.info(f"Données de session réinitialisées pour: {self.current_category}")
        # self.save_state() # Save state might be too aggressive here, depends on context

    def reset_race_with_confirmation(self):
        if not self.current_category: self.show_feedback(self.assign_feedback_label, "Aucune catégorie à réinit.", "red"); return
        if self.rankings or self.buffer or self._running or self.start_time:
            if messagebox.askyesno("Confirmation Réinitialisation", f"Réinitialiser course pour '{self.current_category}'? Données non exportées perdues."):
                self._reset_race_state(clear_instance_counter=True); 
                self.show_feedback(self.assign_feedback_label, f"Course '{self.current_category}' réinitialisée.", "green")
                self.save_state() # Save after a confirmed reset
            else: logging.info("Réinitialisation annulée.")
        else: 
            self._reset_race_state(clear_instance_counter=True)
            self.show_feedback(self.assign_feedback_label, "Aucune donnée active à réinit.", "orange")
            self.save_state() # Save even if no data, to clear recovery file

    def new_arrival(self):
        if not self._running or not self.start_time: self.show_feedback(self.assign_feedback_label, "Course non démarrée/terminée.", "red"); return
        arr_time_obj = datetime.datetime.now() - self.start_time; self.buffer.append(arr_time_obj)
        total_s = int(arr_time_obj.total_seconds()); h,r=divmod(total_s,3600); m,s=divmod(r,60)
        self.buf_list.insert(tk.END, f"{self.buf_list.size() + 1}. {h:02}:{m:02}:{s:02}")
        self.buf_list.see(tk.END); logging.debug(f"Nvelle arrivée buffer: {h:02}:{m:02}:{s:02}"); self.save_state() 

    def delete_selected_buffer_time(self):
        sel_indices = self.buf_list.curselection()
        if not sel_indices: self.show_feedback(self.assign_feedback_label, "Aucune arrivée sélectionnée.", "red"); return
        for index in sorted(sel_indices, reverse=True):
            try: del self.buffer[index]; self.buf_list.delete(index)
            except IndexError: logging.error(f"Erreur index suppression buffer: {index}")
        items_text = self.buf_list.get(0, tk.END); self.buf_list.delete(0, tk.END)
        for i, item_full_text in enumerate(items_text):
            try: time_part = item_full_text.split('. ', 1)[1]; self.buf_list.insert(tk.END, f"{i + 1}. {time_part}")
            except IndexError: self.buf_list.insert(tk.END, item_full_text) 
        self.save_state(); self.show_feedback(self.assign_feedback_label, "Arrivée(s) buffer supprimée(s).", "green")

    def assign_arrival(self, mark_as_abandon=False):
        bib_txt = self.entry_bib.get().strip()
        if not bib_txt.isdigit(): self.show_feedback(self.assign_feedback_label, "Dossard invalide.", "red"); return
        bib = int(bib_txt)
        if not any(p['bib'] == bib for p in self.filtered_participants_for_chrono): 
            self.show_feedback(self.assign_feedback_label, f"Dossard {bib} non trouvé.", "red"); return
        if any(r['bib'] == bib for r in self.rankings):
            self.show_feedback(self.assign_feedback_label, f"Dossard {bib} déjà classé.", "orange"); self.entry_bib.delete(0,tk.END); return

        if mark_as_abandon:
            self.rankings.append({'bib': bib, 'time': None, 'abandon': True})
            self.show_feedback(self.assign_feedback_label, f"Dossard {bib} abandonné.", "green")
        else: 
            if not self.buffer: self.show_feedback(self.assign_feedback_label, "Buffer vide.", "red"); return
            time_obj = self.buffer.pop(0); self.buf_list.delete(0)    
            items = self.buf_list.get(0, tk.END); self.buf_list.delete(0, tk.END) 
            for i, item_text in enumerate(items): 
                try: self.buf_list.insert(tk.END, f"{i+1}. {item_text.split('. ',1)[1]}")
                except IndexError: self.buf_list.insert(tk.END, item_text) 
            self.rankings.append({'bib': bib, 'time': time_obj, 'abandon': False})
            time_str = str(time_obj).split('.')[0]
            self.show_feedback(self.assign_feedback_label, f"Dossard {bib}: {time_str}", "green")
        self.entry_bib.delete(0, tk.END); self.save_state()

    def add_manual_result(self):
        bib_txt = self.manual_bib_entry.get().strip()
        time_str = self.manual_time_entry.get().strip()
        is_abandon = self.manual_abandon_var.get()
        if not bib_txt.isdigit(): self.show_feedback(self.manual_feedback_label, "Dossard manuel invalide.", "red"); return
        bib = int(bib_txt)
        if not self.current_category: self.show_feedback(self.manual_feedback_label, "Aucune catégorie.", "red"); return
        if not any(p['bib'] == bib for p in self.filtered_participants_for_chrono): 
            self.show_feedback(self.manual_feedback_label, f"Dossard {bib} non trouvé.", "red"); return
        if any(r['bib'] == bib for r in self.rankings): 
            self.show_feedback(self.manual_feedback_label, f"Dossard {bib} déjà classé.", "orange"); return
        final_time_obj = None
        if not is_abandon:
            try:
                h, m, s = map(int, time_str.split(':')); final_time_obj = datetime.timedelta(hours=h, minutes=m, seconds=s)
            except ValueError: self.show_feedback(self.manual_feedback_label, "Format temps HH:MM:SS.", "red"); return
        self.rankings.append({'bib': bib, 'time': final_time_obj, 'abandon': is_abandon})
        msg = f"Dossard {bib} abandon" if is_abandon else f"Dossard {bib} temps {time_str}"
        self.show_feedback(self.manual_feedback_label, msg + " ajouté.", "green")
        self.manual_bib_entry.delete(0, tk.END); self.manual_time_entry.delete(0, tk.END); self.manual_abandon_var.set(False)
        self.save_state()

    def export_results(self):
        if not self.current_category: messagebox.showerror("Erreur", "Aucune catégorie pour export."); return
        if not self.rankings: messagebox.showinfo("Info", f"Aucun résultat pour '{self.current_category}'."); return
        
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        normalized_cat_for_lookup = self.current_category 
        
        file_path = None
        while True: 
            if not file_path: 
                current_run_num = self.race_instance_counter[normalized_cat_for_lookup] + 1
                suffix = f"_course_{current_run_num}" if current_run_num > 1 else ""
                cat_name_for_file = normalized_cat_for_lookup.replace(' ', '_').replace('/', '-') 
                default_filename = f"resultats_{cat_name_for_file}{suffix}.csv"
                
                file_path = filedialog.asksaveasfilename(
                    initialdir=str(RESULTS_DIR), 
                    defaultextension='.csv', 
                    initialfile=default_filename, 
                    filetypes=[('CSV (point-virgule)', '*.csv'), ('Tous', '*.*')]
                )
            if not file_path: logging.info("Export annulé."); return 
            try:
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f: 
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(["Résultats Catégorie:", self.current_category, "", "", "", ""]) 
                    
                    dist_h_val = self.distances['h'].get(normalized_cat_for_lookup, "N/A")
                    dist_f_val = self.distances['f'].get(normalized_cat_for_lookup, "N/A")
                    annees_val = self.annees_categories.get(normalized_cat_for_lookup, "N/A") 

                    dist_h_str = f"{int(dist_h_val)}m" if isinstance(dist_h_val, (int, float)) else "N/A"
                    dist_f_str = f"{int(dist_f_val)}m" if isinstance(dist_f_val, (int, float)) else "N/A"
                    
                    writer.writerow([f"Distance Hommes ({self.current_category}):", dist_h_str, 
                                     f"Distance Femmes ({self.current_category}):", dist_f_str, "", ""])
                    writer.writerow([f"Années:", annees_val, "", "", "", ""]) 
                    writer.writerow([]) 

                    writer.writerow(['Classement Scratch Général (valides)', "", "", "", "", ""])
                    writer.writerow(['Pos.', 'Dossard', 'Nom', 'Prénom', 'Sexe', 'Temps'])
                    valid_ranks = sorted([r for r in self.rankings if not r['abandon'] and r['time'] is not None], key=lambda r: r['time'])
                    if not valid_ranks: 
                        writer.writerow(["", "(Aucun classement scratch à afficher)", "", "", "", ""])
                    for pos, r_data in enumerate(valid_ranks, 1):
                        p_details = next((p for p in self.participants if p['bib'] == r_data['bib']), None) 
                        time_s = str(r_data['time']).split('.')[0] if r_data['time'] else "Abd."
                        if p_details: writer.writerow([pos, p_details['bib'], p_details['nom'], p_details['prenom'], p_details['sexe'].upper(), time_s])
                        else: writer.writerow([pos, r_data['bib'], "N/A", "N/A", "N/A", time_s])
                    
                    category_abandons_all = [r for r in self.rankings if r['abandon']]

                    groups = defaultdict(list)
                    for r_data in valid_ranks: 
                        p_details = next((p for p in self.participants if p['bib'] == r_data['bib']), None) 
                        if p_details: groups[p_details['sexe']].append((r_data, p_details))
                    
                    for sex_key in ['h', 'f']: 
                        writer.writerow([]) 
                        sex_name = "Hommes" if sex_key == 'h' else "Femmes" if sex_key == 'f' else f"Sexe {sex_key.upper()}"
                        writer.writerow([f"Classement Catégorie {self.current_category} - {sex_name}", "", "", "", "", ""])
                        writer.writerow(['Pos.', 'Dossard', 'Nom', 'Prénom', 'Temps', '']) 
                        
                        sex_ranks_tuples = groups.get(sex_key, []) 
                        sorted_sex_group = sorted(sex_ranks_tuples, key=lambda item: item[0]['time'])
                        
                        if not sorted_sex_group:
                             writer.writerow(["", "(Aucun classé)", "", "", "", ""])
                        for pos_sex, (r_data, p_details) in enumerate(sorted_sex_group, 1):
                            time_s = str(r_data['time']).split('.')[0] if r_data['time'] else "Abd."
                            writer.writerow([pos_sex, p_details['bib'], p_details['nom'], p_details['prenom'], time_s, ''])
                        
                        sex_specific_abandons = [r for r in category_abandons_all if next((p['sexe'] for p in self.participants if p['bib'] == r['bib']), None) == sex_key]
                        writer.writerow(["Abandons " + sex_name, "", "", "", "", ""]) 
                        if sex_specific_abandons:
                            writer.writerow(['Dossard', 'Nom', 'Prénom', '', '', '']) 
                            for r_data_abandon in sex_specific_abandons:
                                p_details_abandon = next((p for p in self.participants if p['bib'] == r_data_abandon['bib']), None)
                                if p_details_abandon: writer.writerow([p_details_abandon['bib'], p_details_abandon['nom'], p_details_abandon['prenom'], '', '', ''])
                                else: writer.writerow([r_data_abandon['bib'], "N/A", "N/A", '', '', ''])
                        else:
                            writer.writerow(["", "(Aucun abandon)", "", "", "", ""])
                
                logging.info(f"Résultats exportés: {file_path}")
                messagebox.showinfo("Succès", f"Résultats exportés vers:\n{file_path}")
                self.race_instance_counter[normalized_cat_for_lookup] += 1 
                self.save_state(); break 
            except (IOError, PermissionError) as e_io:
                logging.error(f"Erreur écriture fichier {file_path}: {e_io}")
                if not messagebox.askretrycancel("Erreur d'écriture", f"Impossible d'écrire fichier (ouvert/protégé):\n{file_path}\n\n{e_io}\n\nRéessayer ?"):
                    logging.info("Export abandonné après erreur écriture."); return
                file_path = None 
            except Exception as e_exp:
                logging.exception("Erreur export résultats."); messagebox.showerror("Erreur Export", f"Erreur export: {e_exp}"); return

if __name__ == '__main__':
    app = RaceTimerApp()  
    app.mainloop()
