"""KB Regenerate Phase 3 — Compliance matrix deep analysis.

Cross-references matrix.json (source of truth) against backend
compliance_matrix.py and frontend matrix-data.ts to detect drift.
Used by /kb-regenerate command.
"""
import json, re, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MATRIX_PATH = os.path.join(ROOT, 'eagle-plugin/data/matrix.json')
BACKEND_PATH = os.path.join(ROOT, 'server/app/compliance_matrix.py')
FRONTEND_PATH = os.path.join(ROOT, 'client/components/contract-matrix/matrix-data.ts')

issues = []
warnings = []

# --- Layer A: matrix.json internal consistency ---

with open(MATRIX_PATH, 'r') as f:
    matrix = json.load(f)

print('=== Layer A: matrix.json Internal Consistency ===')

# A1: Thresholds strictly ascending
thresholds = matrix['thresholds']
values = [t['value'] for t in thresholds]
for i in range(1, len(values)):
    if values[i] <= values[i-1]:
        issues.append(f'Thresholds not ascending: {values[i-1]} >= {values[i]}')
if values == sorted(values) and len(values) == len(set(values)):
    print(f'  A1 Thresholds ascending: PASS ({len(thresholds)} tiers)')
else:
    print(f'  A1 Thresholds ascending: FAIL')

# A2: All triggers non-empty
empty_triggers = [t['label'] for t in thresholds if not t.get('triggers')]
if empty_triggers:
    issues.append(f'Empty triggers: {empty_triggers}')
    print(f'  A2 Triggers non-empty: FAIL ({empty_triggers})')
else:
    print(f'  A2 Triggers non-empty: PASS')

# A3: above_threshold values match threshold values
threshold_values = set(values)
threshold_values.add(0)
doc_rules = matrix['doc_rules']
above_vals = [r['above'] for r in doc_rules.get('above_threshold', [])]
bad_above = [v for v in above_vals if v not in threshold_values]
if bad_above:
    issues.append(f'above_threshold references unknown values: {bad_above}')
    print(f'  A3 above_threshold refs: FAIL ({bad_above})')
else:
    print(f'  A3 above_threshold refs: PASS')

# A4: by_method keys
by_method_keys = set(doc_rules.get('by_method', {}).keys())
print(f'  A4 by_method keys: {sorted(by_method_keys)}')

# A5: by_type keys
by_type_keys = set(doc_rules.get('by_type', {}).keys())
ct_ids = {ct['id'] for ct in matrix.get('contract_types', [])}
bad_type_keys = by_type_keys - ct_ids
if bad_type_keys:
    issues.append(f'by_type references unknown types: {bad_type_keys}')
    print(f'  A5 by_type keys: FAIL (unknown: {bad_type_keys})')
else:
    print(f'  A5 by_type keys: PASS ({sorted(by_type_keys)})')

# A6: special_factors keys
sf_keys = set(doc_rules.get('special_factors', {}).keys())
known_flags = {'isIT', 'isSB', 'isRD', 'isHS', 'isAnimalWelfare', 'isForeign', 'isConference', 'isServices'}
unknown_flags = sf_keys - known_flags
if unknown_flags:
    warnings.append(f'Unknown special_factors flags: {unknown_flags}')
    print(f'  A6 special_factors: WARN (unknown: {unknown_flags})')
else:
    print(f'  A6 special_factors: PASS ({len(sf_keys)} flags)')

# A7: approval_chains
chains = matrix.get('approval_chains', {})
has_ja = 'ja' in chains
has_ap = 'ap' in chains
if has_ja and has_ap:
    print(f'  A7 approval_chains: PASS (ja: {len(chains["ja"])} tiers, ap: {len(chains["ap"])} tiers)')
else:
    issues.append(f'Missing approval chains: ja={has_ja}, ap={has_ap}')
    print(f'  A7 approval_chains: FAIL')

# --- Layer B: Backend compliance_matrix.py ---
print()
print('=== Layer B: Backend compliance_matrix.py ===')

with open(BACKEND_PATH, 'r') as f:
    backend_src = f.read()

# B1: Extract _threshold() calls
threshold_calls = re.findall(r'_threshold\("([^"]+)"\)', backend_src)
all_triggers = set()
for t in thresholds:
    all_triggers.update(t.get('triggers', []))

bad_triggers = [tc for tc in threshold_calls if tc not in all_triggers]
if bad_triggers:
    issues.append(f'Backend _threshold() calls with unknown triggers: {bad_triggers}')
    print(f'  B1 _threshold() triggers: FAIL ({bad_triggers})')
else:
    print(f'  B1 _threshold() triggers: PASS ({len(threshold_calls)} calls, all resolve)')

# B2: Backend METHODS
methods_start = backend_src.find('METHODS = [')
types_start = backend_src.find('TYPES = [')
methods_section_be = backend_src[methods_start:types_start]
backend_method_ids = re.findall(r'"id":\s*"([^"]+)"', methods_section_be)
print(f'  B2 Backend METHODS: {len(backend_method_ids)} methods: {backend_method_ids}')

# B3: Backend TYPES
types_end = backend_src.find(']', types_start)
types_section_be = backend_src[types_start:types_end + 1]
backend_type_ids = re.findall(r'"id":\s*"([^"]+)"', types_section_be)
matrix_ct_ids = [ct['id'] for ct in matrix.get('contract_types', [])]
missing_in_backend = set(matrix_ct_ids) - set(backend_type_ids)
extra_in_backend = set(backend_type_ids) - set(matrix_ct_ids)
if missing_in_backend:
    warnings.append(f'Types in matrix.json but not in backend TYPES: {missing_in_backend}')
    print(f'  B3 Backend TYPES: WARN (missing from backend: {missing_in_backend})')
