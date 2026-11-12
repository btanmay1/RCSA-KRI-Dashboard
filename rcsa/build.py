"""Build every artefact from the catalogue:

  data/*.csv                 catalogue + 12 months of KRI values + issues
  data/rcsa.db               SQLite database with scoring views (sql/schema.sql)
  data/powerbi/*.csv         flattened view extracts that Power BI imports
  excel/RCSA_KRI_Workbook.xlsx   RCSA register, heat maps, KRI dashboard, issue log - all live Excel formulas
  docs/*.png                 dashboard preview images

    python -m rcsa.build
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import catalogue as K

ROOT = Path(__file__).resolve().parent.parent
DATA, EXCEL, DOCS = ROOT / "data", ROOT / "excel", ROOT / "docs"
BANDS = [("Low", 1, 5, 1), ("Medium", 6, 11, 2), ("High", 12, 19, 3), ("Critical", 20, 25, 4)]


def band(score: float) -> str:
    return next(b for b, lo, hi, _ in BANDS if lo <= score <= hi)


# ----------------------------------------------------------------------------- data
def catalogue_frames() -> dict[str, pd.DataFrame]:
    risks = pd.DataFrame(K.RISKS, columns=["risk_id", "title", "description", "category", "sub_process", "owner", "impact", "likelihood"])
    controls = pd.DataFrame(K.CONTROLS, columns=["control_id", "name", "control_type", "nature", "frequency", "owner", "design_rating", "operating_rating"])
    rc = pd.DataFrame(K.RISK_CONTROL_MAP, columns=["risk_id", "control_id"])
    kris = pd.DataFrame([k[:6] + (k[9],) for k in K.KRIS], columns=["kri_id", "name", "unit", "linked_risks", "green_max", "amber_max", "owner"])
    return {"risk": risks, "control": controls, "risk_control": rc, "kri": kris}


def kri_values(seed: int = 2026) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    shocks = {("K03", 7): 5, ("K03", 8): 3, ("K09", 9): 4, ("K09", 10): 5, ("K09", 11): 4,
              ("K10", 10): 3.5, ("K10", 11): 2.5, ("K05", 6): 1.0, ("K11", 11): 2.6, ("K12", 4): 4}
    rows = []
    for kid, _, unit, _, _, _, base, drift, noise, _ in K.KRIS:
        for t, m in enumerate(K.MONTHS):
            v = max(0.0, base + drift * t + rng.normal(0, noise) + shocks.get((kid, t), 0))
            v = float(round(v)) if unit == "count" else round(v, 2)
            rows.append((kid, m, v))
    return pd.DataFrame(rows, columns=["kri_id", "month", "value"])


def issues(controls: pd.DataFrame, rc: pd.DataFrame, kv: pd.DataFrame, kris: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    as_of = date.fromisoformat(K.AS_OF_DATE)
    out = []
    weak = controls[(controls.design_rating != "Effective") | (controls.operating_rating != "Effective")]
    for _, c in weak.iterrows():
        sev = "High" if "Ineffective" in (c.design_rating, c.operating_rating) else "Medium"
        raised = as_of - timedelta(days=int(rng.integers(10, 200)))
        due = raised + timedelta(days=60 if sev == "High" else 90)
        closed = None
        if rng.random() < 0.35 and raised + timedelta(days=30) < as_of:
            closed = raised + timedelta(days=int(rng.integers(20, min(120, (as_of - raised).days))))
        gap = "design" if c.design_rating != "Effective" else "operating"
        out.append(dict(title=f"{c['name']}: {gap} weakness identified in RCSA", source="RCSA control weakness",
                        risk_id=rc.loc[rc.control_id == c.control_id, "risk_id"].iloc[0], control_id=c.control_id, kri_id=None,
                        severity=sev, owner=c.owner, raised_date=raised, due_date=due, closed_date=closed))
    rag = kv.merge(kris, on="kri_id")
    red = rag[rag.value > rag.amber_max].sort_values("month").groupby("kri_id").first().reset_index()
    for _, r in red.iterrows():
        y, m = map(int, r.month.split("-"))
        raised = date(y + (m == 12), m % 12 + 1, 5)
        if raised > as_of:
            raised = as_of
        due = raised + timedelta(days=45)
        out.append(dict(title=f"KRI breach (Red): {r['name']}", source="KRI breach", risk_id=r.linked_risks.split(";")[0],
                        control_id=None, kri_id=r.kri_id, severity="High", owner=r.owner, raised_date=raised, due_date=due,
                        closed_date=None))
    df = pd.DataFrame(out).sort_values("raised_date").reset_index(drop=True)
    df.insert(0, "issue_id", [f"ISS-{i:03d}" for i in range(1, len(df) + 1)])
    df["status"] = np.where(df.closed_date.notna(), "Closed", "Open")
    for c in ("raised_date", "due_date", "closed_date"):
        df[c] = df[c].map(lambda d: d.isoformat() if isinstance(d, date) else None)
    return df


# ----------------------------------------------------------------------------- python reference scoring
def python_scores(f: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Independent implementation of the scoring model, used to cross-check the SQL views."""
    cs = f["control"].assign(control_score=lambda d: np.minimum(d.design_rating.map(K.RATING_SCORE), d.operating_rating.map(K.RATING_SCORE)))
    avg = f["risk_control"].merge(cs, on="control_id").groupby("risk_id").control_score.mean()
    r = f["risk"].set_index("risk_id").assign(avg=avg)
    r["inherent_score"] = r.impact * r.likelihood
    red = (r.avg - 1) / 2 * K.MAX_REDUCTION
    r["residual_likelihood"] = [max(1, math.floor(l * (1 - x) + 0.5)) for l, x in zip(r.likelihood, red)]
    r["residual_score"] = r.impact * r.residual_likelihood
    return r.reset_index()[["risk_id", "inherent_score", "residual_likelihood", "residual_score"]]


