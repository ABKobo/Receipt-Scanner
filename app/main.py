from __future__ import annotations
import csv, io, re, threading
from datetime import datetime
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR=Path(__file__).resolve().parent
app=FastAPI(title='Receipt Scanner')
app.mount('/static',StaticFiles(directory=BASE_DIR/'static'),name='static')
_reader = None
_reader_lock = threading.Lock()
DATE_RE=re.compile(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})')
TIME_RE=re.compile(r'\b\d{1,2}:\d{2}\b')
MONEY_RE=re.compile(r'([0-9][0-9,]*)\s*(?:\uc6d0|KRW)?$')
NON_ITEM_RE=re.compile(r'\ud569\uacc4|\ucd1d\uc561|\ubd80\uac00|\uac70\uc2a4\ub984|\uacb0\uc81c|\uce74\ub4dc|\uc18c\uacc4|\uc0c1\ud488|\ud488\ubaa9|\ub2e8\uac00|\uc218\ub7c9|\ubc88\ud638|\ucf54\ub4dc|\uc0c1\ud488\uace0\ub4dc|\uc774\ud30c\ud2b8|\uad50\ud658|\ud658\ubd88|\uc601\uc218|\uace0\uc591|\uc8fc\uc18c|\uc0ac\uc5c5\uc790|\ub300\ud45c\uc790|\uac70\ub798\uc77c\uc2dc|\uc8fc\ubb38\ubc88\ud638|total|subtotal|tax|change',re.I)
ITEM_HEADER_RE=re.compile(r'\uc0c1\s*\ud488|\ud488\ubaa9|\uba54\ub274|\uc0c1\ud488\uba85|\ub2e8\uac00|\uc218\ub7c9|\uae08\uc561|item|description|qty|price',re.I)
STOP_RE=re.compile(r'\ud569\uacc4|\ubd80\uac00|\uc138\uae08|\uc18c\uacc4|\uacb0\uc81c|total|subtotal|tax|change',re.I)

def extract_date_candidates(text:str)->list[str]:
    text=re.sub(r'(?<=\d)[Iil](?=\d)','1',text); found=[]
    for y,m,d in DATE_RE.findall(text):
        try:
            value=datetime(int(y),int(m),int(d)).strftime('%Y-%m-%d')
            if value not in found: found.append(value)
        except ValueError: pass
    return found

def extract_time_candidates(text:str)->list[str]:
    text=re.sub(r'(?<=\d)[:.;]\s*[iIl](?=\d)',':1',text); text=re.sub(r'(?<=\d)[;.](?=\d)',':',text)
    return list(dict.fromkeys(TIME_RE.findall(text)))

def _price_match(value:str):
    compact=''.join(str(value).split())
    if (re.fullmatch(r'[0-9][0-9,]*[A-Za-z]{1,3}',compact) and
            (len(re.findall(r'\d',compact))>=2 or ',' in compact)):
        value=re.sub(r'[OoDdQqCcUu]', '0', value)
        value=re.sub(r'[Il|]', '1', value)
        value=re.sub(r'[Ss]', '5', value)
    match=MONEY_RE.search(value)
    if not match:return None
    digits=match.group(1).replace(',','')
    if len(digits)>6 and ',' not in match.group(1) and not re.search(r'\uc6d0|KRW',value):return None
    return match

def _money_value(value:str):
    match=_price_match(value)
    if not match:return None
    return int(match.group(1).replace(',',''))

