# Power BI build guide

The Power BI report reads the CSV extracts in [`../data/powerbi/`](../data/powerbi), which come from the SQL scoring views.
All measures are in [`measures.dax`](measures.dax), and [`theme.json`](theme.json) sets the RAG and series colours.

## 1. Load data
Get Data → Text/CSV → load each file in `data/powerbi/`:
`risk_scores.csv`, `control_scores.csv`, `risk_control.csv`, `kri_rag.csv`, `issue_ageing.csv`.
Set `kri_rag[month]` to Text and `issue_ageing` date columns to Date.

(Or connect to `data/rcsa.db` through the SQLite ODBC driver and import the four `v_*` views.)

## 2. Model
| From | To | Cardinality |
|---|---|---|
| `risk_scores[risk_id]` | `risk_control[risk_id]` | 1 : * |
| `control_scores[control_id]` | `risk_control[control_id]` | 1 : * (both directions) |
| `risk_scores[risk_id]` | `issue_ageing[risk_id]` | 1 : * |
| `DimMonth[month]` | `kri_rag[month]` | 1 : * |

Create the calculated tables `DimMonth` and `DimRAG`, then paste in the measures from `measures.dax`.
Mark `DimMonth` as a date table on `DimMonth[date]`.

## 3. Pages
1. **RCSA overview**: KPI cards (Risks Assessed, Inherent High or Critical, Residual High or Critical, Risks Outside Appetite,
   Risk Reduction %). Two matrix heat maps (rows `impact` 5→1, columns `likelihood` / `residual_likelihood`, values
   `Heat Map Count`, background colour by field value `Heat Map Colour`). Risk register table with `inherent_rating` and
   `residual_rating` conditionally formatted.
2. **Controls**: bar chart of control score by control, a design vs operating matrix, and a table of controls that are not fully effective.
3. **KRI monitoring**: matrix of `kri_id` × `DimMonth[Month Label]` showing `KRI Value`, background colour from `KRI RAG Colour`.
   Line chart of a selected KRI with green/amber threshold constant lines. A card for `KRIs Red Latest`, and a table showing `KRI Breach Alert`.
4. **Issues**: `Open Issues`, `Overdue Issues`, `Overdue %` and `Avg Open Issue Age` cards; a column chart of open issues by
   `ageing_bucket`; an issue table filtered to Open with `due_status` conditionally formatted.

Slicers: risk category, sub-process, risk owner, KRI owner.

## 4. Check against Excel
After refresh, the KPI cards should match the `Summary` sheet in `excel/RCSA_KRI_Workbook.xlsx`:
18 risks, 25 controls, 12 inherent High/Critical risks, 2 residual High/Critical risks, 6 outside appetite, 2 KRIs Red in the latest month, 19 open issues, 9 overdue.
