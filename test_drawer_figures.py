#!/usr/bin/env python3
"""Test que les tiroirs sont maintenant présents dans l'export."""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

def test_drawer_figures_generation():
    """Test que les figures des tiroirs sont générées."""
    print("=" * 70)
    print("TEST: Drawer Figures Generation")
    print("=" * 70)
    
    # Setup streamlit session state BEFORE importing export_manager
    import streamlit as st
    st.session_state.project_name = "Test Project"
    st.session_state.unit_select = "mm"
    
    from export_manager import get_all_machining_plans_figures
    
    # Créer un meuble avec 4 tiroirs pour le test
    test_cabinet = {
        'dims': {
            'L_raw': 400.0, 'W_raw': 300.0, 'H_raw': 900.0,
            't_lr_raw': 19.0, 't_fb_raw': 18.0, 't_tb_raw': 18.0
        },
        'drawers': [
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,
                'y_slide': 200.0,
            },
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,
                'y_slide': 350.0,
            },
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,
                'y_slide': 500.0,
            },
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,
                'y_slide': 650.0,
            }
        ],
        'door_props': {'has_door': False},
        'vertical_dividers': [],
        'shelves': []
    }
    
    try:
        # Essayer d'appeler la fonction
        print("\n✓ Calling get_all_machining_plans_figures()...")
        
        # Call the function
        figures = get_all_machining_plans_figures([test_cabinet], [0])
        
        print(f"\n✓ Generated {len(figures)} figures")
        
        # Check for drawer figures
        drawer_figure_titles = [title for title, _ in figures if 'Tiroir' in title or 'Façade' in title or 'Dos' in title]
        print(f"\n✓ Found {len(drawer_figure_titles)} drawer-related figures:")
        for title in drawer_figure_titles:
            print(f"    - {title}")
        
        # Count expected vs actual
        print("\n" + "=" * 70)
        print("ANALYSIS")
        print("=" * 70)
        
        # Grouping: 4 identical drawers = 1 group
        # Per group: 1 facade + 1 dos + 1 fond = 3 figures
        # Expected: 4 panels minimum (traverse haut/bas, montant gauche/droit) + 3 drawer figures + 1 fond
        expected_drawer_figures = 3  # 1 facade + 1 dos + 1 fond
        actual_drawer_figures = len(drawer_figure_titles)
        
        if actual_drawer_figures >= expected_drawer_figures:
            print(f"✓ SUCCESS: Found {actual_drawer_figures} drawer figures (expected minimum {expected_drawer_figures})")
            print("\nThe drawer facade, back, and bottom figures are now being generated!")
            return 0
        else:
            print(f"✗ FAILURE: Found {actual_drawer_figures} drawer figures (expected minimum {expected_drawer_figures})")
            print("\nAll figures generated:")
            for title, _ in figures:
                print(f"    {title}")
            return 1
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_drawer_figures_generation())
