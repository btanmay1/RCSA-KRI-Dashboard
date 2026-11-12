"""RCSA/PRSA catalogue for the card onboarding (KYC) process: 18 risks, 25 controls, mapping, 12 KRIs.

Ratings reflect an illustrative self-assessment; they are inputs to the scoring model, not real bank data.
"""

PROCESS = "Card Onboarding (KYC)"
SUB_PROCESSES = ["Application & sourcing", "Identity & document verification", "Screening",
                 "Customer due diligence", "Credit decision & limit", "Account set-up & data", "Record keeping"]

# risk_id, title, description, category, sub_process, owner, impact (1-5), likelihood (1-5)
RISKS = [
    ("R01", "Customer identity not verified", "Account opened for an impersonated or synthetic identity because identity was not verified against a reliable source.", "Fraud", "Identity & document verification", "Head of Onboarding Ops", 5, 4),
    ("R02", "Incomplete KYC documentation", "Card issued with missing officially valid documents (OVD) or proof of address.", "Regulatory compliance", "Identity & document verification", "Head of Onboarding Ops", 4, 4),
    ("R03", "Forged or tampered documents accepted", "Altered or counterfeit documents are not detected at verification.", "Fraud", "Identity & document verification", "Fraud Risk Manager", 5, 3),
    ("R04", "PEP not identified at onboarding", "Politically exposed person onboarded without being identified and escalated.", "Financial crime (AML)", "Screening", "MLRO", 4, 3),
    ("R05", "Sanctions screening miss", "Sanctioned individual onboarded because the screening hit was missed or wrongly discounted.", "Financial crime (Sanctions)", "Screening", "MLRO", 5, 2),
    ("R06", "Adverse media not screened", "Negative news on the applicant is not considered in the onboarding decision.", "Financial crime (AML)", "Screening", "MLRO", 3, 3),
    ("R07", "Incorrect customer risk rating", "Customer assigned a low AML risk rating that does not reflect occupation, geography or product.", "Financial crime (AML)", "Customer due diligence", "KYC Policy Lead", 4, 3),
    ("R08", "EDD not performed for high-risk customers", "High-risk customers onboarded without enhanced due diligence and senior sign-off.", "Financial crime (AML)", "Customer due diligence", "KYC Policy Lead", 5, 3),
    ("R09", "Address not verified", "Communication address is not verified, leading to card interception or misdelivery.", "Fraud", "Identity & document verification", "Head of Onboarding Ops", 3, 3),
    ("R10", "Duplicate customer profiles created", "Same customer onboarded under more than one profile, breaking single-customer view and exposure limits.", "Data management", "Account set-up & data", "Data Governance Lead", 3, 4),
    ("R11", "Customer data captured incorrectly", "Manual keying errors in name, DOB, PAN or income flow into credit and AML systems.", "Data management", "Account set-up & data", "Data Governance Lead", 3, 4),
    ("R12", "Customer data privacy breach", "KYC images or personal data accessed or exfiltrated without authorisation during onboarding.", "Information security & privacy", "Record keeping", "Chief Privacy Officer", 5, 2),
    ("R13", "Customer consent not captured", "Bureau pull or data processing carried out without recorded customer consent.", "Regulatory compliance", "Application & sourcing", "Compliance Manager", 4, 3),
    ("R14", "Limit assigned without income verification", "Credit limit set before bureau check and income verification are complete.", "Credit", "Credit decision & limit", "Credit Policy Manager", 4, 3),
    ("R15", "Unauthorised override of KYC rejection", "A rejected application is overridden without the required authority.", "Internal fraud / conduct", "Credit decision & limit", "Head of Onboarding Ops", 4, 2),
    ("R16", "Onboarding SLA breach and backlog", "Volumes exceed capacity, causing SLA breaches and pressure to shortcut checks.", "Operational / process", "Account set-up & data", "Head of Onboarding Ops", 3, 4),
    ("R17", "Third-party sourcing agent misconduct", "Direct selling agents (DSA) submit manipulated applications or mis-sell the product.", "Third party", "Application & sourcing", "Vendor Risk Manager", 4, 4),
    ("R18", "Video KYC record not retained", "V-CIP session recordings or audit trails are not stored as regulations require.", "Regulatory compliance", "Record keeping", "Compliance Manager", 4, 2),
]

