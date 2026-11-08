import json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import run_ocr

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('mlops-data/evaluation')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('mlops-logs/evaluation.jsonl')

def norm(value):
    return re.sub(r'[^a-z0-9]+', '', value.lower())

def cer(reference, predicted):
    a, b = norm(reference), norm(predicted)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)

def truth_from_box(path):
    parts=[]
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        fields=line.split(',', 8)
        if len(fields)==9:
            parts.append(fields[8].strip())
    return '\n'.join(parts)

def truth_from_entities(path):
    return json.loads(path.read_text(encoding='utf-8'))

OUT.parent.mkdir(parents=True, exist_ok=True)
rows=[]
for image in sorted((ROOT/'images').glob('*.jpg')):
    started=time.time()
    result=run_ocr(image.read_bytes(), include_raw=True)
    elapsed=round((time.time()-started)*1000)
    entity=truth_from_entities(ROOT/'entities'/f'{image.stem}.txt')
    reference=truth_from_box(ROOT/'box'/f'{image.stem}.txt')
    predicted=result.pop('raw_text','')
    row={'image':image.name,'elapsed_ms':elapsed,'cer':cer(reference,predicted),
         'date_exact':norm(entity.get('date','')) in norm(' '.join(result.get('dates',[]))),
         'total_reference':entity.get('total',''),'items_evaluated':False,
         'result':result}
    rows.append(row)
    with OUT.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
print(json.dumps({'count':len(rows),'mean_cer':sum(x['cer'] for x in rows)/len(rows) if rows else None,
                  'date_accuracy':sum(x['date_exact'] for x in rows)/len(rows) if rows else None},ensure_ascii=False))
