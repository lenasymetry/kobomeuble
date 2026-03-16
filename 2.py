import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import datetime
from io import BytesIO 
import math
import copy
import hashlib
import base64
import os
import importlib 

from utils import calculate_available_space_between_horizontal_shelves
from geometry_helpers import cuboid_mesh_for, cylinder_mesh_for, add_zone_annotations_to_figure, add_hatched_zones_3d, add_zone_outlines_3d, add_zone_debug_boxes_3d, check_element_placement_validity
from excel_export import create_styled_excel
from project_definitions import get_default_dims_19, get_default_door_props_19, get_default_drawer_props_19, get_legrabox_specs
from machining_logic import (
    calculate_origins_recursively, get_hinge_y_positions, get_mobile_shelf_holes, 
    calculate_back_panel_holes, detect_collisions, calculate_zones_from_dividers, 
    get_vertical_divider_tranche_holes, get_traverse_holes_for_divider, get_traverse_face_holes_for_divider, get_mounting_holes_for_zone_element,
    get_vertical_shelf_tranche_holes, calculate_vertical_zones_in_x_zone, calculate_all_zones_2d,
    calculate_hole_positions
)
from drawing_interface import draw_machining_view_pro_final
from state_manager import (
    initialize_session_state, get_selected_cabinet, load_save_state, add_cabinet, clear_scene, delete_selected_cabinet,
    update_selected_cabinet_dim, update_selected_cabinet_door, update_selected_cabinet_drawer,
    add_shelf_callback, update_shelf_prop, delete_shelf_callback,
    update_selected_cabinet_material, update_selected_cabinet_door_material, 
    update_selected_cabinet_drawer_material, update_shelf_material, update_hinge_count, update_hinge_position,
    add_vertical_divider_callback, add_vertical_divider_double_callback,
    update_vertical_divider_prop, delete_vertical_divider_callback, update_vertical_divider_material,
    add_vertical_shelf_callback, update_vertical_shelf_prop, delete_vertical_shelf_callback, update_vertical_shelf_material,
    add_drawer_callback, add_drawers_stack_callback, update_drawer_prop, delete_drawer_callback, update_drawer_material,
    get_default_debit_data, update_selected_cabinet_base_element, update_hinge_count, update_hinge_position
)
from export_manager import generate_stacked_html_plans  # import for machining plans export

st.set_page_config(page_title="KoboMeuble", layout="wide")
initialize_session_state()

def get_automatic_edge_banding(part_name):
    name = part_name.lower()
    if "etagère" in name or "etagere" in name: return True, False, False, False
    elif "fond" in name or "dos" in name:
        if "façade" in name or "face" in name: return True, True, True, True
        return False, False, False, False
    elif "traverse" in name: return True, True, False, False
    else: return True, True, True, True

def has_holes_for_piece(ref_key, cabinet, piece_data=None):
    """
    Vérifie si une pièce a des trous sur sa feuille d'usinage.
    Retourne True si la pièce a au moins un trou.
    """
    dims = cabinet['dims']
    
    # Montants principaux : toujours des trous (vis et tourillons)
    if "Montant" in ref_key and ("Gauche" in ref_key or "Droit" in ref_key):
        return True
    
    # Traverses : toujours des trous (vis et tourillons pour assemblage)
    if "Traverse" in ref_key:
        return True
    
    # Portes : toujours des trous (charnières)
    if "Porte" in ref_key:
        return True
    
    # Étagères fixes : toujours des trous (assemblage)
    if "Etagère" in ref_key and "Fixe" in ref_key:
        return True
    
    # Étagères mobiles : vérifier si elles ont des trous de taquets
    if "Etagère" in ref_key and "Mobile" in ref_key:
        if 'shelves' in cabinet:
            for s in cabinet['shelves']:
                if s.get('shelf_type') == 'mobile':
                    # Les étagères mobiles ont toujours des trous pour les taquets
                    return True
    
    # Montants secondaires : toujours des trous
    if "Montant Secondaire" in ref_key or "Divider" in ref_key:
        return True
    
    # Tiroirs : toujours des trous (assemblage)
    if "Tiroir" in ref_key or "Façade" in ref_key:
        return True
    
    # Fonds : vérifier s'ils ont des trous (vis de fixation)
    if "Fond" in ref_key:
        # Les fonds ont généralement des trous pour la fixation
        return True
    
    # Par défaut, pas de trous
    return False

def calculate_all_project_parts():
    all_parts = []
    lettre_code = 65 
    shelf_dims_cache = {} 

    for i, cabinet in enumerate(st.session_state['scene_cabinets']):
        dims = cabinet['dims']
        debit_data = cabinet['debit_data']
        
        t_lr, t_tb, t_fb = dims['t_lr_raw'], dims['t_tb_raw'], dims['t_fb_raw']
        h_side = dims['H_raw'] 
        L_traverse = dims['L_raw'] - 2 * t_lr 
        dim_fond_vertical = dims['H_raw'] - 2.0; dim_fond_horizontal = dims['L_raw'] - 2.0
        
        panel_dims = {
            "Traverse Bas": (L_traverse, dims['W_raw'], t_tb),
            "Traverse Haut": (L_traverse, dims['W_raw'], t_tb),
            "Montant Gauche": (h_side, dims['W_raw'], t_lr),
            "Montant Droit": (h_side, dims['W_raw'], t_lr),
            "Fond": (dim_fond_vertical, dim_fond_horizontal, t_fb)
        }
        
        # Récupérer les préférences des éléments de base (par défaut tous activés)
        base_el = cabinet.get('base_elements', {
            'has_back_panel': True,
            'has_left_upright': True,
            'has_right_upright': True,
            'has_bottom_traverse': True,
            'has_top_traverse': True
        })
        
        # 1. Structure
        for piece in debit_data:
            ref_full = piece.get("Référence Pièce", "")
            ref_key = ref_full.split(' (')[0].strip()
            
            # Vérifier si l'élément doit être inclus
            should_include = True
            if "Traverse Bas" in ref_key and not base_el.get('has_bottom_traverse', True):
                should_include = False
            elif "Traverse Haut" in ref_key and not base_el.get('has_top_traverse', True):
                should_include = False
            elif "Montant Gauche" in ref_key and not base_el.get('has_left_upright', True):
                should_include = False
            elif "Montant Droit" in ref_key and not base_el.get('has_right_upright', True):
                should_include = False
            elif "Fond" in ref_key and not base_el.get('has_back_panel', True):
                should_include = False
            
            if not should_include:
                continue
            
            new_piece = piece.copy()
            new_piece['Lettre'] = f"C{i}-{chr(lettre_code)}"
            lettre_code += 1
            new_piece["Référence Pièce"] = ref_full 
            new_piece["Matière"] = cabinet.get('material_body', 'Matière Corps')
            new_piece["Caisson"] = f"C{i}"
            # Quantité : par défaut 1 si non précisé
            new_piece["Qté"] = piece.get("Qté", 1)
            # Pour le fond : mettre "CF plan" (le fond a toujours des trous de fixation)
            if "Fond" in ref_key:
                new_piece["Usinage"] = "CF plan"
            # Vérifier si la pièce a des trous pour mettre "CF plan"
            elif has_holes_for_piece(ref_key, cabinet, new_piece):
                new_piece["Usinage"] = "CF plan"
            else:
                new_piece["Usinage"] = new_piece.get("Usinage", "")
            # Chant : privilégier les choix utilisateur s'ils existent, sinon utiliser l'automatique
            cav_auto, car_auto, cg_auto, cd_auto = get_automatic_edge_banding(ref_key)
            cav = piece.get("Chant Avant", cav_auto)
            car = piece.get("Chant Arrière", car_auto)
            cg  = piece.get("Chant Gauche", cg_auto)
            cd  = piece.get("Chant Droit", cd_auto)
            new_piece["Chant Avant"] = bool(cav)
            new_piece["Chant Arrière"] = bool(car)
            new_piece["Chant Gauche"] = bool(cg)
            new_piece["Chant Droit"] = bool(cd)

            match_found = False
            for key, dims_tuple in panel_dims.items():
                if key in ref_key:
                    new_piece["Longueur (mm)"] = dims_tuple[0]; new_piece["Largeur (mm)"] = dims_tuple[1]; new_piece["Epaisseur"] = dims_tuple[2]
                    match_found = True; break
            if not match_found and "Fond" in ref_key:
                    new_piece["Longueur (mm)"] = dim_fond_vertical; new_piece["Largeur (mm)"] = dim_fond_horizontal; new_piece["Epaisseur"] = t_fb
            all_parts.append(new_piece)
        
        # 2. Porte
        if cabinet['door_props']['has_door']:
            dp = cabinet['door_props']
            dH = dims['H_raw'] - (2 * dp['door_gap']) 
            if dp.get('door_model') == 'floor_length': dH += st.session_state.foot_height 
            
            # Vérifier si une zone est assignée
            zone_id = dp.get('zone_id', None)
            all_zones_2d = calculate_all_zones_2d(cabinet)
            if zone_id is not None and zone_id < len(all_zones_2d):
                zone = all_zones_2d[zone_id]
                dW = (zone['x_max'] - zone['x_min']) - (2 * dp['door_gap'])
            else:
                dW = dims['L_raw'] - (2 * dp['door_gap']) if dp.get('door_type') == 'single' else (dims['L_raw'] - 2*dp['door_gap'])/2
            
            cav, car, cg, cd = get_automatic_edge_banding("Porte")
            porte_ref = f"Porte (C{i})"
            usinage_porte = "CF plan" if has_holes_for_piece("Porte", cabinet) else ""
            all_parts.append({"Lettre": f"C{i}-P", "Référence Pièce": porte_ref, "Matière": dp.get('material', 'Matière Porte'), "Caisson": f"C{i}", "Qté": 1 if dp.get('door_type')=='single' else 2, "Longueur (mm)": dH, "Largeur (mm)": dW, "Epaisseur": dp.get('door_thickness', 19.0), "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd, "Usinage": usinage_porte})

        # 3. Tiroirs (tous les tiroirs de la liste) - dimensions adaptées à la zone
        if 'drawers' in cabinet and cabinet['drawers']:
            all_zones_2d_drawers = calculate_all_zones_2d(cabinet)
            legrabox_specs = get_legrabox_specs()
            for drawer_idx, drp in enumerate(cabinet['drawers']):
                drawer_system = drp.get('drawer_system', 'TANDEMBOX')
                tech_type = drp.get('drawer_tech_type', 'K')
                
                # Largeur utile du tiroir en fonction de la zone
                zone_id = drp.get('zone_id', None)
                gap_mm = drp.get('drawer_gap', 2.0)
                t_lr = dims['t_lr_raw']
                
                if zone_id is not None and zone_id < len(all_zones_2d_drawers):
                    zone = all_zones_2d_drawers[zone_id]
                    zone_width_total = zone['x_max'] - zone['x_min']  # Largeur totale incluant chants
                    zone_width_interior = zone_width_total - (2 * t_lr)  # Largeur intérieure
                else:
                    zone_width_total = dims['L_raw']
                    zone_width_interior = dims['L_raw'] - (2 * t_lr)
                
                # Dimensionnement selon le système
                if drawer_system == 'LÉGRABOX':
                    # LÉGRABOX : Face = largeur totale de la zone (incluant chants)
                    drawer_face_width = zone_width_total - (2 * gap_mm)
                    # Dos : largeur intérieure - 38mm
                    drawer_back_width = max(0.0, zone_width_interior - 38.0)
                    # Fond : largeur intérieure - 35mm, profondeur intérieure - 10mm
                    t_fb_raw = float(dims.get('t_fb_raw', 0.0))
                    zone_depth_interior = dims['W_raw'] - (2 * t_lr)  # Profondeur intérieure
                    drawer_bottom_width = max(0.0, zone_width_interior - 35.0)
                    drawer_bottom_depth = max(0.0, zone_depth_interior - 10.0)
                    # Hauteur dos selon modèle LÉGRABOX
                    legrabox_spec = legrabox_specs.get(tech_type, legrabox_specs['K'])
                    fixed_back_h = legrabox_spec['back_height']
                else:
                    # TANDEMBOX : logique existante
                    drawer_face_width = zone_width_total - (2 * gap_mm)
                    drawer_back_width = max(0.0, drawer_face_width - 40.0)
                    back_height_map = {'N': 69.0, 'M': 84.0, 'K': 116.0, 'D': 199.0}
                    fixed_back_h = back_height_map.get(tech_type, 116.0)
                    t_fb_raw = float(dims.get('t_fb_raw', 0.0))
                    drawer_bottom_width = max(0.0, drawer_face_width - 49.0)
                    drawer_bottom_depth = float(dims['W_raw']) - (20.0 + t_fb_raw)
                
                cav, car, cg, cd = get_automatic_edge_banding("Façade")
                facade_ref = f"Façade Tiroir {drawer_idx+1} (C{i})"
                usinage_facade = "CF plan" if has_holes_for_piece("Façade Tiroir", cabinet) else ""
                all_parts.append({
                    "Lettre": f"C{i}-TF{drawer_idx+1}",
                    "Référence Pièce": facade_ref,
                    "Matière": drp.get('material', 'Matière Tiroir'),
                    "Caisson": f"C{i}",
                    "Qté": 1,
                    "Longueur (mm)": drp.get('drawer_face_H_raw', 150.0),
                    "Largeur (mm)": drawer_face_width,
                    "Epaisseur": drp.get('drawer_face_thickness', 19.0),
                    "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd,
                    "Usinage": usinage_facade
                })
                
                # Dos du tiroir
                cav, car, cg, cd = get_automatic_edge_banding("Tiroir Dos")
                dos_ref = f"Tiroir Dos {drawer_idx+1} (C{i})"
                usinage_dos = "CF plan" if has_holes_for_piece("Tiroir Dos", cabinet) else ""
                all_parts.append({
                    "Lettre": f"C{i}-TD{drawer_idx+1}",
                    "Référence Pièce": dos_ref,
                    "Matière": drp.get('material_inner', cabinet.get('material_body', 'Matière Corps')),
                    "Caisson": f"C{i}",
                    "Qté": 1,
                    "Longueur (mm)": fixed_back_h,
                    "Largeur (mm)": drawer_back_width,
                    "Epaisseur": float(drp.get('inner_thickness', 16.0)),
                    "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd,
                    "Usinage": usinage_dos
                })
                
                # Fond du tiroir
                cav, car, cg, cd = get_automatic_edge_banding("Tiroir Fond")
                fond_ref = f"Tiroir Fond {drawer_idx+1} (C{i})"
                usinage_fond_base = "Feuillure G/D" if drawer_system == 'LÉGRABOX' else ""
                usinage_fond = "CF plan" if has_holes_for_piece("Tiroir Fond", cabinet) else usinage_fond_base
                all_parts.append({
                    "Lettre": f"C{i}-TFD{drawer_idx+1}",
                    "Référence Pièce": fond_ref,
                    "Matière": drp.get('material_inner', cabinet.get('material_body', 'Matière Corps')),
                    "Caisson": f"C{i}",
                    "Qté": 1,
                    "Longueur (mm)": drawer_bottom_width,
                    "Largeur (mm)": drawer_bottom_depth,
                    "Epaisseur": float(drp.get('inner_thickness', 16.0)),
                    "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd,
                    "Usinage": usinage_fond
                })
            
        # 4. Étagères (CORRIGÉ ICI POUR USINAGE ET REGROUPEMENT)
        # Dictionnaire pour regrouper les étagères identiques : clé = (dim_L, dim_W, épaisseur, matière, type, usinage)
        shelves_grouped = {}
        
        if 'shelves' in cabinet:
            for s_idx, s in enumerate(cabinet['shelves']):
                s_type = s.get('shelf_type', 'mobile')
                s_th = float(s.get('thickness', 19.0))
                dim_W = dims['W_raw'] - 10.0
                
                # Vérifier si une zone est assignée
                zone_id = s.get('zone_id', None)
                all_zones_2d = calculate_all_zones_2d(cabinet)
                if zone_id is not None and zone_id < len(all_zones_2d):
                    zone = all_zones_2d[zone_id]
                    # La zone est déjà calculée entre les montants, donc on prend directement la largeur
                    if s_type == 'mobile':
                        dim_L = (zone['x_max'] - zone['x_min']) - 2.0  # 2mm de chaque côté pour les étagères mobiles
                    else:
                        dim_L = (zone['x_max'] - zone['x_min'])  # Étagère fixe prend toute la zone
                else:
                    if s_type == 'fixe':
                        dim_L = L_traverse 
                    else:
                        dim_L = L_traverse - 2.0
                
                shelf_dims_cache[f"C{i}_S{s_idx}"] = (dim_L, dim_W)
                
                cav, car, cg, cd = get_automatic_edge_banding("Etagère")
                
                # --- MODIFICATION DEMANDÉE : USINAGE ---
                # Vérifier si l'étagère a des trous
                shelf_ref = f"Etagère {s_type.capitalize()}"
                usinage_txt = "CF plan" if has_holes_for_piece(shelf_ref, cabinet) else ""
                
                # Clé pour regrouper : dimensions, épaisseur, matière, type, usinage
                shelf_key = (round(dim_L, 1), round(dim_W, 1), round(s_th, 1), 
                           s.get('material', 'Matière Étagère'), s_type, usinage_txt)
                
                if shelf_key in shelves_grouped:
                    # Incrémenter la quantité
                    shelves_grouped[shelf_key]['Qté'] += 1
                    # Ajouter le caisson à la liste des caissons si pas déjà présent
                    if f"C{i}" not in shelves_grouped[shelf_key]['Caissons']:
                        shelves_grouped[shelf_key]['Caissons'].append(f"C{i}")
                else:
                    # Première occurrence de cette étagère
                    shelves_grouped[shelf_key] = {
                        "Lettre": f"C{i}-E{s_idx+1}",  # Garder la première lettre rencontrée
                        "Référence Pièce": f"Etagère {s_type.capitalize()}",
                        "Matière": s.get('material', 'Matière Étagère'),
                        "Caissons": [f"C{i}"],
                        "Qté": 1,
                        "Longueur (mm)": dim_L,
                        "Largeur (mm)": dim_W,
                        "Epaisseur": s_th,
                        "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd,
                        "Usinage": usinage_txt
                    }
        
        # Ajouter les étagères regroupées à all_parts
        for shelf_key, shelf_data in shelves_grouped.items():
            # Construire la référence pièce avec les caissons
            shelf_type = shelf_data['Référence Pièce'].split()[-1]  # "Mobile" ou "Fixe"
            caissons_list = shelf_data['Caissons']
            if len(caissons_list) > 1:
                shelf_data["Référence Pièce"] = f"Etagère {shelf_type} ({', '.join(caissons_list)})"
                shelf_data["Caisson"] = ', '.join(caissons_list)  # Champ "Caisson" avec tous les caissons
            else:
                shelf_data["Référence Pièce"] = f"Etagère {shelf_type} ({caissons_list[0]})"
                shelf_data["Caisson"] = caissons_list[0]  # Champ "Caisson" avec un seul caisson
            
            # Retirer 'Caissons' du dictionnaire avant d'ajouter à all_parts
            shelf_data.pop('Caissons')
            all_parts.append(shelf_data)
        
        # 5. Montants verticaux secondaires
        if 'vertical_dividers' in cabinet and cabinet['vertical_dividers']:
            for div_idx, div in enumerate(cabinet['vertical_dividers']):
                div_th = div.get('thickness', 19.0)
                div_h = h_side - 2 * t_tb  # Hauteur entre traverses
                div_w = dims['W_raw']  # Largeur (profondeur)
                
                cav, car, cg, cd = get_automatic_edge_banding("Montant")
                divider_ref = f"Montant Secondaire {div_idx+1} (C{i})"
                usinage_divider = "CF plan" if has_holes_for_piece("Montant Secondaire", cabinet) else ""
                all_parts.append({
                    "Lettre": f"C{i}-MS{div_idx+1}",
                    "Référence Pièce": divider_ref,
                    "Matière": div.get('material', cabinet.get('material_body', 'Matière Corps')),
                    "Caisson": f"C{i}",
                    "Qté": 1,
                    "Longueur (mm)": div_h,
                    "Largeur (mm)": div_w,
                    "Epaisseur": div_th,
                    "Chant Avant": cav, "Chant Arrière": car, "Chant Gauche": cg, "Chant Droit": cd,
                    "Usinage": usinage_divider
                })
            
    return all_parts, shelf_dims_cache

# Fonction pour charger le logo en base64
def load_image_base64(filename):
    """Charge une image et la convertit en base64"""
    try:
        from PIL import Image
        import io
        candidates = [filename]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, filename))
        candidates.append(os.path.join(os.path.dirname(script_dir), filename))
        final_path = None
        for path in candidates:
            if os.path.exists(path):
                final_path = path
                break
        if not final_path:
            return None
        img = Image.open(final_path)
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG")
        encoded = base64.b64encode(output_buffer.getvalue()).decode()
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None

# Charger le logo
logo_base64 = load_image_base64("logo.png")

# En-tête avec fond bleu marine légèrement transparent
if logo_base64:
    header_html = f"""
    <style>
    .main-header {{
        background-color: rgba(0, 51, 102, 0.5); /* Bleu marine avec plus de transparence */
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
    }}
    .main-header h1 {{
        color: white;
        margin: 0;
        font-size: 2.5rem;
        font-weight: bold;
    }}
    .main-header img {{
        height: 60px;
        width: auto;
    }}
    </style>
    <div class="main-header">
        <img src="{logo_base64}" alt="Logo KoboMeuble" />
        <h1>KoboMeuble</h1>
    </div>
    """
else:
    header_html = """
    <style>
    .main-header {
        background-color: rgba(0, 51, 102, 0.5); /* Bleu marine avec plus de transparence */
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2.5rem;
        font-weight: bold;
    }
    </style>
    <div class="main-header">
        <h1>KoboMeuble 🛠️</h1>
    </div>
    """

st.markdown(header_html, unsafe_allow_html=True)
col1, col2 = st.columns([1, 2])
selected_cab = get_selected_cabinet()