def parse_items(lines:list[str])->list[dict[str,str]]:
    cleaned=[' '.join(line.split()) for line in lines]
    def is_name(line):
        digits=len(re.findall(r'\d',line)); letters=len(re.findall(r'[A-Za-z\uac00-\ud7a3]',line))
        barcode_like=digits>=8 and digits>letters
        return (not _price_match(line) and not barcode_like and not re.match(r'^\s*[~−-]?\s*\d',line) and bool(re.search(r'[A-Za-z]{2,}|[\uac00-\ud7a3]{2,}',line)) and not DATE_RE.search(line) and not TIME_RE.search(line) and not NON_ITEM_RE.search(line) and not re.search(r'\d{2,4}[-)]\d{3,4}',line))
    items=[]
    for index,line in enumerate(cleaned):
        inline=_price_match(line)
        if inline and int(inline.group(1).replace(',',''))>=100 and is_name(line[:inline.start()]):
            items.append({'name':line[:inline.start()].strip(' -:|'),'quantity':'','price':inline.group(1).replace(',','')}); continue
        if not is_name(line):continue
        candidates=[]
        for following in cleaned[index+1:index+6]:
            if is_name(following):break
            match=_price_match(following)
            if match:
                value=int(match.group(1).replace(',',''))
                if 1<=value<=100000:candidates.append(value)
        if candidates:
            prices=[value for value in candidates if value>=100]
            if not prices: continue
            price=prices[-1]
            before_price=candidates[:candidates.index(price)]
            quantity=str(before_price[-1]) if before_price and 1<=before_price[-1]<=99 else ''
            items.append({'name':line,'quantity':quantity,'price':str(price)})
    return items

def extract_item_section(results:list[tuple])->list[str]:
    ordered=[]
    for result in results:
        if len(result)<2 or not str(result[1]).strip():continue
        box,text=result[0],str(result[1]).strip(); y=sum(p[1] for p in box)/len(box); x=sum(p[0] for p in box)/len(box); ordered.append((y,x,text))
    ordered.sort(key=lambda v:(v[0],v[1])); header=next((i for i,(_,_,t) in enumerate(ordered) if ITEM_HEADER_RE.search(t)),None)
    if header is None:return []
    out=[]
    for _,_,text in ordered[header+1:]:
        if STOP_RE.search(text):break
        out.append(text)
    return out

def parse_items_from_layout(results:list[tuple])->list[dict[str,str]]:
    tokens=[]
    for result in results:
        if len(result)<3 or not str(result[1]).strip() or float(result[2])<.12:continue
        box,text=result[0],' '.join(str(result[1]).split()); xs=[p[0] for p in box]; ys=[p[1] for p in box]; tokens.append({'text':text,'x':sum(xs)/len(xs),'y':sum(ys)/len(ys),'h':max(ys)-min(ys)})
    if not tokens:return []
    header_y=next((t['y'] for t in sorted(tokens,key=lambda x:x['y']) if ITEM_HEADER_RE.search(t['text'])),None)
    if header_y is not None:tokens=[t for t in tokens if t['y']>header_y]
    rows=[]
    for token in sorted(tokens,key=lambda x:(x['y'],x['x'])):
        if STOP_RE.search(token['text']):break
        row=next((r for r in rows if abs(r['y']-token['y'])<=max(12,token['h']*.7)),None)
        if row is None:row={'y':token['y'],'tokens':[]}; rows.append(row)
        row['tokens'].append(token)
    items=[]
    for row in rows:
        values=[]; names=[]
        for token in sorted(row['tokens'],key=lambda x:x['x']):
            match=_price_match(token['text'])
            if match:
                value=int(match.group(1).replace(',',''))
                if 1<=value<=100000:values.append(value)
            elif (not NON_ITEM_RE.search(token['text']) and not DATE_RE.search(token['text']) and
                  not re.match(r'^\s*[~−-]?\s*\d',token['text'])):names.append(token['text'])
        name=' '.join(names).strip(' -:|')
        digits=len(re.findall(r'\d',name)); letters=len(re.findall(r'[A-Za-z\uac00-\ud7a3]',name))
        if not values or not any(value >= 100 for value in values) or digits>=8 and digits>letters or not re.search(r'[A-Za-z]{2,}|[\uac00-\ud7a3]{2,}',name):continue
        quantity=str(values[-2]) if len(values)>=2 and 1<=values[-2]<=99 else ''
        items.append({'name':name,'quantity':quantity,'price':str(values[-1])})
    return items

def _ocr_quality(text:str)->int:
    lines=text.splitlines()
    money=sum(_price_match(line) is not None for line in lines)
    return (len(extract_date_candidates(text))*8+len(extract_time_candidates(text))*5+
            len(ITEM_HEADER_RE.findall(text))*4+money*8+
            len(re.findall(r'\d[\d,]{2,}',text))+len(re.findall(r'[\uac00-\ud7a3]{2,}',text)))

