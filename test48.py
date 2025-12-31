import re
import json
import os
import glob
import tkinter as tk
from tkinter import filedialog
import sys

# --- CONFIGURATION FIXE ---
START_PERSON = "Claude"
IMG_HOMME = "homme.png"
IMG_FEMME = "femme.png"

# --- CONFIGURATION GOOGLE FORM ---
LINK_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSdS_779CnVozTmjY_Cyg4C0LPf2QiNnQ6jbwsHqEWL8YbjkrA/viewform"
BASE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdS_779CnVozTmjY_Cyg4C0LPf2QiNnQ6jbwsHqEWL8YbjkrA/viewform"
ENTRY_ID_FIELD = "1781229215"

# --- 0. SÉLECTION AUTOMATIQUE DU DOSSIER ---
def select_working_folder():
    root = tk.Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Sélectionnez le dossier du projet")
    if not folder_path: sys.exit()
    
    ged_files = glob.glob(os.path.join(folder_path, "*.ged"))
    if not ged_files:
        print("ERREUR : Pas de fichier .ged trouvé !"); sys.exit()

    photos_path = os.path.join(folder_path, "photos")
    if not os.path.exists(photos_path):
        os.makedirs(photos_path)
        print("Dossier 'photos' créé.")

    return ged_files[0], photos_path, os.path.join(folder_path, "index.html")

GEDCOM_FILE, PHOTOS_FOLDER, OUTPUT_FILE = select_working_folder()

# --- 1. FONCTIONS UTILITAIRES ---
def format_date_fr(gedcom_date):
    if not gedcom_date: return ""
    gedcom_date = gedcom_date.upper().strip()
    months = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
        "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
        "JANV": "01", "FEVR": "02", "AVR": "04", "MAI": "05", "JUIN": "06", 
        "JUIL": "07", "AOUT": "08", "SEPT": "09", "DEC": "12"
    }
    
    m_full = re.match(r"^(\d{1,2})\s+([A-Z]{3,4})\s+(\d{4})", gedcom_date)
    if m_full:
        day, month, year = m_full.groups()
        return f"{int(day):02d}/{months.get(month,'00')}/{year}"
    
    m_my = re.match(r"^([A-Z]{3,4})\s+(\d{4})", gedcom_date)
    if m_my:
        month, year = m_my.groups()
        return f"??/{months.get(month,'??')}/{year}"
        
    m_y = re.search(r"(\d{4})", gedcom_date)
    if m_y: return m_y.group(1)
    
    return gedcom_date

def get_sort_value(date_str):
    if not date_str: return 99999999
    if re.match(r"^\d{4}$", date_str): return int(date_str) * 10000
    parts = date_str.split('/')
    if len(parts) == 3:
        try: return (int(parts[2]) * 10000) + (int(parts[1]) * 100) + int(parts[0])
        except: pass
    return 99999999

def format_name_upper(raw_name):
    parts = raw_name.split('/')
    if len(parts) >= 2:
        return f"{parts[0].strip()} {parts[1].strip().upper()}"
    return raw_name.upper()

# --- 2. GESTION DES PHOTOS ET NOTES ---
def scan_media_for_individual(ind_id):
    main_photo = None
    gallery = []
    user_notes = [] 
    if not os.path.exists(PHOTOS_FOLDER): return None, [], []

    for filename in os.listdir(PHOTOS_FOLDER):
        name_part = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()

        if name_part == ind_id or name_part.startswith(ind_id + "_"):
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                if name_part == ind_id: main_photo = filename
                else: gallery.append(filename)
            elif ext == '.txt':
                try:
                    with open(os.path.join(PHOTOS_FOLDER, filename), 'r', encoding='utf-8') as f:
                        user_notes.append(f.read())
                except: pass 
    return main_photo, gallery, user_notes

