#!/usr/bin/env python3
"""
Discrepancy-Detector training/eval dataset generator.

Emits records in Abridge's *exact* `synthetic-ambient-fhir` 8-field schema, but
with a KNOWN, LABELED clinical discrepancy planted in each encounter (or a clean
control). Ground-truth labels are written to a SEPARATE sidecar file keyed by
`id` so the detector operates on precisely the same input shape as Abridge's
real data and can never "cheat" by reading the answer key.

Two detectors share this one corpus:
  1. Record-vs-Conversation Discrepancy Detector  -> `labels[*].discrepancies`
  2. Drug Adverse-Effect Alert                     -> `labels[*].adverse_events`

Everything is synthetic. No PHI. Deterministic under a fixed seed.
"""
import json, random, hashlib, os, datetime as dt

SEED = 20260718
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATE = dt.date(2026, 7, 1)          # "today" for relative dating (fixed => reproducible)
N_RECORDS = 100

# ---------------------------------------------------------------------------
# Deterministic id helper (synthea-style uuids, but seeded)
# ---------------------------------------------------------------------------
def uid(rng):
    h = ''.join(rng.choice('0123456789abcdef') for _ in range(32))
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def urn(u): return f"urn:uuid:{u}"

# ---------------------------------------------------------------------------
# Coding systems
# ---------------------------------------------------------------------------
SNOMED = "http://snomed.info/sct"
LOINC  = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