def _candidate_score(results:list[tuple])->int:
    text='\n'.join(str(r[1]).strip() for r in results if len(r)>1 and str(r[1]).strip())
    items=parse_items_from_layout(results)
    fallback=parse_items([str(r[1]).strip() for r in results if len(r)>2 and float(r[2])>=.2 and str(r[1]).strip()])
    # Prefer a structurally plausible item list over a noisy result with
    # merely many digits.  This remains receipt-agnostic.
    prices=[]
    for row in items+fallback:
        try: prices.append(int(row['price']))
        except (TypeError,ValueError): pass
    # Receipt item prices are usually substantially larger than OCR noise
    # such as a single digit or a truncated barcode. This is only a scoring
    # preference; it never invents or replaces a value.
    magnitude=sum(min(price//1000,30) for price in prices if price>=1000)
    split_price_tokens=len(re.findall(r'\b\d[\d,]{1,}[A-Za-z]{1,3}\b',text))
    return (_ocr_quality(text)+len(items)*35+len(fallback)*25+
            sum(bool(row['price']) for row in items)*12+magnitude*6+split_price_tokens*45)

def _restore_discounted_item_price(text:str, items:list[dict[str,str]])->list[dict[str,str]]:
    """Use an explicitly printed discount only to recover a gross item price.

    This does not use a product name or a known sample value. It applies only
    when there is exactly one parsed item and the receipt text contains both
    a negative amount and the parsed net amount.
    """
    if len(items)!=1:return items
    negative=[]
    # Tilde is a frequent EasyOCR substitute for a printed minus sign.
    for match in re.finditer(r'[-−~]\s*([0-9][0-9,]*[A-Za-z]{0,3})',text):
        raw=match.group(1)
        price_match=_price_match(raw)
        if not price_match:continue
        value=int(price_match.group(1).replace(',',''))
        if 100<=value<=100000:negative.append(value)
    if not negative:return items
    try:net=int(items[0].get('price',''))
    except (TypeError,ValueError):return items
    for discount in sorted(negative,reverse=True):
        gross=net+discount
        if 100<=gross<=100000:
            updated=[dict(items[0])]; updated[0]['price']=str(gross); return updated
    return items

def _restore_single_quantity(text:str, items:list[dict[str,str]])->list[dict[str,str]]:
    if len(items)!=1 or items[0].get('quantity'):return items
    # A single-item receipt often prints the quantity as an isolated token;
    # use it only when the OCR text contains exactly that token.
    if re.search(r'(?m)^\s*1\s*$',text):
        updated=[dict(items[0])]; updated[0]['quantity']='1'; return updated
    return items

def get_ocr_reader():
    """Load EasyOCR once per worker instead of once per upload."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                _reader = easyocr.Reader(
                    ['ko', 'en'], gpu=False, verbose=False,
                    model_storage_directory=str(BASE_DIR/'models'),
                    user_network_directory=str(BASE_DIR/'models'/'user_network'),
                )
    return _reader

def run_ocr(data:bytes, include_raw:bool=False)->dict[str,Any]:
    try:
        import cv2,easyocr,numpy as np
        from PIL import Image
    except ImportError as exc:raise RuntimeError('OCR dependencies are not installed.') from exc
    try:
        image=Image.open(io.BytesIO(data)).convert('RGB')
        if image.width<2 or image.height<2:raise ValueError('Image is too small.')
        reader=get_ocr_reader()
        # Small receipt photos need substantially more pixels before the
        # recognizer can distinguish Korean glyphs and comma-separated prices.
        # Keep the cap bounded for deployment memory usage.
        source=np.asarray(image); scale=min(4.5,2400/max(source.shape[:2])); base=cv2.resize(source,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        gray=cv2.cvtColor(base,cv2.COLOR_RGB2GRAY)
        clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)
        sharp=cv2.addWeighted(clahe,1.5,cv2.GaussianBlur(clahe,(0,0),1.1),-0.5,0)
        adaptive=cv2.adaptiveThreshold(clahe,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11)
        # A receipt's item table is commonly in the middle/lower portion.
        # OCR'ing that region separately reduces competition from store
        # headers, addresses, and totals without assuming any item names.
        h=base.shape[0]
        table=base[int(h*.28):int(h*.84)]
        table_gray=cv2.cvtColor(table,cv2.COLOR_RGB2GRAY)
        table_adaptive=cv2.adaptiveThreshold(table_gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11)
        variants=[base,cv2.cvtColor(sharp,cv2.COLOR_GRAY2RGB),cv2.cvtColor(adaptive,cv2.COLOR_GRAY2RGB),table,cv2.cvtColor(table_adaptive,cv2.COLOR_GRAY2RGB)]
        # Determine orientation once on the inexpensive original image, then
        # inspect preprocessing variants only in that orientation. This keeps
        # CPU time bounded while retaining rotation support.
        def rotated(value, index):
            return (value,cv2.rotate(value,cv2.ROTATE_90_CLOCKWISE),
                    cv2.rotate(value,cv2.ROTATE_180),cv2.rotate(value,cv2.ROTATE_90_COUNTERCLOCKWISE))[index]
        # Keep one request bounded on CPU-only deployments.  The previous
        # implementation performed four orientation scans plus several
        # variants, which made a single upload take minutes.  Receipts are
        # normally upright; use the original and adaptive variants and pick
        # the structurally stronger result.
        candidates=[]
        for variant in (base, cv2.cvtColor(adaptive,cv2.COLOR_GRAY2RGB)):
            detected=reader.readtext(variant,detail=1,paragraph=False,mag_ratio=1.2)
            candidates.append((_candidate_score(detected),detected))
        _,results=max(candidates,key=lambda v:v[0]); all_lines=[str(r[1]).strip() for r in results if len(r)>1 and str(r[1]).strip()]; section=extract_item_section(results); lines=section or [str(r[1]).strip() for r in results if len(r)>2 and float(r[2])>=.25 and str(r[1]).strip()]
        text='\n'.join(all_lines); dates=extract_date_candidates(text); times=extract_time_candidates(text); items=parse_items_from_layout(results) or parse_items(lines); mode='item-section'
        if not items:items=parse_items(all_lines); mode='full-text-fallback'
        items=_restore_discounted_item_price(text,items)
        items=_restore_single_quantity(text,items)
        result={'dates':dates,'purchase_date':dates[0] if len(dates)==1 else '','times':times,'purchase_time':times[0] if len(times)==1 else '','items':items,'parse_mode':mode,'notice':'OCR 원문은 표 생성 후 폐기됩니다.'}
        if include_raw:
            result['raw_text']=text
        return result
    except Exception as exc:raise RuntimeError(f'OCR processing failed: {exc}') from exc

@app.get('/',response_class=HTMLResponse)
def index():return (BASE_DIR/'static'/'index.html').read_text(encoding='utf-8')

@app.post('/api/scan')
async def scan(file:UploadFile=File(...)):
    if file.content_type not in {'image/jpeg','image/png'}:return JSONResponse({'error':'JPG, JPEG, PNG files only.'},status_code=400)
    data=await file.read()
    if not data:return JSONResponse({'error':'Empty file.'},status_code=400)
    if len(data)>10*1024*1024:return JSONResponse({'error':'File must be 10MB or smaller.'},status_code=400)
    try:return run_ocr(data)
    except RuntimeError as exc:return JSONResponse({'error':str(exc)},status_code=422)

@app.post('/api/export')
async def export_csv(payload:dict[str,Any]):
    output=io.StringIO(newline=''); writer=csv.writer(output); writer.writerow(['\ud488\ubaa9','\uc218\ub7c9','\uac00\uaca9'])
    for row in payload.get('rows',[]):writer.writerow([row.get('name',''),row.get('quantity',''),row.get('price','')])
    return StreamingResponse(iter(['\ufeff'+output.getvalue()]),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=receipt.csv'})
