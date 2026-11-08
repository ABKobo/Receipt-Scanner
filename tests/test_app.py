from fastapi.testclient import TestClient
from app.main import app, extract_date_candidates, extract_time_candidates, parse_items, parse_items_from_layout

client = TestClient(app)

def test_parsers():
    assert extract_date_candidates('2025-01-03') == ['2025-01-03']
    assert extract_time_candidates('transaction 14:22') == ['14:22']
    assert parse_items(['Apple 1,200 KRW', 'total 1,200 KRW']) == [{'name':'Apple','quantity':'','price':'1200'}]
    assert parse_items(['Apple','1,200 KRW','total','1,200 KRW']) == [{'name':'Apple','quantity':'','price':'1200'}]
    boxes=[([[0,0],[30,0],[30,10],[0,10]],'Item Qty Price',.99),([[0,20],[50,20],[50,30],[0,30]],'Apple',.99),([[60,20],[70,20],[70,30],[60,30]],'2',.99),([[90,20],[140,20],[140,30],[90,30]],'2,400',.99),([[0,40],[30,40],[30,50],[0,50]],'Total',.99)]
    assert parse_items_from_layout(boxes) == [{'name':'Apple','quantity':'2','price':'2400'}]

def test_rejects_bad_type():
    assert client.post('/api/scan', files={'file':('x.txt',b'hello','text/plain')}).status_code == 400

def test_csv():
    r=client.post('/api/export',json={'rows':[{'name':'Apple','quantity':'2','price':'1200'}]})
    assert r.status_code == 200 and 'Apple' in r.content.decode('utf-8-sig') and '날짜' not in r.content.decode('utf-8-sig')