with col1:
    st.header("Éditeur de Scène")
    tab_assembly, tab_edit = st.tabs(["🏗️ Assemblage & Fichiers", "✏️ Éditeur de Caisson"])

    with tab_assembly:
        st.subheader("Fichier Projet")
        # CSS pour égaliser les largeurs des champs
        st.markdown("""
        <style>
        div[data-testid="column"]:nth-of-type(1) input,
        div[data-testid="column"]:nth-of-type(2) input,
        div[data-testid="column"]:nth-of-type(1) div[data-baseweb="input"],
        div[data-testid="column"]:nth-of-type(2) div[data-baseweb="input"] {
            width: 100% !important;
        }
        </style>
        """, unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Nom du Projet", key='project_name')
        with c2:
            st.date_input("Date souhaitée", key='date_souhaitee', value=datetime.date.today())
        st.text_input("Client", key='client')
        st.text_input("Adresse Chantier", key='adresse_chantier')
        st.text_input("Réf. Chantier", key='ref_chantier')
        st.text_input("Téléphone / Mail", key='telephone')
        st.markdown("##### Matériaux (Défaut)")
        st.text_input("Panneau / Décor", key='panneau_decor')
        c1, c2 = st.columns(2)
        st.text_input("Chant (mm)", key='chant_mm')
        st.text_input("Décor Chant", key='decor_chant')
        st.markdown("---")
        st.info("La sauvegarde est incluse dans le téléchargement XLS.")
        st.file_uploader("Charger un Projet (.xlsx)", type=["xlsx"], key="file_loader", on_change=load_save_state)
        st.markdown("---")
        st.subheader("Assemblage de la Scène")
        st.button("1. Ajouter le Caisson Central", on_click=add_cabinet, args=('central',), disabled=bool(st.session_state['scene_cabinets']), use_container_width=True)
        if st.session_state['scene_cabinets']:
            opts = [f"{i}: {c['name']}" for i, c in enumerate(st.session_state['scene_cabinets'])]
            st.selectbox("Ajouter relatif à :", options=range(len(opts)), format_func=lambda x: opts[x], key='base_cabinet_index')
            c1, c2, c3 = st.columns(3)
            c1.button("⬅️ Gauche", on_click=add_cabinet, args=('left',), use_container_width=True)
            c2.button("➡️ Droite", on_click=add_cabinet, args=('right',), use_container_width=True)
            c3.button("⬆️ Dessus", on_click=add_cabinet, args=('up',), use_container_width=True)
        st.button("Vider la scène 🗑️", on_click=clear_scene, use_container_width=True)
        st.markdown("---")
        st.subheader("Options des Pieds (Global)")
        st.toggle("Ajouter des pieds", key='has_feet')
        if st.session_state.has_feet:
            feet_map = {"20": 20.0, "80-100": 100.0, "110-120": 120.0}
            sel_feet = st.selectbox("Hauteur (mm)", options=["20", "80-100", "110-120"], index=1)
            st.session_state.foot_height = feet_map[sel_feet]
            st.number_input("Diamètre pieds (mm)", min_value=10.0, key='foot_diameter', value=50.0, format="%.0f", step=1.0)

    with tab_edit:
        st.subheader("Sélection et Suppression")
        if not st.session_state['scene_cabinets']:
            st.info("Ajoutez un caisson central pour commencer l'édition.")
        else:
            opts = [f"{i}: {c['name']}" for i, c in enumerate(st.session_state['scene_cabinets'])]
            st.selectbox("Éditer le caisson :", options=range(len(opts)), format_func=lambda x: opts[x], key='selected_cabinet_index')
            st.button("Supprimer le Caisson", on_click=delete_selected_cabinet, use_container_width=True, type="primary")
            
            if selected_cab:
                idx = st.session_state.selected_cabinet_index
                t_dims, t_acc, t_sh, t_div, t_deb = st.tabs(["Dimensions", "Porte/Tiroir", "Étagères", "Montants Secondaires", "Feuille de Débit"])
                with t_dims:
                    st.markdown(f"#### Matières et Dimensions du Corps")
                    st.text_input(f"Matière Corps", value=selected_cab.get('material_body', 'Matière Corps'), key=f"material_body_{idx}", on_change=lambda: update_selected_cabinet_material('material_body'))
                    st.markdown("##### Dimensions Externes")
                    dims = selected_cab['dims']
                    st.number_input("Longueur (X)", value=dims['L_raw'], key=f"L_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('L_raw'), format="%.0f", step=1.0)
                    st.number_input("Largeur (Y - Profondeur)", value=dims['W_raw'], key=f"W_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('W_raw'), format="%.0f", step=1.0)
                    st.number_input("Hauteur (Z)", value=dims['H_raw'], key=f"H_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('H_raw'), format="%.0f", step=1.0)
                    st.markdown("##### Épaisseurs des Panneaux")
                    st.number_input("Parois latérales (Montants)", value=dims['t_lr_raw'], key=f"t_lr_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('t_lr_raw'), format="%.0f", step=1.0)
                    st.number_input("Arrière (Fond)", value=dims['t_fb_raw'], key=f"t_fb_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('t_fb_raw'), format="%.0f", step=1.0)
                    st.number_input("Haut/Bas (Traverses)", value=dims['t_tb_raw'], key=f"t_tb_raw_{idx}", on_change=lambda: update_selected_cabinet_dim('t_tb_raw'), format="%.0f", step=1.0)
                    
                    st.markdown("##### Éléments de Base")
                    st.markdown("Cocher les éléments à inclure dans le caisson :")
                    # Initialiser les préférences si elles n'existent pas
                    if 'base_elements' not in selected_cab:
                        selected_cab['base_elements'] = {
                            'has_back_panel': True,
                            'has_left_upright': True,
                            'has_right_upright': True,
                            'has_bottom_traverse': True,
                            'has_top_traverse': True
                        }
                    base_el = selected_cab['base_elements']
                    st.toggle("Panneau Arrière (Fond)", value=base_el.get('has_back_panel', True), key=f"base_element_has_back_panel_{idx}", on_change=lambda: update_selected_cabinet_base_element('has_back_panel'))
                    st.toggle("Montant Gauche", value=base_el.get('has_left_upright', True), key=f"base_element_has_left_upright_{idx}", on_change=lambda: update_selected_cabinet_base_element('has_left_upright'))
                    st.toggle("Montant Droit", value=base_el.get('has_right_upright', True), key=f"base_element_has_right_upright_{idx}", on_change=lambda: update_selected_cabinet_base_element('has_right_upright'))
                    st.toggle("Traverse Bas", value=base_el.get('has_bottom_traverse', True), key=f"base_element_has_bottom_traverse_{idx}", on_change=lambda: update_selected_cabinet_base_element('has_bottom_traverse'))
                    st.toggle("Traverse Haut", value=base_el.get('has_top_traverse', True), key=f"base_element_has_top_traverse_{idx}", on_change=lambda: update_selected_cabinet_base_element('has_top_traverse'))

                with t_acc:
                    d_p = selected_cab['door_props']; dr_p = selected_cab['drawer_props']
                    # Calculer les zones disponibles (SANS inclure les éléments sans zone_id)
                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                    zone_options = [None] + [z['id'] for z in all_zones_2d]
                    zone_labels = ["Tout le caisson"] + [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d]
                    
                    st.markdown("#### Porte (Façade)")
                    st.toggle("Ajouter une porte", value=d_p['has_door'], key=f"has_door_{idx}", on_change=lambda: update_selected_cabinet_door('has_door'))
                    if d_p['has_door']:
                        # Sélection de zone pour la porte
                        if len(all_zones_2d) > 1:
                            current_zone = d_p.get('zone_id', None)
                            zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                            st.selectbox(
                                "Zone d'emplacement",
                                options=zone_options,
                                index=zone_index,
                                format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Tout le caisson",
                                key=f"door_zone_{idx}",
                                on_change=lambda: update_selected_cabinet_door('zone_id')
                            )
                        st.selectbox("Type de porte", options=['single', 'double'], index=0 if d_p.get('door_type')=='single' else 1, format_func=lambda x: 'Simple' if x=='single' else 'Double', key=f"door_type_{idx}", on_change=lambda: update_selected_cabinet_door('door_type'))
                        if d_p.get('door_type')=='single': st.selectbox("Sens d'ouverture", options=['right', 'left'], index=0 if d_p.get('door_opening')=='right' else 1, format_func=lambda x: 'Droite' if x=='right' else 'Gauche', key=f"door_opening_{idx}", on_change=lambda: update_selected_cabinet_door('door_opening'))
                        st.number_input("Épaisseur (mm)", value=d_p.get('door_thickness', 19.0), key=f"door_thickness_{idx}", on_change=lambda: update_selected_cabinet_door('door_thickness'), format="%.0f", step=1.0)
                        st.selectbox("Modèle", options=['standard', 'floor_length'], index=0 if d_p.get('door_model')=='standard' else 1, format_func=lambda x: 'Standard' if x=='standard' else 'Cache-pied', key=f"door_model_{idx}", on_change=lambda: update_selected_cabinet_door('door_model'))
                        st.number_input("Jeu extérieur (mm)", value=d_p.get('door_gap', 2.0), key=f"door_gap_{idx}", on_change=lambda: update_selected_cabinet_door('door_gap'), format="%.1f", step=0.1)
                        st.text_input("Matière Porte", value=d_p.get('material', 'Matière Porte'), key=f"door_material_{idx}", on_change=lambda: update_selected_cabinet_door_material('material'))
                        
                        # Configuration des charnières
                        st.markdown("##### Charnières")
                        hinge_mode = d_p.get('hinge_mode', 'default')
                        hinge_mode_index = 0 if hinge_mode == 'default' else 1
                        selected_hinge_mode = st.selectbox(
                            "Mode de charnières",
                            options=['default', 'custom'],
                            index=hinge_mode_index,
                            format_func=lambda x: 'Par défaut' if x=='default' else 'Personnalisé',
                            key=f"hinge_mode_{idx}",
                            on_change=lambda: update_selected_cabinet_door('hinge_mode')
                        )
                        
                        if selected_hinge_mode == 'custom':
                            # Mode personnalisé : permettre à l'utilisateur de définir le nombre et les positions
                            custom_positions = d_p.get('custom_hinge_positions', [])
                            num_hinges = st.number_input(
                                "Nombre de charnières",
                                value=len(custom_positions) if custom_positions else 3,
                                min_value=1,
                                max_value=10,
                                step=1,
                                key=f"num_hinges_{idx}",
                                on_change=lambda: update_hinge_count(idx)
                            )
                            
                            # Ajuster la liste si le nombre a changé
                            if len(custom_positions) != num_hinges:
                                if len(custom_positions) < num_hinges:
                                    # Ajouter des positions par défaut
                                    door_height = selected_cab['dims']['H_raw']
                                    for i in range(len(custom_positions), num_hinges):
                                        # Répartir équitablement
                                        pos = (i + 1) * door_height / (num_hinges + 1)
                                        custom_positions.append(pos)
                                else:
                                    # Retirer les positions en trop
                                    custom_positions = custom_positions[:num_hinges]
                                d_p['custom_hinge_positions'] = custom_positions
                            
                            # Afficher les champs pour chaque charnière
                            for i in range(num_hinges):
                                current_pos = custom_positions[i] if i < len(custom_positions) else (i + 1) * selected_cab['dims']['H_raw'] / (num_hinges + 1)
                                new_pos = st.number_input(
                                    f"Position charnière {i+1} (mm depuis le bas)",
                                    value=float(current_pos),
                                    min_value=0.0,
                                    max_value=float(selected_cab['dims']['H_raw']),
                                    step=1.0,
                                    format="%.0f",
                                    key=f"hinge_pos_{idx}_{i}",
                                    on_change=lambda idx_cab=idx, idx_hinge=i: update_hinge_position(idx_cab, idx_hinge)
                                )
                                if i < len(custom_positions):
                                    custom_positions[i] = new_pos
                                else:
                                    custom_positions.append(new_pos)
                            d_p['custom_hinge_positions'] = custom_positions[:num_hinges]

                    st.markdown("#### Configuration des Tiroirs")
                    st.button("➕ Ajouter un Tiroir", key=f"add_drawer_{idx}", on_click=add_drawer_callback)
                    st.button("🧱 Ajouter plusieurs tiroirs (empiler)", key=f"add_drawers_stack_{idx}", on_click=add_drawers_stack_callback)
                    
                    # --- POSE EN 2 TEMPS (APERÇU -> VALIDER) : TIROIR ---
                    pending = st.session_state.get('pending_placement')
                    if pending and pending.get('cabinet_index') == idx and pending.get('kind') in ('drawer', 'drawer_stack'):
                        p = pending.get('props', {})
                        is_stack_mode = pending.get('kind') == 'drawer_stack' or bool(p.get('_stack_mode'))
                        st.warning("Pose en cours : le tiroir est en prévisualisation. Cliquez sur **Valider la position** pour le poser définitivement.")
                        with st.expander("✅ Valider la position (Tiroir)" if not is_stack_mode else "✅ Valider la position (Tiroirs empilés)"):
                            all_zones_2d_sel = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                            zone_options = [None] + [z['id'] for z in all_zones_2d_sel]
                            zone_labels = ["Tout le caisson"] + [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_sel]
                            current_zone = p.get('zone_id', None)
                            zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                            p['zone_id'] = st.selectbox(
                                "Zone d'emplacement",
                                options=zone_options,
                                index=zone_index,
                                format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Tout le caisson",
                                key=f"pending_drawer_zone_{idx}",
                            )
                            
                            if is_stack_mode:
                                # Empilement : l'utilisateur ne saisit PAS de dimensions (ni hauteur, ni offset).
                                p['stack_count'] = int(st.number_input(
                                    "Nombre de tiroirs dans la zone",
                                    min_value=1,
                                    max_value=12,
                                    value=int(p.get('stack_count', 3)),
                                    step=1,
                                    key=f"pending_drawer_stack_{idx}",
                                    help="Les hauteurs et positions sont calculées automatiquement pour remplir toute la zone (2mm entre tiroirs)."
                                ))
                                
                                # Choix : Encastré ou En applique
                                is_applique_current = bool(p.get('_applique_mode', False))
                                mount_type = st.selectbox(
                                    "Mode de montage LEGRABOX",
                                    options=['Encastré', 'En applique'],
                                    index=1 if is_applique_current else 0,
                                    key=f"pending_drawer_mount_type_{idx}",
                                    help="Encastré: tiroirs restent ENTRE les traverses | En applique: faces sortent du caisson"
                                )
                                p['_applique_mode'] = (mount_type == 'En applique')
                            
                            # Calculer la hauteur maximale disponible dans la zone sélectionnée
                            if p.get('zone_id') is not None and p['zone_id'] < len(all_zones_2d_sel):
                                zone = all_zones_2d_sel[p['zone_id']]
                                max_height_in_zone = zone['y_max'] - zone['y_min']
                            else:
                                dims = selected_cab['dims']
                                max_height_in_zone = dims['H_raw'] - dims['t_tb_raw'] * 2
                            
                        # Sélection du système (TANDEMBOX ou LÉGRABOX)
                        drawer_system = p.get('drawer_system', 'TANDEMBOX')
                        system_idx = 0 if drawer_system == 'TANDEMBOX' else 1
                        p['drawer_system'] = st.selectbox(
                            "Système de Tiroir",
                            options=['TANDEMBOX', 'LÉGRABOX'],
                            index=system_idx,
                            key=f"pending_drawer_system_{idx}",
                        )
                        
                        # Sélection du type selon le système
                        if p['drawer_system'] == 'LÉGRABOX':
                            tech_opts = ['N', 'M', 'K', 'C']
                        else:
                            tech_opts = ['K', 'M', 'N', 'D']
                        curr_tech = p.get('drawer_tech_type', 'K')
                        idx_tech = tech_opts.index(curr_tech) if curr_tech in tech_opts else 0
                        p['drawer_tech_type'] = st.selectbox(
                            f"Type ({p['drawer_system']})",
                            options=tech_opts,
                            index=idx_tech,
                            key=f"pending_drawer_tech_type_{idx}",
                        )
                        
                        if not is_stack_mode:
                            # Mode tiroir unique : on garde les champs manuels
                            face_h_default = float(p.get('drawer_face_H_raw', 150.0))
                            face_h_min = 50.0
                            face_h_max = float(max_height_in_zone)
                            face_h_value = max(face_h_min, min(face_h_default, face_h_max))
                            
                            p['drawer_face_H_raw'] = st.number_input(
                                "Hauteur Face (mm)",
                                value=face_h_value,
                                key=f"pending_drawer_face_H_raw_{idx}",
                                format="%.0f",
                                step=1.0,
                                min_value=face_h_min,
                                max_value=face_h_max,
                            )
                            
                            # Position Y du bas du tiroir dans la zone
                            if p.get('zone_id') is not None and p['zone_id'] < len(all_zones_2d_sel):
                                zone = all_zones_2d_sel[p['zone_id']]
                                bottom_offset_min = 0.0
                                bottom_offset_max = zone['y_max'] - zone['y_min'] - p['drawer_face_H_raw']
                            else:
                                dims = selected_cab['dims']
                                bottom_offset_min = 0.0
                                bottom_offset_max = dims['H_raw'] - dims['t_tb_raw'] * 2 - p['drawer_face_H_raw']
                            
                            bottom_offset_default = float(p.get('drawer_bottom_offset', 0.0))
                            bottom_offset_value = max(bottom_offset_min, min(bottom_offset_default, bottom_offset_max))
                            
                            p['drawer_bottom_offset'] = st.number_input(
                                "Position Y - Offset depuis le bas de la zone (mm)",
                                value=bottom_offset_value,
                                key=f"pending_drawer_bottom_offset_{idx}",
                                format="%.0f",
                                step=1.0,
                                min_value=bottom_offset_min,
                                max_value=bottom_offset_max,
                                help="Position verticale du bas du tiroir dans la zone sélectionnée"
                            )
                        
                        p['drawer_face_thickness'] = st.number_input(
                            "Épaisseur Face (mm)",
                            value=float(p.get('drawer_face_thickness', 19.0)),
                            key=f"pending_drawer_face_thickness_{idx}",
                            format="%.0f",
                            step=1.0,
                            min_value=10.0,
                        )
                        p['inner_thickness'] = st.number_input(
                            "Épaisseur Intérieur (dos/fond) (mm)",
                            value=float(p.get('inner_thickness', 16.0)),
                            key=f"pending_drawer_inner_thickness_{idx}",
                            format="%.0f",
                            step=1.0,
                            min_value=5.0,
                        )
                        p['drawer_gap'] = st.number_input(
                            "Jeu extérieur (mm)",
                            value=float(p.get('drawer_gap', 2.0)),
                            key=f"pending_drawer_gap_{idx}",
                            format="%.1f",
                            step=0.1,
                        )
                        p['drawer_handle_type'] = st.selectbox(
                            "Poignée",
                            options=['none', 'integrated_cutout'],
                            index=['none', 'integrated_cutout'].index(p.get('drawer_handle_type', 'none')),
                            format_func=lambda x: 'Aucune' if x=='none' else 'Intégrée (Découpe)',
                            key=f"pending_drawer_handle_type_{idx}",
                        )
                        if p.get('drawer_handle_type') == 'integrated_cutout':
                            p['drawer_handle_width'] = st.number_input(
                                "Largeur Poignée",
                                value=float(p.get('drawer_handle_width', 150.0)),
                                key=f"pending_drawer_handle_width_{idx}",
                                format="%.0f",
                                step=1.0,
                            )
                            p['drawer_handle_height'] = st.number_input(
                                "Hauteur Poignée",
                                value=float(p.get('drawer_handle_height', 40.0)),
                                key=f"pending_drawer_handle_height_{idx}",
                                format="%.0f",
                                step=1.0,
                            )
                            p['drawer_handle_offset_top'] = st.number_input(
                                "Offset Haut",
                                value=float(p.get('drawer_handle_offset_top', 10.0)),
                                key=f"pending_drawer_handle_offset_top_{idx}",
                                format="%.0f",
                                step=1.0,
                            )
                        p['material'] = st.text_input(
                            "Matière Face Tiroir",
                            value=p.get('material', 'Matière Tiroir'),
                            key=f"pending_drawer_material_{idx}",
                        )
                        p['material_inner'] = st.text_input(
                            "Matière Intérieur Tiroir (Dos/Fond)",
                            value=p.get('material_inner', p.get('material', 'Matière Tiroir')),
                            key=f"pending_drawer_material_inner_{idx}",
                        )
                        c_ok, c_cancel = st.columns(2)
                        if c_ok.button("Valider la position", key=f"pending_drawer_validate_{idx}", use_container_width=True, type="primary"):
                            selected_cab.setdefault('drawers', [])
                            stack_count = int(p.get('stack_count', 1)) if is_stack_mode else 1
                            # Cas 1 : tiroir unique (comportement identique à avant)
                            if (not is_stack_mode) or stack_count <= 1 or p.get('zone_id') is None or p['zone_id'] >= len(all_zones_2d_sel):
                                # Stocker les coordonnées de la zone avec le tiroir pour référence future
                                if p.get('zone_id') is not None:
                                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=True)
                                    if p['zone_id'] < len(all_zones_2d):
                                        zone = all_zones_2d[p['zone_id']]
                                        p['stored_zone_coords'] = {
                                            'x_min': zone['x_min'],
                                            'x_max': zone['x_max'],
                                            'y_min': zone['y_min'],
                                            'y_max': zone['y_max']
                                        }
                                selected_cab['drawers'].append(copy.deepcopy(p))
                            else:
                                # Cas 2 : empilement automatique de plusieurs tiroirs dans la zone
                                zone = all_zones_2d_sel[p['zone_id']]
                                dims = selected_cab['dims']
                                t_tb_mm = float(dims.get('t_tb_raw', 19.0))
                                H_raw = float(dims.get('H_raw', 1000.0))
                                
                                # Vérifier le mode (encastré ou appliqué)
                                is_applique = bool(p.get('_applique_mode', False))
                                
                                if is_applique:
                                    # Mode APPLIQUE : formule H_raw - n*2mm - 2x1mm (jeu de 1mm haut/bas)
                                    # Les faces dépassent du meuble et recouvrent les montants + 1mm de jeu de chaque côté
                                    n_junctions = stack_count - 1
                                    total_face_height = H_raw - (n_junctions * 2.0) - 2.0  # -2 pour les 2x1mm de jeu
                                    face_h = total_face_height / float(stack_count) if stack_count > 0 else 0.0
                                    if face_h < 10.0:
                                        face_h = 10.0
                                    # Position : début du caisson avec 1mm de jeu
                                    current_z_offset = -1.0  # Commence 1mm avant le bas (o[2])
                                else:
                                    # Mode ENCASTE : formule H_raw - 2*t_tb - 4mm - n*2mm
                                    # Les tiroirs restent à l'intérieur, avec marges
                                    n_junctions = stack_count - 1
                                    total_face_height = H_raw - 2.0 * t_tb_mm - 4.0 - (n_junctions * 2.0)
                                    face_h = total_face_height / float(stack_count) if stack_count > 0 else 0.0
                                    if face_h < 10.0:
                                        face_h = 10.0
                                    # Position du premier tiroir : 2mm après traverse basse
                                    current_z_offset = t_tb_mm + 2.0
                                
                                for k in range(stack_count):
                                    d_copy = copy.deepcopy(p)
                                    d_copy.pop('stack_count', None)
                                    d_copy.pop('_stack_mode', None)
                                    # GARDER _applique_mode pour que les tiroirs validés restent en applique
                                    
                                    d_copy['drawer_face_H_raw'] = face_h
                                    d_copy['drawer_bottom_offset'] = current_z_offset
                                    # Préparer offset pour próchain tiroir (hauteur + 2mm gap)
                                    current_z_offset += face_h + 2.0
                                    # Stocker les coordonnées de la zone pour ce tiroir
                                    d_copy['stored_zone_coords'] = {
                                        'x_min': zone['x_min'],
                                        'x_max': zone['x_max'],
                                        'y_min': zone['y_min'],
                                        'y_max': zone['y_max']
                                    }
                                    selected_cab['drawers'].append(d_copy)
                            st.session_state['pending_placement'] = None
                            st.rerun()
                        if c_cancel.button("Annuler", key=f"pending_drawer_cancel_{idx}", use_container_width=True):
                            st.session_state['pending_placement'] = None
                            st.rerun()
                    
                    # Afficher la liste des tiroirs existants
                    if 'drawers' in selected_cab and selected_cab['drawers']:
                        # Calculer toutes les zones 2D disponibles (SANS inclure les éléments sans zone_id)
                        all_zones_2d_drawers = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                        zone_options_drawers = [None] + [z['id'] for z in all_zones_2d_drawers]
                        zone_labels_drawers = ["Tout le caisson"] + [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_drawers]
                        
                        for i, d in enumerate(selected_cab['drawers']):
                            current_zone = d.get('zone_id', None)
                            zone_index = zone_options_drawers.index(current_zone) if current_zone in zone_options_drawers else 0
                            
                            with st.expander(f"⚙️ Tiroir {i+1}"):
                                # Sélection de zone
                                if len(all_zones_2d_drawers) > 1:
                                    st.selectbox(
                                        "Zone d'emplacement",
                                        options=zone_options_drawers,
                                        index=zone_index,
                                        format_func=lambda x: zone_labels_drawers[zone_options_drawers.index(x)] if x in zone_options_drawers else "Tout le caisson",
                                        key=f"drawer_zone_{idx}_{i}",
                                        on_change=lambda x=i: update_drawer_prop(x, 'zone_id')
                                    )
                                    
                                    # Si une zone est sélectionnée, afficher les limites de la zone
                                    if current_zone is not None and current_zone < len(all_zones_2d_drawers):
                                        zone = all_zones_2d_drawers[current_zone]
                                        st.caption(f"Zone sélectionnée : Largeur X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm, Hauteur Y = {zone['y_min']:.0f}-{zone['y_max']:.0f}mm")
                                
                                # Sélection du système (TANDEMBOX ou LÉGRABOX)
                                drawer_system = d.get('drawer_system', 'TANDEMBOX')
                                system_idx = 0 if drawer_system == 'TANDEMBOX' else 1
                                st.selectbox(
                                    "Système de Tiroir",
                                    options=['TANDEMBOX', 'LÉGRABOX'],
                                    index=system_idx,
                                    key=f"drawer_system_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_system')
                                )
                                
                                # Sélection du type selon le système
                                if drawer_system == 'LÉGRABOX':
                                    tech_opts = ['N', 'M', 'K', 'C']
                                else:
                                    tech_opts = ['K', 'M', 'N', 'D']
                                curr_tech = d.get('drawer_tech_type', 'K')
                                idx_tech = tech_opts.index(curr_tech) if curr_tech in tech_opts else 0
                                st.selectbox(
                                    f"Type ({drawer_system})",
                                    options=tech_opts,
                                    index=idx_tech,
                                    key=f"drawer_tech_type_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_tech_type')
                                )
                                
                                st.number_input(
                                    "Hauteur Face (mm)",
                                    value=d.get('drawer_face_H_raw', 150.0),
                                    key=f"drawer_face_H_raw_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_face_H_raw'),
                                    format="%.0f",
                                    step=1.0,
                                )
                                st.number_input(
                                    "Position Y - Offset depuis le bas de la zone (mm)",
                                    value=d.get('drawer_bottom_offset', 0.0),
                                    key=f"drawer_bottom_offset_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_bottom_offset'),
                                    format="%.0f",
                                    step=1.0,
                                    help="Position verticale du bas du tiroir dans la zone sélectionnée"
                                )
                                st.number_input(
                                    "Épaisseur Face (mm)",
                                    value=d.get('drawer_face_thickness', 19.0),
                                    key=f"drawer_face_thickness_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_face_thickness'),
                                    format="%.0f",
                                    step=1.0,
                                )
                                st.number_input(
                                    "Jeu extérieur (mm)",
                                    value=d.get('drawer_gap', 2.0),
                                    key=f"drawer_gap_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_gap'),
                                    format="%.1f",
                                    step=0.1,
                                )
                                st.number_input(
                                    "Épaisseur Intérieur (dos/fond) (mm)",
                                    value=d.get('inner_thickness', 16.0),
                                    key=f"drawer_inner_thickness_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'inner_thickness'),
                                    format="%.0f",
                                    step=1.0,
                                )
                                st.selectbox(
                                    "Poignée",
                                    options=['none', 'integrated_cutout'],
                                    index=['none', 'integrated_cutout'].index(d.get('drawer_handle_type', 'none')),
                                    format_func=lambda x: 'Aucune' if x=='none' else 'Intégrée (Découpe)',
                                    key=f"drawer_handle_type_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'drawer_handle_type')
                                )
                                if d.get('drawer_handle_type') == 'integrated_cutout':
                                    st.number_input(
                                        "Largeur Poignée",
                                        value=d.get('drawer_handle_width', 150.0),
                                        key=f"drawer_handle_width_{idx}_{i}",
                                        on_change=lambda x=i: update_drawer_prop(x, 'drawer_handle_width'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                    st.number_input(
                                        "Hauteur Poignée",
                                        value=d.get('drawer_handle_height', 40.0),
                                        key=f"drawer_handle_height_{idx}_{i}",
                                        on_change=lambda x=i: update_drawer_prop(x, 'drawer_handle_height'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                    st.number_input(
                                        "Offset Haut",
                                        value=d.get('drawer_handle_offset_top', 10.0),
                                        key=f"drawer_handle_offset_top_{idx}_{i}",
                                        on_change=lambda x=i: update_drawer_prop(x, 'drawer_handle_offset_top'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                st.text_input(
                                    "Matière Face Tiroir",
                                    value=d.get('material', 'Matière Tiroir'),
                                    key=f"drawer_material_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_material(x)
                                )
                                st.text_input(
                                    "Matière Intérieur Tiroir (Dos/Fond)",
                                    value=d.get('material_inner', d.get('material', 'Matière Tiroir')),
                                    key=f"drawer_material_inner_{idx}_{i}",
                                    on_change=lambda x=i: update_drawer_prop(x, 'material_inner')
                                )
                                st.button("Supprimer ce tiroir 🗑️", key=f"del_drawer_{idx}_{i}", on_click=lambda x=i: delete_drawer_callback(x))

                with t_sh:
                    st.markdown("#### Configuration des Étagères")
                    st.button("Ajouter une étagère au Caisson", key=f"add_shelf_{idx}", on_click=add_shelf_callback)
                    
                    # --- POSE EN 2 TEMPS (APERÇU -> VALIDER) : ÉTAGÈRE ---
                    pending = st.session_state.get('pending_placement')
                    if pending and pending.get('cabinet_index') == idx and pending.get('kind') == 'shelf':
                        p = pending.get('props', {})
                        st.warning("Pose en cours : l'étagère est en prévisualisation. Cliquez sur **Valider la position** pour la poser définitivement.")
                        with st.expander("✅ Valider la position (Étagère)"):
                            all_zones_2d_sel = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                            zone_options = [None] + [z['id'] for z in all_zones_2d_sel]
                            zone_labels = ["Tout le caisson"] + [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_sel]
                            current_zone = p.get('zone_id', None)
                            zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                            p['zone_id'] = st.selectbox(
                                "Zone d'emplacement",
                                options=zone_options,
                                index=zone_index,
                                format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Tout le caisson",
                                key=f"pending_shelf_zone_{idx}",
                            )
                            p['shelf_type'] = st.selectbox(
                                "Type",
                                options=['mobile', 'fixe'],
                                index=0 if p.get('shelf_type', 'mobile') == 'mobile' else 1,
                                format_func=lambda x: 'Mobile (Taquets)' if x=='mobile' else 'Fixe',
                                key=f"pending_shelf_type_{idx}",
                            )
                            # Clamping pour éviter StreamlitAPIException
                            height_default = float(p.get('height', 200.0))
                            height_min = 0.0
                            height_max = float(selected_cab['dims']['H_raw'] - selected_cab['dims']['t_tb_raw'] * 2)
                            height_value = max(height_min, min(height_default, height_max))
                            
                            p['height'] = st.number_input(
                                "Position Y - Hauteur (mm depuis traverse inférieure)",
                                value=height_value,
                                key=f"pending_shelf_height_{idx}",
                                format="%.0f",
                                step=1.0,
                                min_value=height_min,
                                max_value=height_max,
                            )
                            p['thickness'] = st.number_input(
                                "Épaisseur (mm)",
                                value=float(p.get('thickness', 19.0)),
                                key=f"pending_shelf_thickness_{idx}",
                                format="%.0f",
                                step=1.0,
                                min_value=10.0,
                            )
                            p['material'] = st.text_input(
                                "Matière",
                                value=p.get('material', 'Matière Étagère'),
                                key=f"pending_shelf_material_{idx}",
                            )
                            c_ok, c_cancel = st.columns(2)
                            if c_ok.button("Valider la position", key=f"pending_shelf_validate_{idx}", use_container_width=True, type="primary"):
                                selected_cab.setdefault('shelves', [])
                                # Stocker les coordonnées de la zone ET la largeur/position calculées avec l'étagère
                                if p.get('zone_id') is not None:
                                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=True)
                                    if p['zone_id'] < len(all_zones_2d):
                                        zone = all_zones_2d[p['zone_id']]
                                        p['stored_zone_coords'] = {
                                            'x_min': zone['x_min'],
                                            'x_max': zone['x_max'],
                                            'y_min': zone['y_min'],
                                            'y_max': zone['y_max']
                                        }
                                        # Calculer et stocker la largeur et la position X de l'étagère
                                        # pour qu'elles ne changent jamais, même si les zones sont recalculées
                                        s_type = p.get('shelf_type', 'mobile')
                                        zone_width_mm = zone['x_max'] - zone['x_min']
                                        # IMPORTANT : plus aucun jeu visuel entre étagère et montants
                                        # On colle l'étagère exactement entre les limites X de la zone
                                        if s_type == 'mobile':
                                            stored_shelf_width_mm = zone_width_mm
                                            stored_shelf_x_start_mm = zone['x_min']
                                        else:
                                            stored_shelf_width_mm = zone_width_mm
                                            stored_shelf_x_start_mm = zone['x_min']
                                        
                                        p['stored_shelf_width_mm'] = stored_shelf_width_mm
                                        p['stored_shelf_x_start_mm'] = stored_shelf_x_start_mm
                                selected_cab['shelves'].append(copy.deepcopy(p))
                                st.session_state['pending_placement'] = None
                                st.rerun()
                            if c_cancel.button("Annuler", key=f"pending_shelf_cancel_{idx}", use_container_width=True):
                                st.session_state['pending_placement'] = None
                                st.rerun()
                    if 'shelves' in selected_cab:
                        # Calculer toutes les zones 2D disponibles (SANS inclure les éléments sans zone_id)
                        # Pour le choix de zone, on veut voir les zones existantes AVANT le placement
                        all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                        zone_options = [None] + [z['id'] for z in all_zones_2d]
                        zone_labels = ["Tout le caisson"] + [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d]
                        
                        for i, s in enumerate(selected_cab['shelves']):
                            s_type = s.get('shelf_type', 'mobile')
                            current_zone = s.get('zone_id', None)
                            zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                            
                            with st.expander(f"⚙️ Étagère {i+1} ({'Mobile' if s_type=='mobile' else 'Fixe'})"):
                                # Sélection de zone (parmi les zones existantes AVANT placement)
                                if len(all_zones_2d) > 1:
                                    st.selectbox(
                                        "Zone d'emplacement",
                                        options=zone_options,
                                        index=zone_index,
                                        format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Tout le caisson",
                                        key=f"shelf_zone_{idx}_{i}",
                                        on_change=lambda x=i: update_shelf_prop(x, 'zone_id')
                                    )
                                    
                                    # Si une zone est sélectionnée, afficher les limites de la zone
                                    if current_zone is not None and current_zone < len(all_zones_2d):
                                        zone = all_zones_2d[current_zone]
                                        st.caption(f"Zone sélectionnée : Largeur X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm, Hauteur Y = {zone['y_min']:.0f}-{zone['y_max']:.0f}mm")
                                
                                st.selectbox("Type", options=['mobile', 'fixe'], index=0 if s_type=='mobile' else 1, format_func=lambda x: 'Mobile (Taquets)' if x=='mobile' else 'Fixe', key=f"shelf_t_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'shelf_type'))
                                st.number_input("Position Y - Hauteur (mm depuis traverse inférieure)", value=s['height'], key=f"shelf_h_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'height'), format="%.0f", step=1.0, help="Hauteur de l'étagère dans la zone (modifiable)")
                                st.number_input("Épaisseur (mm)", value=s['thickness'], key=f"shelf_e_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'thickness'), format="%.0f", step=1.0)
                                st.text_input("Matière", value=s.get('material', 'Matière Étagère'), key=f"shelf_m_{idx}_{i}", on_change=lambda x=i: update_shelf_material(x, 'material'))
                                if s_type == 'mobile':
                                    st.selectbox("Motif Trous", options=['full_height', '5_holes_centered', 'custom_n_m'], index=['full_height', '5_holes_centered', 'custom_n_m'].index(s.get('mobile_machining_type', 'full_height')), format_func=lambda x: {'full_height':'Toute hauteur', '5_holes_centered':'5 Trous Centrés', 'custom_n_m':'Personnalisé'}.get(x, x), key=f"shelf_m_type_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'mobile_machining_type'))
                                    if s.get('mobile_machining_type') == 'custom_n_m':
                                        st.number_input("Trous au-dessus (N)", value=s.get('custom_holes_above', 0), key=f"shelf_c_above_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'custom_holes_above'), step=1)
                                        st.number_input("Trous en-dessous (M)", value=s.get('custom_holes_below', 0), key=f"shelf_c_below_{idx}_{i}", on_change=lambda x=i: update_shelf_prop(x, 'custom_holes_below'), step=1)
                                st.button("Supprimer cette étagère 🗑️", key=f"del_shelf_{idx}_{i}", on_click=lambda x=i: delete_shelf_callback(x))
                    
                    # --- SECTION DEBUG : MONTANTS ASSEMBLÉS ---
                    st.markdown("---")
                    with st.expander("🔍 Debug : Montants assemblés aux éléments", expanded=False):
                        st.caption("Cette section affiche quels montants sont assemblés à chaque élément posé dans le caisson.")
                        
                        # Calculer toutes les zones 2D
                        all_zones_2d_debug = calculate_all_zones_2d(selected_cab, include_all_elements=True)
                        dims = selected_cab['dims']
                        L_raw = dims['L_raw']
                        t_lr = dims['t_lr_raw']
                        
                        # Fonction helper pour déterminer les montants touchés par un élément
                        def get_touching_uprights(element, element_type='shelf'):
                            """Retourne la liste des montants touchés par un élément"""
                            touching = []
                            zone_id = element.get('zone_id', None)
                            
                            # IMPORTANT : Utiliser les LIMITES DE LA ZONE pour détecter les montants (même logique que l'usinage)
                            zone_x_min = None
                            zone_x_max = None
                            
                            if element_type == 'shelf':
                                # Pour les étagères, utiliser stored_zone_coords si disponible, sinon la zone calculée
                                if element.get('stored_zone_coords'):
                                    zone_x_min = element['stored_zone_coords']['x_min']
                                    zone_x_max = element['stored_zone_coords']['x_max']
                                elif zone_id is not None and zone_id < len(all_zones_2d_debug):
                                    zone = all_zones_2d_debug[zone_id]
                                    zone_x_min = zone['x_min']
                                    zone_x_max = zone['x_max']
                            elif element_type == 'drawer':
                                # Pour les tiroirs, utiliser la zone avec les gaps
                                if zone_id is not None and zone_id < len(all_zones_2d_debug):
                                    zone = all_zones_2d_debug[zone_id]
                                    drawer_gap = element.get('drawer_gap', 2.0)
                                    zone_x_min = zone['x_min'] + drawer_gap
                                    zone_x_max = zone['x_max'] - drawer_gap
                            
                            if zone_x_min is None or zone_x_max is None:
                                # Élément sur tout le caisson : touche les deux montants principaux
                                touching.append("Montant Principal Gauche (Mg)")
                                touching.append("Montant Principal Droit (Md)")
                                return touching
                            
                            # Vérifier les montants principaux
                            if abs(zone_x_min - t_lr) < 1.0:
                                touching.append("Montant Principal Gauche (Mg)")
                            if abs(zone_x_max - (L_raw - t_lr)) < 1.0:
                                touching.append("Montant Principal Droit (Md)")
                            
                            # Vérifier les montants secondaires
                            if 'vertical_dividers' in selected_cab:
                                for div_idx, div in enumerate(selected_cab['vertical_dividers']):
                                    div_x = div['position_x']
                                    div_th = div.get('thickness', 19.0)
                                    div_left_edge = div_x - div_th / 2.0
                                    div_right_edge = div_x + div_th / 2.0
                                    
                                    # Élément touche la face GAUCHE si la zone se termine au bord gauche du montant
                                    touches_left_face = abs(zone_x_max - div_left_edge) < 1.0
                                    # Élément touche la face DROITE si la zone commence au bord droit du montant
                                    touches_right_face = abs(zone_x_min - div_right_edge) < 1.0
                                    
                                    if touches_left_face:
                                        touching.append(f"Montant Secondaire {div_idx+1} - Face Gauche (1/2)")
                                    if touches_right_face:
                                        touching.append(f"Montant Secondaire {div_idx+1} - Face Droite (2/2)")
                            
                            return touching if touching else ["⚠️ Aucun montant détecté"]
                        
                        # Afficher pour chaque étagère
                        if 'shelves' in selected_cab and selected_cab['shelves']:
                            st.markdown("**Étagères :**")
                            for i, s in enumerate(selected_cab['shelves']):
                                s_type = s.get('shelf_type', 'mobile')
                                touching = get_touching_uprights(s, 'shelf')
                                zone_id = s.get('zone_id', None)
                                zone_info = f"Zone {zone_id}" if zone_id is not None else "Tout le caisson"
                                
                                st.markdown(f"- **Étagère {i+1}** ({'Mobile' if s_type=='mobile' else 'Fixe'}, {zone_info}):")
                                for mt in touching:
                                    st.markdown(f"  • {mt}")
                        
                        # Afficher pour tous les tiroirs
                        if 'drawers' in selected_cab and selected_cab['drawers']:
                            st.markdown("**Tiroirs :**")
                            for drawer_idx, drawer in enumerate(selected_cab['drawers']):
                                touching = get_touching_uprights(drawer, 'drawer')
                                zone_id = drawer.get('zone_id', None)
                                zone_info = f"Zone {zone_id}" if zone_id is not None else "Tout le caisson"
                                
                                st.markdown(f"- **Tiroir {drawer_idx+1}** ({zone_info}):")
                                for mt in touching:
                                    st.markdown(f"  • {mt}")

                with t_div:
                    st.markdown("#### Montants Verticaux Secondaires (Séparations)")
                    st.info("Les montants secondaires divisent le caisson en plusieurs zones. Les étagères, portes et tiroirs peuvent être assignés à des zones spécifiques.")
                    c_div_add1, c_div_add2 = st.columns(2)
                    c_div_add1.button("➕ Ajouter un Montant Secondaire", key=f"add_divider_{idx}", on_click=add_vertical_divider_callback, use_container_width=True)
                    c_div_add2.button("➕ Double Montants Secondaires", key=f"add_double_divider_{idx}", on_click=add_vertical_divider_double_callback, use_container_width=True)
                    
                    # --- POSE EN 2 TEMPS (APERÇU -> VALIDER) : MONTANT SECONDAIRE ---
                    pending = st.session_state.get('pending_placement')
                    if pending and pending.get('cabinet_index') == idx and pending.get('kind') in ('vertical_divider', 'vertical_divider_double'):
                        p = pending.get('props', {})
                        is_double = pending.get('kind') == 'vertical_divider_double' or bool(p.get('double'))
                        txt_title = "✅ Valider la position (Double montant secondaire)" if is_double else "✅ Valider la position (Montant secondaire)"
                        st.warning("Pose en cours : le montant secondaire est en prévisualisation. Cliquez sur **Valider la position** pour le poser définitivement.")
                        with st.expander(txt_title):
                            existing_count = len(selected_cab.get('vertical_dividers', []))
                            is_first = (existing_count == 0)
                            all_zones_2d_sel = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                            
                            if is_first:
                                p['zone_id'] = None
                                st.info("💡 Premier montant : placement libre (il créera ensuite 2 zones).")
                            else:
                                zone_options = [z['id'] for z in all_zones_2d_sel] if all_zones_2d_sel else []
                                zone_labels = [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_sel]
                                if zone_options:
                                    current_zone = p.get('zone_id', zone_options[0])
                                    zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                                    p['zone_id'] = st.selectbox(
                                        "Zone d'emplacement",
                                        options=zone_options,
                                        index=zone_index,
                                        format_func=lambda x: zone_labels[zone_options.index(x)],
                                        key=f"pending_divider_zone_{idx}",
                                    )
                            
                            dims = selected_cab['dims']
                            min_x = float(dims['t_lr_raw'] + 50)
                            max_x = float(dims['L_raw'] - dims['t_lr_raw'] - 50)

                            # Option de placement : manuel ou milieu de la zone (pour les doubles)
                            placement_mode = "Milieu de la zone" if (is_double and p.get('zone_id') is not None) else "Manuel"
                            if is_double:
                                placement_mode = st.radio(
                                    "Position X",
                                    options=["Manuel", "Milieu de la zone"],
                                    index=1 if p.get('zone_id') is not None else 0,
                                    key=f"pending_divider_place_mode_{idx}",
                                )

                            if is_double and placement_mode == "Milieu de la zone" and p.get('zone_id') is not None and all_zones_2d_sel:
                                # Centre automatiquement le double montant au milieu de la zone choisie
                                z_mid = next((z for z in all_zones_2d_sel if z['id'] == p['zone_id']), None)
                                if z_mid:
                                    p['position_x'] = (z_mid['x_min'] + z_mid['x_max']) / 2.0
                                    st.info(f"Position X au milieu de la zone sélectionnée (X ≈ {p['position_x']:.0f} mm).")
                            else:
                                p['position_x'] = st.number_input(
                                    "Position X (mm depuis le montant gauche)",
                                    value=float(p.get('position_x', (min_x + max_x) / 2.0)),
                                    key=f"pending_divider_position_x_{idx}",
                                    format="%.0f",
                                    step=1.0,
                                    min_value=min_x,
                                    max_value=max_x,
                                )
                            p['thickness'] = st.number_input(
                                "Épaisseur (mm)",
                                value=float(p.get('thickness', 19.0)),
                                key=f"pending_divider_thickness_{idx}",
                                format="%.0f",
                                step=1.0,
                                min_value=10.0,
                            )
                            p['material'] = st.text_input(
                                "Matière",
                                value=p.get('material', 'Matière Corps'),
                                key=f"pending_divider_material_{idx}",
                            )
                            c_ok, c_cancel = st.columns(2)
                            if c_ok.button("Valider la position", key=f"pending_divider_validate_{idx}", use_container_width=True, type="primary"):
                                selected_cab.setdefault('vertical_dividers', [])
                                # Stocker les coordonnées de la zone avec le montant pour référence future
                                stored_zone = None
                                if p.get('zone_id') is not None:
                                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=True)
                                    if p['zone_id'] < len(all_zones_2d):
                                        stored_zone = all_zones_2d[p['zone_id']]
                                if is_double:
                                    # Créer 2 montants côte à côte sans jeu
                                    # center_x est le centre de l'ensemble du double montant
                                    center_x = float(p.get('position_x', (min_x + max_x) / 2.0))
                                    th = float(p.get('thickness', 19.0))
                                    # Pour centrer l'ensemble : le premier panneau commence à center_x - thickness
                                    # et le deuxième commence à center_x (ils sont collés)
                                    pos_left = center_x - th
                                    pos_right = center_x
                                    for px in (pos_left, pos_right):
                                        d_copy = copy.deepcopy(p)
                                        d_copy['position_x'] = px
                                        d_copy.pop('double', None)
                                        if stored_zone is not None:
                                            d_copy['stored_zone_coords'] = {
                                                'x_min': stored_zone['x_min'],
                                                'x_max': stored_zone['x_max'],
                                                'y_min': stored_zone['y_min'],
                                                'y_max': stored_zone['y_max']
                                            }
                                        selected_cab['vertical_dividers'].append(d_copy)
                                else:
                                    if stored_zone is not None:
                                        p['stored_zone_coords'] = {
                                            'x_min': stored_zone['x_min'],
                                            'x_max': stored_zone['x_max'],
                                            'y_min': stored_zone['y_min'],
                                            'y_max': stored_zone['y_max']
                                        }
                                    selected_cab['vertical_dividers'].append(copy.deepcopy(p))
                                st.session_state['pending_placement'] = None
                                st.rerun()
                            if c_cancel.button("Annuler", key=f"pending_divider_cancel_{idx}", use_container_width=True):
                                st.session_state['pending_placement'] = None
                                st.rerun()
                    
                    # Calculer toutes les zones 2D (X et Y combinés) - SANS inclure les éléments sans zone_id
                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                    st.markdown("##### Zones disponibles :")
                    for zone in all_zones_2d:
                        st.caption(f"{zone['label']}: X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm, Y = {zone['y_min']:.0f}-{zone['y_max']:.0f}mm")
                    
                    if 'vertical_dividers' in selected_cab and selected_cab['vertical_dividers']:
                        for i, div in enumerate(selected_cab['vertical_dividers']):
                            with st.expander(f"🔧 Montant Secondaire {i+1}"):
                                # Le premier montant (i == 0) peut toujours être placé librement dans la Zone 0 originale
                                # Les montants suivants doivent être placés dans une zone existante
                                is_first_divider = (i == 0)
                                
                                if is_first_divider:
                                    # Premier montant : pas de sélection de zone, placement libre dans Zone 0 originale
                                    st.info("💡 Premier montant : vous pouvez le placer librement dans tout le caisson (Zone 0). Il créera ensuite 2 zones.")
                                    # S'assurer que zone_id est None pour le premier montant
                                    if div.get('zone_id') is not None:
                                        div['zone_id'] = None
                                else:
                                    # Montants suivants : sélection de zone
                                    current_zone_id = div.get('zone_id', None)
                                    zone_options = [z['id'] for z in all_zones_2d]
                                    zone_labels = [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d]
                                    zone_index = zone_options.index(current_zone_id) if current_zone_id in zone_options else 0
                                    
                                    selected_zone_id = st.selectbox(
                                        "Zone d'emplacement",
                                        options=zone_options,
                                        index=zone_index,
                                        format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Zone inconnue",
                                        key=f"divider_zone_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_divider_prop(x, 'zone_id')
                                    )
                                    
                                    # Ne PAS ajuster automatiquement - l'utilisateur doit placer manuellement
                                    if selected_zone_id < len(all_zones_2d):
                                        zone = all_zones_2d[selected_zone_id]
                                        # Afficher les limites de la zone mais ne pas modifier la position
                                        st.caption(f"Zone sélectionnée : X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm (largeur: {zone['x_max'] - zone['x_min']:.0f}mm)")
                                
                                st.number_input(
                                    "Position X (mm depuis le montant gauche)",
                                    value=div['position_x'],
                                    key=f"divider_position_x_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_divider_prop(x, 'position_x'),
                                    format="%.0f",
                                    step=1.0,
                                    min_value=float(selected_cab['dims']['t_lr_raw'] + 50),
                                    max_value=float(selected_cab['dims']['L_raw'] - selected_cab['dims']['t_lr_raw'] - 50),
                                    help="Position du montant dans le caisson" if is_first_divider else "Ajustement fin de la position"
                                )
                                st.number_input(
                                    "Épaisseur (mm)",
                                    value=div['thickness'],
                                    key=f"divider_thickness_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_divider_prop(x, 'thickness'),
                                    format="%.0f",
                                    step=1.0,
                                    min_value=10.0
                                )
                                st.text_input(
                                    "Matière",
                                    value=div.get('material', 'Matière Corps'),
                                    key=f"divider_material_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_divider_material(x)
                                )
                                st.button(
                                    "🗑️ Supprimer ce montant",
                                    key=f"del_divider_{idx}_{i}",
                                    on_click=lambda x=i: delete_vertical_divider_callback(x),
                                    use_container_width=True
                                )
                    
                    st.markdown("---")
                    st.markdown("#### Étagères Verticales")
                    st.info("Les étagères verticales créent des séparations partielles (pas de la traverse inf à la traverse sup). Elles peuvent lier étagère/traverse, traverse/étagère ou étagère/étagère.")
                    st.button("➕ Ajouter une Étagère Verticale", key=f"add_vertical_shelf_{idx}", on_click=add_vertical_shelf_callback, use_container_width=True)
                    
                    # --- POSE EN 2 TEMPS (APERÇU -> VALIDER) : ÉTAGÈRE VERTICALE ---
                    pending = st.session_state.get('pending_placement')
                    if pending and pending.get('cabinet_index') == idx and pending.get('kind') == 'vertical_shelf':
                        p = pending.get('props', {})
                        st.warning("Pose en cours : l'étagère verticale est en prévisualisation. Cliquez sur **Valider la position** pour la poser définitivement.")
                        with st.expander("✅ Valider la position (Étagère verticale)"):
                            all_zones_2d_sel = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                            if all_zones_2d_sel:
                                zone_options = [z['id'] for z in all_zones_2d_sel]
                                zone_labels = [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_sel]
                                current_zone = p.get('zone_id', zone_options[0])
                                zone_index = zone_options.index(current_zone) if current_zone in zone_options else 0
                                p['zone_id'] = st.selectbox(
                                    "Zone d'emplacement",
                                    options=zone_options,
                                    index=zone_index,
                                    format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Zone inconnue",
                                    key=f"pending_vs_zone_{idx}",
                                )
                                # Pendant la pose, on cale Y sur la zone sélectionnée (prévisualisation)
                                zone = all_zones_2d_sel[zone_index]
                                # S'assurer que les valeurs sont dans les limites valides avec clamping
                                dims = selected_cab['dims']
                                zone_y_min = float(zone['y_min'])
                                zone_y_max = float(zone['y_max'])
                                
                                # Calculer l'espace disponible entre les planches horizontales en tenant compte des épaisseurs
                                vs_thickness = float(p.get('thickness', 19.0))
                                position_x = float(p.get('position_x', (zone['x_min'] + zone['x_max']) / 2.0))
                                available_spaces, blocking_shelves = calculate_available_space_between_horizontal_shelves(
                                    selected_cab, zone['x_min'], zone['x_max'], position_x, vs_thickness
                                )
                                
                                # Trouver l'espace disponible qui correspond à la zone Y
                                matching_space = None
                                for space in available_spaces:
                                    if space['y_min'] <= zone_y_min and space['y_max'] >= zone_y_max:
                                        matching_space = space
                                        break
                                
                                if matching_space:
                                    # Utiliser les faces intérieures des planches comme limites
                                    bottom_y_min = max(0.0, matching_space['y_min_face'])
                                    bottom_y_max = min(float(dims['H_raw'] - 50), matching_space['y_max_face'])
                                    p['bottom_y'] = max(bottom_y_min, min(zone_y_min, bottom_y_max))
                                    top_y_min = float(p['bottom_y'] + 50)
                                    top_y_max = min(float(dims['H_raw']), matching_space['y_max_face'])
                                    p['top_y'] = max(top_y_min, min(zone_y_max, top_y_max))
                                else:
                                    # Fallback : utiliser les limites de la zone avec clamping
                                    bottom_y_min = 0.0
                                    bottom_y_max = float(dims['H_raw'] - 50)
                                    p['bottom_y'] = max(bottom_y_min, min(zone_y_min, bottom_y_max))
                                    top_y_min = float(p['bottom_y'] + 50)
                                    top_y_max = float(dims['H_raw'])
                                    p['top_y'] = max(top_y_min, min(zone_y_max, top_y_max))
                                
                                st.info(f"Hauteur Y : {p['bottom_y']:.0f}mm à {p['top_y']:.0f}mm (déterminée par la zone pendant la pose).")
                            else:
                                p['zone_id'] = None
                            
                            dims = selected_cab['dims']
                            # Retirer toutes les contraintes min/max pour éviter les erreurs StreamlitAPIException
                            # L'utilisateur peut entrer n'importe quelle valeur
                            p['thickness'] = st.number_input(
                                "Épaisseur (mm)",
                                value=float(p.get('thickness', 19.0)),
                                key=f"pending_vs_thickness_{idx}",
                                format="%.0f",
                                step=1.0,
                            )
                            p['position_x'] = st.number_input(
                                "Position X (mm depuis le montant gauche)",
                                value=float(p.get('position_x', 300.0)),
                                key=f"pending_vs_position_x_{idx}",
                                format="%.0f",
                                step=1.0,
                            )
                            # Si aucune zone n'est sélectionnée, permettre la saisie libre de bottom_y et top_y
                            if p.get('zone_id', None) is None:
                                p['bottom_y'] = st.number_input(
                                    "Position Y Bas - Hauteur bas (mm depuis traverse inférieure)",
                                    value=float(p.get('bottom_y', 100.0)),
                                    key=f"pending_vs_bottom_y_{idx}",
                                    format="%.0f",
                                    step=1.0,
                                )
                                
                                p['top_y'] = st.number_input(
                                    "Position Y Haut - Hauteur haut (mm depuis traverse inférieure)",
                                    value=float(p.get('top_y', float(p.get('bottom_y', 100.0)) + 200.0)),
                                    key=f"pending_vs_top_y_{idx}",
                                    format="%.0f",
                                    step=1.0,
                                )
                            
                            p['material'] = st.text_input(
                                "Matière",
                                value=p.get('material', 'Matière Corps'),
                                key=f"pending_vs_material_{idx}",
                            )
                            c_ok, c_cancel = st.columns(2)
                            if c_ok.button("Valider la position", key=f"pending_vs_validate_{idx}", use_container_width=True, type="primary"):
                                selected_cab.setdefault('vertical_shelves', [])
                                # Stocker les coordonnées de la zone avec l'étagère verticale pour référence future
                                if p.get('zone_id') is not None:
                                    all_zones_2d = calculate_all_zones_2d(selected_cab, include_all_elements=True)
                                    if p['zone_id'] < len(all_zones_2d):
                                        zone = all_zones_2d[p['zone_id']]
                                        p['stored_zone_coords'] = {
                                            'x_min': zone['x_min'],
                                            'x_max': zone['x_max'],
                                            'y_min': zone['y_min'],
                                            'y_max': zone['y_max']
                                        }
                                selected_cab['vertical_shelves'].append(copy.deepcopy(p))
                                st.session_state['pending_placement'] = None
                                st.rerun()
                            if c_cancel.button("Annuler", key=f"pending_vs_cancel_{idx}", use_container_width=True):
                                st.session_state['pending_placement'] = None
                                st.rerun()
                    
                    if 'vertical_shelves' in selected_cab and selected_cab['vertical_shelves']:
                        for i, vs in enumerate(selected_cab['vertical_shelves']):
                            with st.expander(f"📐 Étagère Verticale {i+1}"):
                                # Calculer les zones disponibles (SANS inclure les éléments sans zone_id)
                                all_zones_2d_for_selection = calculate_all_zones_2d(selected_cab, include_all_elements=False)
                                
                                # Sélection de la zone 2D (parmi les zones existantes AVANT placement)
                                current_zone_id = vs.get('zone_id', None)
                                zone_options = [z['id'] for z in all_zones_2d_for_selection]
                                zone_labels = [f"{z['label']} (X:{z['x_min']:.0f}-{z['x_max']:.0f}mm, Y:{z['y_min']:.0f}-{z['y_max']:.0f}mm)" for z in all_zones_2d_for_selection]
                                zone_index = zone_options.index(current_zone_id) if current_zone_id in zone_options else 0
                                
                                selected_zone_id = st.selectbox(
                                    "Zone d'emplacement",
                                    options=zone_options,
                                    index=zone_index,
                                    format_func=lambda x: zone_labels[zone_options.index(x)] if x in zone_options else "Zone inconnue",
                                    key=f"vertical_shelf_zone_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_shelf_prop(x, 'zone_id')
                                )
                                
                                # Si une zone est sélectionnée, afficher les limites mais NE PAS modifier les positions stockées
                                # Les éléments validés gardent leurs positions fixes
                                if selected_zone_id is not None and selected_zone_id < len(all_zones_2d_for_selection):
                                    zone = all_zones_2d_for_selection[selected_zone_id]
                                    # Afficher les limites de la zone
                                    st.caption(f"Zone sélectionnée : X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm, Y = {zone['y_min']:.0f}-{zone['y_max']:.0f}mm")
                                    
                                    # NE PAS modifier les positions stockées pour les éléments validés
                                    # Les positions sont modifiables uniquement via les number_input ci-dessous
                                    vs_th = vs.get('thickness', 19.0)
                                    min_x_in_zone = zone['x_min'] + vs_th / 2.0  # Au moins la moitié de l'épaisseur depuis le bord gauche
                                    max_x_in_zone = zone['x_max'] - vs_th / 2.0  # Au moins la moitié de l'épaisseur depuis le bord droit
                                    
                                    # Retirer toutes les contraintes min/max pour éviter les erreurs StreamlitAPIException
                                    # L'utilisateur peut entrer n'importe quelle valeur
                                    st.number_input(
                                        "Position X (mm depuis le montant gauche) - Déplacement gauche/droite",
                                        value=float(vs['position_x']),
                                        key=f"vertical_shelf_position_x_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'position_x'),
                                        format="%.0f",
                                        step=1.0,
                                        help=f"Zone sélectionnée : X = {zone['x_min']:.0f}-{zone['x_max']:.0f}mm"
                                    )
                                    
                                    st.number_input(
                                        "Position Y Bas - Hauteur bas (mm depuis traverse inférieure)",
                                        value=float(vs.get('bottom_y', 0.0)),
                                        key=f"vertical_shelf_bottom_y_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'bottom_y'),
                                        format="%.0f",
                                        step=1.0,
                                        help=f"Zone Y : {zone['y_min']:.0f}-{zone['y_max']:.0f}mm"
                                    )
                                    
                                    st.number_input(
                                        "Position Y Haut - Hauteur haut (mm depuis traverse inférieure)",
                                        value=float(vs.get('top_y', 100.0)),
                                        key=f"vertical_shelf_top_y_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'top_y'),
                                        format="%.0f",
                                        step=1.0,
                                        help=f"Zone Y : {zone['y_min']:.0f}-{zone['y_max']:.0f}mm"
                                    )
                                else:
                                    # Pas de zone sélectionnée : permettre tous les ajustements sans contraintes
                                    st.number_input(
                                        "Position X (mm depuis le montant gauche)",
                                        value=float(vs['position_x']),
                                        key=f"vertical_shelf_position_x_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'position_x'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                    
                                    st.number_input(
                                        "Position Y Bas - Hauteur bas (mm depuis traverse inférieure)",
                                        value=float(vs.get('bottom_y', 0.0)),
                                        key=f"vertical_shelf_bottom_y_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'bottom_y'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                    
                                    st.number_input(
                                        "Position Y Haut - Hauteur haut (mm depuis traverse inférieure)",
                                        value=float(vs.get('top_y', 100.0)),
                                        key=f"vertical_shelf_top_y_{idx}_{i}",
                                        on_change=lambda x=i: update_vertical_shelf_prop(x, 'top_y'),
                                        format="%.0f",
                                        step=1.0,
                                    )
                                st.number_input(
                                    "Épaisseur (mm)",
                                    value=vs['thickness'],
                                    key=f"vertical_shelf_thickness_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_shelf_prop(x, 'thickness'),
                                    format="%.0f",
                                    step=1.0,
                                )
                                st.text_input(
                                    "Matière",
                                    value=vs.get('material', 'Matière Corps'),
                                    key=f"vertical_shelf_material_{idx}_{i}",
                                    on_change=lambda x=i: update_vertical_shelf_material(x)
                                )
                                st.button(
                                    "🗑️ Supprimer cette étagère verticale",
                                    key=f"del_vertical_shelf_{idx}_{i}",
                                    on_click=lambda x=i: delete_vertical_shelf_callback(x),
                                    use_container_width=True
                                )

                with t_deb:
                    st.markdown(f"#### Feuille de Débit (Caisson {idx})")
                    debit_rows = selected_cab.get('debit_data', [])
                    
                    # Si debit_data est vide ou n'existe pas, l'initialiser avec les pièces de base
                    if not debit_rows:
                        debit_rows = get_default_debit_data()
                        selected_cab['debit_data'] = debit_rows
                    
                    df = pd.DataFrame(debit_rows)
                    
                    # S'assurer que toutes les colonnes nécessaires existent
                    required_cols = ["Référence Pièce", "Longueur (mm)", "Largeur (mm)", "Epaisseur", "Qté", "Usinage"]
                    chant_cols = ["Chant Avant", "Chant Arrière", "Chant Gauche", "Chant Droit"]
                    
                    # Ajouter les colonnes manquantes
                    for col in required_cols:
                        if col not in df.columns:
                            if col == "Usinage":
                                df[col] = ""
                            elif col == "Qté":
                                df[col] = 1
                            else:
                                df[col] = 0
                    
                    # Recalculer automatiquement Longueur/Largeur/Epaisseur pour les pièces structurelles
                    dims = selected_cab['dims']
                    t_lr, t_tb, t_fb = dims['t_lr_raw'], dims['t_tb_raw'], dims['t_fb_raw']
                    h_side = dims['H_raw']
                    L_traverse = dims['L_raw'] - 2 * t_lr
                    dim_fond_vertical = dims['H_raw'] - 2.0
                    dim_fond_horizontal = dims['L_raw'] - 2.0
                    panel_dims = {
                        "Traverse Bas": (L_traverse, dims['W_raw'], t_tb),
                        "Traverse Haut": (L_traverse, dims['W_raw'], t_tb),
                        "Montant Gauche": (h_side, dims['W_raw'], t_lr),
                        "Montant Droit": (h_side, dims['W_raw'], t_lr),
                        "Fond": (dim_fond_vertical, dim_fond_horizontal, t_fb),
                    }
                    for row_idx, row in df.iterrows():
                        ref = str(row.get("Référence Pièce", ""))
                        ref_key = ref.split(" (")[0].strip()
                        for key, dims_tuple in panel_dims.items():
                            if key in ref_key:
                                df.at[row_idx, "Longueur (mm)"] = dims_tuple[0]
                                df.at[row_idx, "Largeur (mm)"] = dims_tuple[1]
                                df.at[row_idx, "Epaisseur"] = dims_tuple[2]
                                break
                    
                    # S'assurer que les colonnes de chant existent et sont bien booléennes
                    for col in chant_cols:
                        if col not in df.columns:
                            df[col] = False
                        else:
                            # Convertir en booléen si ce n'est pas déjà le cas
                            df[col] = df[col].fillna(False).astype(bool)
                    
                    # Réorganiser les colonnes pour un meilleur affichage
                    display_cols = required_cols + chant_cols
                    df = df[[col for col in display_cols if col in df.columns] + [col for col in df.columns if col not in display_cols]]
                    
                    edited_df = st.data_editor(
                        df,
                        key=f"editor_{idx}",
                        hide_index=True,
                        column_config={
                            "Chant Avant": st.column_config.CheckboxColumn("Chant Avant", default=False),
                            "Chant Arrière": st.column_config.CheckboxColumn("Chant Arrière", default=False),
                            "Chant Gauche": st.column_config.CheckboxColumn("Chant Gauche", default=False),
                            "Chant Droit": st.column_config.CheckboxColumn("Chant Droit", default=False),
                        },
                        num_rows="dynamic"
                    )
                    
                    # Écrire les modifications dans l'état du caisson
                    st.session_state['scene_cabinets'][idx]['debit_data'] = edited_df.to_dict(orient="records")

all_calculated_parts, shelf_dims_cache = calculate_all_project_parts()

with col2:
    sel_idx = st.session_state.get('selected_cabinet_index')
    if sel_idx is None and st.session_state['scene_cabinets']: sel_idx = 0
    cab_for_check = st.session_state['scene_cabinets'][sel_idx] if sel_idx is not None and 0 <= sel_idx < len(st.session_state['scene_cabinets']) else None
    
    # Désactivation des alertes de collision d'usinage
    # collisions = []
    # (Code de détection de collision désactivé)

    st.header("Prévisualisation 3D")
    fig3d = go.Figure()
    scene = st.session_state['scene_cabinets']
    unit_factor = {"mm":0.001,"cm":0.01,"m":1.0}[st.session_state.unit_select]
    abs_origins = calculate_origins_recursively(st.session_state.scene_cabinets, unit_factor)
    
    BODY_COLOR = "#D6C098"
    ACCESSORY_COLOR = "#B8A078"
    BODY_OPACITY = 1.0
    ACCESSORY_OPACITY = 1.0
    
    if not st.session_state['scene_cabinets']:
        st.info("La scène est vide.")
    else:
        pending = st.session_state.get('pending_placement')
        for i, cab in enumerate(st.session_state['scene_cabinets']):
            # IMPORTANT: rendre à partir d'une copie pour éviter toute mutation involontaire pendant l'affichage
            cab_render = copy.deepcopy(cab)
            if pending and pending.get('cabinet_index') == i:
                kind = pending.get('kind')
                p = pending.get('props', {})
                if kind == 'vertical_divider':
                    cab_render.setdefault('vertical_dividers', []).append({**copy.deepcopy(p), '_preview': True})
                elif kind == 'vertical_divider_double':
                    # Double montant : 2 montants côte à côte, centrés sur position_x, sans jeu
                    th = float(p.get('thickness', 19.0))
                    L_raw = cab.get('dims', {}).get('L_raw', 0.0)
                    center_x = float(p.get('position_x', (L_raw / 2.0 if L_raw else 0.0)))
                    pos_left = center_x - th / 2.0
                    pos_right = center_x + th / 2.0
                    div_left = {**copy.deepcopy(p), 'position_x': pos_left, '_preview': True}
                    div_right = {**copy.deepcopy(p), 'position_x': pos_right, '_preview': True}
                    cab_render.setdefault('vertical_dividers', []).extend([div_left, div_right])
                elif kind == 'vertical_shelf':
                    cab_render.setdefault('vertical_shelves', []).append({**copy.deepcopy(p), '_preview': True})
                elif kind == 'shelf':
                    # Ajouter l'étagère en preview avec le flag _preview
                    shelf_preview = copy.deepcopy(p)
                    shelf_preview['_preview'] = True
                    cab_render.setdefault('shelves', []).append(shelf_preview)
                elif kind in ('drawer', 'drawer_stack'):
                    # Ajouter le(s) tiroir(s) en preview avec le flag _preview
                    # - drawer : tiroir unique
                    # - drawer_stack : tiroirs empilés automatiquement (sans demander de dimensions)
                    if kind == 'drawer_stack':
                        # Construire une preview d'empilement si une zone est sélectionnée
                        stack_count = int(p.get('stack_count', 3))
                        # Zones calculées SANS inclure les tiroirs
                        zones_for_preview = calculate_all_zones_2d(cab, include_all_elements=False)
                        zone_id = p.get('zone_id', None)
                        dims = cab['dims']
                        t_tb_mm = float(dims.get('t_tb_raw', 19.0))
                        H_raw = float(dims.get('H_raw', 1000.0))
                        
                        if zone_id is not None and 0 <= int(zone_id) < len(zones_for_preview) and stack_count >= 1:
                            z = zones_for_preview[int(zone_id)]
                            
                            # Vérifier le mode (encastré ou appliqué)
                            is_applique = bool(p.get('_applique_mode', False))
                            
                            if is_applique:
                                # Mode APPLIQUE : formule H_raw - n*2mm - 2x1mm (jeu de 1mm haut/bas)
                                n_junctions = stack_count - 1
                                total_face_height = H_raw - (n_junctions * 2.0) - 2.0
                                face_h = total_face_height / float(stack_count) if stack_count > 0 else 0.0
                                if face_h < 10.0:
                                    face_h = 10.0
                                # Position : début du caisson avec 1mm de jeu
                                current_z_offset = -1.0
                            else:
                                # Mode ENCASTE : formule H_raw - 2*t_tb - 4mm - n*2mm
                                n_junctions = stack_count - 1
                                total_face_height = H_raw - 2.0 * t_tb_mm - 4.0 - (n_junctions * 2.0)
                                face_h = total_face_height / float(stack_count) if stack_count > 0 else 0.0
                                if face_h < 10.0:
                                    face_h = 10.0
                                current_z_offset = t_tb_mm + 2.0
                            
                            for k in range(stack_count):
                                d_prev = copy.deepcopy(p)
                                d_prev['_preview'] = True
                                d_prev['drawer_face_H_raw'] = face_h
                                d_prev['drawer_bottom_offset'] = current_z_offset
                                cab_render.setdefault('drawers', []).append(d_prev)
                                # Préparer offset pour prochain tiroir (hauteur + 2mm gap)
                                current_z_offset += face_h + 2.0
                        else:
                            # Pas de zone : fallback sur un tiroir unique preview
                            drawer_preview = copy.deepcopy(p)
                            drawer_preview['_preview'] = True
                            cab_render.setdefault('drawers', []).append(drawer_preview)
                    else:
                        drawer_preview = copy.deepcopy(p)
                        drawer_preview['_preview'] = True
                        cab_render.setdefault('drawers', []).append(drawer_preview)
            o = abs_origins[i]; d = cab['dims']; L, W, H = d['L_raw']*unit_factor, d['W_raw']*unit_factor, d['H_raw']*unit_factor
            tl, tb, tt = d['t_lr_raw']*unit_factor, d['t_fb_raw']*unit_factor, d['t_tb_raw']*unit_factor
            
            # Récupérer les préférences des éléments de base (par défaut tous activés)
            base_el = cab.get('base_elements', {
                'has_back_panel': True,
                'has_left_upright': True,
                'has_right_upright': True,
                'has_bottom_traverse': True,
                'has_top_traverse': True
            })
            
            # Traverse Bas
            if base_el.get('has_bottom_traverse', True):
                fig3d.add_trace(cuboid_mesh_for(L-2*tl, W, tt, (o[0]+tl, o[1], o[2]), color=BODY_COLOR, opacity=BODY_OPACITY, showlegend=False))
            # Traverse Haut
            if base_el.get('has_top_traverse', True):
                fig3d.add_trace(cuboid_mesh_for(L-2*tl, W, tt, (o[0]+tl, o[1], o[2]+H-tt), color=BODY_COLOR, opacity=BODY_OPACITY, showlegend=False))
            # Montant Gauche
            if base_el.get('has_left_upright', True):
                fig3d.add_trace(cuboid_mesh_for(tl, W, H, (o[0], o[1], o[2]), color=BODY_COLOR, opacity=BODY_OPACITY, showlegend=False))
            # Montant Droit
            if base_el.get('has_right_upright', True):
                fig3d.add_trace(cuboid_mesh_for(tl, W, H, (o[0]+L-tl, o[1], o[2]), color=BODY_COLOR, opacity=BODY_OPACITY, showlegend=False))
            # Panneau Arrière (Fond)
            if base_el.get('has_back_panel', True):
                fig3d.add_trace(cuboid_mesh_for(L-2*tl, tb, H-2*tt, (o[0]+tl, o[1]+W-tb, o[2]+tt), color=BODY_COLOR, opacity=BODY_OPACITY, showlegend=False))
            
            # Rendu des montants verticaux secondaires AVANT TOUS les autres éléments pour qu'ils soient visibles
            if 'vertical_dividers' in cab_render and cab_render['vertical_dividers']:
                DIVIDER_COLOR = "#8B7355"
                for div in cab_render['vertical_dividers']:
                    # position_x est en mm depuis le début du caisson (o[0])
                    div_x_mm = div['position_x']
                    div_th_mm = div.get('thickness', 19.0)
                    div_x = div_x_mm * unit_factor
                    div_th = div_th_mm * unit_factor
                    is_preview = bool(div.get('_preview'))
                    # Montant vertical : position X = o[0] + div_x_mm (en unités)
                    # Le montant va de (div_x_mm - div_th_mm/2) à (div_x_mm + div_th_mm/2) en mm
                    # Profondeur : W - tb pour ne pas traverser le panneau arrière
                    fig3d.add_trace(cuboid_mesh_for(
                        div_th, W - tb, H-2*tt,
                        (o[0] + div_x - div_th/2, o[1], o[2] + tt),
                        color=("#666666" if is_preview else DIVIDER_COLOR),
                        opacity=(0.35 if is_preview else BODY_OPACITY),
                        showlegend=False
                    ))
            
            # Rendu des étagères verticales (après les montants secondaires mais avant les autres éléments)
            if 'vertical_shelves' in cab_render and cab_render['vertical_shelves']:
                VERTICAL_SHELF_COLOR = "#A0826D"
                all_zones_2d = calculate_all_zones_2d(cab_render)
                
                for vs in cab_render['vertical_shelves']:
                    vs_th_mm = vs.get('thickness', 19.0)
                    is_preview = bool(vs.get('_preview'))
                    
                    # Utiliser TOUJOURS les positions stockées (ne JAMAIS recalculer)
                    # Cela garantit que l'étagère validée ne déplace pas d'autres éléments
                    # Pour les éléments en prévisualisation, utiliser les valeurs du pending
                    vs_x_mm = vs.get('position_x', 300.0)
                    vs_bottom_y_mm = vs.get('bottom_y', 0.0)
                    vs_top_y_mm = vs.get('top_y', 100.0)
                    
                    # NE JAMAIS modifier les positions stockées - utiliser telles quelles pour le rendu
                    # Les éléments validés gardent leurs positions fixes, même si les zones changent
                    
                    vs_height_mm = vs_top_y_mm - vs_bottom_y_mm
                    vs_x = vs_x_mm * unit_factor
                    vs_th = vs_th_mm * unit_factor
                    vs_height = vs_height_mm * unit_factor
                    vs_bottom_z = o[2] + tt + (vs_bottom_y_mm * unit_factor)
                    
                    # Validation du placement pour les étagères verticales en preview
                    is_valid_placement = True
                    if is_preview:
                        all_zones_2d_for_validation = calculate_all_zones_2d(cab_render, include_all_elements=True)
                        is_valid_placement, validation_reason = check_element_placement_validity(vs, all_zones_2d_for_validation, cab_render, element_type='vertical_shelf')
                    
                    # Choisir la couleur selon la validité du placement
                    if is_preview and not is_valid_placement:
                        vs_color = "rgba(255, 0, 0, 1.0)"  # Rouge vif pour placement invalide
                        vs_opacity = 0.8
                    else:
                        vs_color = "#666666" if is_preview else VERTICAL_SHELF_COLOR
                        vs_opacity = 0.35 if is_preview else BODY_OPACITY
                    
                    # Étagère verticale : position X = o[0] + vs_x_mm (en unités)
                    # L'étagère va de (vs_x_mm - vs_th_mm/2) à (vs_x_mm + vs_th_mm/2) en mm
                    fig3d.add_trace(cuboid_mesh_for(
                        vs_th, W, vs_height,
                        (o[0] + vs_x - vs_th/2, o[1], vs_bottom_z),
                        color=vs_color,
                        opacity=vs_opacity,
                        showlegend=False
                    ))
            
            if cab_render['door_props']['has_door']:
                dp = cab_render['door_props']; gap = dp['door_gap'] * unit_factor; thk = dp.get('door_thickness', 19.0) * unit_factor; dy = o[1] - thk
                dH = H + st.session_state.foot_height*unit_factor - gap if dp.get('door_model')=='floor_length' and (i==0) and st.session_state.has_feet else H - 2*gap
                dz = o[2] + (gap * (1.0 if dp.get('door_model')=='standard' else 0.0))
                rot_angle = 45 if dp.get('door_opening')=='right' else -45
                
                # Vérifier si une zone est assignée
                zone_id = dp.get('zone_id', None)
                all_zones_2d = calculate_all_zones_2d(cab_render)
                
                if zone_id is not None and zone_id < len(all_zones_2d):
                    # Porte dans une zone spécifique - strictement limitée à la zone
                    zone = all_zones_2d[zone_id]
                    zone_x_min_mm = zone['x_min']
                    zone_x_max_mm = zone['x_max']
                    zone_x_min_abs = o[0] + (zone_x_min_mm * unit_factor)
                    zone_x_max_abs = o[0] + (zone_x_max_mm * unit_factor)
                    zone_width_abs = zone_x_max_abs - zone_x_min_abs
                    # La porte doit être dans la zone, avec le gap + marge de sécurité
                    safety_margin_mm = 2.0  # 2mm pour éviter de toucher les montants
                    safety_margin = safety_margin_mm * unit_factor
                    dW_zone = zone_width_abs - 2*gap - 2*safety_margin
                    # Position de départ de la porte dans la zone
                    door_x_start = zone_x_min_abs + gap + safety_margin
                    pivot_x = zone_x_max_abs - gap - safety_margin if dp.get('door_opening')=='right' else zone_x_min_abs + gap + safety_margin
                    if dW_zone > 0:
                        fig3d.add_trace(cuboid_mesh_for(dW_zone, thk, dH, (door_x_start, dy, dz), color=ACCESSORY_COLOR, opacity=ACCESSORY_OPACITY, name=f"Porte {i}", rotation_angle=rot_angle, rotation_axis='z', rotation_pivot=(pivot_x, dy, dz)))
                else:
                    # Porte sur tout le caisson
                    if dp.get('door_type') == 'single':
                        pivot_x = o[0] + L - gap if dp.get('door_opening')=='right' else o[0] + gap
                        fig3d.add_trace(cuboid_mesh_for(L-2*gap, thk, dH, (o[0]+gap, dy, dz), color=ACCESSORY_COLOR, opacity=ACCESSORY_OPACITY, name=f"Porte {i}", rotation_angle=rot_angle, rotation_axis='z', rotation_pivot=(pivot_x, dy, dz)))
                    else:
                        dl_half = (L-2*gap)/2; pivot_g = o[0] + gap; pivot_d = o[0] + L - gap
                        fig3d.add_trace(cuboid_mesh_for(dl_half, thk, dH, (o[0]+gap, dy, dz), color=ACCESSORY_COLOR, opacity=ACCESSORY_OPACITY, name=f"Porte G {i}", rotation_angle=-45, rotation_axis='z', rotation_pivot=(pivot_g, dy, dz)))
                        fig3d.add_trace(cuboid_mesh_for(dl_half, thk, dH, (o[0]+L-gap-dl_half, dy, dz), color=ACCESSORY_COLOR, opacity=ACCESSORY_OPACITY, name=f"Porte D {i}", rotation_angle=45, rotation_axis='z', rotation_pivot=(pivot_d, dy, dz)))

            # Rendu de tous les tiroirs
            if 'drawers' in cab_render and cab_render['drawers']:
                # IMPORTANT : Calculer les zones SANS inclure les tiroirs (include_all_elements=False)
                # Les tiroirs ne créent pas de zones, ils sont placés dans des zones existantes
                all_zones_2d_drawers = calculate_all_zones_2d(cab_render, include_all_elements=False)
                
                for drawer_idx, drp in enumerate(cab_render['drawers']):
                    gap = drp.get('drawer_gap', 2.0) * unit_factor
                    thk = drp.get('drawer_face_thickness', 19.0) * unit_factor
                    is_preview = bool(drp.get('_preview'))
                    
                    # Vérifier si une zone est assignée
                    zone_id = drp.get('zone_id', None)
                    
                    if zone_id is not None and zone_id < len(all_zones_2d_drawers):
                        # Tiroir dans une zone spécifique
                        zone = all_zones_2d_drawers[zone_id]
                        zone_x_min_mm = zone['x_min']
                        zone_x_max_mm = zone['x_max']
                        zone_y_min_mm = zone['y_min']  # Profondeur minimum de la zone
                        zone_y_max_mm = zone['y_max']  # Profondeur maximum de la zone
                        
                        zone_x_min_abs = o[0] + (zone_x_min_mm * unit_factor)
                        zone_x_max_abs = o[0] + (zone_x_max_mm * unit_factor)
                        zone_y_min_abs = o[1] + (zone_y_min_mm * unit_factor)
                        zone_y_max_abs = o[1] + (zone_y_max_mm * unit_factor)
                        
                        zone_width_abs = zone_x_max_abs - zone_x_min_abs
                        zone_depth_abs = zone_y_max_abs - zone_y_min_abs
                        
                        # Hauteur du tiroir : utiliser directement la hauteur stockée
                        drawer_height = drp.get('drawer_face_H_raw', 150.0) * unit_factor
                        
                        # Vérifier le mode (encastré ou en applique)
                        is_applique = bool(drp.get('_applique_mode', False))
                        
                        if is_applique:
                            # Mode EN APPLIQUE : recouvrir COMPLÈTEMENT les montants délimitant la zone
                            # Largeur = largeur zone + 2x épaisseur montant + 1mm jeu de chaque côté
                            t_montant_mm = float(cab_render['dims'].get('t_lr_raw', 19.0))
                            dW_zone = zone_width_abs + (2.0 * t_montant_mm * unit_factor) + (2.0 * unit_factor)
                            # Commencer avant le montant gauche (épaisseur montant + 1mm jeu)
                            drawer_x_start = zone_x_min_abs - (t_montant_mm * unit_factor) - (1.0 * unit_factor)
                            # Profondeur : juste l'épaisseur de la face du tiroir
                            drawer_depth = drp.get('drawer_face_thickness', 19.0) * unit_factor
                            # Position Y : les tiroirs sortent AVANT le panneau avant
                            drawer_y_pos = o[1] - drawer_depth
                        else:
                            # Mode ENCASTE : largeur zone - jeux
                            dW_zone = zone_width_abs - 2 * gap
                            drawer_x_start = zone_x_min_abs + gap
                            # Mode ENCASTE : tiroirs restent à l'intérieur avec retrait de 19mm
                            drawer_depth = zone_depth_abs + (19.0 * unit_factor)
                            drawer_y_pos = zone_y_min_abs - (19.0 * unit_factor)
                        
                        # Position Z (hauteur) : drawer_bottom_offset incluit déjà t_tb depuis le fond du caisson
                        drawer_z_pos = o[2] + (drp.get('drawer_bottom_offset', 0.0) * unit_factor)
                        
                        if dW_zone > 0 and drawer_depth > 0:
                            drawer_color = "#666666" if is_preview else ACCESSORY_COLOR
                            drawer_opacity = 0.35 if is_preview else ACCESSORY_OPACITY
                            fig3d.add_trace(cuboid_mesh_for(
                                dW_zone, drawer_depth, drawer_height,
                                (drawer_x_start, drawer_y_pos, drawer_z_pos),
                                color=drawer_color,
                                opacity=drawer_opacity,
                                name=f"Tiroir {i}-{drawer_idx}"
                            ))
                    else:
                        # Tiroir sur tout le caisson
                        # Vérifier le mode (encastré ou en applique)
                        is_applique = bool(drp.get('_applique_mode', False))
                        
                        # Hauteur et position Z du tiroir
                        drawer_height = drp.get('drawer_face_H_raw', 150.0) * unit_factor
                        drawer_z_pos = o[2] + (drp.get('drawer_bottom_offset', 0.0) * unit_factor)
                        
                        if is_applique:
                            # Mode EN APPLIQUE : recouvrir toute la largeur + épaisseurs montants + 1mm jeu
                            t_montant_mm = float(cab_render['dims'].get('t_lr_raw', 19.0))
                            dW_zone = L + (2.0 * t_montant_mm * unit_factor) + (2.0 * unit_factor)
                            drawer_x_start = o[0] - (t_montant_mm * unit_factor) - (1.0 * unit_factor)
                            # Profondeur : juste l'épaisseur de la face
                            drawer_depth = drp.get('drawer_face_thickness', 19.0) * unit_factor
                            drawer_y_pos = o[1] - drawer_depth
                        else:
                            # Mode ENCASTE : avancer de 19mm vers l'ouverture
                            dW_zone = L - 2 * gap
                            drawer_x_start = o[0] + gap
                            drawer_depth = W - 2 * tb + (19.0 * unit_factor)
                            drawer_y_pos = o[1] + tb - (19.0 * unit_factor)
                        
                        drawer_color = "#666666" if is_preview else ACCESSORY_COLOR
                        drawer_opacity = 0.35 if is_preview else ACCESSORY_OPACITY
                        fig3d.add_trace(cuboid_mesh_for(
                            dW_zone, drawer_depth, drawer_height,
                            (drawer_x_start, drawer_y_pos, drawer_z_pos),
                            color=drawer_color,
                            opacity=drawer_opacity,
                            name=f"Tiroir {i}-{drawer_idx}"
                        ))

            if 'shelves' in cab_render:
                for s in cab_render['shelves']:
                    sh_z = o[2] + tt + (s['height'] * unit_factor)
                    is_preview = bool(s.get('_preview'))
                    # IMPORTANT : Utiliser TOUJOURS les positions stockées pour les étagères validées
                    # Ne JAMAIS recalculer la position à partir de la zone pour les éléments validés
                    # Les zones peuvent changer, mais les positions stockées restent fixes
                    zone_id = s.get('zone_id', None)
                    
                    # Rechercher la zone correspondante
                    zone = None
                    if zone_id is not None:
                        all_zones_2d = calculate_all_zones_2d(cab_render)
                        
                        if is_preview:
                            # Pour les éléments en preview, utiliser zone_id directement
                            if zone_id < len(all_zones_2d):
                                zone = all_zones_2d[zone_id]
                        else:
                            # Pour les éléments validés, essayer d'abord de trouver par coordonnées stockées
                            stored_zone_coords = s.get('stored_zone_coords', None)
                            if stored_zone_coords:
                                # Chercher la zone correspondante par coordonnées
                                for z in all_zones_2d:
                                    if (abs(z['x_min'] - stored_zone_coords['x_min']) < 0.1 and
                                        abs(z['x_max'] - stored_zone_coords['x_max']) < 0.1 and
                                        abs(z['y_min'] - stored_zone_coords['y_min']) < 0.1 and
                                        abs(z['y_max'] - stored_zone_coords['y_max']) < 0.1):
                                        zone = z
                                        break
                            
                            # Si pas trouvé par coordonnées, utiliser zone_id (comportement legacy ou fallback)
                            if zone is None and zone_id < len(all_zones_2d):
                                zone = all_zones_2d[zone_id]
                    
                    if zone is not None:
                        # IMPORTANT : Pour les étagères validées, utiliser la largeur et position stockées
                        # pour éviter que leur largeur change quand de nouveaux éléments sont ajoutés
                        if not is_preview and s.get('stored_shelf_width_mm') is not None and s.get('stored_shelf_x_start_mm') is not None:
                            # Utiliser les valeurs stockées directement pour les éléments validés
                            shelf_width = s['stored_shelf_width_mm'] * unit_factor
                            shelf_x_start = o[0] + (s['stored_shelf_x_start_mm'] * unit_factor)
                        else:
                            # Pour les éléments en preview, recalculer à partir de la zone
                            zone_x_min_mm = zone['x_min']  # En mm
                            zone_x_max_mm = zone['x_max']  # En mm
                            
                            # Convertir en coordonnées absolues pour la 3D
                            zone_x_min_abs = o[0] + (zone_x_min_mm * unit_factor)
                            zone_x_max_abs = o[0] + (zone_x_max_mm * unit_factor)
                            zone_width_abs = zone_x_max_abs - zone_x_min_abs
                            
                            # L'étagère doit être STRICTEMENT dans la zone, sans toucher les montants
                            s_type = s.get('shelf_type', 'mobile')
                            
                            # Calculer les positions des montants verticaux (principaux et secondaires) pour vérification
                            # IMPORTANT : Les étagères horizontales doivent toucher les montants principaux OU secondaires,
                            # mais PAS les étagères verticales
                            divider_bounds = []
                            # Montant gauche (principal)
                            divider_bounds.append((o[0], o[0] + tl))
                            # Montant droit (principal)
                            divider_bounds.append((o[0] + L - tl, o[0] + L))
                            # Montants secondaires
                            if 'vertical_dividers' in cab_render:
                                for div in cab_render['vertical_dividers']:
                                    div_x_mm = div['position_x']
                                    div_th_mm = div.get('thickness', 19.0)
                                    div_x_min_abs = o[0] + (div_x_mm - div_th_mm/2.0) * unit_factor
                                    div_x_max_abs = o[0] + (div_x_mm + div_th_mm/2.0) * unit_factor
                                    divider_bounds.append((div_x_min_abs, div_x_max_abs))
                            # Les étagères verticales NE sont PAS ajoutées - elles ne sont pas des montants
                            
                            # PLUS DE JEU : l'étagère suit exactement la largeur de la zone en X
                            if s_type == 'mobile':
                                shelf_width = zone_width_abs
                                shelf_x_start = zone_x_min_abs
                            else:
                                shelf_width = zone_width_abs
                                shelf_x_start = zone_x_min_abs
                        
                        # Calculer les positions des montants verticaux pour vérification de collision
                        divider_bounds = []
                        # Montant gauche (principal)
                        divider_bounds.append((o[0], o[0] + tl))
                        # Montant droit (principal)
                        divider_bounds.append((o[0] + L - tl, o[0] + L))
                        # Montants secondaires
                        if 'vertical_dividers' in cab_render:
                            for div in cab_render['vertical_dividers']:
                                div_x_mm = div['position_x']
                                div_th_mm = div.get('thickness', 19.0)
                                div_x_min_abs = o[0] + (div_x_mm - div_th_mm/2.0) * unit_factor
                                div_x_max_abs = o[0] + (div_x_mm + div_th_mm/2.0) * unit_factor
                                divider_bounds.append((div_x_min_abs, div_x_max_abs))
                        # Les étagères verticales NE sont PAS ajoutées - elles ne sont pas des montants
                            
                            # Vérification de sécurité : s'assurer que l'étagère ne dépasse pas
                            shelf_x_end = shelf_x_start + shelf_width
                            
                        # Pour les éléments validés avec valeurs stockées, on considère qu'ils sont toujours valides
                        # Pour les éléments en preview, vérifier qu'ils sont dans la zone
                        if not is_preview and s.get('stored_shelf_width_mm') is not None:
                            in_zone = True  # Les éléments validés sont toujours considérés comme valides
                            touches_divider = False  # Pas de vérification de collision pour les éléments validés
                        else:
                            # Pour les éléments en preview, vérifier qu'ils sont dans la zone
                            zone_x_min_abs = o[0] + (zone['x_min'] * unit_factor)
                            zone_x_max_abs = o[0] + (zone['x_max'] * unit_factor)
                            in_zone = shelf_width > 0 and shelf_x_start >= zone_x_min_abs and shelf_x_end <= zone_x_max_abs
                            touches_divider = False
                            
                            if in_zone and divider_bounds:
                                for div_min, div_max in divider_bounds:
                                    # Vérifier si l'étagère chevauche le montant (avec une petite tolérance)
                                    if (shelf_x_start <= div_max + 0.001 and shelf_x_end >= div_min - 0.001):
                                        touches_divider = True
                                        break
                            
                        # Validation du placement : vérifier si l'élément est dans une zone valide
                        is_valid_placement = True
                        if is_preview:
                            # Pour les éléments en preview, vérifier la validité du placement
                            all_zones_2d_for_validation = calculate_all_zones_2d(cab_render, include_all_elements=True)
                            is_valid_placement, validation_reason = check_element_placement_validity(s, all_zones_2d_for_validation, cab_render, element_type='shelf')
                            
                            # Choisir la couleur selon la validité du placement
                            if in_zone and not touches_divider and not is_valid_placement:
                                shelf_color = "rgba(255, 0, 0, 1.0)"  # Rouge vif pour placement invalide
                                shelf_opacity = 0.8
                            else:
                                shelf_color = "#666666"
                                shelf_opacity = 0.35
                        else:
                            shelf_color = BODY_COLOR
                            shelf_opacity = BODY_OPACITY
                        
                        fig3d.add_trace(cuboid_mesh_for(
                            shelf_width, W-0.01, s['thickness']*unit_factor, (shelf_x_start, o[1], sh_z),
                            color=shelf_color,
                            opacity=shelf_opacity,
                            showlegend=False
                        ))
                    else:
                        # Pas de zone ou zone_id invalide : étagère sur toute la largeur
                        fig3d.add_trace(cuboid_mesh_for(
                            L-2*tl, W-0.01, s['thickness']*unit_factor, (o[0]+tl, o[1], sh_z),
                            color=("#666666" if is_preview else BODY_COLOR),
                            opacity=(0.35 if is_preview else BODY_OPACITY),
                            showlegend=False
                        ))
            
            # Ajouter les annotations de toutes les zones 2D (après tous les éléments)
            # NE PAS afficher les labels noirs pendant la prévisualisation (seulement les labels bleus des zones existantes)
            # Utiliser include_all_elements=True pour voir toutes les zones créées
            if not (pending and pending.get('cabinet_index') == i):
                all_zones_2d = calculate_all_zones_2d(cab_render, include_all_elements=True)
                
                # DEBUG : Ajouter les boîtes de debug pour visualiser les bounding boxes exactes
                add_zone_debug_boxes_3d(fig3d, all_zones_2d, o, cab['dims'], unit_factor, 
                                       wireframe=True, opacity=0.4, y_plane_offset=-0.008)
                
            for zone in all_zones_2d:
                # Calculer le centre GÉOMÉTRIQUE EXACT de la zone (centroid)
                # Center_X = (X_min + X_max) / 2
                # Center_Y = (Y_min + Y_max) / 2
                zone_center_x_mm = (zone['x_min'] + zone['x_max']) / 2.0
                zone_center_y_mm = (zone['y_min'] + zone['y_max']) / 2.0
                
                # Convertir en coordonnées 3D absolues
                # X : depuis o[0] (montant gauche) + position X en mm
                annot_x = o[0] + (zone_center_x_mm * unit_factor)
                # Y : EXACTEMENT au même plan que les boîtes de debug pour éviter la parallaxe
                # Utiliser exactement le même y_plane_offset que les boîtes de debug (-0.008)
                y_plane_debug = o[1] + W / 2.0 - 0.008  # Même offset que les boîtes de debug
                annot_y = y_plane_debug
                # Z : depuis o[2] (bas du caisson) + traverse inférieure + position Y en mm
                annot_z = o[2] + tt + (zone_center_y_mm * unit_factor)
                
                # Utiliser Scatter3d avec mode='text' pour afficher les labels en 3D
                # IMPORTANT : Dans Plotly, le texte est rendu avec son point d'origine au centre géométrique
                # Pour minimiser l'effet de parallaxe lors du zoom, on utilise :
                # - Une taille de police modérée
                # - Exactement le même plan Y que les boîtes de debug
                # - Le texte sera ancré au point (x, y, z) qui est le centre géométrique de la zone
                fig3d.add_trace(go.Scatter3d(
                    x=[annot_x],
                    y=[annot_y],
                    z=[annot_z],
                    mode='text',
                    text=[f"<b>{zone['label']}</b>"],
                    textfont=dict(size=14, color="black", family="Arial Black"),  # Taille réduite pour minimiser l'effet de parallaxe
                    showlegend=False,
                    hoverinfo='skip'
                ))
            
            # --- AFFICHAGE DES ZONES AVANT/APRÈS (pendant la pose) ---
            if pending and pending.get('cabinet_index') == i:
                # 1. Calculer les zones AVANT la pose (sans l'élément pending)
                zones_before = calculate_all_zones_2d(cab, include_all_elements=True)
                
                # 2. Calculer les zones APRÈS la pose (avec l'élément pending dans cab_render)
                zones_after = calculate_all_zones_2d(cab_render, include_all_elements=True)
                
                # 3. Identifier les nouvelles zones (celles qui n'existent pas avant)
                before_sig = {
                    (round(z['x_min'], 3), round(z['x_max'], 3), round(z['y_min'], 3), round(z['y_max'], 3))
                    for z in zones_before
                }
                new_zone_ids = set()
                for z in zones_after:
                    sig = (round(z['x_min'], 3), round(z['x_max'], 3), round(z['y_min'], 3), round(z['y_max'], 3))
                    if sig not in before_sig:
                        new_zone_ids.add(z['id'])
                
                # 4. Afficher les zones AVANT (remplissage bleu + contours épais + labels)
                if zones_before:
                    add_zone_outlines_3d(fig3d, zones_before, o, cab['dims'], unit_factor, 
                                         zone_ids_to_show=None, 
                                         fill_color="rgba(0,100,200,0.3)", 
                                         line_color="rgba(0,100,200,0.95)", 
                                         line_width=4, 
                                         y_plane_offset=-0.015)
                    
                    # Ajouter les labels des zones existantes
                    W = cab['dims']['W_raw'] * unit_factor
                    t_tb = cab['dims']['t_tb_raw'] * unit_factor
                    # Utiliser exactement le même plan Y que les boîtes de debug pour éviter la parallaxe
                    y_plane_debug_before = o[1] + W / 2.0 - 0.015  # Même offset que les zones existantes (-0.015)
                    
                    for zone_before in zones_before:
                        # Calculer le centre GÉOMÉTRIQUE EXACT de la zone (centroid)
                        zone_center_x_mm = (zone_before['x_min'] + zone_before['x_max']) / 2.0
                        zone_center_y_mm = (zone_before['y_min'] + zone_before['y_max']) / 2.0
                        annot_x = o[0] + (zone_center_x_mm * unit_factor)
                        annot_z = o[2] + t_tb + (zone_center_y_mm * unit_factor)
                        
                        fig3d.add_trace(go.Scatter3d(
                            x=[annot_x],
                            y=[y_plane_debug_before],
                            z=[annot_z],
                            mode='text',
                            text=[f"<b>{zone_before['label']}</b>"],
                            textfont=dict(size=16, color="blue", family="Arial Black"),  # Taille réduite pour minimiser l'effet de parallaxe
                            showlegend=False,
                            hoverinfo='skip'
                        ))
                
                # 5. Afficher les nouvelles zones APRÈS (hachures grises)
                if new_zone_ids:
                    add_hatched_zones_3d(fig3d, zones_after, o, cab['dims'], unit_factor, 
                                        zone_ids_to_hatch=new_zone_ids, color="rgba(200,100,0,0.7)", line_width=2, y_plane_offset=-0.01)

        if st.session_state.has_feet:
            l_coords = [abs_origins[i][0] for i in range(len(scene))]; min_L = min(l_coords); max_L = max([abs_origins[i][0] + scene[i]['dims']['L_raw']*unit_factor for i in range(len(scene))])
            min_W = min([abs_origins[i][1] for i in range(len(scene))]); max_W = max([abs_origins[i][1] + scene[i]['dims']['W_raw']*unit_factor for i in range(len(scene))])
            fh = st.session_state.foot_height * unit_factor
            for x in [min_L+0.05, max_L-0.05]:
                for y in [min_W+0.05, max_W-0.05]:
                    fig3d.add_trace(cylinder_mesh_for((x, y, -fh), fh, 0.02, color='#333', showlegend=False))

    # Caméra fixée pour voir de face (côté intérieur du caisson)
    # eye=dict(x=0, y=-2, z=1.4) : voir depuis l'avant (y négatif = depuis l'avant)
    fig3d.update_layout(scene=dict(aspectmode='data', xaxis=dict(visible=True, showgrid=True, title="X"), yaxis=dict(visible=True, showgrid=True, title="Y"), zaxis=dict(visible=True, showgrid=True, title="Z"), camera=dict(eye=dict(x=0, y=-2, z=1.4), center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))), margin=dict(l=0,r=0,t=0,b=0), uirevision='constant') 
    st.plotly_chart(fig3d, use_container_width=True)
    
    st.markdown("---")
    st.subheader("📤 Exportation")
    if st.session_state['scene_cabinets']:
        # Forcer le rechargement des modules pour les dernières modifications
        import drawing_interface
        import export_manager
        import machining_logic
        import dxf_export
        import dxf_export.titleblock
        importlib.reload(machining_logic)
        importlib.reload(drawing_interface)
        importlib.reload(export_manager)
        importlib.reload(dxf_export.titleblock)
        importlib.reload(dxf_export)
        from export_manager import generate_stacked_html_plans as generate_plans_fresh
        
        # Export HTML
        html_data, html_ok = generate_plans_fresh(st.session_state['scene_cabinets'], list(range(len(st.session_state['scene_cabinets']))))
        
        # Export DXF robuste scene graph (multi-layouts + audit)
        dxf_mode_label = st.selectbox(
            "Mode DXF",
            ["Atelier/CNC (robuste)", "CAD éditable (DIMENSION)"],
            index=1,
            help="Les cotes sont exportées en DIMENSION AutoCAD (éditables).",
        )
        dxf_mode = "cnc" if dxf_mode_label.startswith("Atelier/CNC") else "editable"
        dxf_force_primitives = st.checkbox(
            "Forcer cotes en primitives (anti-crash)",
            value=False,
            help="Désactivé: les cotations AutoCAD sont forcées.",
            disabled=True,
        )
        dxf_debug = st.checkbox(
            "Mode DEBUG anti-écran noir",
            value=False,
            help="Export par étape logique et log de rendu pour isoler une entité problématique.",
        )

        try:
            from dxf_export import export_project_to_dxf

            logo_path = os.path.join(os.path.dirname(__file__), "logo.png")

            dxf_result = export_project_to_dxf(
                {
                    "cabinets_data": st.session_state['scene_cabinets'],
                    "indices": list(range(len(st.session_state['scene_cabinets']))),
                    "project_name": st.session_state.project_name,
                    "client": st.session_state.client,
                    "comments": st.session_state.ref_chantier,
                    "version": "V1",
                    "paper_width_mm": 420.0,
                    "paper_height_mm": 297.0,
                    "page_margin_mm": 10.0,
                    "bbox_margin_factor": 1.05,
                    "text_height": 2.5,
                    "dimensions_text_height": 10.0,
                    "triangle_size": 8.0,
                    "logo_path": logo_path,
                },
                mode=dxf_mode,
                force_primitives_dims=dxf_force_primitives,
                debug=dxf_debug,
                debug_stage="all",
            )

            dwg_data = dxf_result.dxf_bytes
            dwg_ok = dxf_result.ok
            dwg_filename = f"usinage_{st.session_state.project_name.replace(' ', '_')}.dxf"
            dxf_report = dxf_result.report
            dxf_mode_used = dxf_result.mode_used
        except Exception as e:
            dwg_data = f"Erreur export DXF: {str(e)}".encode('utf-8')
            dwg_ok = False
            dxf_report = str(e)
            dxf_mode_used = dxf_mode

        dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 1])
        project_info_export = {"project_name": st.session_state.project_name, "client": st.session_state.client, "adresse_chantier": st.session_state.adresse_chantier, "ref_chantier": st.session_state.ref_chantier, "telephone": st.session_state.telephone, "date_souhaitee": st.session_state.date_souhaitee, "panneau_decor": st.session_state.panneau_decor, "chant_mm": st.session_state.chant_mm, "decor_chant": st.session_state.decor_chant, "corps_meuble": "Ensemble", "quantity": 1, "date": datetime.date.today().strftime("%Y-%m-%d")}
        save_data_export = {'project_name': st.session_state.project_name, 'scene_cabinets': st.session_state.scene_cabinets}
        xls_data = create_styled_excel(project_info_export, pd.DataFrame(all_calculated_parts), save_data_export)
        if html_ok and html_data:
            dl_col1.download_button("📄 Télécharger Dossier Plans (HTML)", html_data, f"Dossier_{st.session_state.project_name.replace(' ', '_')}.html", "text/html", use_container_width=True)
        else:
            # Afficher le message d'erreur détaillé si disponible
            if html_data:
                try:
                    error_html = html_data.decode('utf-8') if isinstance(html_data, bytes) else html_data
                    dl_col1.error(f"⚠️ Erreur lors de la génération du fichier HTML.")
                    with dl_col1.expander("Détails de l'erreur"):
                        st.markdown(error_html, unsafe_allow_html=True)
                except:
                    dl_col1.error("⚠️ Erreur lors de la génération du fichier HTML. Vérifiez la console pour plus de détails.")
            else:
                dl_col1.error("⚠️ Erreur lors de la génération du fichier HTML. Aucune donnée générée.")
        dl_col2.download_button("📥 Télécharger Fiche de Débit (.xlsx)", xls_data, f"Projet_{st.session_state.project_name.replace(' ', '_')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        if dwg_ok and dwg_data:
            dl_col3.download_button("📐 Télécharger Plans AutoCAD (.dxf)", dwg_data, dwg_filename or f"Plans_{st.session_state.project_name.replace(' ', '_')}.dxf", "application/dxf", use_container_width=True)
            dl_col3.info(f"💡 Mode utilisé: {dxf_mode_used}. Ouvrir ce DXF puis enregistrer en DWG dans AutoCAD.")
            with dl_col3.expander("Rapport audit DXF"):
                st.text(dxf_report or "Aucun rapport.")
        else:
            if dwg_data:
                try:
                    dwg_error = dwg_data.decode('utf-8') if isinstance(dwg_data, bytes) else str(dwg_data)
                    dl_col3.warning(f"⚠️ Export DXF indisponible : {dwg_error}")
                    with dl_col3.expander("Rapport audit DXF"):
                        st.text(dxf_report or dwg_error)
                except Exception:
                    dl_col3.warning("⚠️ Export DXF indisponible.")
            else:
                dl_col3.warning("⚠️ Export DXF indisponible.")
    st.markdown("---")
    st.subheader("📋 Feuille de Débit")
    if all_calculated_parts:
        df_debit = pd.DataFrame(all_calculated_parts)
        # Formater les colonnes de dimensions : pas de virgule pour les nombres >= 1000
        dim_columns = ["Longueur (mm)", "Largeur (mm)", "Epaisseur"]
        for col in dim_columns:
            if col in df_debit.columns:
                def format_dimension(val):
                    if pd.isna(val) or val == "":
                        return ""
                    try:
                        num_val = float(val)
                        # Si >= 1000, format entier sans virgule
                        if num_val >= 1000:
                            return str(int(num_val))
                        else:
                            # Format décimal si nécessaire, sinon entier
                            if num_val == int(num_val):
                                return str(int(num_val))
                            return str(num_val)
                    except:
                        return str(val) if val else ""
                df_debit[col] = df_debit[col].apply(format_dimension)
        st.dataframe(df_debit, hide_index=True, use_container_width=True)

    st.markdown("---")
    unit_str = st.session_state.unit_select
    sel_idx = st.session_state.get('selected_cabinet_index')
    if sel_idx is None and st.session_state['scene_cabinets']: sel_idx = 0
    st.subheader(f"📋 Feuilles d'usinage (Caisson {sel_idx})")
    
    if sel_idx is not None and 0 <= sel_idx < len(st.session_state['scene_cabinets']):
        cab = st.session_state['scene_cabinets'][sel_idx]
        dims = cab['dims']
        L_raw, W_raw, H_raw = dims['L_raw'], dims['W_raw'], dims['H_raw']
        t_lr, t_fb, t_tb = dims['t_lr_raw'], dims['t_fb_raw'], dims['t_tb_raw']
        W_back, H_back = L_raw - 2.0, H_raw - 2.0
        h_side, L_trav, W_mont = H_raw, L_raw-2*t_lr, W_raw
        
        ys_vis, ys_dowel = calculate_hole_positions(W_raw)
        holes_mg, holes_md = [], []
        tranche_holes_mg, tranche_holes_md = [], []
        
        # Trous d'assemblage montant/traverse : uniquement sur la FACE des montants principaux
        # (pas de trous en tranche sur Mg/Md).
        for x in ys_vis:
            holes_mg.append({'type':'vis','x':x,'y':t_tb/2,'diam_str':"⌀3"})
            holes_mg.append({'type':'vis','x':x,'y':h_side-t_tb/2,'diam_str':"⌀3"})
            holes_md.append({'type':'vis','x':x,'y':t_tb/2,'diam_str':"⌀3"})
            holes_md.append({'type':'vis','x':x,'y':h_side-t_tb/2,'diam_str':"⌀3"})
        for x in ys_dowel:
            holes_mg.append({'type':'tourillon','x':x,'y':t_tb/2,'diam_str':"⌀8/22"})
            holes_mg.append({'type':'tourillon','x':x,'y':h_side-t_tb/2,'diam_str':"⌀8/22"})
            holes_md.append({'type':'tourillon','x':x,'y':t_tb/2,'diam_str':"⌀8/22"})
            holes_md.append({'type':'tourillon','x':x,'y':h_side-t_tb/2,'diam_str':"⌀8/22"})
            
        # IMPORTANT : utiliser EXACTEMENT la même trame X que pour les
        # trous d'assemblage montant / traverse sur la profondeur W_raw.
        # Ainsi, tous les trous d'étagère fixe sont alignés en X avec
        # les vis/tourillons des traverses.
        ys_vis_sf, ys_dowel_sf = ys_vis, ys_dowel
        fixed_shelf_tr_draw = {}
        
        # Calculer les zones pour les éléments
        all_zones_2d = calculate_all_zones_2d(cab)
        zones = calculate_zones_from_dividers(cab)  # Pour compatibilité avec le code existant
        
        # Dictionnaires pour stocker les trous d'assemblage par montant secondaire
        # Séparer les trous par face (gauche et droite) pour pouvoir générer 2 plans si nécessaire
        divider_element_holes_left = {}
        divider_element_holes_right = {}
        if 'vertical_dividers' in cab and cab['vertical_dividers']:
            divider_element_holes_left = {i: [] for i in range(len(cab['vertical_dividers']))}
            divider_element_holes_right = {i: [] for i in range(len(cab['vertical_dividers']))}
        # Garder aussi l'ancien format pour compatibilité
        divider_element_holes = divider_element_holes_left if 'vertical_dividers' in cab and cab['vertical_dividers'] else {}
        
        if 'shelves' in cab:
            for s_idx, s in enumerate(cab['shelves']):
                s_type = s.get('shelf_type', 'mobile')
                zone_id = s.get('zone_id', None)
                
                if s_type == 'fixe':
                    yc_val = t_tb + s['height'] + s['thickness']/2.0 
                    
                    # IMPORTANT : Utiliser les LIMITES DE LA ZONE pour détecter les montants
                    # Les coordonnées stockées sont égales aux limites de la zone (sans jeu)
                    # Donc on utilise directement les limites de la zone pour la détection
                    zone_x_min = None
                    zone_x_max = None
                    
                    # Priorité 1 : utiliser stored_zone_coords si disponible
                    if s.get('stored_zone_coords'):
                        zone_x_min = s['stored_zone_coords']['x_min']
                        zone_x_max = s['stored_zone_coords']['x_max']
                    # Priorité 2 : utiliser la zone calculée
                    elif zone_id is not None and zone_id < len(all_zones_2d):
                        zone = all_zones_2d[zone_id]
                        zone_x_min = zone['x_min']
                        zone_x_max = zone['x_max']
                    
                    if zone_x_min is not None and zone_x_max is not None:
                        # Montant gauche principal si la zone commence au montant gauche
                        if abs(zone_x_min - t_lr) < 1.0:
                            # Trous sur la FACE du montant : tourillons ⌀8/10, vis ⌀3/10
                            for x in ys_vis_sf: holes_mg.append({'type':'vis','x':x+10.0,'y':yc_val,'diam_str':"⌀3/10"})
                            for x in ys_dowel_sf: holes_mg.append({'type':'tourillon','x':x+10.0,'y':yc_val,'diam_str':"⌀8/10"})
                        # Montant droit principal si la zone se termine au montant droit
                        if abs(zone_x_max - (L_raw - t_lr)) < 1.0:
                            # Trous sur la FACE du montant : tourillons ⌀8/10, vis ⌀3/10
                            for x in ys_vis_sf: holes_md.append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3/10"})
                            for x in ys_dowel_sf: holes_md.append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
                        
                        # Montants secondaires qui touchent cette étagère fixe
                        # Utiliser les limites de la zone pour détecter les montants
                        for div_idx, div in enumerate(cab['vertical_dividers']):
                            div_x = div['position_x']
                            div_th = div.get('thickness', 19.0)
                            div_left_edge = div_x - div_th / 2.0  # Bord gauche du montant
                            div_right_edge = div_x + div_th / 2.0  # Bord droit du montant
                            
                            # Élément touche la face GAUCHE si la zone se termine au bord gauche du montant
                            touches_left_face = abs(zone_x_max - div_left_edge) < 1.0
                            # Élément touche la face DROITE si la zone commence au bord droit du montant
                            touches_right_face = abs(zone_x_min - div_right_edge) < 1.0
                            
                            if touches_left_face:
                                # Élément à gauche du montant : trous sur la FACE gauche (1/2) - tourillons ⌀8/10, vis ⌀3/10
                                for x in ys_vis_sf:
                                    divider_element_holes_left[div_idx].append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3/10"})
                                for x in ys_dowel_sf:
                                    divider_element_holes_left[div_idx].append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
                            if touches_right_face:
                                # Élément à droite du montant : trous sur la FACE droite (2/2) - tourillons ⌀8/10, vis ⌀3/10
                                for x in ys_vis_sf:
                                    divider_element_holes_right[div_idx].append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3/10"})
                                for x in ys_dowel_sf:
                                    divider_element_holes_right[div_idx].append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
                    else:
                        # Étagère sur tout le caisson : trous sur les FACES des deux montants principaux - tourillons ⌀8/10, vis ⌀3/10
                        for x in ys_vis_sf: holes_mg.append({'type':'vis','x':x+10.0,'y':yc_val,'diam_str':"⌀3/10"})
                        for x in ys_dowel_sf: holes_mg.append({'type':'tourillon','x':x+10.0,'y':yc_val,'diam_str':"⌀8/10"})
                        for x in ys_vis_sf: holes_md.append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3/10"})
                        for x in ys_dowel_sf: holes_md.append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
                    
                    # Trous de liaison dans la tranche de l'étagère
                    # Règle demandée :
                    # - Les trous de tourillons doivent être les mêmes que ceux sur la face des montants
                    # - Les vis sont aussi présentes, alignées avec les tourillons
                    # - Les tourillons aux extrémités sont à 25mm des DEUX bords (calculés par calculate_hole_positions)
                    # IMPORTANT : Calculer les trous en fonction de la largeur RÉELLE de l'étagère
                    # Récupérer la largeur réelle de l'étagère depuis shelf_dims_cache
                    shelf_width = W_raw - 10.0  # Par défaut : largeur standard
                    if f"C{sel_idx}_S{s_idx}" in shelf_dims_cache:
                        _, shelf_width = shelf_dims_cache[f"C{sel_idx}_S{s_idx}"]
                    
                    # Calculer les trous spécifiquement pour cette largeur d'étagère
                    ys_vis_shelf, ys_dowel_shelf = calculate_hole_positions(shelf_width)
                    
                    tr = []
                    # Trous sur la TRANCHE de l'étagère : vis ⌀3/10
                    # Utiliser les positions calculées pour la largeur réelle de l'étagère
                    # Cela garantit que les tourillons sont à 25mm des DEUX bords de l'étagère
                    for y_pos in ys_vis_shelf:
                        tr.append({'type':'vis','x':s['thickness']/2,'y':y_pos,'diam_str':"⌀3/10"})
                    for y_pos in ys_dowel_shelf:
                        tr.append({'type':'tourillon','x':s['thickness']/2,'y':y_pos,'diam_str':"⌀8/22"})
                    fixed_shelf_tr_draw[s_idx] = tr
                else:
                    # Étagère mobile : les taquets sont déjà calculés, on les filtre par zone
                    mobile_holes = get_mobile_shelf_holes(h_side, t_tb, s, W_mont)
                    
                    # IMPORTANT : Utiliser les LIMITES DE LA ZONE pour détecter les montants
                    # Les coordonnées stockées sont égales aux limites de la zone (sans jeu)
                    # Donc on utilise directement les limites de la zone pour la détection
                    zone_x_min = None
                    zone_x_max = None
                    
                    # Priorité 1 : utiliser stored_zone_coords si disponible
                    if s.get('stored_zone_coords'):
                        zone_x_min = s['stored_zone_coords']['x_min']
                        zone_x_max = s['stored_zone_coords']['x_max']
                    # Priorité 2 : utiliser la zone calculée
                    elif zone_id is not None and zone_id < len(all_zones_2d):
                        zone = all_zones_2d[zone_id]
                        zone_x_min = zone['x_min']
                        zone_x_max = zone['x_max']
                    
                    if zone_x_min is not None and zone_x_max is not None:
                        # Montant gauche si la zone commence au montant gauche
                        if abs(zone_x_min - t_lr) < 1.0:
                            holes_mg.extend(mobile_holes)
                        # Montant droit si la zone se termine au montant droit
                        if abs(zone_x_max - (L_raw - t_lr)) < 1.0:
                            holes_md.extend(mobile_holes)
                    else:
                        # Étagère mobile sur tout le caisson : trous sur les deux montants principaux
                        holes_mg.extend(mobile_holes)
                        holes_md.extend(mobile_holes)
                    
                    # Montants secondaires qui touchent cette étagère
                    if zone_x_min is not None and zone_x_max is not None:
                        # IMPORTANT : Utiliser les limites de la zone pour détecter les montants
                        for div_idx, div in enumerate(cab['vertical_dividers']):
                            div_x = div['position_x']
                            div_th = div.get('thickness', 19.0)
                            div_left_edge = div_x - div_th / 2.0  # Bord gauche du montant
                            div_right_edge = div_x + div_th / 2.0  # Bord droit du montant
                            
                            # Élément touche la face GAUCHE si la zone se termine au bord gauche du montant
                            touches_left_face = abs(zone_x_max - div_left_edge) < 1.0
                            # Élément touche la face DROITE si la zone commence au bord droit du montant
                            touches_right_face = abs(zone_x_min - div_right_edge) < 1.0
                            
                            if touches_left_face:
                                # Élément à gauche du montant : trous sur la face gauche (1/2)
                                divider_element_holes_left[div_idx].extend(mobile_holes)
                            if touches_right_face:
                                # Élément à droite du montant : trous sur la face droite (2/2)
                                divider_element_holes_right[div_idx].extend(mobile_holes)
                    
        if cab['door_props']['has_door']:
            # Utiliser les positions personnalisées si le mode est 'custom'
            door_props = cab['door_props']
            if door_props.get('hinge_mode') == 'custom' and door_props.get('custom_hinge_positions'):
                yh = get_hinge_y_positions(h_side, custom_positions=door_props['custom_hinge_positions'])
            else:
                yh = get_hinge_y_positions(h_side)
            door_type = cab['door_props'].get('door_type', 'single')
            if door_type == 'double':
                # Porte double : trous sur les deux montants
                # Porte gauche : trous sur montant gauche (x=20.0 et x=52.0 depuis le bord gauche)
                # Porte droite : trous sur montant droit (x=20.0 et x=52.0 depuis le bord droit, donc W_mont-20.0 et W_mont-52.0)
                for y in yh:
                    # Trous pour la porte gauche sur montant gauche
                    holes_mg.append({'type':'vis','x':20.0,'y':y,'diam_str':"⌀5/11.5"})
                    holes_mg.append({'type':'vis','x':52.0,'y':y,'diam_str':"⌀5/11.5"})
                    # Trous pour la porte droite sur montant droit
                    holes_md.append({'type':'vis','x':W_mont-20.0,'y':y,'diam_str':"⌀5/11.5"})
                    holes_md.append({'type':'vis','x':W_mont-52.0,'y':y,'diam_str':"⌀5/11.5"})
            else:
                # Porte simple : trous selon le sens d'ouverture
                for y in yh:
                    if cab['door_props']['door_opening'] == 'left':
                        holes_mg.append({'type':'vis','x':20.0,'y':y,'diam_str':"⌀5/11.5"})
                        holes_mg.append({'type':'vis','x':52.0,'y':y,'diam_str':"⌀5/11.5"})
                    else:
                        holes_md.append({'type':'vis','x':20.0,'y':y,'diam_str':"⌀5/11.5"})
                        holes_md.append({'type':'vis','x':52.0,'y':y,'diam_str':"⌀5/11.5"})

        # Traiter tous les tiroirs de la liste
        if 'drawers' in cab and cab['drawers']:
            for drawer_idx, drp in enumerate(cab['drawers']):
                tech_type = drp.get('drawer_tech_type', 'K')
                y_slide = t_tb + 33.0 + drp.get('drawer_bottom_offset', 0.0)
                drawer_zone_id = drp.get('zone_id', None)
                
                x_slide_holes = []
                wr = W_raw
                if wr > 643:
                    x_slide_holes = [19, 37, 133, 261, 293, 389, 421, 549]
                else:
                    if tech_type == 'N':
                        if 403 < wr < 452: x_slide_holes = [19, 37, 133, 165, 229, 325]
                        elif 453 < wr < 502: x_slide_holes = [19, 37, 133, 165, 261, 357]
                        elif 503 < wr < 552: x_slide_holes = [19, 37, 133, 261, 293, 453]
                        elif 553 < wr < 602: x_slide_holes = [19, 37, 133, 261, 293, 453]
                    if not x_slide_holes:
                        if 273 < wr < 302: x_slide_holes = [19, 37, 133, 261]
                        elif 303 < wr < 352: x_slide_holes = [19, 37, 133, 165, 261]
                        elif 353 < wr < 402: x_slide_holes = [19, 37, 133, 165, 325]
                        elif 403 < wr < 452: x_slide_holes = [19, 37, 133, 165, 229, 325]
                        elif 453 < wr < 502: x_slide_holes = [19, 37, 133, 165, 261, 357]
                        elif 503 < wr < 552: x_slide_holes = [19, 37, 133, 261, 293, 453]
                        elif 553 < wr < 602: x_slide_holes = [19, 37, 133, 261, 293, 453]
                        elif 603 < wr < 652: x_slide_holes = [19, 37, 133, 261, 293, 325, 357, 517]

                # IMPORTANT : Utiliser les LIMITES DE LA ZONE pour détecter les montants
                # Le tiroir est dans une zone, et cette zone définit quels montants le délimitent
                zone_x_min = None
                zone_x_max = None
                
                if drawer_zone_id is not None and drawer_zone_id < len(all_zones_2d):
                    zone = all_zones_2d[drawer_zone_id]
                    zone_x_min = zone['x_min']
                    zone_x_max = zone['x_max']
                
                if zone_x_min is not None and zone_x_max is not None:
                    # Montant gauche principal si la zone commence au montant gauche
                    if abs(zone_x_min - t_lr) < 1.0:
                        for x_s in x_slide_holes:
                            holes_mg.append({'type': 'vis', 'x': x_s, 'y': y_slide, 'diam_str': "⌀5/12"})
                    # Montant droit principal si la zone se termine au montant droit
                    if abs(zone_x_max - (L_raw - t_lr)) < 1.0:
                        for x_s in x_slide_holes:
                            holes_md.append({'type': 'vis', 'x': W_mont - x_s, 'y': y_slide, 'diam_str': "⌀5/12"})
                    
                    # Montants secondaires qui touchent ce tiroir
                    # Utiliser les limites de la zone pour détecter les montants
                    if 'vertical_dividers' in cab:
                        for div_idx, div in enumerate(cab['vertical_dividers']):
                            div_x = div['position_x']
                            div_th = div.get('thickness', 19.0)
                            div_left_edge = div_x - div_th / 2.0  # Bord gauche du montant
                            div_right_edge = div_x + div_th / 2.0  # Bord droit du montant
                            
                            # Élément touche la face GAUCHE si la zone se termine au bord gauche du montant
                            touches_left_face = abs(zone_x_max - div_left_edge) < 1.0
                            # Élément touche la face DROITE si la zone commence au bord droit du montant
                            touches_right_face = abs(zone_x_min - div_right_edge) < 1.0
                            
                            if touches_left_face:
                                # Élément à gauche du montant : trous sur la face gauche (1/2)
                                for x_s in x_slide_holes:
                                    divider_element_holes_left[div_idx].append({'type':'vis','x':x_s,'y':y_slide,'diam_str':"⌀3"})
                            if touches_right_face:
                                # Élément à droite du montant : trous sur la face droite (2/2)
                                for x_s in x_slide_holes:
                                    divider_element_holes_right[div_idx].append({'type':'vis','x':x_s,'y':y_slide,'diam_str':"⌀3"})
                else:
                    # Tiroir sur tout le caisson : trous sur les deux montants principaux
                    for x_s in x_slide_holes:
                        holes_mg.append({'type': 'vis', 'x': x_s, 'y': y_slide, 'diam_str': "⌀5/12"})
                        holes_md.append({'type': 'vis', 'x': W_mont - x_s, 'y': y_slide, 'diam_str': "⌀5/12"})

        proj = {"project_name": st.session_state.project_name, "corps_meuble": f"Caisson {sel_idx}", "quantity": 1, "date": ""}
        # Trous sur les TRANCHES des traverses : tourillons ⌀8/22 (pas de vis sur les tranches des traverses)
        tholes = [{'type':'tourillon','x':t_tb/2,'y':y,'diam_str':"⌀8/22"} for y in ys_dowel]
        
        # Ajouter les trous sur les TRANCHES des traverses (haut et bas) pour les montants secondaires
        if 'vertical_dividers' in cab and cab['vertical_dividers']:
            for div in cab['vertical_dividers']:
                div_x = div['position_x']
                div_traverse_holes = get_traverse_holes_for_divider(L_trav, div_x, t_lr, t_tb, W_raw)
                tholes.extend(div_traverse_holes)
        
        # Ajouter les trous sur les FACES des traverses (gauche et droite) pour les montants secondaires
        # Les trous sont projetés depuis les tranches des montants secondaires
        traverse_face_holes_left = []  # Trous sur la face gauche de la traverse
        traverse_face_holes_right = []  # Trous sur la face droite de la traverse
        if 'vertical_dividers' in cab and cab['vertical_dividers']:
            for div in cab['vertical_dividers']:
                div_x = div['position_x']
                # IMPORTANT : Les montants secondaires ont une profondeur de W - t_fb
                # Donc les trous doivent être calculés pour cette profondeur réduite
                div_traverse_face_holes = get_traverse_face_holes_for_divider(L_trav, div_x, t_lr, t_tb, W_raw, t_fb)
                # Les trous sont positionnés sur la face de la traverse (pas sur les tranches)
                # On les ajoute aux trous de face de la traverse
                traverse_face_holes_left.extend(div_traverse_face_holes)
                traverse_face_holes_right.extend(div_traverse_face_holes)
        
        # Récupérer les préférences des éléments de base (par défaut tous activés)
        base_el = cab.get('base_elements', {
            'has_back_panel': True,
            'has_left_upright': True,
            'has_right_upright': True,
            'has_bottom_traverse': True,
            'has_top_traverse': True
        })
        
        c_trav = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":False, "Chant Droit":False}
        # Traverses avec trous sur les tranches (haut et bas) et sur les faces (gauche et droite)
        if base_el.get('has_bottom_traverse', True):
            st.plotly_chart(draw_machining_view_pro_final("Traverse Bas (Tb)", L_trav, W_mont, t_tb, unit_str, proj, c_trav, traverse_face_holes_left, [], tholes), use_container_width=True)
        if base_el.get('has_top_traverse', True):
            st.plotly_chart(draw_machining_view_pro_final("Traverse Haut (Th)", L_trav, W_mont, t_tb, unit_str, proj, c_trav, traverse_face_holes_right, [], tholes), use_container_width=True)
        
        c_mont = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
        if base_el.get('has_left_upright', True):
            st.plotly_chart(draw_machining_view_pro_final("Montant Gauche (Mg)", W_mont, h_side, t_lr, unit_str, proj, c_mont, holes_mg, tranche_holes_mg), use_container_width=True)
        if base_el.get('has_right_upright', True):
            st.plotly_chart(draw_machining_view_pro_final("Montant Droit (Md)", W_mont, h_side, t_lr, unit_str, proj, c_mont, holes_md, tranche_holes_md), use_container_width=True)
        
        c_fond = {"Chant Avant":False, "Chant Arrière":False, "Chant Gauche":False, "Chant Droit":False}
        if base_el.get('has_back_panel', True):
            st.plotly_chart(draw_machining_view_pro_final("Panneau Arrière (F)", W_back, H_back, t_fb, unit_str, proj, c_fond, calculate_back_panel_holes(W_back, H_back, cab)), use_container_width=True)
        
        if cab['door_props']['has_door']:
            dp = cab['door_props']
            door_type = dp.get('door_type', 'single')
            dH = H_raw + st.session_state.foot_height - dp['door_gap'] - 10.0 if dp.get('door_model')=='floor_length' else H_raw - (2 * dp['door_gap'])
            
            if door_type == 'double':
                # Porte double : générer deux feuilles d'usinage (une pour chaque battant)
                dW_half = (L_raw - (2 * dp['door_gap'])) / 2.0
                # Utiliser les positions personnalisées si le mode est 'custom'
                if dp.get('hinge_mode') == 'custom' and dp.get('custom_hinge_positions'):
                    y_h = get_hinge_y_positions(dH, custom_positions=dp['custom_hinge_positions'])
                else:
                    y_h = get_hinge_y_positions(dH)
                
                # Porte gauche : trous à gauche (xc=23.5, xv=33.0)
                holes_p_g = []
                xc_g = 23.5
                xv_g = 33.0
                for y in y_h:
                    holes_p_g.append({'type':'tourillon','x':xc_g,'y':y,'diam_str':"⌀35"})
                    holes_p_g.append({'type':'vis','x':xv_g,'y':y+22.5,'diam_str':"⌀8"})
                    holes_p_g.append({'type':'vis','x':xv_g,'y':y-22.5,'diam_str':"⌀8"})
                
                # Porte droite : trous à droite (xc=dW_half-23.5, xv=dW_half-33.0)
                holes_p_d = []
                xc_d = dW_half - 23.5
                xv_d = dW_half - 33.0
                for y in y_h:
                    holes_p_d.append({'type':'tourillon','x':xc_d,'y':y,'diam_str':"⌀35"})
                    holes_p_d.append({'type':'vis','x':xv_d,'y':y+22.5,'diam_str':"⌀8"})
                    holes_p_d.append({'type':'vis','x':xv_d,'y':y-22.5,'diam_str':"⌀8"})
                
                c_p = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
                proj_door = {"project_name": st.session_state.project_name, "corps_meuble": f"Caisson {sel_idx}", "quantity": 2, "date": ""}
                st.plotly_chart(draw_machining_view_pro_final(f"Porte (C{sel_idx})", dW_half, dH, dp['door_thickness'], unit_str, proj_door, c_p, holes_p_g), use_container_width=True)
            else:
                # Porte simple : une seule feuille d'usinage
                dW = L_raw - (2 * dp['door_gap'])
                # Utiliser les positions personnalisées si le mode est 'custom'
                if dp.get('hinge_mode') == 'custom' and dp.get('custom_hinge_positions'):
                    y_h = get_hinge_y_positions(dH, custom_positions=dp['custom_hinge_positions'])
                else:
                    y_h = get_hinge_y_positions(dH)
                
                holes_p = []
                xc = 23.5 if dp['door_opening']=='left' else dW-23.5
                xv = 33.0 if dp['door_opening']=='left' else dW-33.0
                for y in y_h: 
                    holes_p.append({'type':'tourillon','x':xc,'y':y,'diam_str':"⌀35"})
                    holes_p.append({'type':'vis','x':xv,'y':y+22.5,'diam_str':"⌀8"})
                    holes_p.append({'type':'vis','x':xv,'y':y-22.5,'diam_str':"⌀8"})

                c_p = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
                st.plotly_chart(draw_machining_view_pro_final(f"Porte (C{sel_idx})", dW, dH, dp['door_thickness'], unit_str, proj, c_p, holes_p), use_container_width=True)
            
        # Plans d'usinage pour tous les tiroirs (dimensions adaptatives à la zone)
        # Grouper les tiroirs identiques pour éviter les doublons
        if 'drawers' in cab and cab['drawers']:
            # Fonction helper pour calculer la signature d'un tiroir (dimensions + usinages)
            def get_drawer_signature(drp, all_zones_2d, L_raw, W_raw, t_fb, t_lr):
                drawer_system = drp.get('drawer_system', 'TANDEMBOX')
                drawer_zone_id = drp.get('zone_id', None)
                gap_mm = drp.get('drawer_gap', 2.0)
                
                if drawer_zone_id is not None and drawer_zone_id < len(all_zones_2d):
                    zone = all_zones_2d[drawer_zone_id]
                    zone_width_total = zone['x_max'] - zone['x_min']
                    zone_width_interior = zone_width_total - (2 * t_lr)
                else:
                    zone_width_total = L_raw
                    zone_width_interior = L_raw - (2 * t_lr)
                
                dr_H = drp.get('drawer_face_H_raw', 150.0)
                tech_type = drp.get('drawer_tech_type', 'K')
                dr_thickness = drp.get('drawer_face_thickness', 19.0)
                inner_thickness = float(drp.get('inner_thickness', 16.0))
                cutout = None
                if drp.get('drawer_handle_type') == 'integrated_cutout':
                    cutout = (
                        drp.get('drawer_handle_width', 150.0),
                        drp.get('drawer_handle_height', 40.0),
                        drp.get('drawer_handle_offset_top', 10.0)
                    )
                
                if drawer_system == 'LÉGRABOX':
                    legrabox_specs = get_legrabox_specs()
                    legrabox_spec = legrabox_specs.get(tech_type, legrabox_specs['K'])
                    fixed_back_h = legrabox_spec['back_height']
                    dr_L = zone_width_total - (2 * gap_mm)  # Face = largeur totale
                    d_L_t = max(0.0, zone_width_interior - 38.0)  # Dos = intérieur - 38mm
                    zone_depth_interior = W_raw - (2 * t_lr)
                    fond_L = max(0.0, zone_width_interior - 35.0)  # Fond largeur = intérieur - 35mm
                    fond_H = max(0.0, zone_depth_interior - 10.0)  # Fond profondeur = intérieur - 10mm
                else:
                    # TANDEMBOX
                    dr_L = zone_width_total - (2 * gap_mm)
                    back_height_map = {'N': 69.0, 'M': 84.0, 'K': 116.0, 'D': 199.0}
                    fixed_back_h = back_height_map.get(tech_type, 116.0)
                    d_L_t = max(0.0, dr_L - 49.0)
                    fond_L = max(0.0, dr_L - 49.0)
                    fond_H = round(W_raw - (20.0 + t_fb), 1)
                
                # Signature : (face_L, face_H, face_th, system, tech_type, cutout, dos_L, dos_H, dos_th, fond_L, fond_H, fond_th)
                return (
                    round(dr_L, 1), round(dr_H, 1), round(dr_thickness, 1), drawer_system, tech_type, cutout,
                    round(d_L_t, 1), round(fixed_back_h, 1), round(inner_thickness, 1),
                    round(fond_L, 1), round(fond_H, 1), round(inner_thickness, 1)
                )
            
            # Grouper les tiroirs par signature
            drawer_groups = {}
            for drawer_idx, drp in enumerate(cab['drawers']):
                sig = get_drawer_signature(drp, all_zones_2d, L_raw, W_raw, t_fb, t_lr)
                if sig not in drawer_groups:
                    drawer_groups[sig] = []
                drawer_groups[sig].append((drawer_idx, drp))
            
            # Générer les plans pour chaque groupe (une seule feuille par groupe avec quantité)
            group_num = 0
            legrabox_specs = get_legrabox_specs()
            for sig, group in drawer_groups.items():
                group_num += 1
                dr_L, dr_H, dr_thickness, drawer_system, tech_type, cutout, d_L_t, fixed_back_h, inner_thickness, fond_L, fond_H, _ = sig
                quantity = len(group)
                
                # Prendre le premier tiroir du groupe pour les données de référence
                first_drawer_idx, first_drp = group[0]
                
                # Calculer les trous d'usinage selon le système
                f_holes = []
                d_holes_t = []
                bottom_holes = []
                
                if drawer_system == 'LÉGRABOX':
                    # LÉGRABOX : utiliser les spécifications
                    legrabox_spec = legrabox_specs.get(tech_type, legrabox_specs['K'])
                    # Trous face (tourillons 10/12)
                    for y in legrabox_spec['face_holes']['y_coords']:
                        if y < dr_H:
                            x_offset = legrabox_spec['face_holes']['x_offset']
                            f_holes.append({'type': 'tourillon', 'x': x_offset, 'y': y, 'diam_str': legrabox_spec['face_holes']['diam_str']})
                            f_holes.append({'type': 'tourillon', 'x': dr_L - x_offset, 'y': y, 'diam_str': legrabox_spec['face_holes']['diam_str']})
                    # Trous dos (vis 2.5/3)
                    for y in legrabox_spec['back_holes']['y_coords']:
                        if y < fixed_back_h:
                            x_offset = legrabox_spec['back_holes']['x_offset']
                            d_holes_t.append({'type': 'vis', 'x': x_offset, 'y': y, 'diam_str': legrabox_spec['back_holes']['diam_str']})
                            d_holes_t.append({'type': 'vis', 'x': d_L_t - x_offset, 'y': y, 'diam_str': legrabox_spec['back_holes']['diam_str']})
                    # Trous fond (vis 2.5/3)
                    for y in legrabox_spec['bottom_holes']['y_coords']:
                        if y < fond_H:
                            x_offset = legrabox_spec['bottom_holes']['x_offset']
                            bottom_holes.append({'type': 'vis', 'x': x_offset, 'y': y, 'diam_str': legrabox_spec['bottom_holes']['diam_str']})
                            bottom_holes.append({'type': 'vis', 'x': fond_L - x_offset, 'y': y, 'diam_str': legrabox_spec['bottom_holes']['diam_str']})
                else:
                    # TANDEMBOX : logique existante
                    face_coords_map = {'K': [47.5, 79.5, 111.5], 'M': [47.5, 79.5], 'N': [32.5, 64.5], 'D': [47.5, 79.5, 207.5]}
                    y_coords_face = face_coords_map.get(tech_type, [47.5, 79.5, 111.5])
                    for y in y_coords_face:
                        if y < dr_H:
                            f_holes.append({'type': 'tourillon', 'x': 32.5, 'y': y, 'diam_str': "⌀10/12"})
                            f_holes.append({'type': 'tourillon', 'x': dr_L - 32.5, 'y': y, 'diam_str': "⌀10/12"})
                    back_coords_map = {'K': [30.0, 62.0, 94.0], 'M': [32.0, 64.0], 'N': [31.0, 47.0], 'D': [31.0, 63.0, 95.0, 159.0, 191.0]}
                    y_coords_back = back_coords_map.get(tech_type, [30.0, 62.0, 94.0])
                    for dy in y_coords_back:
                        d_holes_t.append({'type': 'vis', 'x': 9.0, 'y': dy, 'diam_str': "⌀2.5/3"})
                        d_holes_t.append({'type': 'vis', 'x': d_L_t - 9.0, 'y': dy, 'diam_str': "⌀2.5/3"})

                # Convertir cutout tuple en dict si présent
                cutout_dict = None
                if cutout:
                    cutout_dict = {'width': cutout[0], 'height': cutout[1], 'offset_top': cutout[2]}
                
                # Créer un proj avec la quantité pour ce groupe
                proj_group = proj.copy()
                proj_group['quantity'] = quantity
                
                # Titre avec quantité si > 1
                title_suffix = f" (x{quantity})" if quantity > 1 else ""
                system_label = f" [{drawer_system} {tech_type}]" if drawer_system == 'LÉGRABOX' else f" [Type {tech_type}]"
                
                c_tf = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        f"Tiroir-Face Groupe {group_num} (C{sel_idx}){system_label}{title_suffix}",
                        dr_L, dr_H, dr_thickness,
                        unit_str, proj_group, c_tf, f_holes, [], [], cutout_dict
                    ),
                    use_container_width=True
                )
                
                c_td = {"Chant Avant":False, "Chant Arrière":False, "Chant Gauche":False, "Chant Droit":False}
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        f"Tiroir-Dos Groupe {group_num} (C{sel_idx}){system_label}{title_suffix}",
                        d_L_t, fixed_back_h, inner_thickness,
                        unit_str, proj_group, c_td, d_holes_t
                    ),
                    use_container_width=True
                )
                
                # Fond avec feuillure pour LÉGRABOX
                fond_title = f"Tiroir-Fond Groupe {group_num} (C{sel_idx}){system_label}{title_suffix}"
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        fond_title,
                        fond_L, fond_H, inner_thickness,
                        unit_str, proj_group, c_td, bottom_holes if drawer_system == 'LÉGRABOX' else [],
                        [], [], None, drawer_system == 'LÉGRABOX'  # has_rebate=True pour LÉGRABOX
                    ),
                    use_container_width=True
                )

        if 'shelves' in cab:
            # Fonction pour générer une signature unique pour chaque étagère
            def get_shelf_signature(s_idx, s, shelf_dims_cache, fixed_shelf_tr_draw, sel_idx):
                sl, sw = shelf_dims_cache.get(f"C{sel_idx}_S{s_idx}", (100,100))
                s_type = s.get('shelf_type', 'mobile')
                trh = fixed_shelf_tr_draw.get(s_idx, []) if s_type == 'fixe' else []
                thickness = s.get('thickness', 19.0)
                
                # Normaliser les trous pour la comparaison (tri par position)
                trh_normalized = tuple(sorted(
                    [(round(h.get('x', 0), 1), round(h.get('y', 0), 1), h.get('type', ''), h.get('diam_str', '')) 
                     for h in trh],
                    key=lambda h: (h[1], h[0])  # Trier par y puis x
                )) if trh else ()
                
                # Signature : (longueur, largeur, épaisseur, type, trous_normalisés)
                return (round(sl, 1), round(sw, 1), round(thickness, 1), s_type, trh_normalized)
            
            # Grouper les étagères par signature
            shelf_groups = {}
            for s_idx, s in enumerate(cab['shelves']):
                sig = get_shelf_signature(s_idx, s, shelf_dims_cache, fixed_shelf_tr_draw, sel_idx)
                if sig not in shelf_groups:
                    shelf_groups[sig] = []
                shelf_groups[sig].append((s_idx, s))
            
            # Générer les plans pour chaque groupe (une seule feuille par groupe avec quantité)
            group_num = 0
            for sig, group in shelf_groups.items():
                group_num += 1
                sl, sw, thickness, s_type, trh_normalized = sig
                quantity = len(group)
                
                # Prendre le premier étagère du groupe pour les données de référence
                first_shelf_idx, first_s = group[0]
                
                # Reconstruire les trous depuis la signature normalisée
                trh = []
                if trh_normalized:
                    trh = [
                        {'type': h[2], 'x': h[0], 'y': h[1], 'diam_str': h[3]}
                        for h in trh_normalized
                    ]
                
                # Créer un proj avec la quantité pour ce groupe
                proj_group = proj.copy()
                proj_group['quantity'] = quantity
                
                # Titre avec quantité si > 1
                title_suffix = f" (x{quantity})" if quantity > 1 else ""
                type_label = "Mobile" if s_type == 'mobile' else "Fixe"
                
                c_eta = {"Chant Avant":True, "Chant Arrière":False, "Chant Gauche":False, "Chant Droit":False}
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        f"Etagère Groupe {group_num} ({type_label}) (C{sel_idx}){title_suffix}",
                        sl, sw, thickness, unit_str, proj_group, c_eta, [], [], trh
                    ),
                    use_container_width=True
                )

        # Plans d'usinage pour les montants verticaux secondaires
        if 'vertical_dividers' in cab and cab['vertical_dividers']:
            # Parcourir tous les éléments et ajouter les trous sur les montants qui les touchent
            # (divider_element_holes a déjà été défini plus haut)
            
            # Les trous des étagères fixes sur les montants principaux ont déjà été ajoutés dans la section précédente
            # Ici, on ne gère que les montants secondaires
            # Étagères fixes
            # NOTE : les trous sur les montants principaux Mg/Md ont déjà été ajoutés plus haut
            # Ici on répartit uniquement les usinages sur les montants secondaires, face 1/2 (gauche) et 2/2 (droite)
            if 'shelves' in cab:
                for s_idx, s in enumerate(cab['shelves']):
                    s_type = s.get('shelf_type', 'mobile')
                    zone_id = s.get('zone_id', None)
                    
                    if s_type == 'fixe' and zone_id is not None and zone_id < len(zones):
                        zone = zones[zone_id]
                        yc_val = t_tb + s['height'] + s['thickness']/2.0
                        
                        # Recalculer les coordonnées X réelles de l'étagère (même logique que pour Mg/Md)
                        shelf_x_start_mm = None
                        shelf_x_end_mm = None
                        
                        # Utiliser les coordonnées stockées si disponibles
                        if s.get('stored_shelf_x_start_mm') is not None:
                            shelf_x_start_mm = s['stored_shelf_x_start_mm']
                            shelf_x_end_mm = shelf_x_start_mm + s.get('stored_shelf_width_mm', 0.0)
                        else:
                            zone_width_mm = zone['x_max'] - zone['x_min']
                            safety_margin_mm = 5.0
                            # Les étagères fixes prennent toute la zone moins la marge de sécurité
                            shelf_x_start_mm = zone['x_min'] + safety_margin_mm
                            shelf_x_end_mm = shelf_x_start_mm + (zone_width_mm - 2 * safety_margin_mm)
                        
                        # Pour chaque montant secondaire, déterminer si l'étagère touche la face gauche ou droite
                        for div_idx, div in enumerate(cab['vertical_dividers']):
                            div_x = div['position_x']
                            div_th = div.get('thickness', 19.0)
                            div_left_edge = div_x - div_th / 2.0   # face gauche du montant
                            div_right_edge = div_x + div_th / 2.0  # face droite du montant
                            
                            # Face GAUCHE : X_max de l'étagère coïncide avec la face gauche du montant
                            touches_left_face = shelf_x_end_mm is not None and abs(shelf_x_end_mm - div_left_edge) < 1.0
                            # Face DROITE : X_min de l'étagère coïncide avec la face droite du montant
                            touches_right_face = shelf_x_start_mm is not None and abs(shelf_x_start_mm - div_right_edge) < 1.0
                            
                            # Cas de sécurité : si l'étagère traverse complètement le montant (X_min < div_left_edge et X_max > div_right_edge)
                            # on reporte les usinages sur les deux faces
                            crosses_divider = False
                            if shelf_x_start_mm is not None and shelf_x_end_mm is not None:
                                crosses_divider = (shelf_x_start_mm < div_left_edge and shelf_x_end_mm > div_right_edge)
                            
                            if touches_left_face or crosses_divider:
                                # Élément à gauche (ou traversant) : trous sur la face gauche (1/2)
                                for x in ys_vis_sf:
                                    divider_element_holes_left[div_idx].append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3"})
                                for x in ys_dowel_sf:
                                    divider_element_holes_left[div_idx].append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
                            if touches_right_face or crosses_divider:
                                # Élément à droite (ou traversant) : trous sur la face droite (2/2)
                                for x in ys_vis_sf:
                                    divider_element_holes_right[div_idx].append({'type':'vis','x':x,'y':yc_val,'diam_str':"⌀3"})
                                for x in ys_dowel_sf:
                                    divider_element_holes_right[div_idx].append({'type':'tourillon','x':x,'y':yc_val,'diam_str':"⌀8/10"})
            
            # NOTE : Les trous pour les tiroirs sur les montants secondaires sont déjà ajoutés
            # dans la section "if 'drawers' in cab and cab['drawers']" plus haut
            
            # Générer les plans d'usinage pour chaque montant secondaire
            for div_idx, div in enumerate(cab['vertical_dividers']):
                div_th = div.get('thickness', 19.0)
                div_h = h_side  # Hauteur totale du montant
                div_w = W_mont  # Largeur (profondeur)
                
                # Trous sur les tranches haut et bas - alternance vis/tourillon sur toute la longueur (profondeur)
                div_tranche_holes = get_vertical_divider_tranche_holes(W_mont, div_th)
                
                # Vérifier si le montant a des éléments des deux côtés
                has_left_elements = len(divider_element_holes_left[div_idx]) > 0
                has_right_elements = len(divider_element_holes_right[div_idx]) > 0
                
                c_div = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
                
                # TOUJOURS générer 2 plans (1/2 et 2/2) pour chaque montant secondaire
                # Plan 1/2 : Face gauche (même si vide)
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        f"Montant Secondaire {div_idx+1} (C{sel_idx}) - 1/2",
                        div_w, div_h, div_th,
                        unit_str, proj, c_div,
                        divider_element_holes_left[div_idx],
                        div_tranche_holes, []
                    ),
                    use_container_width=True
                )
                # Plan 2/2 : Face droite (même si vide)
                st.plotly_chart(
                    draw_machining_view_pro_final(
                        f"Montant Secondaire {div_idx+1} (C{sel_idx}) - 2/2",
                        div_w, div_h, div_th,
                        unit_str, proj, c_div,
                        divider_element_holes_right[div_idx],
                        div_tranche_holes, []
                    ),
                    use_container_width=True
                )
        
        # Plans d'usinage pour les étagères verticales
        if 'vertical_shelves' in cab and cab['vertical_shelves']:
            for vs_idx, vs in enumerate(cab['vertical_shelves']):
                vs_th = vs.get('thickness', 19.0)
                vs_bottom_y = vs.get('bottom_y', 0.0)
                vs_top_y = vs.get('top_y', 100.0)
                vs_height = vs_top_y - vs_bottom_y
                vs_w = W_mont  # Largeur (profondeur)
                
                # AUCUN trou sur la face - uniquement sur les tranches haut et bas
                vs_holes = []  # Pas de trous sur la face
                
                # Trous sur les tranches haut et bas : 8 trous de tourillons (4 par tranche)
                vs_tranche_holes = get_vertical_shelf_tranche_holes(W_mont, vs_th)
                
                c_vs = {"Chant Avant":True, "Chant Arrière":True, "Chant Gauche":True, "Chant Droit":True}
                # Les trous des étagères verticales vont sur les tranches LONGUES (haut et bas)
                st.plotly_chart(draw_machining_view_pro_final(f"Étagère Verticale {vs_idx+1} (C{sel_idx})", vs_w, vs_height, vs_th, unit_str, proj, c_vs, vs_holes, vs_tranche_holes, []), use_container_width=True)

    else:
        st.info("Créez un caisson pour voir les plans.")