# ----------------------------------------------------------------------------- database
def build_db(f: dict[str, pd.DataFrame], db_path: Path) -> sqlite3.Connection:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO parameter VALUES (?, ?)", [("as_of_date", K.AS_OF_DATE), ("max_reduction", str(K.MAX_REDUCTION)),
                                                            ("risk_appetite_residual", str(K.RISK_APPETITE_RESIDUAL))])
    con.executemany("INSERT INTO rating_band VALUES (?, ?, ?, ?)", BANDS)
    for table in ("risk", "control", "risk_control", "kri", "kri_value", "issue"):
        f[table].to_sql(table, con, if_exists="append", index=False)
    con.commit()
    return con


# ----------------------------------------------------------------------------- excel
def build_excel(f: dict[str, pd.DataFrame], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    HFILL, HFONT = PatternFill("solid", fgColor="1F3864"), Font(bold=True, color="FFFFFF")
    thin = Side(style="thin", color="BFBFBF")
    BORDER = Border(top=thin, bottom=thin, left=thin, right=thin)
    FILL = {"Green": "C6EFCE", "Amber": "FFEB9C", "Red": "FFC7CE",
            "Low": "C6EFCE", "Medium": "FFEB9C", "High": "F8CBAD", "Critical": "FF7C80"}
    wb = Workbook()

    def sheet(title, headers, rows, widths=None):
        ws = wb.create_sheet(title)
        for j, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=j, value=h)
            c.fill, c.font, c.border = HFILL, HFONT, BORDER
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for i, row in enumerate(rows, 2):
            for j, v in enumerate(row, 1):
                c = ws.cell(row=i, column=j, value=v)
                c.border = BORDER
        for j, w in enumerate(widths or [], 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
        return ws

    def rag_format(ws, rng, labels):
        for lab in labels:
            ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{lab}"'], fill=PatternFill("solid", fgColor=FILL[lab])))

    wb.remove(wb.active)
    ws = wb.create_sheet("Summary")  # filled at the end

    # Parameters
    p = sheet("Parameters", ["Parameter", "Value", "Meaning"], [
        ["As-of date", date.fromisoformat(K.AS_OF_DATE), "Reporting date for issue ageing"],
        ["Max likelihood reduction", K.MAX_REDUCTION, "Reduction applied when all mapped controls are Effective"],
        ["Residual risk appetite", K.RISK_APPETITE_RESIDUAL, "Residual score above this is outside appetite"],
    ], [28, 14, 60])
    p["B2"].number_format = "dd-mmm-yyyy"
    p["B3"].number_format = "0%"

    # Control library
    rows = []
    for i, c in enumerate(f["control"].itertuples(), 2):
        rows.append([c.control_id, c.name, c.control_type, c.nature, c.frequency, c.owner, c.design_rating, c.operating_rating,
                     f'=MATCH(G{i},{{"Ineffective","Partially Effective","Effective"}},0)',
                     f'=MATCH(H{i},{{"Ineffective","Partially Effective","Effective"}},0)', f"=MIN(I{i},J{i})"])
    cl = sheet("Control_Library", ["Control ID", "Control", "Type", "Nature", "Frequency", "Owner", "Design rating",
                                   "Operating rating", "Design score", "Operating score", "Control score (min)"],
               rows, [10, 48, 11, 18, 22, 20, 18, 18, 10, 10, 12])
    n_c = len(rows) + 1
    dv = DataValidation(type="list", formula1='"Effective,Partially Effective,Ineffective"', allow_blank=False)
    cl.add_data_validation(dv)
    dv.add(f"G2:H{n_c}")
    rag_format(cl, f"G2:H{n_c}", [])
    for lab, col in (("Effective", "C6EFCE"), ("Partially Effective", "FFEB9C"), ("Ineffective", "FFC7CE")):
        cl.conditional_formatting.add(f"G2:H{n_c}", CellIsRule(operator="equal", formula=[f'"{lab}"'], fill=PatternFill("solid", fgColor=col)))

    # Risk-control map
    rows = []
    for i, m in enumerate(f["risk_control"].itertuples(), 2):
        rows.append([m.risk_id, m.control_id,
                     f"=INDEX(Control_Library!$B:$B,MATCH(B{i},Control_Library!$A:$A,0))",
                     f"=INDEX(Control_Library!$K:$K,MATCH(B{i},Control_Library!$A:$A,0))"])
    sheet("Risk_Control_Map", ["Risk ID", "Control ID", "Control", "Control score"], rows, [10, 11, 50, 13])

    # Risk register (RCSA)
    rows = []
    for i, r in enumerate(f["risk"].itertuples(), 2):
        rate = lambda c: f'IF({c}{i}>=20,"Critical",IF({c}{i}>=12,"High",IF({c}{i}>=6,"Medium","Low")))'
        rows.append([r.risk_id, r.title, r.description, r.category, r.sub_process, r.owner, r.impact, r.likelihood,
                     f"=G{i}*H{i}", "=" + rate("I"),
                     f"=COUNTIF(Risk_Control_Map!$A:$A,A{i})",
                     f"=ROUND(AVERAGEIF(Risk_Control_Map!$A:$A,A{i},Risk_Control_Map!$D:$D),2)",
                     f'=IF(L{i}>=2.75,"Effective",IF(L{i}>=1.75,"Partially Effective","Ineffective"))',
                     f"=(AVERAGEIF(Risk_Control_Map!$A:$A,A{i},Risk_Control_Map!$D:$D)-1)/2*Parameters!$B$3",
                     f"=MAX(1,ROUND(H{i}*(1-N{i}),0))", f"=G{i}*O{i}", "=" + rate("P"),
                     f'=IF(P{i}>Parameters!$B$4,"Outside appetite","Within appetite")'])
    rr = sheet("Risk_Register", ["Risk ID", "Risk", "Description", "Category", "Sub-process", "Risk owner", "Impact (1-5)",
                                 "Likelihood (1-5)", "Inherent score", "Inherent rating", "Mapped controls", "Avg control score",
                                 "Control effectiveness", "Likelihood reduction", "Residual likelihood", "Residual score",
                                 "Residual rating", "Appetite status"],
               rows, [9, 34, 60, 24, 26, 22, 9, 10, 9, 11, 9, 10, 18, 11, 10, 9, 11, 16])
    n_r = len(rows) + 1
    for c in range(1, 19):
        rr.cell(row=1, column=c).alignment = Alignment(wrap_text=True, vertical="center")
    for row in rr.iter_rows(min_row=2, max_row=n_r, min_col=3, max_col=3):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for i in range(2, n_r + 1):
        rr[f"N{i}"].number_format = "0%"
    dv2 = DataValidation(type="whole", operator="between", formula1="1", formula2="5")
    rr.add_data_validation(dv2)
    dv2.add(f"G2:H{n_r}")
    rag_format(rr, f"J2:J{n_r}", ["Low", "Medium", "High", "Critical"])
    rag_format(rr, f"Q2:Q{n_r}", ["Low", "Medium", "High", "Critical"])
    rr.conditional_formatting.add(f"R2:R{n_r}", CellIsRule(operator="equal", formula=['"Outside appetite"'], fill=PatternFill("solid", fgColor="FFC7CE")))

    # Heat maps
    hm = wb.create_sheet("Heat_Map")
    for top, title, lcol in ((1, "Inherent risk heat map (count of risks)", "$H:$H"), (10, "Residual risk heat map (count of risks)", "$O:$O")):
        hm.cell(row=top, column=1, value=title).font = Font(bold=True, size=12)
        hm.cell(row=top + 1, column=1, value="Impact ↓ / Likelihood →").font = Font(italic=True)
        for l in range(1, 6):
            c = hm.cell(row=top + 1, column=l + 1, value=l)
            c.font, c.alignment = Font(bold=True), Alignment(horizontal="center")
        for k, imp in enumerate(range(5, 0, -1)):
            row = top + 2 + k
            hm.cell(row=row, column=1, value=imp).font = Font(bold=True)
            for l in range(1, 6):
                c = hm.cell(row=row, column=l + 1, value=f"=COUNTIFS(Risk_Register!$G:$G,{imp},Risk_Register!{lcol},{l})")
                c.fill = PatternFill("solid", fgColor=FILL[band(imp * l)])
                c.alignment, c.border, c.font = Alignment(horizontal="center", vertical="center"), BORDER, Font(bold=True, size=12)
            hm.row_dimensions[row].height = 30
    hm.cell(row=19, column=1, value="Cell colour = rating band of impact × likelihood: Low 1-5, Medium 6-11, High 12-19, Critical 20-25.").font = Font(italic=True)
    hm.column_dimensions["A"].width = 26
    for l in "BCDEF":
        hm.column_dimensions[l].width = 10

    # KRI library and data
    rows = [[k.kri_id, k.name, k.unit, k.linked_risks, k.green_max, k.amber_max, k.owner] for k in f["kri"].itertuples()]
    sheet("KRI_Library", ["KRI ID", "KRI", "Unit", "Linked risks", "Green if ≤", "Amber if ≤ (else Red)", "Owner"], rows,
          [8, 55, 8, 12, 10, 14, 24])
    rows = []
    for i, v in enumerate(f["kri_value"].itertuples(), 2):
        rows.append([v.kri_id, v.month, v.value,
                     f"=INDEX(KRI_Library!$E:$E,MATCH(A{i},KRI_Library!$A:$A,0))",
                     f"=INDEX(KRI_Library!$F:$F,MATCH(A{i},KRI_Library!$A:$A,0))",
                     f'=IF(C{i}<=D{i},"Green",IF(C{i}<=E{i},"Amber","Red"))'])
    kd = sheet("KRI_Data", ["KRI ID", "Month", "Value", "Green max", "Amber max", "RAG"], rows, [8, 10, 10, 10, 10, 10])
    n_k = len(rows) + 1
    rag_format(kd, f"F2:F{n_k}", ["Green", "Amber", "Red"])

    # KRI dashboard matrix
    kdash = wb.create_sheet("KRI_Dashboard")
    heads = ["KRI ID", "KRI", "Green ≤", "Amber ≤"] + K.MONTHS + ["Latest RAG", "Months Red", "Months Amber"]
    for j, h in enumerate(heads, 1):
        c = kdash.cell(row=1, column=j, value=h)
        c.fill, c.font, c.border = HFILL, HFONT, BORDER
        c.alignment = Alignment(wrap_text=True, horizontal="center")
    first_m, last_m = 5, 4 + len(K.MONTHS)
    for i, k in enumerate(f["kri"].itertuples(), 2):
        vals = [k.kri_id, k.name, k.green_max, k.amber_max]
        for j, v in enumerate(vals, 1):
            kdash.cell(row=i, column=j, value=v).border = BORDER
        for j in range(first_m, last_m + 1):
            mcol = get_column_letter(j)
            c = kdash.cell(row=i, column=j, value=f'=SUMIFS(KRI_Data!$C:$C,KRI_Data!$A:$A,$A{i},KRI_Data!$B:$B,{mcol}$1)')
            c.border, c.alignment = BORDER, Alignment(horizontal="center")
        L = get_column_letter(last_m)
        kdash.cell(row=i, column=last_m + 1, value=f'=IF({L}{i}<=C{i},"Green",IF({L}{i}<=D{i},"Amber","Red"))').border = BORDER
        kdash.cell(row=i, column=last_m + 2, value=f'=COUNTIFS(KRI_Data!$A:$A,A{i},KRI_Data!$F:$F,"Red")').border = BORDER
        kdash.cell(row=i, column=last_m + 3, value=f'=COUNTIFS(KRI_Data!$A:$A,A{i},KRI_Data!$F:$F,"Amber")').border = BORDER
    n_kri = len(f["kri"]) + 1
    rngm = f"{get_column_letter(first_m)}2:{get_column_letter(last_m)}{n_kri}"
    fc = get_column_letter(first_m)
    kdash.conditional_formatting.add(rngm, FormulaRule(formula=[f"{fc}2>$D2"], fill=PatternFill("solid", fgColor=FILL["Red"]), stopIfTrue=True))
    kdash.conditional_formatting.add(rngm, FormulaRule(formula=[f"{fc}2>$C2"], fill=PatternFill("solid", fgColor=FILL["Amber"]), stopIfTrue=True))
    kdash.conditional_formatting.add(rngm, FormulaRule(formula=[f"{fc}2<=$C2"], fill=PatternFill("solid", fgColor=FILL["Green"])))
    rag_format(kdash, f"{get_column_letter(last_m + 1)}2:{get_column_letter(last_m + 1)}{n_kri}", ["Green", "Amber", "Red"])
    kdash.column_dimensions["A"].width, kdash.column_dimensions["B"].width = 8, 52
    for j in range(3, last_m + 4):
        kdash.column_dimensions[get_column_letter(j)].width = 9
    kdash.freeze_panes = "C2"

    # Issues
    rows = []
    for i, s in enumerate(f["issue"].itertuples(), 2):
        d = lambda x: date.fromisoformat(x) if x else None
        rows.append([s.issue_id, s.title, s.source, s.risk_id, s.control_id, s.kri_id, s.severity, s.owner,
                     d(s.raised_date), d(s.due_date), d(s.closed_date), s.status,
                     f'=IF(L{i}="Closed",K{i}-I{i},Parameters!$B$2-I{i})',
                     f'=IF(L{i}="Closed","Closed",IF(J{i}<Parameters!$B$2,"Overdue","On track"))',
                     f'=IF(L{i}="Closed","Closed",IF(M{i}<=30,"0-30 days",IF(M{i}<=60,"31-60 days",IF(M{i}<=90,"61-90 days","90+ days"))))'])
    iss = sheet("Issues", ["Issue ID", "Issue", "Source", "Risk", "Control", "KRI", "Severity", "Owner", "Raised", "Due", "Closed",
                           "Status", "Age (days)", "Due status", "Ageing bucket"], rows,
                [9, 60, 20, 7, 8, 7, 9, 22, 12, 12, 12, 9, 9, 11, 13])
    n_i = len(rows) + 1
    for col in "IJK":
        for i in range(2, n_i + 1):
            iss[f"{col}{i}"].number_format = "dd-mmm-yyyy"
    iss.conditional_formatting.add(f"N2:N{n_i}", CellIsRule(operator="equal", formula=['"Overdue"'], fill=PatternFill("solid", fgColor="FFC7CE")))

    # Summary KPIs (all formulas)
    ws["A1"] = f"RCSA / PRSA and KRI summary - {K.PROCESS}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "=\"As of \"&TEXT(Parameters!B2,\"dd-mmm-yyyy\")"
    last = get_column_letter(last_m + 1)
    kpis = [
        ("Risks assessed", "=COUNTA(Risk_Register!A2:A1000)"),
        ("Controls mapped", "=COUNTA(Control_Library!A2:A1000)"),
        ("Risk-control links", "=COUNTA(Risk_Control_Map!A2:A1000)"),
        ("Inherent High/Critical risks", '=COUNTIF(Risk_Register!J:J,"High")+COUNTIF(Risk_Register!J:J,"Critical")'),
        ("Residual High/Critical risks", '=COUNTIF(Risk_Register!Q:Q,"High")+COUNTIF(Risk_Register!Q:Q,"Critical")'),
        ("Risks outside appetite", '=COUNTIF(Risk_Register!R:R,"Outside appetite")'),
        ("Average inherent score", "=ROUND(AVERAGE(Risk_Register!I2:I1000),1)"),
        ("Average residual score", "=ROUND(AVERAGE(Risk_Register!P2:P1000),1)"),
        ("Controls not fully effective", "=COUNTIF(Control_Library!K2:K1000,\"<3\")"),
        ("KRIs Red in latest month", f'=COUNTIF(KRI_Dashboard!{last}2:{last}100,"Red")'),
        ("KRIs Amber in latest month", f'=COUNTIF(KRI_Dashboard!{last}2:{last}100,"Amber")'),
        ("KRI breaches (Red months, 12m)", '=COUNTIF(KRI_Data!F:F,"Red")'),
        ("Open issues", '=COUNTIF(Issues!L:L,"Open")'),
        ("Overdue issues", '=COUNTIF(Issues!N:N,"Overdue")'),
        ("Open issues aged 90+ days", '=COUNTIF(Issues!O:O,"90+ days")'),
    ]
    for i, (lab, fml) in enumerate(kpis, 4):
        ws.cell(row=i, column=1, value=lab).border = BORDER
        c = ws.cell(row=i, column=2, value=fml)
        c.border, c.font = BORDER, Font(bold=True)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 12
    ws.cell(row=21, column=1, value="Scoring: inherent = impact x likelihood. Control score = min(design, operating) on a 1-3 scale. "
                                    "Controls reduce likelihood by (avg control score - 1) / 2 x max reduction. "
                                    "Residual = impact x residual likelihood.").font = Font(italic=True)
    wb.save(path)


# ----------------------------------------------------------------------------- preview charts
STATUS = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#ec835a", "Critical": "#d03b3b",
          "Green": "#0ca30c", "Amber": "#fab219", "Red": "#d03b3b"}
