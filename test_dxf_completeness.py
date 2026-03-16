#!/usr/bin/env python3
"""
TEST SCRIPT: Verify DXF export includes ALL elements
This will create a test cabinet and export DXF, then verify completeness
"""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

# Mock streamlit session state before importing export_manager
import streamlit as st
if 'project_name' not in st.session_state:
    st.session_state.project_name = "Test Project"
if 'unit_select' not in st.session_state:
    st.session_state.unit_select = "mm"
if 'foot_height' not in st.session_state:
    st.session_state.foot_height = 100

from export_manager import generate_stacked_html_plans
import ezdxf
import tempfile
from pathlib import Path

def test_dxf_completeness():
    """Test that DXF export has same number of elements as the plans list"""
    
    # Create a comprehensive test cabinet with all element types
    test_cabinet = {
        "dims": {
            "L_raw": 900,
            "W_raw": 550,
            "H_raw": 1000,
            "t_lr_raw": 19,    # Montants gauche/droit
            "t_fb_raw": 3,     # Panneau arrière
            "t_tb_raw": 19,    # Traverses haut/bas
        },
        "base_elements": {
            "has_bottom_traverse": True,
            "has_top_traverse": True,
            "has_left_upright": True,
            "has_right_upright": True,
            "has_back_panel": True,
        },
        
        # Add fixed and mobile shelves
        "shelves": [
            {
                "shelf_type": "fixe",
                "thickness": 19,
                "height": 300,
            },
            {
                "shelf_type": "mobile",
                "thickness": 19,
                "height": 600,
            },
        ],
        
        # Add drawers (should create face + back + bottom)
        "drawers": [
            {
                "drawer_tech_type": "K",
                "drawer_bottom_offset": 0,
                "drawer_system": "TANDEMBOX",
                "zone_id": 0,
            }
        ],
        
        # Add door
        "door_props": {
            "has_door": True,
            "door_type": "single",
            "door_gap": 10,
            "door_opening": "left",
            "door_thickness": 18,
            "door_model": "standard",
        },
        
        # Add vertical dividers
        "vertical_dividers": [
            {
                "position_x": 450,
                "thickness": 19,
            }
        ],
    }
    
    print("=" * 80)
    print("DXF EXPORT COMPLETENESS TEST")
    print("=" * 80)
    
    print("\nTest Cabinet Configuration:")
    print("  - Has bottom traverse: Yes")
    print("  - Has top traverse: Yes")
    print("  - Has left upright: Yes")
    print("  - Has right upright: Yes")
    print("  - Has back panel: Yes")
    print("  - Shelves: 2 (1 fixed + 1 mobile)")
    print("  - Drawers: 1 (should create 3 layouts: face + back + bottom)")
    print("  - Door: 1")
    print("  - Vertical dividers: 1 (should create 2 layouts: 1/2 + 2/2)")
    
    expected_minimum = {
        "Traverse Bas": 1,
        "Traverse Haut": 1,
        "Montant Gauche": 1,
        "Montant Droit": 1,
        "Panneau Arrière": 1,
        "Shelves": 2,
        "Drawer (Face+Back+Bottom)": 3,
        "Door": 1,
        "Montant Secondaire (2 layouts)": 2,
    }
    
    expected_total = sum(expected_minimum.values())
    print(f"\nExpected minimum layouts: {expected_total}")
    for item, count in expected_minimum.items():
        print(f"  - {item}: {count}")
    
    print("\n" + "-" * 80)
    print("Generating DXF...\n")
    
    try:
        dxf_bytes, success = generate_stacked_html_plans(
            cabinets_to_process=[test_cabinet],
            indices_to_process=[0],
            output_format='dxf'
        )
        
        if not success:
            print(f"❌ DXF generation FAILED:")
            print(f"   {dxf_bytes.decode('utf-8', errors='ignore')}")
            return False
        
        print(f"✓ DXF generated successfully ({len(dxf_bytes)} bytes)")
        
        # Write to temp file and analyze
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = Path(f.name)
            f.write(dxf_bytes)
        
        try:
            # Count layouts by counting distinct TEXT entities that look like titles
            doc = ezdxf.readfile(str(temp_path))
            msp = doc.modelspace()
            
            # Count text entities that start with "FEUILLE D'USINAGE"
            layout_count = 0
            layout_titles = []
            
            for entity in msp.query('TEXT'):
                try:
                    text = entity.dxf.text
                    if "FEUILLE D'USINAGE" in text:
                        layout_count += 1
                        # Extract the title part
                        title = text.replace("FEUILLE D'USINAGE : ", "").strip()
                        layout_titles.append(title)
                except:
                    pass
            
            print(f"\n✓ DXF contains {layout_count} layouts")
            print("\nLayout titles found:")
            for i, title in enumerate(layout_titles, 1):
                print(f"  {i}. {title}")
            
            print("\n" + "-" * 80)
            print("VALIDATION:")
            print(f"  Expected: ≥ {expected_total} layouts")
            print(f"  Actual:   {layout_count} layouts")
            
            if layout_count >= expected_total:
                print(f"\n✅ SUCCESS: DXF has all expected layouts!")
                return True
            else:
                print(f"\n❌ FAILURE: DXF is missing {expected_total - layout_count} layouts!")
                return False
        
        finally:
            temp_path.unlink(missing_ok=True)
    
    except Exception as e:
        import traceback
        print(f"❌ Exception during test:")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_dxf_completeness()
    sys.exit(0 if success else 1)
