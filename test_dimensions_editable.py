#!/usr/bin/env python3
"""
Test: Verify that dimensions are created as proper AutoCAD DIMENSION entities
that can be edited with AutoCAD's COTE/DIMENSION tools.
"""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

import ezdxf

print("Creating test DXF with AutoCAD dimensions...")
print("-" * 80)

# Create a new DXF document
dxf = ezdxf.new('R2010')
msp = dxf.modelspace()

# Create the COTATIONS_PRO dimstyle (same as in export_manager.py)
if 'COTATIONS_PRO' not in dxf.dimstyles:
    dimstyle = dxf.dimstyles.new('COTATIONS_PRO')
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
    print("✅ Created COTATIONS_PRO dimstyle")

# Create COTES layer
if 'COTES' not in dxf.layers:
    dxf.layers.new('COTES', dxfattribs={'color': 3})  # Green = Dimensions
    print("✅ Created COTES layer")

# Draw a panel (rectangle)
panel_width = 500
panel_height = 300
x0, y0 = 100, 100
x1, y1 = x0 + panel_width, y0 + panel_height

# Draw the panel outline
msp.add_lwpolyline(
    [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
    dxfattribs={"layer": "0"}
)
print("✅ Drew panel outline (500x300mm)")

# Add horizontal dimension at the bottom
print("Adding horizontal dimension (width)...")
try:
    dim_h = msp.add_linear_dim(
        base=(x0, y0 - 80),
        p1=(x0, y0),
        p2=(x1, y0),
        angle=0,
        dimstyle='COTATIONS_PRO',
        dxfattribs={'layer': 'COTES', 'color': 3}
    )
    # DimStyleOverride properties
    if dim_h:
        dim_h.render()
        print("✅ Horizontal dimension created (should be editable with COTE tool)")
except Exception as e:
    print(f"❌ Failed to create horizontal dimension: {e}")

# Add vertical dimension on the left
print("Adding vertical dimension (height)...")
try:
    dim_v = msp.add_linear_dim(
        base=(x0 - 80, y0),
        p1=(x0, y0),
        p2=(x0, y1),
        angle=90,
        dimstyle='COTATIONS_PRO',
        dxfattribs={'layer': 'COTES', 'color': 3}
    )
    if dim_v:
        dim_v.render()
        print("✅ Vertical dimension created (should be editable with COTE tool)")
except Exception as e:
    print(f"❌ Failed to create vertical dimension: {e}")

# Check dimension entities in document
print("\n" + "=" * 80)
print("📊 Dimension Statistics:")
dim_count = 0
for entity in dxf.entities:
    if entity.dxftype() == 'DIMENSION':
        dim_count += 1
        try:
            print(f"   Found DIMENSION entity")
        except Exception:
            print(f"   Found DIMENSION entity (properties not accessible)")

print(f"Total DIMENSION entities: {dim_count}")

if dim_count > 0:
    print("\n✅ SUCCESS: Dimensions are proper AutoCAD DIMENSION entities!")
    print("   These can be edited with AutoCAD's COTE/DIMENSION tools")
else:
    print("\n⚠️  No DIMENSION entities found")

# Save the DXF
output_file = '/Users/lenapatarin/Documents/ANNEE1/code/test_dimensions_editable.dxf'
dxf.saveas(output_file)
print(f"\n✅ Test DXF saved to: {output_file}")
print("\nInstructions for AutoCAD:")
print("1. Open test_dimensions_editable.dxf in AutoCAD")
print("2. Click on a dimension (should be GREEN)")
print("3. Right-click and select 'Properties'")
print("4. You should see DimensionName = 'DIMENSION' (not LINE or LWPOLYLINE)")
print("5. Use AutoCAD's COTE/DIMENSION tool to edit the dimensions")