INK, INK2, SURFACE, GRID, BLUE = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df", "#2a78d6"


def build_previews(con: sqlite3.Connection, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID, "figure.facecolor": SURFACE,
                         "axes.facecolor": SURFACE})
    risk = pd.read_sql("SELECT * FROM v_risk_scores", con)
    kri = pd.read_sql("SELECT * FROM v_kri_rag", con)
    iss = pd.read_sql("SELECT * FROM v_issue_ageing", con)

    def heat(ax, lcol, title):
        for imp in range(1, 6):
            for l in range(1, 6):
                n = int(((risk.impact == imp) & (risk[lcol] == l)).sum())
                ax.add_patch(Rectangle((l - 0.5 + 0.02, imp - 0.5 + 0.02), 0.96, 0.96, color=STATUS[band(imp * l)],
                                       alpha=1.0 if n else 0.28, lw=0))
                if n:
                    ax.text(l, imp, str(n), ha="center", va="center", fontsize=12, fontweight="bold", color=INK)
        ax.set_xlim(0.5, 5.5); ax.set_ylim(0.5, 5.5); ax.set_aspect("equal")
        ax.set_xticks(range(1, 6)); ax.set_yticks(range(1, 6))
        ax.set_xlabel("Likelihood"); ax.set_ylabel("Impact"); ax.set_title(title, loc="left", fontweight="bold")
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)

    fig = plt.figure(figsize=(15, 10.5))
    gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 1.25], height_ratios=[1, 1.05], hspace=0.35, wspace=0.3)
    fig.suptitle(f"RCSA / PRSA and KRI dashboard - {K.PROCESS} (as of {K.AS_OF_DATE})", x=0.02, ha="left", fontsize=14, fontweight="bold")
    heat(fig.add_subplot(gs[0, 0]), "likelihood", "Inherent risk heat map")
    heat(fig.add_subplot(gs[0, 1]), "residual_likelihood", "Residual risk heat map")
    fig.legend(handles=[Patch(color=STATUS[b], label=f"{b} ({lo}-{hi})") for b, lo, hi, _ in BANDS],
               loc="upper left", bbox_to_anchor=(0.02, 0.535), ncol=4, frameon=False, title="Rating band (impact x likelihood); number = count of risks",
               title_fontsize=8, fontsize=8)

    # KPI tiles
    ax = fig.add_subplot(gs[0, 2]); ax.axis("off")
    latest = kri[kri.month == K.MONTHS[-1]]
    tiles = [("Risks / controls", f"{len(risk)} / 25"),
             ("High+Critical: residual / inherent", f"{risk.residual_rating.isin(['High', 'Critical']).sum()} / {risk.inherent_rating.isin(['High', 'Critical']).sum()}"),
             ("Outside appetite", str((risk.appetite_status == 'Outside appetite').sum())),
             ("KRIs Red, latest month", f"{(latest.rag == 'Red').sum()} of {len(latest)}"),
             ("KRI breaches, 12 months", str(int(kri.is_breach.sum()))),
             ("Open / overdue issues", f"{(iss.status == 'Open').sum()} / {(iss.due_status == 'Overdue').sum()}")]
    for i, (lab, val) in enumerate(tiles):
        x, y = (i % 2) * 0.5, 0.9 - (i // 2) * 0.33
        ax.text(x, y, lab, fontsize=9, color=INK2, transform=ax.transAxes)
        ax.text(x, y - 0.13, val, fontsize=17, fontweight="bold", color=INK, transform=ax.transAxes)
    ax.set_title("Headline indicators", loc="left", fontweight="bold")

    # KRI RAG matrix
    ax = fig.add_subplot(gs[1, 0:2])
    kids = sorted(kri.kri_id.unique())
    for i, kid in enumerate(kids):
        for j, m in enumerate(K.MONTHS):
            r = kri[(kri.kri_id == kid) & (kri.month == m)].iloc[0]
            ax.add_patch(Rectangle((j + 0.03, i + 0.06), 0.94, 0.88, color=STATUS[r.rag], lw=0))
            ax.text(j + 0.5, i + 0.5, r.rag[0], ha="center", va="center", fontsize=8, fontweight="bold",
                    color="white" if r.rag in ("Green", "Red") else INK)
    names = kri.drop_duplicates("kri_id").set_index("kri_id").name
    ax.set_yticks([i + 0.5 for i in range(len(kids))])
    ax.set_yticklabels([f"{k}  {names[k][:46]}" for k in kids], fontsize=8)
    ax.set_xticks([j + 0.5 for j in range(len(K.MONTHS))])
    ax.set_xticklabels([pd.Timestamp(m).strftime("%b %y") for m in K.MONTHS], fontsize=8)
    ax.set_xlim(0, len(K.MONTHS)); ax.set_ylim(len(kids), 0)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("KRI status by month (G = Green, A = Amber, R = Red breach)", loc="left", fontweight="bold")

    # Issue ageing
    ax = fig.add_subplot(gs[1, 2])
    order = ["0-30 days", "31-60 days", "61-90 days", "90+ days"]
    counts = iss[iss.status == "Open"].ageing_bucket.value_counts().reindex(order, fill_value=0)
    bars = ax.bar(order, counts.values, color=BLUE, width=0.6)
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.1, str(v), ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_title("Open issues by age", loc="left", fontweight="bold")
    ax.set_ylabel("Open issues")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
    ax.set_ylim(0, counts.max() + 1.5)

    fig.savefig(out / "dashboard_preview.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- main
def main() -> None:
    for d in (DATA, DATA / "powerbi", EXCEL, DOCS):
        d.mkdir(parents=True, exist_ok=True)
    f = catalogue_frames()
    f["kri_value"] = kri_values()
    f["issue"] = issues(f["control"], f["risk_control"], f["kri_value"], f["kri"])
    for name, df in f.items():
        df.to_csv(DATA / f"{name}.csv", index=False)

    con = build_db(f, DATA / "rcsa.db")
    views = {v: pd.read_sql(f"SELECT * FROM {v}", con) for v in ("v_risk_scores", "v_control_scores", "v_kri_rag", "v_issue_ageing")}
    for v, df in views.items():
        df.to_csv(DATA / "powerbi" / f"{v[2:]}.csv", index=False)
    f["risk_control"].to_csv(DATA / "powerbi" / "risk_control.csv", index=False)

    # Cross-check SQL scoring against the independent Python implementation
    py = python_scores(f).set_index("risk_id")
    sq = views["v_risk_scores"].set_index("risk_id")[py.columns]
    assert py.equals(sq.astype(py.dtypes.to_dict())), "SQL and Python residual scoring disagree"

    build_excel(f, EXCEL / "RCSA_KRI_Workbook.xlsx")
    build_previews(con, DOCS)

    r = views["v_risk_scores"]
    print(f"Risks: {len(r)} | Controls: {len(f['control'])} | Links: {len(f['risk_control'])} | KRIs: {len(f['kri'])} x {len(K.MONTHS)} months | Issues: {len(f['issue'])}")
    print(r[["risk_id", "impact", "likelihood", "inherent_score", "inherent_rating", "avg_control_score",
             "residual_likelihood", "residual_score", "residual_rating", "appetite_status"]].to_string(index=False))
    k = views["v_kri_rag"]
    print("\nKRI RAG counts:", k.rag.value_counts().to_dict(), "| latest month:", k[k.month == K.MONTHS[-1]].rag.value_counts().to_dict())
    i = views["v_issue_ageing"]
    print("Issues:", i.status.value_counts().to_dict(), "| overdue:", (i.due_status == "Overdue").sum(),
          "| ageing:", i[i.status == "Open"].ageing_bucket.value_counts().to_dict())
    print("SQL scoring matches Python reference: OK")


if __name__ == "__main__":
    main()
