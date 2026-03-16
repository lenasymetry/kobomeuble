#!/usr/bin/env python3
"""Test que les trous des tiroirs sont maintenant sur les montants."""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

def test_mounting_holes():
    """Test que les trous de vis des tiroirs sont sur les montants."""
    print("=" * 70)
    print("TEST: Mounting Holes for Drawer Slides")
    print("=" * 70)
    
    import streamlit as st
    st.session_state.project_name = "Test"
    st.session_state.unit_select = "mm"
    
    from export_manager import get_all_machining_plans_figures
    
    # Meuble avec 2 tiroirs
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
                'drawer_bottom_offset': 0.0,  # Important!
            },
            {
                'drawer_system': 'TANDEMBOX',
                'drawer_tech_type': 'K',
                'drawer_face_H_raw': 150.0,
                'drawer_face_thickness': 19.0,
                'inner_thickness': 16.0,
                'drawer_gap': 2.0,
                'zone_id': 0,
                'drawer_bottom_offset': 200.0,  # Décalé verticalement
            }
        ],
        'door_props': {'has_door': False},
        'vertical_dividers': [],
        'shelves': []
    }
    
    try:
        print("\n✓ Generating all machining figures...")
        figures = get_all_machining_plans_figures([test_cabinet], [0])
        
        # Find the Montant Gauche figure
        montant_fig = None
        for title, fig in figures:
            if 'Montant Gauche' in title:
                montant_fig = (title, fig)
                break
        
        if not montant_fig:
            print("✗ No 'Montant Gauche' figure found")
            return 1
        
        title, fig = montant_fig
        print(f"\n✓ Found montant figure: {title}")
        
        # Analyze the figure data
        # Plotly figures contain trace data
        if hasattr(fig, 'data'):
            print(f"  Figure has {len(fig.data)} traces")
            
            # Try to extract hole information
            hole_count = 0
            for trace in fig.data:
                if hasattr(trace, 'name') and 'trou' in str(trace.name).lower():
                    hole_count += 1
                if hasattr(trace, 'hovertext') and trace.hovertext:
                    for text in (trace.hovertext if isinstance(trace.hovertext, list) else [trace.hovertext]):
                        if text and ('⌀' in str(text) or 'vis' in str(text).lower()):
                            hole_count += 1
            
            print(f"  Detected hole-related traces: {hole_count}")
            
            if hole_count > 0:
                print("\n✓ SUCCESS: Mounting holes appear to be in the figure!")
                print("  The drawer slide holes (trous de vis) should now be visible on the montants")
                return 0
            else:
                print("\n✗ Could not detect mounting holes in figure")
                print("  This might indicate the holes are not being added to the montants")
                return 1
        else:
            print("  Figure object doesn't have expected structure")
            return 1
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_mounting_holes())