# control_id, name, type, nature, frequency, owner, design rating, operating rating (Effective / Partially Effective / Ineffective)
CONTROLS = [
    ("C01", "OVD checklist verification by maker", "Preventive", "Manual", "Per application", "Onboarding Ops", "Effective", "Partially Effective"),
    ("C02", "OCR and image-tamper detection on uploads", "Preventive", "Automated", "Per application", "Fraud Analytics", "Effective", "Effective"),
    ("C03", "Aadhaar e-KYC / DigiLocker validation", "Preventive", "Automated", "Per application", "Onboarding Ops", "Effective", "Effective"),
    ("C04", "Video KYC (V-CIP) with liveness check", "Preventive", "IT-dependent manual", "Per application", "Onboarding Ops", "Effective", "Partially Effective"),
    ("C05", "Real-time sanctions screening (UN/OFAC/MHA lists)", "Preventive", "Automated", "Per application", "Financial Crime Ops", "Effective", "Effective"),
    ("C06", "PEP screening at onboarding", "Preventive", "Automated", "Per application", "Financial Crime Ops", "Effective", "Partially Effective"),
    ("C07", "Adverse media screening", "Detective", "Automated", "Per application", "Financial Crime Ops", "Partially Effective", "Partially Effective"),
    ("C08", "Customer risk rating model auto-assignment", "Preventive", "Automated", "Per application", "KYC Policy", "Effective", "Effective"),
    ("C09", "EDD checklist with senior management sign-off", "Preventive", "Manual", "Per high-risk application", "KYC Policy", "Effective", "Partially Effective"),
    ("C10", "Address verification (utility bill / field visit)", "Preventive", "Manual", "Per application", "Onboarding Ops", "Partially Effective", "Partially Effective"),
    ("C11", "De-duplication on PAN, mobile and email", "Preventive", "Automated", "Per application", "Data Governance", "Effective", "Partially Effective"),
    ("C12", "Maker-checker on data entry", "Preventive", "Manual", "Per application", "Onboarding Ops", "Effective", "Effective"),
    ("C13", "Daily QC sampling of onboarded files", "Detective", "Manual", "Daily", "Onboarding QA", "Effective", "Partially Effective"),
    ("C14", "Role-based access and masking on KYC repository", "Preventive", "Automated", "Continuous", "Information Security", "Effective", "Effective"),
    ("C15", "DLP monitoring on KYC data", "Detective", "Automated", "Continuous", "Information Security", "Partially Effective", "Ineffective"),
    ("C16", "Mandatory time-stamped e-consent capture", "Preventive", "Automated", "Per application", "Digital Channels", "Effective", "Partially Effective"),
    ("C17", "Bureau pull and income verification before limit", "Preventive", "Automated", "Per application", "Credit Policy", "Effective", "Effective"),
    ("C18", "Override authority matrix with dual sign-off", "Preventive", "Manual", "Per override", "Credit Policy", "Effective", "Effective"),
    ("C19", "Monthly override review by Compliance", "Detective", "Manual", "Monthly", "Compliance", "Effective", "Partially Effective"),
    ("C20", "Onboarding SLA dashboard and queue monitoring", "Detective", "IT-dependent manual", "Daily", "Onboarding Ops", "Partially Effective", "Partially Effective"),
    ("C21", "DSA due diligence and certification", "Preventive", "Manual", "Annual", "Vendor Management", "Effective", "Partially Effective"),
    ("C22", "DSA sourcing quality review (mystery shopping)", "Detective", "Manual", "Quarterly", "Vendor Management", "Partially Effective", "Ineffective"),
    ("C23", "V-CIP recording retention and audit trail", "Preventive", "Automated", "Per application", "IT Operations", "Effective", "Partially Effective"),
    ("C24", "Sanctions alert clearance within 24h (4-eyes)", "Detective", "Manual", "Daily", "Financial Crime Ops", "Effective", "Partially Effective"),
    ("C25", "Early-life fraud monitoring (first 90 days)", "Detective", "Automated", "Daily", "Fraud Analytics", "Effective", "Effective"),
]