# ---------------------------------------------------------------------------
# Drug knowledge base.  (Synthetic dev data — codes are plausible, not audited.)
#   renal:      dict describing renal-dosing caveat (or None)
#   teratogen:  known teratogen / contraindicated in pregnancy
#   adr:        patient-language symptoms of a known adverse drug reaction
#   interacts:  {other_drug_or_class: harm}   dangerous drug-drug interactions
#   allergy_class: class used to match AllergyIntolerance cross-reactivity
# ---------------------------------------------------------------------------
DRUGS = {
  "atorvastatin":      {"rxnorm":"617312","cls":"statin","dose":"40 mg nightly","renal":None,"teratogen":True,
                        "adr":["muscle aches","muscle pain and weakness","aching in my legs"],
                        "interacts":{"clarithromycin":"rhabdomyolysis / myopathy","gemfibrozil":"myopathy"},"allergy_class":"statin"},
  "simvastatin":       {"rxnorm":"312961","cls":"statin","dose":"20 mg nightly","renal":None,"teratogen":True,
                        "adr":["muscle aches","leg cramps"],"interacts":{"clarithromycin":"rhabdomyolysis"},"allergy_class":"statin"},
  "metformin":         {"rxnorm":"860975","cls":"biguanide","dose":"1000 mg twice daily","teratogen":False,
                        "renal":{"threshold":30,"caution_below":45,"rule":"contraindicated when eGFR < 30; do not start 30-45"},
                        "adr":["nausea and diarrhea","upset stomach"],"interacts":{},"allergy_class":None},
  "lisinopril":        {"rxnorm":"197884","cls":"ACE inhibitor","dose":"20 mg daily","teratogen":True,"renal":{"hyperkalemia":True},
                        "adr":["dry hacking cough","tickle in my throat and a dry cough"],
                        "interacts":{"potassium chloride":"hyperkalemia","spironolactone":"hyperkalemia","losartan":"dual RAAS blockade","valsartan":"dual RAAS blockade"},
                        "allergy_class":"ace_inhibitor"},
  "enalapril":         {"rxnorm":"310809","cls":"ACE inhibitor","dose":"10 mg twice daily","teratogen":True,"renal":{"hyperkalemia":True},
                        "adr":["dry cough"],"interacts":{},"allergy_class":"ace_inhibitor"},
  "losartan":          {"rxnorm":"979485","cls":"ARB","dose":"50 mg daily","teratogen":True,"renal":{"hyperkalemia":True},
                        "adr":["dizziness"],"interacts":{"lisinopril":"dual RAAS blockade"},"allergy_class":None},
  "amlodipine":        {"rxnorm":"197361","cls":"calcium channel blocker","dose":"10 mg daily","renal":None,"teratogen":False,
                        "adr":["ankle swelling","swollen feet"],"interacts":{},"allergy_class":None},
  "hydrochlorothiazide":{"rxnorm":"310798","cls":"thiazide diuretic","dose":"25 mg daily","renal":None,"teratogen":False,
                        "adr":["dizziness"],"interacts":{},"allergy_class":"sulfa"},
  "metoprolol":        {"rxnorm":"866514","cls":"beta blocker","dose":"50 mg twice daily","renal":None,"teratogen":False,
                        "adr":["fatigue","feeling really tired and slow"],"interacts":{},"allergy_class":None},
  "warfarin":          {"rxnorm":"855332","cls":"anticoagulant","dose":"5 mg daily","renal":None,"teratogen":True,
                        "adr":["bruising easily","blood in my urine","bleeding gums"],
                        "interacts":{"ibuprofen":"major bleeding","naproxen":"major bleeding","aspirin":"major bleeding",
                                     "amoxicillin":"raised INR / bleeding","sulfamethoxazole-trimethoprim":"raised INR / bleeding","fluconazole":"raised INR"},
                        "allergy_class":None},
  "apixaban":          {"rxnorm":"1364430","cls":"anticoagulant (DOAC)","dose":"5 mg twice daily","teratogen":True,
                        "renal":{"threshold":25,"rule":"reduce / avoid at very low eGFR"},
                        "adr":["bruising","bleeding"],"interacts":{"ibuprofen":"bleeding","naproxen":"bleeding"},"allergy_class":None},
  "aspirin":           {"rxnorm":"243670","cls":"antiplatelet/NSAID","dose":"81 mg daily","renal":None,"teratogen":False,
                        "adr":["stomach upset"],"interacts":{"warfarin":"major bleeding"},"allergy_class":"nsaid"},
  "ibuprofen":         {"rxnorm":"5640","cls":"NSAID","dose":"600 mg three times daily","teratogen":True,
                        "renal":{"threshold":30,"rule":"avoid in advanced CKD"},
                        "adr":["stomach pain"],"interacts":{"warfarin":"major bleeding","lisinopril":"kidney injury / reduced BP control"},"allergy_class":"nsaid"},
  "naproxen":          {"rxnorm":"849574","cls":"NSAID","dose":"500 mg twice daily","teratogen":True,
                        "renal":{"threshold":30,"rule":"avoid in advanced CKD"},
                        "adr":["stomach pain"],"interacts":{"warfarin":"major bleeding"},"allergy_class":"nsaid"},
  "sertraline":        {"rxnorm":"312940","cls":"SSRI","dose":"100 mg daily","renal":None,"teratogen":False,
                        "adr":["trouble sleeping","low sex drive","nausea"],
                        "interacts":{"tramadol":"serotonin syndrome","sumatriptan":"serotonin syndrome","linezolid":"serotonin syndrome"},"allergy_class":None},
  "tramadol":          {"rxnorm":"836397","cls":"opioid analgesic","dose":"50 mg every 6 hours","renal":None,"teratogen":False,
                        "adr":["constipation","dizziness"],"interacts":{"sertraline":"serotonin syndrome"},"allergy_class":"opioid"},
  "sumatriptan":       {"rxnorm":"313782","cls":"triptan","dose":"50 mg as needed","renal":None,"teratogen":False,
                        "adr":["chest tightness"],"interacts":{"sertraline":"serotonin syndrome"},"allergy_class":None},
  "amoxicillin":       {"rxnorm":"723","cls":"aminopenicillin","dose":"500 mg three times daily","renal":None,"teratogen":False,
                        "adr":["rash","diarrhea"],"interacts":{"warfarin":"raised INR"},"allergy_class":"penicillin"},
  "cephalexin":        {"rxnorm":"309097","cls":"cephalosporin","dose":"500 mg four times daily","renal":None,"teratogen":False,
                        "adr":["diarrhea"],"interacts":{},"allergy_class":"cephalosporin"},
  "sulfamethoxazole-trimethoprim":{"rxnorm":"linkid_smx","cls":"sulfonamide antibiotic","dose":"800/160 mg twice daily","teratogen":True,
                        "renal":{"hyperkalemia":True},"adr":["rash"],
                        "interacts":{"warfarin":"raised INR / bleeding","lisinopril":"hyperkalemia"},"allergy_class":"sulfa"},
  "nitrofurantoin":    {"rxnorm":"311989","cls":"urinary antibiotic","dose":"100 mg twice daily","teratogen":False,
                        "renal":{"threshold":30,"rule":"ineffective/toxic when eGFR < 30"},
                        "adr":["nausea"],"interacts":{},"allergy_class":None},
  "nitroglycerin":     {"rxnorm":"564666","cls":"nitrate","dose":"0.4 mg sublingual as needed","renal":None,"teratogen":False,
                        "adr":["headache"],"interacts":{"sildenafil":"life-threatening hypotension"},"allergy_class":None},
  "isosorbide mononitrate":{"rxnorm":"884173","cls":"nitrate","dose":"30 mg daily","renal":None,"teratogen":False,
                        "adr":["headache"],"interacts":{"sildenafil":"life-threatening hypotension"},"allergy_class":None},
  "sildenafil":        {"rxnorm":"312349","cls":"PDE5 inhibitor","dose":"50 mg as needed","renal":None,"teratogen":False,
                        "adr":["flushing"],"interacts":{"nitroglycerin":"life-threatening hypotension","isosorbide mononitrate":"life-threatening hypotension"},"allergy_class":None},
  "levothyroxine":     {"rxnorm":"966224","cls":"thyroid hormone","dose":"100 mcg daily","renal":None,"teratogen":False,
                        "adr":["palpitations","heart racing and trouble sleeping"],"interacts":{},"allergy_class":None},
  "prednisone":        {"rxnorm":"312615","cls":"corticosteroid","dose":"20 mg daily","renal":None,"teratogen":False,
                        "adr":["high blood sugars","trouble sleeping and mood swings"],"interacts":{},"allergy_class":None},
  "spironolactone":    {"rxnorm":"313096","cls":"potassium-sparing diuretic","dose":"25 mg daily","teratogen":False,
                        "renal":{"hyperkalemia":True},"adr":["breast tenderness"],
                        "interacts":{"lisinopril":"hyperkalemia","potassium chloride":"hyperkalemia"},"allergy_class":None},
  "insulin glargine":  {"rxnorm":"274783","cls":"basal insulin","dose":"20 units nightly","renal":None,"teratogen":False,
                        "adr":["low blood sugar shakes","hypoglycemia"],"interacts":{},"allergy_class":None},
  "gabapentin":        {"rxnorm":"310430","cls":"anticonvulsant","dose":"300 mg three times daily","teratogen":False,
                        "renal":{"threshold":30,"rule":"reduce dose in low eGFR"},"adr":["drowsiness"],"interacts":{},"allergy_class":None},
  "albuterol":         {"rxnorm":"801095","cls":"SABA inhaler","dose":"2 puffs as needed","renal":None,"teratogen":False,
                        "adr":["jittery, shaky hands"],"interacts":{},"allergy_class":None},
  "fluticasone-salmeterol":{"rxnorm":"896188","cls":"ICS/LABA inhaler","dose":"1 puff twice daily","renal":None,"teratogen":False,
                        "adr":["hoarse voice"],"interacts":{},"allergy_class":None},
  "omeprazole":        {"rxnorm":"402014","cls":"proton pump inhibitor","dose":"20 mg daily","renal":None,"teratogen":False,
                        "adr":[],"interacts":{},"allergy_class":None},
  "furosemide":        {"rxnorm":"310429","cls":"loop diuretic","dose":"40 mg daily","renal":None,"teratogen":False,
                        "adr":["dizziness when I stand"],"interacts":{},"allergy_class":"sulfa"},
  "potassium chloride":{"rxnorm":"312961k","cls":"potassium supplement","dose":"20 mEq daily","teratogen":False,
                        "renal":{"hyperkalemia":True},"adr":[],"interacts":{"lisinopril":"hyperkalemia","spironolactone":"hyperkalemia"},"allergy_class":None},
}

# Allergy label -> set of drug names / allergy_class that cross-react
ALLERGY_CROSS = {
  "Penicillin":        {"classes":{"penicillin"}, "example_drug":"amoxicillin", "snomed":"373270004"},
  "Sulfa drugs":       {"classes":{"sulfa"},       "example_drug":"sulfamethoxazole-trimethoprim","snomed":"3006004"},
  "NSAIDs":            {"classes":{"nsaid"},        "example_drug":"ibuprofen","snomed":"293586001"},
  "ACE inhibitors (angioedema)":{"classes":{"ace_inhibitor"},"example_drug":"lisinopril","snomed":"293963004"},
  "Statins (myalgia)": {"classes":{"statin"},       "example_drug":"atorvastatin","snomed":"293992002"},
  "Codeine/opioids":   {"classes":{"opioid"},       "example_drug":"tramadol","snomed":"294276004"},
}

