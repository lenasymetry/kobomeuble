# Refonte DXF robuste (Scene Graph + AutoCAD)

Date: 24 février 2026

## Objectif
Avoir un export DXF multi-feuilles fidèle au rendu UI, avec robustesse AutoCAD en priorité:
- mode `cnc` (défaut): cotes en primitives (`LINE` + flèches + `TEXT`)
- mode `editable`: cotes `DIMENSION` + `DIMSTYLE` minimal (fallback auto vers primitives si instable)

## Architecture implémentée
Nouveau package: `dxf_export/`

- `scene.py`
  - dataclasses de scène neutre: `Scene`, `Line`, `Polyline`, `Arc`, `Circle`, `Text`, `Leader`, `Dimension`, `HatchSimple`, `BlockDef`, `BlockRef`
  - `build_sheet_scene(sheet_data) -> Scene`

- `sanitize.py`
  - `sanitize_layer_name`, `sanitize_table_name`, `sanitize_text`, `limit_length`

- `render_streamlit.py`
  - `convert_plotly_figure_to_scene(fig, name)`
  - `render_scene_to_streamlit(scene)`

- `dimensions.py`
  - `add_dimensions_as_primitives(layout, dim, ...)` (mode CNC robuste)
  - `add_dimensions_editable(layout, dim)` (mode editable)

- `render_dxf.py`
  - `DxfRenderConfig`
  - `render_scene_to_dxf(scene, layout, config, debug_stage, log)`
  - `add_title_block`, `add_legend`, `add_part_geometry`, `add_holes`, `add_pockets`, `add_labels`
  - génération DXF `R2010` ASCII

- `audit.py`
  - `validate_dxf(doc) -> (ok, report)` via `doc.audit()` + contrôles références layer/style/dimstyle

- `__init__.py`
  - `export_project_to_dxf(project_data, mode, force_primitives_dims, debug, debug_stage) -> ExportResult`
  - build multi-layouts `SHEET_01`, `SHEET_02`, ...
  - fallback auto si échec mode editable

Compatibilité legacy:
- `dxf_export_valid.py` conserve `generate_complete_dxf(...)` et délègue au nouveau package.

## Intégration Streamlit
Dans `2.py` (section export):
- sélection mode:
  - `Atelier/CNC (robuste)`
  - `CAD éditable (DIMENSION)`
- option `Forcer cotes en primitives (anti-crash)`
- option `Mode DEBUG anti-écran noir`
- bouton de download DXF inchangé
- affichage du rapport d'audit/fallback dans un expander

## Règles anti-plantage AutoCAD appliquées
- DXF `R2010` via `ezdxf.new("R2010")`
- sortie ASCII stricte
- noms `LAYER/BLOCK/STYLE/DIMSTYLE` en ASCII `[A-Z0-9_-]`, longueur limitée
- textes normalisés ASCII
- priorité à `TEXT` (pas `MTEXT` dans le flux robuste)
- cotes primitives par défaut (pas de `DIMENSION` par défaut)
- pas de hatch complexe par défaut (`allow_hatch=False`)
- validation post-génération + post-relecture

## Debug reproductible anti-écran noir
Le mode debug lance des étapes séquentielles et logge la première étape fautive:
1. `geometry`
2. `text`
3. `legend`
4. `dimensions`

Chaque étape est auditée et le rapport est consolidé dans `ExportResult.report`.

## Utilisation rapide
```python
from dxf_export import export_project_to_dxf

result = export_project_to_dxf(
    {
        "cabinets_data": cabinets_data,
        "indices": list(range(len(cabinets_data))),
        "project_name": "MonProjet",
    },
    mode="cnc",                  # ou "editable"
    force_primitives_dims=True,   # recommandé
    debug=False,
)

if result.ok:
    st.download_button("Exporter DXF", result.dxf_bytes, "usinage.dxf", "application/dxf")
else:
    st.error(result.report)
```