# --- 3. PARSING GEDCOM ---
def parse_gedcom(file_path):
    individuals = {}
    families = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f: lines = f.readlines()
    except:
        with open(file_path, 'r', encoding='latin-1') as f: lines = f.readlines()

    current_id = None
    curr_obj = {}
    last_tag_lvl1 = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        parts = line.split(' ', 2)
        level, tag = parts[0], parts[1]
        val = parts[2] if len(parts) > 2 else ""

        if level == '0' and val in ['INDI', 'FAM']:
            if current_id:
                if 'children' in curr_obj: families[current_id] = curr_obj
                else: individuals[current_id] = curr_obj
            current_id = tag.replace('@', '') 
            curr_obj = {'id': current_id, 'type': val, 'name': '', 'birth': '', 'birth_place': '', 'death': '', 'death_place': '', 'sex': 'U', 'fams': [], 'details': []}
            if val == 'FAM': curr_obj.update({'husb': None, 'wife': None, 'children': [], 'marr': '', 'marr_place': ''})
            continue
        
        if curr_obj.get('type') == 'INDI':
            if tag == 'NAME': curr_obj['name'] = format_name_upper(val)
            elif tag == 'SEX': curr_obj['sex'] = val
            elif tag == 'FAMS': curr_obj['fams'].append(val.replace('@', ''))
            elif tag == 'FAMC': curr_obj['famc'] = val.replace('@', '')
            
            if tag in ['BIRT', 'DEAT', 'OCCU', 'NOTE', 'RESI', 'BURI']: 
                last_tag_lvl1 = tag
                if tag not in ['BIRT', 'DEAT']: 
                    curr_obj['details'].append({'tag': tag, 'value': val, 'date': '', 'place': ''})

            if level == '2':
                if tag == 'DATE':
                    d = format_date_fr(val)
                    if last_tag_lvl1 == 'BIRT': curr_obj['birth'] = d
                    elif last_tag_lvl1 == 'DEAT': curr_obj['death'] = d
                    elif curr_obj['details']: curr_obj['details'][-1]['date'] = d
                elif tag == 'PLAC':
                    if last_tag_lvl1 == 'BIRT': curr_obj['birth_place'] = val
                    elif last_tag_lvl1 == 'DEAT': curr_obj['death_place'] = val
                    elif curr_obj['details']: curr_obj['details'][-1]['place'] = val

        elif curr_obj.get('type') == 'FAM':
            if tag == 'HUSB': curr_obj['husb'] = val.replace('@', '')
            elif tag == 'WIFE': curr_obj['wife'] = val.replace('@', '')
            elif tag == 'CHIL': curr_obj['children'].append(val.replace('@', ''))
            if tag == 'MARR': last_tag_lvl1 = 'MARR'
            if level == '2':
                if tag == 'DATE':
                    d = format_date_fr(val)
                    curr_obj['marr'] = d
                elif tag == 'PLAC':
                    curr_obj['marr_place'] = val

    if current_id:
        if 'children' in curr_obj: families[current_id] = curr_obj
        else: individuals[current_id] = curr_obj

    print("Association des médias...")
    for iid, ind in individuals.items():
        main, gal, notes = scan_media_for_individual(iid)
        ind['main_photo'] = main 
        ind['gallery'] = gal     
        for n in notes:
            ind['details'].append({'tag': 'USER_NOTE', 'value': n, 'date': '', 'place': ''})

    for f in families.values():
        f['children'].sort(key=lambda c: get_sort_value(individuals.get(c, {}).get('birth', '')))
    return individuals, families

# --- 4. HTML / JS ---

