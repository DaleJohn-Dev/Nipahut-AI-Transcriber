"""Plain, offline PDF transcript export; embeds bundled open-license fonts."""
import io
import threading
from pathlib import Path
from xml.sax.saxutils import escape
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

_font_lock=threading.Lock()
def _fonts():
    with _font_lock:
        if 'TranscriptVera' not in pdfmetrics.getRegisteredFontNames():
            folder=Path(reportlab.__file__).parent/'fonts'
            pdfmetrics.registerFont(TTFont('TranscriptVera',str(folder/'Vera.ttf')))
            pdfmetrics.registerFont(TTFont('TranscriptVeraBold',str(folder/'VeraBd.ttf')))

def transcript_pdf(recording, label):
    _fonts()
    output=io.BytesIO()
    title=str(recording.get('title') or 'Transcript')
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=44,
        title=title,author='Nipahut AI Transcriber',pageCompression=1)
    body=ParagraphStyle('Transcript',fontName='TranscriptVera',fontSize=9.5,leading=14,spaceAfter=9,
        alignment=TA_LEFT,splitLongWords=True)
    heading=ParagraphStyle('Title',parent=body,fontName='TranscriptVeraBold',fontSize=16,leading=21,spaceAfter=8)
    meta=ParagraphStyle('Metadata',parent=body,fontSize=8,leading=12,textColor=colors.HexColor('#555555'))
    text=lambda value:escape(str(value)).replace('\n','<br/>')
    story=[Paragraph(text(title),heading),Paragraph(text(recording.get('filename','')),meta)]
    if recording.get('audio_edits_pending'):
        story.append(Paragraph('Audio edits are pending reprocessing; this transcript is from the previous analysis.',meta))
    story.append(Spacer(1,9))
    for segment in recording.get('segments',[]):
        seconds=max(0,int(segment['start']))
        stamp=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
        story.append(Paragraph(f'<font name="TranscriptVeraBold">[{stamp}] {text(label(segment))}:</font> {text(segment["text"])}',body))
    if not recording.get('segments'):story.append(Paragraph('No transcript segments.',body))
    def footer(canvas,document):
        canvas.saveState();canvas.setFont('TranscriptVera',8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawRightString(A4[0]-42,24,f'Page {document.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