CONDITIONS = {
  "Type 2 diabetes mellitus":          {"snomed":"44054006"},
  "Essential hypertension":            {"snomed":"59621000"},
  "Chronic kidney disease stage 4":    {"snomed":"431857002"},
  "Chronic kidney disease stage 3":    {"snomed":"433144002"},
  "Hyperlipidemia":                    {"snomed":"55822004"},
  "Atrial fibrillation":               {"snomed":"49436004"},
  "Coronary artery disease":           {"snomed":"53741008"},
  "Major depressive disorder":         {"snomed":"370143000"},
  "Generalized anxiety disorder":      {"snomed":"21897009"},
  "Migraine without aura":             {"snomed":"37796009"},
  "Hypothyroidism":                    {"snomed":"40930008"},
  "Asthma":                            {"snomed":"195967001"},
  "COPD":                              {"snomed":"13645005"},
  "Pregnancy":                         {"snomed":"77386006"},
  "Gastroesophageal reflux disease":   {"snomed":"235595009"},
  "Osteoarthritis":                    {"snomed":"396275006"},
  "Recurrent urinary tract infection": {"snomed":"197927001"},
  "Chronic low back pain":             {"snomed":"278860009"},
}

LOINC_CODES = {
  "egfr":  ("33914-3","Glomerular filtration rate/1.73 sq M.predicted","mL/min/{1.73_m2}"),
  "scr":   ("2160-0","Creatinine [Mass/volume] in Serum or Plasma","mg/dL"),
  "k":     ("2823-3","Potassium [Moles/volume] in Serum or Plasma","mmol/L"),
  "a1c":   ("4548-4","Hemoglobin A1c/Hemoglobin.total in Blood","%"),
  "ldl":   ("18262-3","LDL Cholesterol (direct)","mg/dL"),
  "inr":   ("6301-6","INR in Platelet poor plasma by Coagulation assay","{INR}"),
  "tsh":   ("3016-3","Thyrotropin [Units/volume] in Serum or Plasma","m[IU]/L"),
  "sbp":   ("8480-6","Systolic blood pressure","mm[Hg]"),
  "dbp":   ("8462-4","Diastolic blood pressure","mm[Hg]"),
  "hr":    ("8867-4","Heart rate","/min"),
  "wt":    ("29463-7","Body Weight","kg"),
  "bmi":   ("39156-5","Body mass index (BMI) [Ratio]","kg/m2"),
}

GIVEN_M = ["James","Robert","Miguel","David","William","Charles","Andre","Hassan","Wei","Samuel"]
GIVEN_F = ["Mary","Linda","Patricia","Elena","Susan","Grace","Amara","Priya","Nia","Ruth"]
FAMILY  = ["Alvarez","Bennett","Okafor","Nguyen","Rossi","Coleman","Haddad","Sørensen","Delgado","Whitfield","Park","Mbeki"]

# ---------------------------------------------------------------------------
# FHIR resource builders
# ---------------------------------------------------------------------------
def iso(d, hour=9, minute=0):
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00-07:00"

def mk_patient(pid, gender, given, family, birth):
    prefix = "Mr." if gender == "male" else "Ms."
    return {
      "resourceType":"Patient","id":pid,
      "name":[{"use":"official","family":family,"given":[given],"prefix":[prefix]}],
      "gender":gender,"birthDate":birth.isoformat(),
      "address":[{"city":"Springfield","state":"CA","country":"US"}],
      "communication":[{"language":{"coding":[{"system":"urn:ietf:bcp:47","code":"en-US","display":"English"}]}}],
    }

def mk_condition(cid, pid, enc, label, onset, status="active"):
    return {
      "resourceType":"Condition","id":cid,
      "clinicalStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-clinical","code":status}]},
      "verificationStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-ver-status","code":"confirmed"}]},
      "category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-category","code":"problem-list-item","display":"Problem List Item"}]}],
      "code":{"coding":[{"system":SNOMED,"code":CONDITIONS[label]["snomed"],"display":label}],"text":label},
      "subject":{"reference":urn(pid)},"encounter":{"reference":urn(enc)},
      "onsetDateTime":iso(onset),"recordedDate":iso(onset),
    }

def mk_med(mid, pid, enc, drug, authored, status="active"):
    d = DRUGS[drug]
    return {
      "resourceType":"MedicationRequest","id":mid,
      "status":status,"intent":"order",
      "category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/medicationrequest-category","code":"community","display":"Community"}],"text":"Community"}],
      "medicationCodeableConcept":{"coding":[{"system":RXNORM,"code":d["rxnorm"],"display":drug}],"text":f"{drug} {d['dose']}"},
      "subject":{"reference":urn(pid)},"encounter":{"reference":urn(enc)},
      "authoredOn":iso(authored),
      "dosageInstruction":[{"text":d["dose"]}],
    }

def mk_allergy(aid, pid, label, onset):
    info = ALLERGY_CROSS[label]
    return {
      "resourceType":"AllergyIntolerance","id":aid,
      "clinicalStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical","code":"active"}]},
      "verificationStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/allergyintolerance-verification","code":"confirmed"}]},
      "type":"allergy","category":["medication"],"criticality":"high",
      "code":{"coding":[{"system":SNOMED,"code":info["snomed"],"display":label}],"text":label},
      "patient":{"reference":urn(pid)},"recordedDate":iso(onset),
      "reaction":[{"manifestation":[{"text":"hives and facial swelling"}],"severity":"severe"}],
    }

def mk_obs(oid, pid, enc, key, value, when, category="laboratory"):
    code, disp, unit = LOINC_CODES[key]
    return {
      "resourceType":"Observation","id":oid,"status":"final",
      "category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":category,"display":category.title()}]}],
      "code":{"coding":[{"system":LOINC,"code":code,"display":disp}],"text":disp},
      "subject":{"reference":urn(pid)},"encounter":{"reference":urn(enc)},
      "effectiveDateTime":iso(when),
      "valueQuantity":{"value":value,"unit":unit,"system":"http://unitsofmeasure.org","code":unit},
    }

def mk_encounter(enc, pid, when, visit_type, display_name):
    return {
      "resourceType":"Encounter","id":enc,
      "meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter"]},
      "status":"finished",
      "class":{"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB"},
      "type":[{"coding":[{"system":SNOMED,"code":"162673000","display":visit_type}],"text":visit_type}],
      "subject":{"reference":urn(pid),"display":display_name},
      "period":{"start":iso(when,9,0),"end":iso(when,9,40)},
    }

# ---------------------------------------------------------------------------
# Archetypes: each returns a base clinical chart the injectors customize.
# ---------------------------------------------------------------------------
def archetype_pool():
    return [
      "cardiometabolic_ckd", "afib_anticoag", "mood_migraine", "copd_asthma",
      "cad_secondary_prevention", "advanced_ckd_dm", "pregnancy", "hypothyroid_htn",
      "recurrent_uti_elderly", "chronic_pain_ckd",
    ]

