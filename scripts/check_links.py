from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
for p in root.rglob('*.md'):
 text=p.read_text(errors='ignore')
 for target in re.findall(r'\[[^]]+\]\(([^)]+)\)',text):
  if target.startswith('http') and not target.startswith(('https://argolink.io',)): raise SystemExit(f'external destination in {p}: {target}')
print('link policy passed')
