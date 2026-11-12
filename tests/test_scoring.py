import sqlite3

import pandas as pd

from rcsa import build as B
from rcsa import catalogue as K


def frames():
    f = B.catalogue_frames()
    f["kri_value"] = B.kri_values()
    f["issue"] = B.issues(f["control"], f["risk_control"], f["kri_value"], f["kri"])
    return f


def test_catalogue_shape():
    f = frames()
    assert len(f["risk"]) == 18 and len(f["control"]) == 25
    assert set(f["risk_control"].control_id) == set(f["control"].control_id), "every control is mapped"
    assert set(f["risk_control"].risk_id) == set(f["risk"].risk_id), "every risk has a control"
    assert len(f["kri_value"]) == len(K.KRIS) * 12


def test_sql_matches_python(tmp_path):
    f = frames()
    con = B.build_db(f, tmp_path / "t.db")
    sql = pd.read_sql("SELECT risk_id, inherent_score, residual_likelihood, residual_score FROM v_risk_scores", con).set_index("risk_id")
    py = B.python_scores(f).set_index("risk_id")
    assert (sql.sort_index().values == py.sort_index().values).all()


def test_residual_never_exceeds_inherent(tmp_path):
    con = B.build_db(frames(), tmp_path / "t.db")
    r = pd.read_sql("SELECT * FROM v_risk_scores", con)
    assert (r.residual_score <= r.inherent_score).all()
    assert (r.residual_likelihood >= 1).all()


def test_fully_effective_controls_give_max_reduction(tmp_path):
    f = frames()
    f["control"]["design_rating"] = "Effective"
    f["control"]["operating_rating"] = "Effective"
    con = B.build_db(f, tmp_path / "t.db")
    r = pd.read_sql("SELECT likelihood, likelihood_reduction, residual_likelihood FROM v_risk_scores", con)
    assert (r.likelihood_reduction == K.MAX_REDUCTION).all()


def test_kri_rag_boundaries(tmp_path):
    con = B.build_db(frames(), tmp_path / "t.db")
    k = pd.read_sql("SELECT * FROM v_kri_rag", con)
    assert (k[k.rag == "Green"].value <= k[k.rag == "Green"].green_max).all()
    assert (k[k.rag == "Red"].value > k[k.rag == "Red"].amber_max).all()
    amber = k[k.rag == "Amber"]
    assert ((amber.value > amber.green_max) & (amber.value <= amber.amber_max)).all()


def test_issue_ageing(tmp_path):
    con = B.build_db(frames(), tmp_path / "t.db")
    i = pd.read_sql("SELECT * FROM v_issue_ageing", con)
    assert (i.age_days >= 0).all()
    assert set(i[i.status == "Closed"].ageing_bucket) <= {"Closed"}
    overdue = i[i.due_status == "Overdue"]
    assert (overdue.due_date < K.AS_OF_DATE).all() and (overdue.status == "Open").all()


def test_web_dashboard_embeds_sql_results(tmp_path):
    import json
    f = frames()
    con = B.build_db(f, tmp_path / "t.db")
    html = B.build_web(con, tmp_path / "docs").read_text(encoding="utf-8")
    assert "/*DATA*/" not in html
    blob = html.split("const D = ", 1)[1].split(";\n", 1)[0]
    data = json.loads(blob.replace("<\/", "</"))
    assert len(data["risks"]) == 18 and len(data["controls"]) == 25
    assert len(data["kri_values"]) == len(K.KRIS) * len(K.MONTHS)
    sql = pd.read_sql("SELECT risk_id, residual_score FROM v_risk_scores", con).set_index("risk_id").residual_score.to_dict()
    assert {r["risk_id"]: r["residual_score"] for r in data["risks"]} == sql
