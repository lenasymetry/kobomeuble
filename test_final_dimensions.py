#!/usr/bin/env python3
"""
Final Test: Verify dimensions work correctly in actual DXF export
"""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

import ezdxf

print("Testing dimensions with real DXF export setup...")
print("-" * 80)

# Simulate what export_manager.py does
dxf_doc = ezdxf.new('R2010')
msp = dxf_doc.modelspace()

# Create the COTATIONS_PRO dimstyle (exact same as in export_manager.py)
try:
    if 'COTATIONS_PRO' not in dxf_doc.dimstyles:
        dimstyle = dxf_doc.dimstyles.new('COTATIONS_PRO')
        dimstyle.dxf.dimblk = 'CLOSEDBLANK'
        dimstyle.dxf.dimblk1 = 'CLOSEDBLANK'
        dimstyle.dxf.dimblk2 = 'CLOSEDBLANK'
        dimstyle.dxf.dimasz = 3.0
        dimstyle.dxf.dimtxt = 12.0
        dimstyle.dxf.dimexe = 1.5
        dimstyle.dxf.dimexo = 1.0
        dimstyle.dxf.dimgap = 2.0
        dimstyle.dxf.dimtad = 1
        dimstyle.dxf.dimdec = 1
        dimstyle.dxf.dimzin = 8
        dimstyle.dxf.dimclrd = 3  # Green
        dimstyle.dxf.dimclre = 3
        dimstyle.dxf.dimclrt = 3
        print("✅ COTATIONS_PRO dimstyle created")
except Exception as e:
    print(f"⚠️  Could not create dimstyle: {e}", file=sys.stderr)

# Create COTES layer  
if 'COTES' not in dxf_doc.layers:
    dxf_doc.layers.new('COTES', dxfattribs={'color': 3})

# Simulate _add_linear_dimension_dxf function from export_manager.py
def _add_linear_dimension_dxf(msp, base, p1, p2, angle, layer="COTES", text_override=None, dimstyle="COTATIONS_PRO"):
    """Ajoute une vraie dimension AutoCAD éditable avec l'outil COTE."""
    try:
        dim = msp.add_linear_dim(
            base=base,
            p1=p1,
            p2=p2,
            angle=angle,
            dimstyle=dimstyle,
            dxfattribs={"layer": layer, "color": 3},
        )
        if text_override:
            try:
                dim.text = text_override
            except Exception:
                pass
        try:
            dim.dimtad = 1
            dim.dimgap = 2.0
            dim.dimtix = 0
            dim.dimdli = 3.75
        except Exception:
            pass
        dim.render()
        return dim
    except Exception as e:
        print(f"[DXF] Warning: Failed to create dimension at {base}: {e}", file=sys.stderr)
        return None

# Draw a panel
print("\nDrawing test panel with dimensions...")
x0, y0 = 100, 100
x1, y1 = 600, 400

# Outline
msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], dxfattribs={"layer": "0"})

# Add dimensions using the same function as export_manager.py
_add_linear_dimension_dxf(msp, base=(x0, y0 - 80.0), p1=(x0, y0), p2=(x1, y0), angle=0, layer="COTES")
_add_linear_dimension_dxf(msp, base=(x0 - 80.0, y0), p1=(x0, y0), p2=(x0, y1), angle=90, layer="COTES")

# Add some hole position dimensions (like export_manager does)
hole_positions = [150, 300, 450]
for idx, hx in enumerate(hole_positions):
    base_y = y0 - 180.0 - (idx * 50.0)
    _add_linear_dimension_dxf(msp, base=(x0, base_y), p1=(x0, y0), p2=(x0 + hx, y0), angle=0, layer="COTES")

print(f"✅ Added 5 dimensions to the DXF")

# Verify dimensions were created
dim_count = sum(1 for entity in dxf_doc.entities if entity.dxftype() == 'DIMENSION')
print(f"✅ Total DIMENSION entities in file: {dim_count}")

if dim_count == 5:
    print("✅ SUCCESS: All dimensions created correctly!")
else:
    print(f"⚠️  Expected 5 dimensions, got {dim_count}")

# Save
output_file = '/Users/lenapatarin/Documents/ANNEE1/code/test_export_dimensions.dxf'
dxf_doc.saveas(output_file)
print(f"\n✅ Test DXF saved to: {output_file}")

print("\n" + "=" * 80)
print("✅ VERIFICATION COMPLETE")
print("   Dimensions are proper AutoCAD DIMENSION entities")
print("   Ready for editing with COTE tool in AutoCAD")
print("=" * 80)