# archetype -> (conditions, home_meds, base_egfr, allergy_or_None, gender_pref)
ARCHETYPE_SPEC = {
  "cardiometabolic_ckd":     (["Type 2 diabetes mellitus","Essential hypertension","Hyperlipidemia","Chronic kidney disease stage 3"],
                              ["metformin","lisinopril","atorvastatin","amlodipine"], 52, None, None),
  "afib_anticoag":           (["Atrial fibrillation","Essential hypertension"],
                              ["warfarin","metoprolol"], 68, None, None),
  "mood_migraine":           (["Major depressive disorder","Migraine without aura","Generalized anxiety disorder"],
                              ["sertraline"], 95, None, None),
  "copd_asthma":             (["COPD","Essential hypertension"],
                              ["fluticasone-salmeterol","albuterol","amlodipine"], 70, "Penicillin", None),
  "cad_secondary_prevention":(["Coronary artery disease","Essential hypertension","Hyperlipidemia"],
                              ["atorvastatin","metoprolol","aspirin","isosorbide mononitrate"], 66, None, "male"),
  "advanced_ckd_dm":         (["Type 2 diabetes mellitus","Chronic kidney disease stage 4","Essential hypertension"],
                              ["insulin glargine","lisinopril","furosemide"], 24, None, None),
  "pregnancy":               (["Pregnancy","Hypothyroidism"],
                              ["levothyroxine"], 105, None, "female"),
  "hypothyroid_htn":         (["Hypothyroidism","Essential hypertension","Hyperlipidemia"],
                              ["levothyroxine","hydrochlorothiazide","atorvastatin"], 78, None, None),
  "recurrent_uti_elderly":   (["Recurrent urinary tract infection","Essential hypertension","Chronic kidney disease stage 4"],
                              ["amlodipine"], 26, "Sulfa drugs", "female"),
  "chronic_pain_ckd":        (["Chronic low back pain","Chronic kidney disease stage 3","Type 2 diabetes mellitus"],
                              ["gabapentin","metformin"], 40, "NSAIDs", None),
}

# ---------------------------------------------------------------------------
# Chart container
# ---------------------------------------------------------------------------
class Chart:
    def __init__(self, rng, archetype, pid, gender, given, family, birth):
        self.rng = rng
        self.archetype = archetype
        self.pid = pid
        self.gender = gender
        self.name_display = f"{('Mr.' if gender=='male' else 'Ms.')} {given} {family}"
        self.given, self.family, self.birth = given, family, birth
        conds, meds, egfr, allergy, _ = ARCHETYPE_SPEC[archetype]
        self.conditions = list(conds)
        self.home_meds = list(meds)        # active outpatient meds (the chart truth)
        self.egfr = egfr
        self.allergy = allergy             # label or None
        self.age = BASE_DATE.year - birth.year

def build_base_chart(rng, archetype, pid):
    gpref = ARCHETYPE_SPEC[archetype][4]
    gender = gpref or rng.choice(["male","female"])
    given = rng.choice(GIVEN_M if gender=="male" else GIVEN_F)
    family = rng.choice(FAMILY)
    if archetype == "pregnancy":
        birth = dt.date(BASE_DATE.year - rng.randint(24,39), rng.randint(1,12), rng.randint(1,28))
    elif archetype in ("advanced_ckd_dm","recurrent_uti_elderly","afib_anticoag","cad_secondary_prevention"):
        birth = dt.date(BASE_DATE.year - rng.randint(62,84), rng.randint(1,12), rng.randint(1,28))
    else:
        birth = dt.date(BASE_DATE.year - rng.randint(38,72), rng.randint(1,12), rng.randint(1,28))
    return Chart(rng, archetype, pid, gender, given, family, birth)

SEVERITY = {"high":"high","moderate":"moderate","low":"low"}

def line(spk, text):
    return f"{spk}: {text}"

# ---------------------------------------------------------------------------
# INJECTORS
# Each takes (chart) -> injected dict, or None if not applicable for this chart.
# The injector may declare chart mutations (ensure_allergy / set_egfr /
# ensure_home_med); the assembler applies them before emitting FHIR so the
# planted discrepancy is always grounded in real resources.
# ---------------------------------------------------------------------------
def _blank():
    return {"type":None,"severity":None,"prescribe":[],"hpi_turns":[],"review_turns":[],
            "plan_turns":[],"note_plan_items":[],"avs_next":[],"discrepancy_label":None,
            "adverse_event_label":None,"drop_med":None,"set_egfr":None,"ensure_allergy":None,
            "ensure_home_med":[],"labs":{}}

def inj_drug_allergy(chart, rng):
    inj = _blank()
    label = chart.allergy or rng.choice(["Penicillin","Sulfa drugs"])
    info = ALLERGY_CROSS[label]; drug = info["example_drug"]
    # avoid nonsense: only if patient isn't already on that exact drug
    if drug in chart.home_meds: return None
    inj["ensure_allergy"] = label
    inj["prescribe"] = [drug]
    reason = "a chest infection" if drug=="amoxicillin" else "a urinary tract infection"
    inj["type"]="drug_allergy_conflict"; inj["severity"]="high"
    art = "an" if DRUGS[drug]['cls'][0].lower() in "aeiou" else "a"
    ev = line("DR", f"For that I'm going to start you on {drug} {DRUGS[drug]['dose']} — should clear {reason} up in about a week.")
    inj["plan_turns"]=[
        line("DR", f"Sounds like {reason}. Let's treat it."),
        ev,
        line("PT","Okay, whatever you think is best."),
    ]
    inj["note_plan_items"]=[(reason[2:].title(),
        f"Clinical picture consistent with {reason[2:]}. Started {drug} {DRUGS[drug]['dose']}.")]
    inj["avs_next"]=[f"Start {drug} {DRUGS[drug]['dose']} as prescribed."]
    inj["discrepancy_label"]={
        "type":"drug_allergy_conflict","severity":"high",
        "explanation":f"{drug} was prescribed but the chart lists a documented {label} allergy; {drug} is {art} {DRUGS[drug]['cls']} and cross-reacts.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"AllergyIntolerance","match_display":label},
        "suggested_fix":f"Do not prescribe {drug}. Choose a non-cross-reactive alternative (e.g. a macrolide or, for UTI, nitrofurantoin if renal function allows) and confirm the allergy with the patient.",
    }
    return inj