if extra_in_backend:
    warnings.append(f'Types in backend but not in matrix.json: {extra_in_backend}')
    print(f'  B3 Backend TYPES extra: WARN ({extra_in_backend})')
if not missing_in_backend and not extra_in_backend:
    print(f'  B3 Backend TYPES: PASS ({len(backend_type_ids)} types)')

# B4: Derived constants
print(f'  B4 Derived constants:')
trigger_to_value = {}
for t in thresholds:
    for tr in t.get('triggers', []):
        trigger_to_value[tr] = t['value']

constant_map = {
    '_MPT': 'micro_purchase_threshold',
    '_SAT': 'simplified_acquisition_threshold',
    '_SYNOPSIS': 'sam_gov_synopsis_required',
    '_SUBK': 'subcontracting_plan_required',
    '_JA_HCA': 'ja_hca_approval_required',
    '_TINA': 'certified_cost_pricing_data_required',
    '_CONGRESS': '8a_sole_source_services_ceiling',
    '_IDIQ_ENH': 'idiq_enhanced_competition',
    '_AP_OA': 'written_acquisition_plan_required',
    '_HCA': 'hca_approval_required',
    '_SPE_JA': 'spe_ja_approval_required',
    '_OAP': 'oap_approval_required',
}
for const_name, trigger in constant_map.items():
    expected = trigger_to_value.get(trigger, '???')
    print(f'     {const_name:<12} = ${expected:>12,}  (trigger: {trigger})')

# --- Layer C: Frontend matrix-data.ts sync ---
print()
print('=== Layer C: Frontend matrix-data.ts Sync ===')

with open(FRONTEND_PATH, 'r') as f:
    frontend_src = f.read()

# C1: Frontend METHODS
types_start_fe = frontend_src.find('export const TYPES')
methods_section_fe = frontend_src[:types_start_fe] if types_start_fe > 0 else frontend_src[:2000]
fe_method_ids = re.findall(r"id:\s*'([^']+)'", methods_section_fe)

be_method_set = set(backend_method_ids)
fe_method_set = set(fe_method_ids)
method_diff = be_method_set.symmetric_difference(fe_method_set)
if method_diff:
    issues.append(f'METHODS mismatch: only-backend={be_method_set - fe_method_set}, only-frontend={fe_method_set - be_method_set}')
    print(f'  C1 METHODS sync: FAIL (diff: {method_diff})')
else:
    print(f'  C1 METHODS sync: PASS ({len(fe_method_ids)} methods match)')

# C2: Frontend TYPES
thresholds_start_fe = frontend_src.find('export const THRESHOLDS')
types_section_fe = frontend_src[types_start_fe:thresholds_start_fe] if types_start_fe > 0 and thresholds_start_fe > 0 else ''
fe_type_ids = re.findall(r"id:\s*'([^']+)'", types_section_fe)
be_type_set = set(backend_type_ids)
fe_type_set = set(fe_type_ids)
type_diff = be_type_set.symmetric_difference(fe_type_set)
if type_diff:
    warnings.append(f'TYPES mismatch: only-backend={be_type_set - fe_type_set}, only-frontend={fe_type_set - be_type_set}')
    print(f'  C2 TYPES sync: WARN (diff: {type_diff})')
else:
    print(f'  C2 TYPES sync: PASS ({len(fe_type_ids)} types match)')

# C3: Frontend THRESHOLDS vs matrix.json
fe_thresholds = re.findall(r"value:\s*(\d+)\s*,\s*label:\s*['\"]([^'\"]+)['\"]", frontend_src)
fe_thresh_map = {int(v): label for v, label in fe_thresholds}
matrix_thresh_map = {t['value']: t['label'] for t in thresholds}

print(f'  C3 THRESHOLDS comparison:')
all_values = sorted(set(list(fe_thresh_map.keys()) + list(matrix_thresh_map.keys())))

drift_count = 0
for val in all_values:
    in_matrix = val in matrix_thresh_map
    in_fe = val in fe_thresh_map
    m_label = matrix_thresh_map.get(val, '---')
    f_label = fe_thresh_map.get(val, '---')

    if in_matrix and in_fe:
        if m_label == f_label:
            print(f'     ${val:>12,}  {m_label:<20}  MATCH')
        else:
            drift_count += 1
            issues.append(f'Threshold label drift at ${val:,}: matrix="{m_label}" vs frontend="{f_label}"')
            print(f'     ${val:>12,}  matrix={m_label:<20}  frontend={f_label:<20}  LABEL DRIFT')
    elif in_matrix and not in_fe:
        drift_count += 1
        warnings.append(f'Threshold ${val:,} ({m_label}) in matrix.json but NOT in frontend')
        print(f'     ${val:>12,}  {m_label:<20}  MISSING FROM FRONTEND')
    else:
        drift_count += 1
        issues.append(f'Threshold ${val:,} ({f_label}) in frontend but NOT in matrix.json')
        print(f'     ${val:>12,}  {"---":<20}  {f_label:<20}  EXTRA IN FRONTEND')

if drift_count == 0:
    print(f'  C3 THRESHOLDS: PASS')
else:
    print(f'  C3 THRESHOLDS: {"FAIL" if issues else "WARN"} ({drift_count} discrepancies)')

# --- Summary ---
print()
print('=' * 60)
print(f'Matrix Analysis Summary')
print(f'  Issues (must fix): {len(issues)}')
for i, issue in enumerate(issues, 1):
    print(f'    {i}. {issue}')
print(f'  Warnings (review): {len(warnings)}')
for i, w in enumerate(warnings, 1):
    print(f'    {i}. {w}')

verdict = 'FAIL' if issues else ('WARN' if warnings else 'PASS')
print(f'  Verdict: {verdict}')
