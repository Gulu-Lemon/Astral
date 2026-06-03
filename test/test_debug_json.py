"""Debug _extract_json truncation."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import LLMClient

# Directly replicate the logic to diagnose
raw = '{"options": [{"label": "test", "type": "dialogue"}, {"label": "cut off'

import re
full = raw
first = full.find('{')
if first != -1:
    full = full[first:]

brace_diff = full.count('{') - full.count('}')
bracket_diff = full.count('[') - full.count(']')
print(f"opens={{ count={full.count('{')} closes=}} count={full.count('}')} diff={brace_diff}")
print(f"opens=[ count={full.count('[')} closes=] count={full.count(']')} diff={bracket_diff}")

in_string = False
escaped = False
for ch in full:
    if escaped: escaped = False; continue
    if ch == '\\': escaped = True; continue
    if ch == '"': in_string = not in_string
print(f"in_string at end: {in_string}")

fixed = full
if in_string:
    fixed += '"'
fixed += ']' * bracket_diff
fixed += '}' * brace_diff
print(f"Fixed JSON: {repr(fixed)}")

try:
    result = json.loads(fixed)
    print(f"SUCCESS: {result}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