def inj_renal_dose(chart, rng):
    # choose a renally-contraindicated drug given a low eGFR
    egfr = chart.egfr
    if egfr is None: return None
    candidates = []
    if egfr < 30: candidates += [("metformin", "your blood sugar"), ("nitrofurantoin","the urine infection"), ("ibuprofen","your back pain")]
    if egfr < 45 and "metformin" not in chart.home_meds: candidates.append(("metformin","your blood sugar"))
    if not candidates: return None
    drug, ctx = rng.choice(candidates)
    if drug in chart.home_meds and drug!="metformin": return None
    d = DRUGS[drug]
    inj=_blank()
    inj["set_egfr"]=egfr
    inj["labs"]={"egfr":egfr}
    inj["prescribe"]=[drug]
    inj["type"]="renal_dose_conflict"; inj["severity"]="high"
    ev=line("DR", f"I'll get you going on {drug} {d['dose']} for {ctx}.")
    inj["plan_turns"]=[ev, line("PT","All right.")]
    inj["note_plan_items"]=[("Medication start", f"Started {drug} {d['dose']}.")]
    inj["avs_next"]=[f"Start {drug} {d['dose']}."]
    inj["discrepancy_label"]={
        "type":"renal_dose_conflict","severity":"high",
        "explanation":f"{drug} started at standard dose but the most recent eGFR is {egfr} mL/min/1.73m2. Rule: {d['renal'].get('rule','renal adjustment required')}.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"Observation","match_display":"Glomerular filtration rate"},
        "suggested_fix":f"Hold or renally dose {drug}; recheck renal function. At eGFR {egfr}, {d['renal'].get('rule','dose adjustment / avoidance is indicated')}.",
    }
    return inj

def inj_ddi(chart, rng):
    # find a home med that dangerously interacts with a candidate new prescription
    options=[]
    for home in chart.home_meds:
        for cand,harm in DRUGS.get(home,{}).get("interacts",{}).items():
            if cand in DRUGS and cand not in chart.home_meds:
                options.append((home,cand,harm))
    # also reverse direction (new drug interacts with home)
    for cand,cd in DRUGS.items():
        for other,harm in cd.get("interacts",{}).items():
            if other in chart.home_meds and cand not in chart.home_meds:
                options.append((other,cand,harm))
    options=[o for o in options if o[1] in DRUGS]
    if not options: return None
    home,cand,harm=rng.choice(options)
    d=DRUGS[cand]
    inj=_blank()
    inj["ensure_home_med"]=[home]
    inj["prescribe"]=[cand]
    inj["type"]="drug_drug_interaction"; inj["severity"]="high" if "life-threatening" in harm or "major" in harm else "moderate"
    ev=line("DR", f"Let's add {cand} {d['dose']} — that should help.")
    inj["plan_turns"]=[ev, line("PT","Okay.")]
    inj["note_plan_items"]=[("New prescription", f"Started {cand} {d['dose']}.")]
    inj["avs_next"]=[f"Start {cand} {d['dose']}."]
    inj["discrepancy_label"]={
        "type":"drug_drug_interaction","severity":inj["severity"],
        "explanation":f"Newly prescribed {cand} interacts with the patient's active {home}: {harm}.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"MedicationRequest","match_display":home},
        "suggested_fix":f"Avoid co-prescribing {cand} with {home} ({harm}). Select a non-interacting alternative or adjust/monitor closely.",
    }
    return inj

def inj_teratogen(chart, rng):
    if "Pregnancy" not in chart.conditions: return None
    drug=rng.choice(["lisinopril","atorvastatin","warfarin"])
    d=DRUGS[drug]
    inj=_blank(); inj["prescribe"]=[drug]
    inj["type"]="drug_condition_conflict"; inj["severity"]="high"
    ev=line("DR", f"I'll start you on {drug} {d['dose']} for that.")
    inj["plan_turns"]=[ev, line("PT","Okay, thank you.")]
    inj["note_plan_items"]=[("New prescription", f"Started {drug} {d['dose']}.")]
    inj["avs_next"]=[f"Start {drug} {d['dose']}."]
    inj["discrepancy_label"]={
        "type":"drug_condition_conflict","severity":"high",
        "explanation":f"{drug} is contraindicated in pregnancy (known teratogen) and the chart documents an active pregnancy.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"Condition","match_display":"Pregnancy"},
        "suggested_fix":f"Do not prescribe {drug} in pregnancy. Choose a pregnancy-safe alternative and counsel the patient.",
    }
    return inj

def inj_duplicate(chart, rng):
    # prescribe a drug in the same class as an active home med
    class_map={}
    for m in chart.home_meds: class_map.setdefault(DRUGS[m]["cls"],[]).append(m)
    dupes=[]
    for drug,d in DRUGS.items():
        if drug in chart.home_meds: continue
        if d["cls"] in class_map:
            dupes.append((drug, class_map[d["cls"]][0], d["cls"]))
    if not dupes: return None
    cand,home,cls=rng.choice(dupes)
    d=DRUGS[cand]
    inj=_blank(); inj["prescribe"]=[cand]
    inj["type"]="duplicate_therapy"; inj["severity"]="moderate"
    ev=line("DR", f"I want to add {cand} {d['dose']} to get better control.")
    inj["plan_turns"]=[ev, line("PT","Sure.")]
    inj["note_plan_items"]=[("Titration", f"Added {cand} {d['dose']}.")]
    inj["avs_next"]=[f"Start {cand} {d['dose']}."]
    inj["discrepancy_label"]={
        "type":"duplicate_therapy","severity":"moderate",
        "explanation":f"{cand} and the active home med {home} are both {cls}s — duplicate therapy in the same class.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"MedicationRequest","match_display":home},
        "suggested_fix":f"Avoid stacking two {cls}s. Titrate the existing {home} or switch, rather than adding {cand}.",
    }
    return inj

def inj_dropped_med(chart, rng):
    important={"atorvastatin","simvastatin","warfarin","apixaban","insulin glargine","levothyroxine","lisinopril","metoprolol"}
    present=[m for m in chart.home_meds if m in important]
    if not present: return None
    drug=rng.choice(present)
    d=DRUGS[drug]
    inj=_blank(); inj["drop_med"]=drug
    inj["type"]="dropped_home_med"; inj["severity"]="moderate" if drug not in ("warfarin","insulin glargine") else "high"
    ev=line("PT", f"Oh — I actually ran out of the {drug} a couple months ago and never refilled it.")
    inj["review_turns"]=[
        line("DR","Let's go through your medicines. What are you taking these days?"),
        ev,
        line("DR","Got it, thanks for telling me."),
    ]
    # note omits restarting the drug on purpose (that's the discrepancy)
    inj["note_plan_items"]=[("Medication reconciliation","Reviewed current medications; list updated.")]
    inj["avs_next"]=["Reviewed your medication list."]
    inj["discrepancy_label"]={
        "type":"dropped_home_med","severity":inj["severity"],
        "explanation":f"The patient reports having stopped {drug}, an active chart medication, and the plan does not restart or address it.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"MedicationRequest","match_display":drug},
        "suggested_fix":f"Reconcile: {drug} is still on the active problem/med list. Confirm whether to restart {drug} ({d['cls']}) and document the decision.",
    }
    return inj

