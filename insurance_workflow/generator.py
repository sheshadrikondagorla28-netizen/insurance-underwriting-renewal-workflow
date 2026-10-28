"""Deterministic synthetic insurance underwriting and renewal dataset generator.

Standard-library only. Business thresholds are explicit configurable assumptions, not real-world advice.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, random, sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

SEED_DEFAULT = 20261022
PRODUCTS = [
    {"product_id":"PRD-AUTO","product_name":"Motor Insurance","product_line":"motor","base_rate":0.035,"max_coverage":100000,"min_age":18,"max_risk_score":100,"max_asset_value":750000,"active":True},
    {"product_id":"PRD-HOME","product_name":"Home Insurance","product_line":"property","base_rate":0.012,"max_coverage":500000,"min_age":18,"max_risk_score":100,"max_asset_value":750000,"active":True},
    {"product_id":"PRD-BIZ","product_name":"Small Business Insurance","product_line":"business","base_rate":0.022,"max_coverage":300000,"min_age":18,"max_risk_score":100,"max_asset_value":750000,"active":True},
]
COVERAGES = [
    {"coverage_option_id":"COV-AUTO-BASIC","product_id":"PRD-AUTO","coverage_name":"Basic","limit_amount":25000,"deductible_amount":1000,"active":True},
    {"coverage_option_id":"COV-AUTO-PLUS","product_id":"PRD-AUTO","coverage_name":"Plus","limit_amount":75000,"deductible_amount":500,"active":True},
    {"coverage_option_id":"COV-HOME-BASIC","product_id":"PRD-HOME","coverage_name":"Basic","limit_amount":150000,"deductible_amount":1500,"active":True},
    {"coverage_option_id":"COV-HOME-PLUS","product_id":"PRD-HOME","coverage_name":"Plus","limit_amount":400000,"deductible_amount":1000,"active":True},
    {"coverage_option_id":"COV-BIZ-BASIC","product_id":"PRD-BIZ","coverage_name":"Basic","limit_amount":100000,"deductible_amount":2000,"active":True},
    {"coverage_option_id":"COV-BIZ-PLUS","product_id":"PRD-BIZ","coverage_name":"Plus","limit_amount":250000,"deductible_amount":1500,"active":True},
]
RISK_FACTORS = [
    {"risk_factor_id":"RSK-CLAIMS","factor_name":"prior_claims","factor_type":"multiplier","factor_value":0.08,"description":"Premium uplift per prior claim"},
    {"risk_factor_id":"RSK-HIGH","factor_name":"high_risk","factor_type":"multiplier","factor_value":0.35,"description":"Premium uplift for high risk"},
    {"risk_factor_id":"RSK-AGE","factor_name":"young_customer","factor_type":"multiplier","factor_value":0.12,"description":"Premium uplift for younger eligible applicants"},
    {"risk_factor_id":"RSK-MISSING","factor_name":"missing_risk_data","factor_type":"referral","factor_value":1,"description":"Refer if required risk data is missing"},
]
PRODUCT_BY_ID = {p['product_id']:p for p in PRODUCTS}
COV_BY_ID = {c['coverage_option_id']:c for c in COVERAGES}

def iso(d): return d.isoformat() if isinstance(d, date) else d

def make_id(prefix, n, year=2026): return f"{prefix}-{year}-{n:06d}"

def calc_premium(product, coverage_limit, risk_score, prior_claims, age, missing=False):
    # Documented transparent formula: base premium = coverage limit * product base rate.
    # Multipliers are additive; minimum premium is 50 currency units.
    mult = 1.0 + (0.08 * prior_claims) + (0.35 if risk_score >= 70 else 0.0) + (0.12 if age < 25 else 0.0)
    return round(max(50.0, coverage_limit * product['base_rate'] * mult), 2)

def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8'); return
    with path.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction='ignore'); w.writeheader()
        for r in rows: w.writerow({k: iso(v) for k,v in r.items()})

def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{k:iso(v) for k,v in r.items()} for r in rows], indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def generate(out_dir: Path, seed=SEED_DEFAULT, scale=1, anomalies=True):
    rng=random.Random(seed); out_dir=Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    n_app=3000*scale; n_quote=4000*scale; n_policy=2000*scale; n_renew=1200*scale
    today=date(2026,10,22)
    applicants=[]; assets=[]; quotes=[]; policies=[]; decisions=[]; endorsements=[]; renewals=[]; ground_truth=[]
    # Master data first, with deterministic IDs and synthetic non-identifying attributes.
    for i in range(1,n_app+1):
        age=rng.randint(18,80); applicants.append({"applicant_id":make_id('APP',i),"applicant_type":rng.choice(['individual','small_business']),"age":age,"region":rng.choice(['north','south','east','west','central']),"customer_since":today-timedelta(days=rng.randint(30,5000)),"consent_status":"synthetic_not_applicable"})
        asset_type={0:'vehicle',1:'property',2:'business_premises'}[(i-1)%3]
        assets.append({"asset_id":f"AST-2026-{i:06d}","applicant_id":make_id('APP',i),"asset_type":asset_type,"asset_value":round(rng.uniform(5000,700000),2),"region":rng.choice(['north','south','east','west','central']),"acquired_date":today-timedelta(days=rng.randint(30,4000)),"asset_status":"active"})
    # Quotes: all references valid; product, coverage and asset types are aligned by product line.
    asset_type_by_line={'motor':'vehicle','property':'property','business':'business_premises'}
    asset_indexes_by_type={kind:[idx for idx,a in enumerate(assets) if a['asset_type']==kind] for kind in set(asset_type_by_line.values())}
    for i in range(1,n_quote+1):
        product=PRODUCTS[(i-1)%len(PRODUCTS)]
        covs=[c for c in COVERAGES if c['product_id']==product['product_id']]; cov=rng.choice(covs)
        candidate_indexes=asset_indexes_by_type[asset_type_by_line[product['product_line']]]
        asset_index=rng.choice(candidate_indexes); asset=assets[asset_index]
        aid=asset['applicant_id']; applicant=applicants[int(aid[-6:])-1]
        risk_missing=(i%97==0); score=None if risk_missing else rng.randint(1,100); claims=rng.randint(0,4)
        eligible=(applicant['age']>=product['min_age'] and asset['asset_value']<=product['max_asset_value'] and (score is None or score<=product['max_risk_score']))
        referral=bool(risk_missing or (score is not None and score>=70))
        premium=None if risk_missing else calc_premium(product,cov['limit_amount'],score,claims,applicant['age'])
        qid=make_id('QTE',i)
        quotes.append({"quote_id":qid,"applicant_id":aid,"asset_id":asset['asset_id'],"product_id":product['product_id'],"coverage_option_id":cov['coverage_option_id'],"submission_date":today-timedelta(days=rng.randint(0,700)),"risk_score":score,"prior_claims":claims,"requested_coverage":cov['limit_amount'],"calculated_premium":premium,"eligibility_status":"eligible" if eligible else "ineligible","quote_status":"referred" if referral else ("offered" if eligible else "declined"),"risk_data_missing":risk_missing})
        if referral or not eligible:
            decisions.append({"underwriting_decision_id":f"UWD-2026-{len(decisions)+1:06d}","quote_id":qid,"decision_date":today,"decision":"refer" if referral else "decline","reason":"missing_risk_data" if risk_missing else ("high_risk_score" if score is not None and score>=70 else "eligibility_rule_failed"),"authority_level":"senior_underwriter" if referral else "automated_rules","rule_version":"1.0"})
    # Select 2,000 policy-linked quotes. Baseline policies only issue when accepted and paid.
    eligible_quotes=[q for q in quotes if q['eligibility_status']=='eligible' and q['calculated_premium'] is not None and q['quote_status']!='referred']
    if len(eligible_quotes)<n_policy: raise ValueError('Not enough eligible quotes to issue requested policy volume; increase scale or revise seed/rules.')
    selected=rng.sample(eligible_quotes,n_policy)
    pair_last_end={}
    for i,q in enumerate(selected,1):
        pair=(q['applicant_id'],q['asset_id'])
        start=today-timedelta(days=rng.randint(0,600))
        if pair in pair_last_end and start <= pair_last_end[pair]: start=pair_last_end[pair]+timedelta(days=1)
        end=start+timedelta(days=365); pair_last_end[pair]=end
        polid=make_id('POL',i); accepted=True; paid=True
        policies.append({"policy_id":polid,"quote_id":q['quote_id'],"applicant_id":q['applicant_id'],"asset_id":q['asset_id'],"product_id":q['product_id'],"coverage_option_id":q['coverage_option_id'],"issue_date":start,"effective_date":start,"expiry_date":end,"premium_amount":q['calculated_premium'],"acceptance_status":"accepted","payment_status":"paid","policy_status":"active","permitted_overlap_reason":None})
    # Endorsements: valid changes only, within product limit; event history retained.
    for i in range(1, max(2, n_policy//10)+1):
        p=policies[(i*7-1)%len(policies)]; prod=PRODUCT_BY_ID[p['product_id']]; cov=COV_BY_ID[p['coverage_option_id']]
        change=min(1000.0, max(100.0, cov['limit_amount']*0.01)); new_limit=min(cov['limit_amount'], prod['max_coverage'])
        original_asset=next(a for a in assets if a['asset_id']==p['asset_id'])
        new_asset_value=round(min(original_asset['asset_value']*1.05, 749999.99),2)
        endorsements.append({"endorsement_id":f"END-{p['policy_id']}-{1:03d}","policy_id":p['policy_id'],"effective_date":p['effective_date']+timedelta(days=30),"endorsement_type":"asset_change","asset_id":p['asset_id'],"previous_asset_value":original_asset['asset_value'],"new_asset_value":new_asset_value,"coverage_change":0.0,"resulting_coverage":new_limit,"endorsement_status":"approved","reason":"mid_term_asset_value_change"})
    # 1,200 renewal records. Some are offers; declined renewals are explicit lifecycle outcomes.
    renewal_policies=rng.sample(policies, min(n_renew,len(policies)))
    for i,p in enumerate(renewal_policies,1):
        status='declined' if i%10==0 else 'offered'
        renewals.append({"renewal_id":f"REN-{p['policy_id']}-2027","policy_id":p['policy_id'],"offer_date":p['expiry_date']-timedelta(days=45),"proposed_effective_date":p['expiry_date']+timedelta(days=1),"proposed_expiry_date":p['expiry_date']+timedelta(days=366),"renewal_premium":round(p['premium_amount']*1.04,2),"renewal_status":status,"decision_reason":"customer_declined" if status=='declined' else "eligible_for_renewal"})
    # Required deliberate anomalies are isolated, labelled, and excluded from valid baseline assertions.
    if anomalies and policies:
        p=policies[0]; q=next(x for x in quotes if x['quote_id']==p['quote_id'])
        p['acceptance_status']='pending'
        ground_truth.append({"case_id":"ANOM-001","entity_type":"Policy","entity_id":p['policy_id'],"issue_type":"policy_issued_without_acceptance","ground_truth_label":"invalid","expected_rule":"Policy issuance requires acceptance_status=accepted and payment_status=paid","injected":True})
        q2=quotes[1]; q2['calculated_premium']=round((q2['calculated_premium'] or 100)*1.7,2)
        ground_truth.append({"case_id":"ANOM-002","entity_type":"Quote","entity_id":q2['quote_id'],"issue_type":"premium_outside_defined_rate_formula","ground_truth_label":"invalid","expected_rule":"calculated_premium must equal documented factor formula when required risk inputs exist","injected":True})
        if endorsements:
            e=endorsements[0]; prod=PRODUCT_BY_ID[next(x for x in policies if x['policy_id']==e['policy_id'])['product_id']]
            e['resulting_coverage']=prod['max_coverage']+5000
            ground_truth.append({"case_id":"ANOM-003","entity_type":"Endorsement","entity_id":e['endorsement_id'],"issue_type":"endorsement_exceeds_product_limit","ground_truth_label":"invalid","expected_rule":"resulting_coverage must not exceed product.max_coverage","injected":True})
        r=renewals[0]; pol=next(x for x in policies if x['policy_id']==r['policy_id']); pol['policy_status']='cancelled'
        r['renewal_status']='offered'
        ground_truth.append({"case_id":"ANOM-004","entity_type":"Renewal","entity_id":r['renewal_id'],"issue_type":"renewal_generated_for_cancelled_policy","ground_truth_label":"invalid","expected_rule":"Cancelled policies must not receive renewal offers","injected":True})
        if len(policies)>1:
            p1,p2=policies[1],policies[2]
            p2['applicant_id']=p1['applicant_id']; p2['asset_id']=p1['asset_id']; p2['effective_date']=p1['effective_date']+timedelta(days=10); p2['expiry_date']=p1['expiry_date']+timedelta(days=10); p2['permitted_overlap_reason']=None
            ground_truth.append({"case_id":"ANOM-005","entity_type":"Policy","entity_id":p2['policy_id'],"issue_type":"overlapping_policy_periods_without_permitted_reason","ground_truth_label":"invalid","expected_rule":"Same applicant and asset policy periods must not overlap unless permitted_overlap_reason is populated","injected":True})
    tables={"applicants":applicants,"insured_assets":assets,"products":PRODUCTS,"coverage_options":COVERAGES,"risk_factors":RISK_FACTORS,"quotes":quotes,"policies":policies,"endorsements":endorsements,"renewals":renewals,"underwriting_decisions":decisions}
    # Export each table to CSV and JSON.
    for name,rows in tables.items(): write_csv(out_dir/f'{name}.csv',rows); write_json(out_dir/f'{name}.json',rows)
    write_csv(out_dir/'ground_truth.csv',ground_truth); write_json(out_dir/'ground_truth.json',ground_truth)
    # SQL seed data (portable SQLite INSERTs) from the same generated records.
    sql_path=out_dir/'seed_data.sql'
    with sql_path.open('w',encoding='utf-8') as f:
        f.write('-- Synthetic insurance workflow seed data; generated deterministically.\nPRAGMA foreign_keys = ON;\n')
        for name,rows in tables.items():
            if not rows: continue
            cols=list(rows[0].keys()); f.write(f'-- Table: {name}\n')
            for row in rows:
                vals=[]
                for c in cols:
                    v=row[c]
                    if v is None: vals.append('NULL')
                    elif isinstance(v,bool): vals.append('1' if v else '0')
                    elif isinstance(v,(int,float)): vals.append(str(v))
                    else: vals.append("'"+str(iso(v)).replace("'","''")+"'")
                f.write(f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({', '.join(vals)});\n")
    # SQL schema: TEXT columns preserve portable CSV-like values; primary/foreign keys are enforced by SQLite.
    pk_cols={"applicants":"applicant_id","insured_assets":"asset_id","products":"product_id","coverage_options":"coverage_option_id","risk_factors":"risk_factor_id","quotes":"quote_id","policies":"policy_id","endorsements":"endorsement_id","renewals":"renewal_id","underwriting_decisions":"underwriting_decision_id"}
    fk_cols={"insured_assets":{"applicant_id":("applicants","applicant_id")},"coverage_options":{"product_id":("products","product_id")},"quotes":{"applicant_id":("applicants","applicant_id"),"asset_id":("insured_assets","asset_id"),"product_id":("products","product_id"),"coverage_option_id":("coverage_options","coverage_option_id")},"policies":{"quote_id":("quotes","quote_id"),"applicant_id":("applicants","applicant_id"),"asset_id":("insured_assets","asset_id"),"product_id":("products","product_id"),"coverage_option_id":("coverage_options","coverage_option_id")},"endorsements":{"policy_id":("policies","policy_id"),"asset_id":("insured_assets","asset_id")},"renewals":{"policy_id":("policies","policy_id")},"underwriting_decisions":{"quote_id":("quotes","quote_id")}}
    with (out_dir/'schema.sql').open('w',encoding='utf-8') as sf:
        sf.write('-- SQLite schema for generated synthetic insurance data. Load before seed_data.sql.\nPRAGMA foreign_keys = ON;\n')
        for name,rows in tables.items():
            if not rows: continue
            cols=list(rows[0].keys()); defs=[]
            for col in cols:
                part=f'\"{col}\" TEXT'
                if pk_cols.get(name)==col: part+=' PRIMARY KEY'
                if name in fk_cols and col in fk_cols[name]:
                    parent,parent_col=fk_cols[name][col]; part+=f' REFERENCES {parent}(\"{parent_col}\")'
                defs.append(part)
            sf.write(f'CREATE TABLE IF NOT EXISTS {name} (\n  '+',\n  '.join(defs)+'\n);\n')
    # Complete data dictionary: every exported entity field is described with type,
    # requiredness, allowed values, units, uniqueness, and a validation note.
    table_descriptions={
      "applicants":"Synthetic applicant master records; no real personal data.",
      "insured_assets":"Synthetic assets owned by applicants.",
      "products":"Three product lines and explicit synthetic underwriting thresholds.",
      "coverage_options":"Coverage choices attached to a product.",
      "risk_factors":"Documented premium and referral factors.",
      "quotes":"Quote submissions with references, risk inputs, eligibility and derived premium.",
      "policies":"Issued policy records linked to the source quote.",
      "endorsements":"Mid-term asset-change events preserving before/after values.",
      "renewals":"Renewal offers and customer decisions linked to policies.",
      "underwriting_decisions":"Recorded referral/decline decisions linked to quotes.",
    }
    primary_keys={"applicants":"applicant_id","insured_assets":"asset_id","products":"product_id","coverage_options":"coverage_option_id","risk_factors":"risk_factor_id","quotes":"quote_id","policies":"policy_id","endorsements":"endorsement_id","renewals":"renewal_id","underwriting_decisions":"underwriting_decision_id"}
    foreign_key_map={
      "insured_assets":{"applicant_id":"applicants.applicant_id"},
      "coverage_options":{"product_id":"products.product_id"},
      "quotes":{"applicant_id":"applicants.applicant_id","asset_id":"insured_assets.asset_id","product_id":"products.product_id","coverage_option_id":"coverage_options.coverage_option_id"},
      "policies":{"quote_id":"quotes.quote_id","applicant_id":"applicants.applicant_id","asset_id":"insured_assets.asset_id","product_id":"products.product_id","coverage_option_id":"coverage_options.coverage_option_id"},
      "endorsements":{"policy_id":"policies.policy_id","asset_id":"insured_assets.asset_id"},
      "renewals":{"policy_id":"policies.policy_id"},
      "underwriting_decisions":{"quote_id":"quotes.quote_id"},
    }
    allowed_values={
      "applicant_type":["individual","small_business"],"region":["north","south","east","west","central"],
      "consent_status":["synthetic_not_applicable"],"asset_type":["vehicle","property","business_premises"],
      "asset_status":["active"],"product_line":["motor","property","business"],
      "factor_type":["multiplier","referral"],"eligibility_status":["eligible","ineligible"],
      "quote_status":["offered","referred","declined"],"policy_status":["active","cancelled"],
      "acceptance_status":["accepted","pending"],"payment_status":["paid","pending","unpaid"],
      "endorsement_type":["asset_change"],"endorsement_status":["approved"],
      "renewal_status":["offered","accepted","declined"],"decision":["refer","decline"],
      "authority_level":["senior_underwriter","automated_rules"],"risk_data_missing":[True,False],"active":[True,False],
    }
    entity_dictionary={}
    for name, rows in tables.items():
        sample=rows[0] if rows else {}
        field_specs={}
        for field, value in sample.items():
            if isinstance(value, bool): typ="boolean"
            elif isinstance(value, int): typ="integer"
            elif isinstance(value, float): typ="decimal"
            elif isinstance(value, date): typ="date (ISO 8601)"
            elif value is None:
                typ="nullable numeric/string; see source field rules"
            else: typ="string"
            all_non_null=all(row.get(field) is not None and row.get(field) != "" for row in rows)
            unit="currency units" if any(token in field for token in ("premium","coverage","deductible","asset_value","base_rate")) and field != "base_rate" else ("rate multiplier" if field == "base_rate" or field == "factor_value" else None)
            validation="Must be populated and conform to the declared type."
            if field == primary_keys[name]: validation="Unique, immutable deterministic primary key; zero-padded IDs where applicable."
            elif field in foreign_key_map.get(name, {}): validation=f"Must match an existing {foreign_key_map[name][field]} value."
            elif field in allowed_values: validation="Must be one of the documented allowed values."
            elif field.endswith("_date") or field.endswith("_period") or field in {"effective_date","expiry_date","offer_date","submission_date","issue_date","proposed_effective_date","proposed_expiry_date","decision_date"}: validation="ISO date; chronology checked against related lifecycle dates."
            elif field in {"calculated_premium","risk_score"}: validation="Nullable only when required risk data is missing; otherwise derived/bounded by documented business rules."
            field_specs[field]={"type":typ,"required":bool(all_non_null),"allowed_values":allowed_values.get(field),"units":unit,"unique":field==primary_keys[name],"validation":validation}
        entity_dictionary[name]={"description":table_descriptions[name],"primary_key":primary_keys[name],"foreign_keys":foreign_key_map.get(name,{}),"fields":field_specs}
    dictionary={"core_entity_count":10,"entities":entity_dictionary,"relationships":{
      "Applicant 1:N InsuredAsset":"one applicant may own multiple insured assets; generated data currently assigns one asset per applicant",
      "Applicant 1:N Quote":"one applicant may submit multiple quotes",
      "InsuredAsset 1:N Quote":"one asset may appear in multiple quotes",
      "Product 1:N CoverageOption":"each coverage option belongs to one product",
      "Quote 1:0..1 Policy":"a quote may result in at most one policy",
      "Policy 1:N Endorsement":"a policy may have multiple mid-term change events",
      "Policy 1:N Renewal":"a policy may have renewal records over time",
      "Quote 1:N UnderwritingDecision":"a quote may have multiple recorded decisions",
      "ground_truth":"separate labels file, not a core entity or model input feature"
    }}
    (out_dir/'data_dictionary.json').write_text(json.dumps(dictionary,indent=2)+'\n',encoding='utf-8')
    (out_dir/'README.md').write_text(f'''# Insurance Underwriting & Renewal Workflow\n\n## Purpose\nReproducible synthetic dataset for evaluating insurance submissions and renewals against eligibility, risk factors, coverage limits, and approval rules. No real customer data or external datasets are used.\n\n## Run\n```bash\npython -m insurance_workflow.generator --output data --seed {seed} --scale 1\npython -m insurance_workflow.validator --data data\n```\nRun commands from the project root. Python 3.10+; standard library only.\n\n## Default volumes\n- Applicants: {n_app:,}\n- Quotes: {n_quote:,}\n- Policies: {n_policy:,}\n- Renewals: {len(renewals):,}\n- Product lines: motor, property, business\n\n## Rules and assumptions\nPremium = max(50, coverage limit × product base rate × (1 + 0.08 × prior claims + 0.35 if risk score ≥ 70 + 0.12 if applicant age < 25)). Missing risk data triggers referral and leaves calculated premium null. Eligibility uses product minimum age, maximum asset value and risk-score thresholds. A policy may be issued only after acceptance and payment. Coverage and endorsement limits are product-specific. Rates and thresholds are transparent synthetic assumptions, not real insurer pricing.\n\n## Output files\nEach entity is exported as CSV and JSON; `seed_data.sql` contains INSERT statements; `data_dictionary.json` documents the model; `ground_truth.csv/json` contains injected anomalies and expected labels; `validation_summary.json` and `source_manifest.json` report validation and file hashes. Lifecycle states and decisions are recorded in the required policy, endorsement, renewal, and underwriting-decision tables.\n\n## Anomaly handling\nFive required negative scenarios are deliberately injected and listed separately in ground truth. They are expected validation failures, not accidental corruption. Do not join ground-truth labels into model input features.\n\n## Reproducibility\nUse the same seed and scale to regenerate identical logical records. Compare SHA-256 hashes from `source_manifest.json`. The manifest excludes itself to avoid self-referential hashing.\n''',encoding='utf-8')
    manifest={"generator":"insurance_workflow.generator","seed":seed,"scale":scale,"generated_on":"fixed-by-seed-no-wall-clock","synthetic_only":True,"external_sources":[],"files":[]}
    for fp in sorted(out_dir.iterdir()):
        if fp.is_file() and fp.name not in {'source_manifest.json','validation_summary.json'}:
            manifest['files'].append({"path":fp.name,"sha256":sha256(fp),"bytes":fp.stat().st_size})
    (out_dir/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return tables, ground_truth

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--output',default='data'); ap.add_argument('--seed',type=int,default=SEED_DEFAULT); ap.add_argument('--scale',type=int,default=1); ap.add_argument('--no-anomalies',action='store_true'); args=ap.parse_args()
    if args.scale<1: ap.error('--scale must be >= 1')
    generate(Path(args.output),args.seed,args.scale,not args.no_anomalies)
    print(f'Generated synthetic insurance dataset in {args.output} (seed={args.seed}, scale={args.scale}).')
if __name__=='__main__': main()
