import io
import os
import sqlite3
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
OUTPUT = os.path.join(BASE_DIR, 'treasure_hunt_qr_codes.pdf')
connection = sqlite3.connect(DB_PATH)
levels = connection.execute('SELECT level_number, token FROM levels ORDER BY level_number').fetchall()
connection.close()
pdf = canvas.Canvas(OUTPUT, pagesize=A4)
width, height = A4
for index, (level_number, token) in enumerate(levels):
    if index:
        pdf.showPage()
    image = qrcode.make('http://localhost:5000/scan/' + token)
    buffer = io.BytesIO(); image.save(buffer, format='PNG'); buffer.seek(0)
    pdf.setFont('Helvetica-Bold', 22)
    pdf.drawCentredString(width / 2, height - 80, f'TREASURE HUNT - LEVEL {level_number}')
    pdf.drawImage(ImageReader(buffer), width / 2 - 130, height / 2 - 130, 260, 260)
    pdf.setFont('Helvetica', 11)
    pdf.drawCentredString(width / 2, height / 2 - 165, 'Place this QR code at the matching hunt location')
pdf.save()
print(f'Created {OUTPUT}')
