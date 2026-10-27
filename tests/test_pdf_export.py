import io
from pypdf import PdfReader
from fastapi.testclient import TestClient
from app import server

def test_plain_pdf_export_preserves_text_unicode_and_overlap(monkeypatch):
    rec={'status':'complete','title':'Meeting & notes <draft>','filename':'test.aac',
        'speakers':[{'id':'a','name':'Peña'},{'id':'b','name':'Ben'}],
        'segments':[{'start':1.2,'end':2,'speaker_id':'a','text':'Kumusta, señor. <literal> & readable.'},
            {'start':2,'end':3,'speaker_id':'overlap','speaker_ids':['a','b'],'overlap':True,'text':'Mixed words.'}]}
    monkeypatch.setattr(server,'get_recording',lambda _:rec)
    response=TestClient(server.app).get('/api/recordings/'+'0'*32+'/export/pdf')
    assert response.status_code==200
    assert response.headers['content-type']=='application/pdf'
    assert 'transcript.pdf' in response.headers['content-disposition']
    assert response.content.startswith(b'%PDF-')
    text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert 'Peña' in text and 'señor' in text
    assert '<literal> & readable.' in text
    assert 'Overlap [Peña + Ben]' in text and 'mixed audio' in text
    assert '[00:00:01]' in text and 'Page 1' in text