RISK_CONTROL_MAP = [
    ("R01", "C03"), ("R01", "C04"), ("R01", "C25"),
    ("R02", "C01"), ("R02", "C13"),
    ("R03", "C02"), ("R03", "C01"),
    ("R04", "C06"),
    ("R05", "C05"), ("R05", "C24"),
    ("R06", "C07"),
    ("R07", "C08"), ("R07", "C13"),
    ("R08", "C09"),
    ("R09", "C10"),
    ("R10", "C11"),
    ("R11", "C12"), ("R11", "C13"),
    ("R12", "C14"), ("R12", "C15"),
    ("R13", "C16"),
    ("R14", "C17"),
    ("R15", "C18"), ("R15", "C19"),
    ("R16", "C20"),
    ("R17", "C21"), ("R17", "C22"), ("R17", "C25"),
    ("R18", "C23"), ("R18", "C04"),
]

# kri_id, name, unit, linked risks, green max, amber max, baseline, monthly drift, noise, owner
# Lower is better for every KRI; RAG: value <= green max -> Green, <= amber max -> Amber, else Red.
KRIS = [
    ("K01", "Applications with incomplete KYC documents at first submission", "%", "R02", 3.0, 5.0, 2.2, 0.05, 0.3, "Head of Onboarding Ops"),
    ("K02", "Documents flagged for tampering", "%", "R03", 0.5, 1.0, 0.3, 0.01, 0.07, "Fraud Risk Manager"),
    ("K03", "Sanctions alerts not cleared within 24 hours", "count", "R05", 2, 5, 1.0, 0.05, 0.6, "MLRO"),
    ("K04", "PEP matches pending EDD for more than 7 days", "count", "R04;R08", 0, 2, 0.2, 0.03, 0.5, "MLRO"),
    ("K05", "High-risk customers onboarded without EDD sign-off", "%", "R08", 0.5, 1.0, 0.2, 0.02, 0.15, "KYC Policy Lead"),
    ("K06", "Duplicate profiles detected after onboarding", "count", "R10", 5, 10, 3.0, 0.15, 1.2, "Data Governance Lead"),
    ("K07", "Data entry error rate in QC sample", "%", "R11;R07", 2.0, 4.0, 1.4, 0.04, 0.25, "Data Governance Lead"),
    ("K08", "KYC overrides per 1,000 approvals", "ratio", "R15", 1.0, 2.0, 0.6, 0.02, 0.15, "Head of Onboarding Ops"),
    ("K09", "Applications breaching 48-hour onboarding SLA", "%", "R16", 5.0, 10.0, 3.8, 0.2, 0.8, "Head of Onboarding Ops"),
    ("K10", "Early-life fraud cases per 10,000 new cards", "ratio", "R01;R17", 3.0, 6.0, 2.0, 0.1, 0.5, "Fraud Risk Manager"),
    ("K11", "V-CIP sessions failing QA or missing recording", "%", "R18;R01", 1.0, 3.0, 0.5, 0.02, 0.25, "Compliance Manager"),
    ("K12", "Applications processed without consent record", "count", "R13", 0, 3, 0.1, 0.0, 0.5, "Compliance Manager"),
]

MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
          "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
AS_OF_DATE = "2026-10-31"

RATING_SCORE = {"Effective": 3, "Partially Effective": 2, "Ineffective": 1}
MAX_REDUCTION = 0.70          # fully effective controls reduce likelihood by 70%
RISK_APPETITE_RESIDUAL = 8    # residual score above this is outside appetite
