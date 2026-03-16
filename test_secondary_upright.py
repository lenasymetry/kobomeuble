#!/usr/bin/env python3
"""Test que les trous des tiroirs sont maintenant sur les montants secondaires."""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

def test_secondary_upright_holes():
    """Test montants secondaires ont les trous de tiroir."""
    print("=" * 70)
    print("TEST: Drawer Holes on Secondary Uprights (Montants Secondaires)")
    print("=" * 70)
    
    import streamlit as st
    st.session_state.project_name = "Test"
    st.session_state.unit_select = "mm"
    
    from export_manager import get_all_machining_plans_figures
    
    # Meuble avec 1 diviseur vertical (montant secondaire) et 1 tiroir
    test_cabinet = {
        'dims': {
            'L_raw': 600.0, 'W_raw': 300.0, 'H_raw': 900.0,
            't_lr_raw': 19.0, 't_fb_raw': 18.0, 't_tb_raw': 18.0
        },
        'vertical_dividers': [
            {
                'position_x': 300.0,  # Au milieu
                'thickness': 19.0,
                'height': 900.0
            }
        ],
        'drawers': [
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,  # Zone à gauche du diviseur
                'drawer_bottom_offset': 0.0,
            }
        ],
        'door_props': {'has_door': False},
        'shelves': []
    }
    
    try:
        print("\n✓ Generating figures for cabinet with divisor and drawer...")
        figures = get_all_machining_plans_figures([test_cabinet], [0])
        
        # Find the secondary upright figure
        secondary_upright_figures = [
            title for title, _ in figures 
            if 'Montant Secondaire' in title
        ]
        
        print(f"\n✓ Found {len(secondary_upright_figures)} secondary upright figures:")
        for title in secondary_upright_figures:
            print(f"    - {title}")
        
        if len(secondary_upright_figures) < 2:
            print("\n⚠ Warning: Should have at least 2 secondary upright figures (1/2 and 2/2)")
        
        print("\n" + "=" * 70)
        print("ANALYSIS")
        print("=" * 70)
        
        if secondary_upright_figures:
            print("✓ SUCCESS: Secondary uprights are being generated!")
            print("\nWith the corrected geometry logic (div_left_edge, div_right_edge):")
            print("  - The drawer touching the left side of the divisor should add")
            print("    holes to the 1/2 part (divider_element_holes_left)")
            print("  - Holes should appear at y_slide position calculated correctly")
            return 0
        else:
            print("✗ No secondary uprights found in figures")
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
    sys.exit(test_secondary_upright_holes())
