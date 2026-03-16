#!/usr/bin/env python3
"""Test complet que l'export DXF contient maintenant les tiroirs."""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

def test_dxf_with_drawers():
    """Test que l'export DXF inclut les tiroirs."""
    print("=" * 70)
    print("TEST: Complete DXF Export with Drawers")
    print("=" * 70)
    
    import streamlit as st
    import io
    import ezdxf
    
    # Setup streamlit
    st.session_state.project_name = "Test Meuble"
    st.session_state.unit_select = "mm"
    
    # Import après setup
    from dxf_export import export_project_to_dxf
    
    # Créer projet avec meuble + 4 tiroirs identiques
    project_data = {
        "cabinets_data": [
            {
                'dims': {
                    'L_raw': 400.0, 'W_raw': 300.0, 'H_raw': 900.0,
                    't_lr_raw': 19.0, 't_fb_raw': 18.0, 't_tb_raw': 18.0
                },
                'name': 'Meuble Test 4 Tiroirs',
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
        ],
        "indices": [0],
        "project_name": "Test Meuble",
        "client": "Test",
        "comments": "Meuble de test avec 4 tiroirs",
        "version": "V1",
        "paper_width_mm": 420.0,
        "paper_height_mm": 297.0,
        "page_margin_mm": 10.0,
        "bbox_margin_factor": 1.05,
        "text_height": 2.5,
        "triangle_size": 8.0,
    }
    
    try:
        print("\n✓ Calling export_project_to_dxf()...")
        result = export_project_to_dxf(project_data, mode="cnc", force_primitives_dims=True, debug=False)
        
        print(f"  DXF export OK: {result.ok}")
        print(f"  Report: {result.report}")
        
        if not result.ok:
            print(f"✗ Export failed: {result.report}")
            return 1
        
        # Vérifier que le DXF est valide
        dxf_bytes = result.dxf_bytes
        print(f"  DXF size: {len(dxf_bytes)} bytes")
        
        # Lire le DXF pour compter les layouts
        try:
            dxf_content = dxf_bytes.decode('utf-8')
            
            # Compter les LAYOUTS
            layout_count = dxf_content.count('LAYOUT')
            print(f"\n✓ DXF Analysis:")
            print(f"    - Layout count: {layout_count}")
            
            # Chercher les références aux tiroirs
            drawer_refs = dxf_content.count('Tiroir') + dxf_content.count('Façade') + dxf_content.count('Dos')
            print(f"    - Drawer text references: {drawer_refs}")
            
            if drawer_refs > 0:
                print(f"\n✓ SUCCESS: Drawers found in DXF export!")
                print(f"  Expected elements:")
                print(f"    - Travergés (2)")
                print(f"    - Montants (2)")
                print(f"    - Fond (1)")
                print(f"    - Tiroir-Façade (1 grouped as x4)")
                print(f"    - Tiroir-Dos (1 grouped as x4)")
                print(f"    - Tiroir-Fond (1 grouped as x4)")
                print(f"    Total expected: 8 layouts minimum")
                return 0
            else:
                print(f"\n✗ No drawer references found in DXF")
                return 1
        except Exception as e:
            print(f"✗ Error analyzing DXF: {e}")
            return 1
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_dxf_with_drawers())