def inj_history_mismatch(chart, rng):
    deniable=[c for c in chart.conditions if c in ("Type 2 diabetes mellitus","Chronic kidney disease stage 4",
              "Chronic kidney disease stage 3","Atrial fibrillation","Coronary artery disease","Hypothyroidism")]
    if not deniable: return None
    cond=rng.choice(deniable)
    inj=_blank()
    inj["type"]="history_mismatch"; inj["severity"]="moderate"
    ev=line("DR", f"And you've never had any problems with {cond.lower()}, correct? Nothing like that in your history.")
    inj["hpi_turns"]=[ev, line("PT","No, nothing like that.")]
    inj["note_plan_items"]=[("History", f"No history of significant chronic disease per patient report.")]
    inj["avs_next"]=[]
    inj["discrepancy_label"]={
        "type":"history_mismatch","severity":"moderate",
        "explanation":f"The visit states the patient has no history of {cond.lower()}, but it is an active, confirmed problem on the chart.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"Condition","match_display":cond},
        "suggested_fix":f"Reconcile the history: {cond} is an active charted diagnosis. Verify with the patient and correct the record.",
    }
    return inj

def inj_adverse_event(chart, rng):
    # a NEW symptom the patient reports that matches a home med's known ADR
    opts=[(m, DRUGS[m]["adr"]) for m in chart.home_meds if DRUGS[m]["adr"]]
    if not opts: return None
    drug,adrs=rng.choice(opts); symptom=rng.choice(adrs)
    inj=_blank()
    ev=line("PT", f"One new thing — for the last few weeks I've had {symptom}. It started after we changed my medicines.")
    inj["hpi_turns"]=[
        line("DR","Anything new since I saw you last?"),
        ev,
        line("DR","Thanks for flagging that."),
    ]
    inj["note_plan_items"]=[("New symptom", f"Reports {symptom}, onset over recent weeks.")]
    inj["avs_next"]=[]
    inj["adverse_event_label"]={
        "type":"adverse_drug_event","severity":"moderate",
        "suspected_drug":drug,"reported_symptom":symptom,
        "explanation":f"Patient reports {symptom}, a recognized adverse effect of their active {drug} ({DRUGS[drug]['cls']}); temporal onset after a medication change raises suspicion of an ADR.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"MedicationRequest","match_display":drug},
        "suggested_fix":f"Consider {drug} as the cause of {symptom}. Evaluate for an adverse drug reaction; weigh dose reduction, switch, or rechallenge.",
    }
    return inj

def inj_control(chart, rng):
    inj=_blank()
    inj["type"]=None
    # a safe, consistent plan (possibly a near-miss for false-positive stress-testing)
    safe = [m for m in chart.home_meds]
    inj["note_plan_items"]=[("Chronic disease management",
        "Stable on current regimen; continue home medications as charted. Labs reviewed and at goal."),
        ("Health maintenance","Age-appropriate screening up to date; return in 3-6 months.")]
    inj["plan_turns"]=[
        line("DR","Everything looks stable. I want to keep you on the same medicines — no changes today."),
        line("PT","Sounds good."),
    ]
    inj["avs_next"]=["Continue your current medications as before.","Routine follow-up in 3-6 months."]
    inj["discrepancy_label"]=None
    return inj

def inj_dropped_result(chart, rng):
    # a prior abnormal lab carried in the chart that the current visit ignores
    picks=[]
    if any(m in chart.home_meds for m in ("lisinopril","spironolactone","enalapril")):
        picks.append(("k",5.8,"potassium","a high potassium of 5.8"))
    if "Type 2 diabetes mellitus" in chart.conditions:
        picks.append(("a1c",9.8,"A1c","an A1c of 9.8%"))
    if "warfarin" in chart.home_meds:
        picks.append(("inr",4.6,"INR","an INR of 4.6"))
    if not picks: return None
    key,val,short,phrase=rng.choice(picks)
    inj=_blank()
    inj["labs"]={key:val}; inj["prior_lab_days"]=95   # dated ~3 months before the visit
    inj["type"]="dropped_result"; inj["severity"]="high" if key in ("k","inr") else "moderate"
    ev=line("PT", f"Also — did that bloodwork from last time come back alright? I never heard anything.")
    inj["hpi_turns"]=[ev, line("DR","We can look into that another time — today I want to focus on your blood pressure.")]
    inj["note_plan_items"]=[("Blood pressure","Continue current regimen; recheck at next visit.")]
    inj["avs_next"]=["Follow up on blood pressure at next visit."]
    inj["discrepancy_label"]={
        "type":"dropped_result","severity":inj["severity"],
        "explanation":f"A prior abnormal result ({phrase}) is on the chart and was raised by the patient, but the visit defers it with no follow-up plan.",
        "transcript_evidence":ev,
        "chart_evidence":{"resource_type":"Observation","match_display":LOINC_CODES[key][1][:20]},
        "suggested_fix":f"Do not defer {phrase}. Address the abnormal {short} today: repeat the test and/or adjust therapy, and document the plan.",
    }
    return inj

INJECTORS = {
  "drug_allergy_conflict": inj_drug_allergy,
  "renal_dose_conflict":   inj_renal_dose,
  "drug_drug_interaction": inj_ddi,
  "drug_condition_conflict":inj_teratogen,
  "duplicate_therapy":     inj_duplicate,
  "dropped_home_med":      inj_dropped_med,
  "history_mismatch":      inj_history_mismatch,
  "dropped_result":        inj_dropped_result,
  "adverse_drug_event":    inj_adverse_event,
  "control":               inj_control,
}

# ---------------------------------------------------------------------------
# ASSEMBLER: chart + injected -> full record + label
# ---------------------------------------------------------------------------
def vitals_for(chart, rng):
    htn = "Essential hypertension" in chart.conditions
    sbp = rng.randint(146,162) if htn else rng.randint(116,128)
    dbp = rng.randint(88,98) if htn else rng.randint(72,80)
    hr  = rng.randint(66,88)
    wt  = rng.randint(58,102)
    bmi = round(wt/ (1.72**2),1)
    return sbp,dbp,hr,wt,bmi

