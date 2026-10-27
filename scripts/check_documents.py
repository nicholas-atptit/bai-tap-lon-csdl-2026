"""Read-only document QA; render derivatives without opening or saving Office originals."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,re,unicodedata,xml.etree.ElementTree as ET,zipfile
import pymupdf as fitz
from PIL import Image,ImageOps,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
def tokens(text):return re.findall(r'\w+',unicodedata.normalize('NFC',text).lower())
def office_text(path,prefix):
    texts=[];images=0
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for n in z.namelist():
            if n.startswith(prefix) and n.endswith('.xml'):
                tree=ET.fromstring(z.read(n))
                texts.extend(x.text or '' for x in tree.iter() if x.tag.rsplit('}',1)[-1]=='t')
            if '/media/' in n:images+=1
    return ' '.join(texts),images
def render_contact(pdf,out,name):
    thumbs=[]
    for i,page in enumerate(pdf):
        pix=page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False)
        path=out/(name+f'_{i+1:02}.png');pix.save(path)
        im=Image.open(path).convert('RGB');im.thumbnail((400,540))
        tile=Image.new('RGB',(420,570),'#dddddd');tile.paste(im,((420-im.width)//2,22));ImageDraw.Draw(tile).text((10,550),str(i+1),fill='black');thumbs.append(tile)
    cols=3 if len(thumbs)<=9 else 4
    sheet=Image.new('RGB',(420*cols,570*((len(thumbs)+cols-1)//cols)),'white')
    for i,im in enumerate(thumbs):sheet.paste(im,((i%cols)*420,(i//cols)*570))
    path=out/(name+'_contact.png');sheet.save(path);return str(path.relative_to(ROOT))
def main():
    out=ROOT/'tests/document_renders'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,exist_ok=False)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'report/MarketLabVN30_Report.docx',ROOT/'report/MarketLabVN30_Report.pdf',ROOT/'slides/MarketLabVN30_Presentation.pptx',ROOT/'slides/MarketLabVN30_Presentation.pdf',ROOT/'docs/diagrams/marketlab_erd.pdf']}
    docx,images=office_text(ROOT/'report/MarketLabVN30_Report.docx','word/document.xml')
    slide_text,_=office_text(ROOT/'slides/MarketLabVN30_Presentation.pptx','ppt/slides/slide')
    report=fitz.open(ROOT/'report/MarketLabVN30_Report.pdf');slides=fitz.open(ROOT/'slides/MarketLabVN30_Presentation.pdf');erd=fitz.open(ROOT/'docs/diagrams/marketlab_erd.pdf')
    assert len(report)==9 and len(slides)==14 and len(erd)==1 and images>=1
    rtext='\n'.join(p.get_text() for p in report);stext='\n'.join(p.get_text() for p in slides)
    missing=Counter(tokens(docx))-Counter(tokens(rtext));assert not missing,missing
    slide_missing=Counter(tokens(slide_text))-Counter(tokens(stext));assert not slide_missing,slide_missing
    assert '176' in rtext and '64' in rtext and '176' in stext
    for n in range(1,17):assert re.search(r'\b'+str(n)+r'\.',rtext),n
    assert '09_live_demo.sql' in rtext and '10_preflight_live.sql' in rtext
    overflow=[]
    for label,pdf in [('report',report),('slides',slides)]:
        for i,page in enumerate(pdf):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        x0,y0,x1,y1=span['bbox']
                        if x0<-.5 or y0<-.5 or x1>page.rect.width+.5 or y1>page.rect.height+.5:overflow.append((label,i+1,span['text']))
    assert not overflow,overflow
    for table in ['Market','Industry','Stock','Dataset','TradingDay','DailyPrice','StockIndex','IndexMembership','ForecastModel','TargetDefinition','ModelRun','ForecastOrigin','Prediction']:
        assert table in erd[0].get_text(),table
    contacts=[render_contact(report,out,'report'),render_contact(slides,out,'slides'),render_contact(erd,out,'erd')]
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    result={'status':'PASS','report_pdf_pages':9,'presentation_pdf_pages':14,'pptx_slides':14,'erd_pdf_pages':1,'docx_pdf_tokens_missing':0,'pptx_pdf_tokens_missing':0,'text_outside_page':overflow,'source_bytes_unchanged':True,'contacts':contacts,'word_native_pdf':'BLOCKED','docx_page_layout_fidelity_claimed':False,'visual_review':'Required separately; render generation alone is not human visual review'}
    (out/'DOCUMENT_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