def generate_html(individuals, families, start_id, img_h, img_f):
    json_db = json.dumps({"individuals": individuals, "families": families})
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Arbre de la Cousinade</title>
    <script src="https://unpkg.com/@panzoom/panzoom@4.5.1/dist/panzoom.min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background-color: #e0e0e0; font-family: 'Segoe UI', sans-serif; overflow: hidden; height: 100vh; width: 100vw; user-select: none; }}
        #controls {{ position: fixed; top: 20px; left: 20px; z-index: 100; background: white; padding: 8px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); display: flex; flex-direction: column; gap: 8px; width: auto; }}
        select {{ padding: 6px; border-radius: 4px; border: 1px solid #ccc; width: 220px; font-size:14px; font-weight:bold; }}
        .btns-row {{ display: flex; gap: 5px; }}
        button {{ padding: 6px 10px; cursor: pointer; flex-grow: 1; border: 1px solid #ccc; background: #f9f9f9; border-radius: 4px; font-weight: bold; }}
        #welcome-box {{ position: fixed; top: 20px; right: 20px; z-index: 100; background: white; padding: 12px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); width: 280px; font-size: 0.9em; color: #2c3e50; border: 1px solid #ccc; }}
        
        #info-bar {{ position: fixed; bottom: 15px; left: 50%; transform: translateX(-50%); z-index: 100; background: white; padding: 8px 20px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); border: 1px solid #ccc; font-size: 0.85em; color: #444; white-space: nowrap; }}
        
        #scene {{ width: 100%; height: 100%; display: flex; justify-content: center; align-items: flex-start; padding-top: 100px; cursor: grab; }}
        #scene:active {{ cursor: grabbing; }}
        #tree-wrapper {{ display: inline-block; transform-origin: 0 0; }}
        .tree-root {{ display: inline-block; margin: 0 60px; }}
        ul {{ padding-top: 25px; position: relative; display: flex; justify-content: center; margin: 0; padding-left: 0; }}
        #tree li {{ float: left; text-align: center; list-style-type: none; position: relative; padding: 25px 10px 0 10px; }}
        #tree li::before, #tree li::after {{ content: ''; position: absolute; top: 0; right: 50%; border-top: 3px solid #444; width: 50%; height: 25px; }}
        #tree li::after {{ right: auto; left: 50%; border-left: 3px solid #444; }}
        #tree li:only-child::after, #tree li:only-child::before {{ display: none; }}
        #tree li:only-child {{ padding-top: 0; }}
        #tree li:first-child::before, #tree li:last-child::after {{ border: 0 none; }}
        #tree li:last-child::before {{ border-right: 3px solid #444; border-radius: 0 5px 0 0; }}
        #tree li:first-child::after {{ border-radius: 5px 0 0 0; }}
        #tree ul ul::before {{ content: ''; position: absolute; top: 0; left: 50%; border-left: 3px solid #444; width: 0; height: 25px; }}
        
        .li-content {{ display: flex; align-items: center; justify-content: center; position: relative; z-index: 2; }}
        .card {{ display: flex; align-items: center; padding: 6px; border-radius: 6px; min-width: 170px; text-align: left; border: 2px solid #999; margin: 0 5px; cursor: pointer; background: #fff; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }}
        .card.male {{ background-color: #e3f2fd; border-color: #2196f3; }}
        .card.female {{ background-color: #fce4ec; border-color: #e91e63; }}
        .card.target-person {{ background-color: #fffde7 !important; border-color: #ffc107 !important; box-shadow: 0 0 12px #ffc107; }}
        
        .card-icon {{ width: 40px; height: 40px; margin-right: 8px; border-radius: 4px; background: #fff; display: flex; justify-content: center; align-items: center; flex-shrink: 0; border: 1px solid #ddd; overflow: hidden; }}
        .card-icon img {{ width: 100%; height: 100%; object-fit: cover; }}
        .name {{ font-weight: bold; color: #2c3e50; font-size: 13px; }}
        .dates {{ font-size: 11px; color: #666; }}
        
        .modal {{ display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(3px); }}
        .modal-content {{ background-color: #fff; margin: 2% auto; padding: 25px; border-radius: 12px; width: 600px; max-width: 95%; box-shadow: 0 10px 40px rgba(0,0,0,0.5); max-height: 90vh; overflow-y: auto; }}
        .close {{ color: #999; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }}
        
        .modal-header {{ display: flex; align-items: center; border-bottom: 3px solid #2196f3; padding-bottom: 15px; margin-bottom: 15px; }}
        .modal-portrait {{ width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 3px solid #eee; margin-right: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h2.modal-title {{ margin: 0; color: #2c3e50; font-size: 1.8em; }}
        .modal-subtitle {{ color: #777; font-size: 0.9em; }}
        
        .event-box {{ background: #f9f9f9; border-left: 4px solid #2196f3; padding: 10px; margin-bottom: 10px; border-radius: 0 8px 8px 0; }}
        .event-title {{ font-weight: bold; color: #555; font-size: 0.9em; text-transform: uppercase; margin-bottom: 5px; }}
        .event-info {{ font-size: 1.05em; color: #000; }}
        .event-place {{ color: #666; font-style: italic; font-size: 0.95em; margin-top: 3px; }}
        
        .note-box {{ background: #fff9c4; padding: 10px; border-radius: 8px; border: 1px dashed #fbc02d; font-style: italic; white-space: pre-wrap; }}
        .contrib-box {{ background: #e0f2f1; padding: 12px; border-radius: 8px; border-left: 4px solid #009688; white-space: pre-wrap; margin-bottom: 10px; font-size: 0.95em; color: #00695c; }}
        
        .gallery-section {{ margin-top: 20px; border-top: 2px solid #eee; padding-top: 10px; }}
        .gallery-title {{ font-weight: bold; color: #555; margin-bottom: 10px; }}
        .gallery-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px; }}
        .gallery-img {{ width: 100%; height: 100px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd; cursor: zoom-in; transition: transform 0.2s; }}
        .gallery-img:hover {{ transform: scale(1.05); }}
        
        .btn-contrib {{ background: #ff9800; color: white; border: none; padding: 15px; border-radius: 6px; cursor: pointer; margin-top: 20px; width: 100%; font-weight: bold; font-size: 1.1em; text-transform: uppercase; box-shadow: 0 3px 6px rgba(0,0,0,0.2); transition: background 0.2s; }}
        .btn-contrib:hover {{ background: #f57c00; }}
        .connector {{ display: flex; align-items: center; justify-content: center; width: 35px; position: relative; }}
        .connector::after {{ content: ''; position: absolute; height: 3px; width: 100%; background: #444; }}
        .marr-date {{ background: #fff; padding: 2px 5px; border-radius: 10px; border: 2px solid #444; font-size: 10px; font-weight: bold; position: relative; z-index: 2; }}
    </style>
</head>
<body>
    <div id="controls">
        <select id="searchBox" onchange="loadTree(this.value)"></select>
        <div class="btns-row">
            <button onclick="panzoom.zoomIn()">+</button>
            <button onclick="panzoom.zoomOut()">-</button>
            <button onclick="centerView()">Centrer</button>
        </div>
    </div>
    <div id="welcome-box"><b>Bienvenue sur l'arbre de la Cousinade.</b><br>Cet arbre est interactif, naviguez librement.</div>
    <div id="info-bar">🖱️ <b>Molette</b> : Zoom | 🖐️ <b>Glisser</b> : Déplacer | 🖱️ <b>Clic Gauche</b> sur une personne : Recentrer | 🖱️ <b>Clic Droit</b> sur une personne : Accéder à sa fiche détaillée</div>
    
    <div id="detailModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <div id="modalBody"></div>
            <button class="btn-contrib" onclick="proposeModif()">✍️ Ajouter une Photo / Anecdote</button>
        </div>
    </div>

    <div id="scene"><div id="tree-wrapper"><div id="tree"></div></div></div>

    <script>
        const db = {json_db};
        const individuals = db.individuals;
        const families = db.families;
        let currentTargetId = "{start_id}";

        const panzoom = Panzoom(document.getElementById('tree-wrapper'), {{ canvas: true, minScale: 0.1, maxScale: 5 }});
        const scene = document.getElementById('scene');
        scene.addEventListener('wheel', (e) => panzoom.zoomWithWheel(e));
        scene.addEventListener('pointerdown', (e) => panzoom.handleDown(e));
        document.addEventListener('pointermove', (e) => panzoom.handleMove(e));
        document.addEventListener('pointerup', (e) => panzoom.handleUp(e));

        // --- SEARCHBOX ---
        const searchSelect = document.getElementById('searchBox');
        
        Object.keys(individuals).sort((a,b) => {{
            let nameA = individuals[a].name.split(" ").pop();
            let nameB = individuals[b].name.split(" ").pop();
            return nameA.localeCompare(nameB);
        }}).forEach(id => {{
            const p = individuals[id];
            let parts = p.name.split(" ");
            let lastName = parts.pop(); 
            let firstName = parts.join(" ");
            let year = p.birth ? p.birth.slice(-4) : "???";
            
            const opt = document.createElement('option');
            opt.value = id;
            opt.text = `${{lastName}} ${{firstName}} (${{year}})`;
            searchSelect.appendChild(opt);
        }});

        function openModal(id) {{
            const p = individuals[id];
            if(!p) return;
            window.currentPersonId = id; 
            
            const headerImg = p.main_photo ? `photos/${{p.main_photo}}` : (p.sex==='F'?'{img_f}':'{img_h}');

            let html = `
            <div class="modal-header">
                <img src="${{headerImg}}" class="modal-portrait">
                <div>
                    <h2 class="modal-title">${{p.name}}</h2>
                    <div class="modal-subtitle">ID: ${{id}}</div>
                </div>
            </div>`;

            if(p.birth || p.birth_place) {{
                html += `<div class="event-box"><div class="event-title">👶 Naissance</div><div class="event-info">${{p.birth||""}}</div><div class="event-place">${{p.birth_place||""}}</div></div>`;
            }}
            if(p.death || p.death_place) {{
                html += `<div class="event-box" style="border-left-color: #616161;"><div class="event-title">✝ Décès</div><div class="event-info">${{p.death||""}}</div><div class="event-place">${{p.death_place||""}}</div></div>`;
            }}
            p.fams.forEach(fid => {{
                const f = families[fid];
                if(f) {{
                    const spouse = individuals[f.husb === id ? f.wife : f.husb];
                    html += `<div class="event-box" style="border-left-color: #e91e63;"><div class="event-title">💍 Mariage avec ${{spouse?spouse.name:"?"}}</div><div class="event-info">${{f.marr?"En "+f.marr:""}}</div><div class="event-place">${{f.marr_place||""}}</div></div>`;
                }}
            }});

            if (p.gallery && p.gallery.length > 0) {{
                html += `<div class="gallery-section"><div class="gallery-title">📸 Galerie Photos</div><div class="gallery-grid">`;
                p.gallery.forEach(photo => {{ 
                    let displayTitle = photo.split('.')[0].replace(id + "_Photo_", "").replace(/_[0-9]+_[A-Za-z0-9]+$/, "").replace(/_/g, " ");
                    if (displayTitle === photo.split('.')[0]) displayTitle = ""; 
                    html += `
                    <div style="text-align:center;">
                        <a href="photos/${{photo}}" target="_blank"><img src="photos/${{photo}}" class="gallery-img"></a>
                        <div style="font-size:10px; color:#777; margin-top:3px; overflow:hidden; text-overflow:ellipsis;">${{displayTitle}}</div>
                    </div>`; 
                }});
                html += `</div></div>`;
            }}

            const tagMap = {{ 'OCCU': '🔨 Profession', 'RESI': '🏠 Résidence', 'NOTE': '📝 Note GEDCOM', 'SOUR': '📚 Source', 'BURI': '⚰️ Inhumation', 'USER_NOTE': '💌 Contribution Famille' }};
            p.details.forEach(d => {{
                let title = tagMap[d.tag] || d.tag;
                let contentClass = d.tag === 'USER_NOTE' ? "contrib-box" : (d.tag === 'NOTE' ? "note-box" : "event-info");
                let style = d.tag === 'USER_NOTE' ? 'style="border-left:none; background:transparent; padding:0;"' : 'style="border-left-color: #4caf50;"';
                let header = d.tag === 'USER_NOTE' ? '<div class="event-title">💌 Message Famille</div>' : '<div class="event-title">'+title+'</div>';
                
                html += `<div class="event-box" ${{style}}>
                    ${{header}}
                    <div class="${{contentClass}}">${{d.value}}</div>
                    ${{d.date ? '<div class="event-info">'+d.date+'</div>' : ''}}
                    ${{d.place ? '<div class="event-place">'+d.place+'</div>' : ''}}
                </div>`;
            }});

            document.getElementById('modalBody').innerHTML = html;
            document.getElementById('detailModal').style.display = "block";
        }}

        function proposeModif() {{
            const id = window.currentPersonId;
            const baseUrl = "{BASE_FORM_URL}";
            const fieldId = "{ENTRY_ID_FIELD}";
            
            if(fieldId && id) {{
                const finalLink = `${{baseUrl}}?usp=pp_url&entry.${{fieldId}}=${{id}}`;
                alert("Redirection vers le formulaire...\\nL'identifiant " + id + " est déjà rempli !");
                window.open(finalLink, '_blank');
            }} else {{
                alert("Erreur de configuration du lien.");
            }}
        }}

        function closeModal() {{ document.getElementById('detailModal').style.display = "none"; }}
        window.onclick = (e) => {{ if(e.target == document.getElementById('detailModal')) closeModal(); }};

        function renderCard(id) {{
            const i = individuals[id];
            if(!i) return "";
            const iconSrc = i.main_photo ? `photos/${{i.main_photo}}` : (i.sex==='F'?'{img_f}':'{img_h}');
            return `<div class="card ${{i.sex==='F'?'female':'male'}} ${{id===currentTargetId?'target-person':''}}" 
                    onclick="loadTree('${{id}}')" oncontextmenu="event.preventDefault(); openModal('${{id}}')">
                <div class="card-icon"><img src="${{iconSrc}}" onerror="this.src='${{i.sex==='F'?'{img_f}':'{img_h}'}}'"></div>
                <div class="card-text">
                    <div class="name">${{i.name}}</div>
                    <div class="dates">${{i.birth?'⭐ '+i.birth:''}}${{i.death?'<br>✝ '+i.death:''}}</div>
                </div>
            </div>`;
        }}

        function buildBranch(personId, depth) {{
            if(depth > 12 || !individuals[personId]) return "";
            const ind = individuals[personId];
            let spouseHtml = "";
            let childrenHtml = "";
            if(ind.fams.length > 0) {{
                const fam = families[ind.fams[0]];
                if(fam) {{
                    const spouseId = fam.husb === personId ? fam.wife : fam.husb;
                    if(spouseId) spouseHtml = `<div class="connector"><span class="marr-date">💍 ${{fam.marr}}</span></div>${{renderCard(spouseId)}}`;
                    if(fam.children.length > 0) childrenHtml = "<ul>" + fam.children.map(c => buildBranch(c, depth + 1)).join('') + "</ul>";
                }}
            }}
            return `<li><div class="li-content">${{renderCard(personId)}}${{spouseHtml}}</div>${{childrenHtml}}</li>`;
        }}

        function loadTree(id) {{
            currentTargetId = id; searchSelect.value = id;
            let root = id; const p = individuals[id];
            if(p.famc && families[p.famc] && families[p.famc].husb) {{
                let dad = families[p.famc].husb; root = dad;
                let gp = individuals[dad];
                if(gp.famc && families[gp.famc] && families[gp.famc].husb) root = families[gp.famc].husb;
            }}
            document.getElementById('tree').innerHTML = `<div class='tree-root'><ul>${{buildBranch(root, 0)}}</ul></div>`;
            setTimeout(centerView, 100);
        }}

        function centerView() {{
            const target = document.querySelector('.target-person');
            if(target) target.scrollIntoView({{block: "center", inline: "center", behavior: "smooth"}});
            else panzoom.reset();
        }}
        loadTree(currentTargetId);
    </script>
</body>
</html>
"""

# --- EXÉCUTION ---
print(f"Génération de {OUTPUT_FILE} depuis {GEDCOM_FILE}...")
indi, fami = parse_gedcom(GEDCOM_FILE)
sid = next((i for i, v in indi.items() if START_PERSON in v['name'] and "1933" in v['birth']), list(indi.keys())[0])
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(generate_html(indi, fami, sid, IMG_HOMME, IMG_FEMME))
print(f"TERMINÉ : {OUTPUT_FILE}")