def assemble(chart, enc_id, when, injected, n_prior_enc):
    rng=chart.rng
    # --- apply chart mutations ---
    if injected["ensure_allergy"]: chart.allergy = injected["ensure_allergy"]
    if injected["set_egfr"] is not None: chart.egfr = injected["set_egfr"]
    for m in injected["ensure_home_med"]:
        if m not in chart.home_meds: chart.home_meds.append(m)

    pid=chart.pid
    resources={"Condition":[],"Observation":[],"MedicationRequest":[],"AllergyIntolerance":[],"Procedure":[]}
    # conditions (active problems reconciled at visit)
    for c in chart.conditions:
        onset = when - dt.timedelta(days=rng.randint(400,3000))
        resources["Condition"].append(mk_condition(uid(rng),pid,enc_id,c,onset))
    # active home meds (authored earlier)
    for m in chart.home_meds:
        auth = when - dt.timedelta(days=rng.randint(200,1500))
        resources["MedicationRequest"].append(mk_med(uid(rng),pid,enc_id,m,auth,status="active"))
    # newly prescribed this visit
    for m in injected["prescribe"]:
        resources["MedicationRequest"].append(mk_med(uid(rng),pid,enc_id,m,when,status="active"))
    # allergy
    if chart.allergy:
        resources["AllergyIntolerance"].append(mk_allergy(uid(rng),pid,chart.allergy, when-dt.timedelta(days=rng.randint(600,3000))))
    # vitals + labs
    sbp,dbp,hr,wt,bmi=vitals_for(chart,rng)
    for key,val in [("sbp",sbp),("dbp",dbp),("hr",hr),("wt",wt),("bmi",bmi)]:
        resources["Observation"].append(mk_obs(uid(rng),pid,enc_id,key,val,when,category="vital-signs"))
    labset={}
    labset["egfr"]=chart.egfr
    if "Type 2 diabetes mellitus" in chart.conditions: labset["a1c"]=round(rng.uniform(6.8,8.4),1)
    if "Hyperlipidemia" in chart.conditions: labset["ldl"]=rng.randint(96,150)
    if "warfarin" in chart.home_meds: labset["inr"]=round(rng.uniform(2.0,2.8),1)
    if "Hypothyroidism" in chart.conditions: labset["tsh"]=round(rng.uniform(1.5,3.8),1)
    labset.update(injected["labs"])
    for key,val in labset.items():
        when_lab = when
        if injected["type"]=="dropped_result" and key in injected["labs"]:
            when_lab = when - dt.timedelta(days=injected.get("prior_lab_days",95))
        resources["Observation"].append(mk_obs(uid(rng),pid,enc_id,key,val,when_lab))

    # --- resolve label chart_evidence to a concrete resource id ---
    def resolve(ev):
        if not ev: return ev
        ce=ev.get("chart_evidence")
        if not ce: return ev
        want_type=ce["resource_type"]; needle=ce["match_display"].lower()
        for r in resources.get(want_type,[]):
            text=json.dumps(r).lower()
            if needle in text:
                disp = (r.get("code",{}).get("text") or r.get("medicationCodeableConcept",{}).get("text")
                        or r.get("code",{}).get("coding",[{}])[0].get("display",""))
                ce["resource_id"]=r["id"]; ce["display"]=disp
                break
        ce.pop("match_display",None)
        return ev
    resolve(injected["discrepancy_label"]); resolve(injected["adverse_event_label"])

    # ================= TRANSCRIPT =================
    nm=chart.given
    T=[]
    T.append(line("DR", rng.choice([
        f"Morning, {nm} — come on in. Good to see you again.",
        f"Hi {nm}, thanks for coming in today. Have a seat.",
        f"{nm}, good to see you. How've you been?"])))
    T.append(line("PT", rng.choice(["Thanks, doctor.","Good to see you too.","Appreciate you fitting me in."])))
    T.append(line("DR","So how have things been since your last visit?"))
    if injected["hpi_turns"]:
        T += injected["hpi_turns"]
    else:
        T.append(line("PT","Pretty steady overall, no big changes."))
    # med review
    T += (injected["review_turns"] or [
        line("DR","Let me just confirm your medicines."),
        line("PT", "Same as before — " + (", ".join(chart.home_meds) if chart.home_meds else "nothing regular") + "."),
        line("DR","Great, that matches what I have."),
    ])
    # exam / vitals
    T.append(line("NURSE", f"Blood pressure today is {sbp} over {dbp}, heart rate {hr}."))
    T.append(line("DR", f"Your weight's about {wt} kilos. Let me listen... heart and lungs sound good."))
    # labs
    lab_bits=[]
    if "a1c" in labset: lab_bits.append(f"A1c {labset['a1c']} percent")
    lab_bits.append(f"kidney function eGFR {chart.egfr}")
    if "inr" in labset: lab_bits.append(f"INR {labset['inr']}")
    T.append(line("DR","Your labs — "+", ".join(lab_bits)+"."))
    # plan
    T.append(line("DR","Let's talk about the plan."))
    T += (injected["plan_turns"] or [
        line("DR","No changes needed — keep doing what you're doing."),
        line("PT","Okay, sounds good."),
    ])
    T.append(line("DR","Any questions before you go?"))
    T.append(line("PT","No, I think that's everything. Thank you."))
    transcript="\n".join(T)

    # ================= NOTE =================
    age=chart.age; sex="man" if chart.gender=="male" else "woman"
    subj_bits=[f"{nm} {chart.family} is a {age}-year-old {sex} presenting for a routine follow-up."]
    if chart.conditions: subj_bits.append("Active problems include "+", ".join(c.lower() for c in chart.conditions)+".")
    for t in injected["hpi_turns"]:
        spk,text=t.split(": ",1)
        if spk=="PT": subj_bits.append("Patient reports: "+text)
    for t in injected["review_turns"]:
        spk,text=t.split(": ",1)
        if spk=="PT" and "ran out" in text: subj_bits.append(text)
    subjective=" ".join(subj_bits)
    objective=(f"Vitals: BP {sbp}/{dbp} mmHg, HR {hr}/min, weight {wt} kg, BMI {bmi} kg/m2. "
               f"Exam: no acute distress; heart regular, lungs clear. "
               f"Labs: eGFR {chart.egfr} mL/min/1.73m2"
               + (f", A1c {labset['a1c']}%" if "a1c" in labset else "")
               + (f", INR {labset['inr']}" if "inr" in labset else "") + ".")
    plan_items = injected["note_plan_items"] or [("Chronic disease management","Stable; continue current regimen.")]
    ap_lines=["**Assessment and Plan:**",""]
    for head,body in plan_items:
        ap_lines += [f"### {head}", body, ""]
    note = (f"**Subjective:** {subjective}\n\n**Objective:** {objective}\n\n"+"\n".join(ap_lines)).strip()

    # ================= AVS =================
    discussed=[h for h,_ in plan_items]
    nexts=injected["avs_next"] or ["Continue current care.","Return as scheduled."]
    avs=("Visit summary\n\nWhat we discussed\n"+"\n".join("• "+d for d in discussed)
         +"\n\nNext steps\n"+"\n".join("• "+n for n in nexts))

    # ================= RECORD =================
    rr_counts={k:len(v) for k,v in resources.items() if v}
    visit_type="General examination of patient (procedure)"
    visit_title=f"Follow-up visit — {', '.join(c for c in chart.conditions[:2])}".rstrip(", ")
    encounter=mk_encounter(enc_id,pid,when,visit_type,chart.name_display)
    long_counts={"Patient":1,"Encounter":n_prior_enc+1,
                 "Condition":len(chart.conditions),
                 "MedicationRequest":len(chart.home_meds)+len(injected["prescribe"]),
                 "Observation":len(resources["Observation"])*(n_prior_enc+1),
                 "AllergyIntolerance":1 if chart.allergy else 0}
    med_labels=sorted(set(chart.home_meds+injected["prescribe"]))
    record={
      "id":f"{pid}::{enc_id}",
      "metadata":{
        "source":"synthea-fhir-r4+discrepancy-injection","synthetic":True,
        "patient_id":pid,"encounter_id":enc_id,"encounter_reference":urn(enc_id),
        "date":iso(when),"status":"finished","visit_type":visit_type,
        "document_status":"current","related_resource_counts":rr_counts,
        "visit_title":visit_title,
      },
      "patient_context":{
        "patient":mk_patient(pid,chart.gender,chart.given,chart.family,chart.birth),
        "longitudinal_summary":{
          "resource_counts":long_counts,
          "condition_labels":list(chart.conditions),
          "medication_labels":med_labels,
          "allergy_labels":[chart.allergy] if chart.allergy else [],
        },
      },
      "encounter_fhir":{"encounter":encounter,
        "related_resources":{k:v for k,v in resources.items() if v}},
      "transcript":transcript,"note":note,"after_visit_summary":avs,
      "after_visit_summary_provenance":{"method":"template_extractive_v1",
        "source":"clinical_note_assessment_and_plan","review_status":"not_clinically_reviewed"},
    }
    # ================= LABEL =================
    discs=[injected["discrepancy_label"]] if injected["discrepancy_label"] else []
    ades=[injected["adverse_event_label"]] if injected["adverse_event_label"] else []
    label={"id":record["id"],"archetype":chart.archetype,
           "has_discrepancy":bool(discs),"discrepancies":discs,
           "has_adverse_event":bool(ades),"adverse_events":ades,
           "is_control":injected["type"] is None}
    return record,label

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def plan_schedule(rng):
    # target distribution over ~100 records (one primary label each)
    sched=( ["drug_allergy_conflict"]*11 + ["renal_dose_conflict"]*10 + ["drug_drug_interaction"]*12
          + ["duplicate_therapy"]*8 + ["dropped_home_med"]*10 + ["history_mismatch"]*8
          + ["drug_condition_conflict"]*4 + ["dropped_result"]*5 + ["adverse_drug_event"]*10
          + ["control"]*22 )
    rng.shuffle(sched)
    return sched

