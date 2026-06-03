"""Test _extract_json truncation repair."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import LLMClient
extract = LLMClient._extract_json

# Test 1: truncated array of objects
t1 = '{"options": [{"label": "test", "type": "dialogue"}, {"label": "cut off'
print(f"Input: {repr(t1)}")
try:
    r1 = extract(t1)
    print(f"Result: {r1}")
except ValueError as e:
    print(f"ValueError: {e}")

# Test 2: valid JSON still works
t2 = '{"options": [{"label": "test"}]}'
r2 = extract(t2)
assert 'options' in r2
print("Test 2 (valid JSON): OK")

# Test 3: actual error case from the bug report
t3 = '''{
  "options": [
    {"label": "test1", "type": "dialogue", "target": "No.06"},
    {"label": "测试测试'''
r3 = extract(t3)
assert 'options' in r3, f"Failed: {r3}"
print(f"Test 3 (real error case): OK ({len(r3['options'])} entries)")

# Test 4: empty options array truncated
t4 = '{"options": ['
r4 = extract(t4)
assert 'options' in r4
print(f"Test 4 (empty array): OK")

# Test 5: unterminated string
t5 = '{"options": [{"label": "test", "desc": "unfinished'
r5 = extract(t5)
assert 'options' in r5
print(f"Test 5 (unterminated string): OK")

print("\nAll JSON fix tests passed!")