def compatible_archetype(disc_type, rng):
    pool=archetype_pool()
    table={
      "drug_condition_conflict":["pregnancy"],
      "renal_dose_conflict":["advanced_ckd_dm","recurrent_uti_elderly"],
      "drug_drug_interaction":["afib_anticoag","mood_migraine","cad_secondary_prevention","cardiometabolic_ckd","advanced_ckd_dm"],
      "drug_allergy_conflict":["copd_asthma","recurrent_uti_elderly","cardiometabolic_ckd","mood_migraine"],
      "duplicate_therapy":["cardiometabolic_ckd","hypothyroid_htn","cad_secondary_prevention"],
      "dropped_home_med":["cardiometabolic_ckd","afib_anticoag","cad_secondary_prevention","hypothyroid_htn","advanced_ckd_dm"],
      "history_mismatch":["cardiometabolic_ckd","afib_anticoag","advanced_ckd_dm","hypothyroid_htn","recurrent_uti_elderly"],
      "dropped_result":["cardiometabolic_ckd","afib_anticoag","advanced_ckd_dm"],
      "adverse_drug_event":["cardiometabolic_ckd","cad_secondary_prevention","mood_migraine","hypothyroid_htn","afib_anticoag"],
    }
    if disc_type in table: return rng.choice(table[disc_type])
    return rng.choice([a for a in pool if a!="pregnancy"])

def main():
    rng=random.Random(SEED)
    sched=plan_schedule(rng)
    records=[]; labels=[]
    pi=0
    for disc_type in sched:
        injector=INJECTORS["control" if disc_type=="control" else disc_type]
        chart=None; injected=None
        for _attempt in range(8):      # retry with fresh compatible charts before giving up
            arche=compatible_archetype(disc_type, rng)
            chart=build_base_chart(rng, arche, uid(rng))
            injected=injector(chart, rng)
            if injected is not None: break
        if injected is None:           # last resort: clean control
            chart=build_base_chart(rng, compatible_archetype("control",rng), uid(rng))
            injected=inj_control(chart, rng)
        # single encounter per patient in v1 (longitudinal counts still reflect history)
        n_prior=rng.randint(1,6)
        when=BASE_DATE - dt.timedelta(days=rng.randint(5,120))
        rec,lab=assemble(chart, uid(rng), when, injected, n_prior)
        records.append(rec); labels.append(lab)
        pi+=1
    records=records[:N_RECORDS]; labels=labels[:N_RECORDS]

    # ---- write outputs ----
    base=os.path.join(OUT_DIR,"discrepancy-train")
    with open(base+".jsonl","w") as f:
        for r in records: f.write(json.dumps(r)+"\n")
    with open(base+".json","w") as f: json.dump(records,f,indent=1)
    with open(base+".labels.jsonl","w") as f:
        for l in labels: f.write(json.dumps(l)+"\n")

    # summary
    from collections import Counter
    dc=Counter()
    for l in labels:
        if l["is_control"] and not l["has_adverse_event"]: dc["control"]+=1
        for d in l["discrepancies"]: dc[d["type"]]+=1
        for a in l["adverse_events"]: dc["adverse_drug_event"]+=1
    summary={"name":"discrepancy-train","records":len(records),
             "patients":len(records),"synthetic":True,
             "label_distribution":dict(dc),
             "index":[{"id":r["id"],"date":r["metadata"]["date"][:10],
                       "visit_title":r["metadata"]["visit_title"],
                       "has_discrepancy":labels[i]["has_discrepancy"],
                       "has_adverse_event":labels[i]["has_adverse_event"],
                       "primary_type":(labels[i]["discrepancies"][0]["type"] if labels[i]["discrepancies"]
                                       else ("adverse_drug_event" if labels[i]["has_adverse_event"] else "control"))}
                      for i,r in enumerate(records)]}
    with open(os.path.join(OUT_DIR,"summary.json"),"w") as f: json.dump(summary,f,indent=1)
    print(f"Wrote {len(records)} records.")
    print("Label distribution:", dict(dc))

if __name__=="__main__":
    main()

