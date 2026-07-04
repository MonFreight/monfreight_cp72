import os
import base64
import io
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os  # must be present

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

pdfmetrics.registerFont(TTFont("NotoSans", os.path.join(FONTS_DIR, "NotoSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("NotoSans-Bold", os.path.join(FONTS_DIR, "NotoSans-Bold.ttf")))



app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

# --------------------------
# EMAIL SETTINGS
# --------------------------
MON_FREIGHT_TO = "info@monfreight.com.au"

import os
import base64
import resend

resend.api_key = os.getenv("RESEND_API_KEY")

def send_cp72_email(recipients, pdf_bytes, sender_name, recipient_name):
    if not resend.api_key:
        raise ValueError("RESEND_API_KEY not set!")

    try:
        resend.Emails.send({
            "from": "No-Reply Mon Freight <no-reply@monfreight.com.au>",
            "to": recipients,
            "subject": f"📄 CP72 Form - {sender_name} → {recipient_name}",
            "html": f"""
                <p>Hello,</p>
                <p>Your CP72 customs declaration form is attached.</p>
                <p><strong>Sender:</strong> {sender_name}<br>
                <strong>Recipient:</strong> {recipient_name}</p>
                <p>Best regards,<br>Mon Freight CP72 System</p>
            """,
            "attachments": [
                {
                    "filename": "CP72_Form.pdf",
                    "content": base64.b64encode(pdf_bytes).decode(),
                    "type": "application/pdf"
                }
            ]
        })

        print("Email sent successfully")
        return True

    except Exception as e:
        print("Email failed:", e)
        return False


@app.route("/", methods=["GET"])
def index():
    return render_template("cp72.html")


@app.route("/submit_cp72", methods=["POST"])
def submit_cp72():
    # Basic form inputs
    sender = request.form.get("sender", "").strip()
    sender_address = request.form.get("senderAddress", "").strip()
    sender_phone = request.form.get("senderPhone", "").strip()
    box_number = request.form.get("boxNumber", "").strip()

    recipient = request.form.get("recipient", "").strip()
    recipient_address = request.form.get("recipientAddress", "").strip()
    recipient_phone = request.form.get("recipientPhone", "").strip()

    weight = request.form.get("weight", "").strip()
    length = request.form.get("length", "").strip()
    width_value = request.form.get("width", "").strip()
    height = request.form.get("height", "").strip()
    volumetric_weight = request.form.get("volumetricWeight", "").strip()
    final_weight = request.form.get("finalWeight", "").strip()
    declared_value = request.form.get("value", "").strip()

    # Delivery option
    delivery_option = request.form.get("deliveryOption", "").strip()

    # Goods rows
    descriptions = request.form.getlist("item_description[]")
    quantities = request.form.getlist("item_quantity[]")
    item_weights = request.form.getlist("item_weight[]")
    origins = request.form.getlist("item_origin[]")
    values = request.form.getlist("item_value[]")

    goods_rows = []
    for i in range(len(descriptions)):
        if (
            descriptions[i].strip()
            or quantities[i].strip()
            or item_weights[i].strip()
            or origins[i].strip()
            or values[i].strip()
        ):
            goods_rows.append(
                [
                    str(len(goods_rows) + 1),
                    descriptions[i].strip(),
                    quantities[i].strip(),
                    item_weights[i].strip(),
                    origins[i].strip(),
                    values[i].strip(),
                ]
            )

    # Customer email copy option
    send_copy_choice = request.form.get("sendCopy", "no")
    customer_email = request.form.get("customerEmail", "").strip()
    send_to_customer = send_copy_choice == "yes" and customer_email

    # Signature image
    signature_data_url = request.form.get("signatureData", "")
    signature_image = None
    if signature_data_url.startswith("data:image"):
        try:
            _, encoded = signature_data_url.split(",", 1)
            signature_bytes = base64.b64decode(encoded)
            signature_image = ImageReader(io.BytesIO(signature_bytes))
        except Exception:
            signature_image = None

    # Generate PDF
    pdf_bytes = generate_cp72_pdf(
        sender,
        sender_address,
        sender_phone,
        box_number,
        recipient,
        recipient_address,
        recipient_phone,
        weight,
        length,
        width_value,
        height,
        volumetric_weight,
        final_weight,
        declared_value,
        goods_rows,
        signature_image,
        delivery_option,
    )

    # Email sending
    recipients = [MON_FREIGHT_TO]
    if send_to_customer:
        recipients.append(customer_email)

    try:
        send_cp72_email(recipients, pdf_bytes, sender, recipient)
        flash("CP72 form submitted successfully. PDF has been emailed.", "success")
    except Exception as e:
        print("Email error:", e)
        flash("Error sending email. Submission received.", "error")

    return redirect(url_for("index", success="true"))



# --------------------------
# TEXT WRAPPER
# --------------------------
def wrap_text(text, max_chars):
    lines = []
    text = text or ""
    while len(text) > max_chars:
        idx = text.rfind(" ", 0, max_chars)
        if idx == -1:
            idx = max_chars
        lines.append(text[:idx])
        text = text[idx:].lstrip()
    if text:
        lines.append(text)
    return lines


# --------------------------
# PDF GENERATOR — Mon Freight branded layout
# --------------------------
NAVY  = colors.HexColor("#073a45")
NAVY2 = colors.HexColor("#052b34")
TEAL  = colors.HexColor("#008fb0")
TEALD = colors.HexColor("#0a6f86")
SKY   = colors.HexColor("#e4f4f8")
SOFT  = colors.HexColor("#f4f9fb")
AMBER = colors.HexColor("#f6a821")
LINE  = colors.HexColor("#d7e2e8")
INK   = colors.HexColor("#0f2229")
MUTED = colors.HexColor("#6c7d86")


def generate_cp72_pdf(
    sender,
    sender_address,
    sender_phone,
    box_number,
    recipient,
    recipient_address,
    recipient_phone,
    weight,
    length,
    width_value,
    height,
    volumetric_weight,
    final_weight,
    declared_value,
    goods_rows,
    signature_image,
    delivery_option,
):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4
    M = 15 * mm
    CW = W - 2 * M          # content width
    page = 1

    # ---------- footer ----------
    def footer():
        c.setStrokeColor(TEAL)
        c.setLineWidth(0.8)
        c.line(M, 13 * mm, W - M, 13 * mm)
        c.setFont("NotoSans", 7.5)
        c.setFillColor(MUTED)
        c.drawString(M, 9.5 * mm, "Mon Freight Pty Ltd  ·  monfreight.com.au  ·  info@monfreight.com.au")
        c.drawRightString(W - M, 9.5 * mm, f"Page {page}")
        c.setFillColor(colors.black)

    # ---------- header band ----------
    def header_band(continued=False):
        band_h = 34 * mm
        c.setFillColor(NAVY)
        c.rect(0, H - band_h, W, band_h, fill=1, stroke=0)
        # subtle dashed flight route across the band
        c.saveState()
        c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
        c.setLineWidth(0.9)
        c.setDash(2, 3)
        c.line(M, H - 29 * mm, W - M, H - 29 * mm)
        c.restoreState()
        # white route illustration on the right (like the website headers)
        illu_path = os.path.join("static", "route-illustration-white.png")
        if os.path.exists(illu_path):
            try:
                c.drawImage(illu_path, W - 62 * mm, H - 33 * mm, width=47 * mm,
                            height=31 * mm, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        # white circular MF logo, straight on the navy band
        logo_path = os.path.join("static", "logo-white.png")
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, M, H - 31 * mm, width=28 * mm,
                            height=28 * mm, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        # titles
        c.setFillColor(colors.white)
        c.setFont("NotoSans-Bold", 15)
        title = "CP72 CUSTOMS DECLARATION" + (" (CONTINUED)" if continued else "")
        c.drawString(M + 33 * mm, H - 13.5 * mm, title)
        c.setFillColor(colors.HexColor("#9fd6e4"))
        c.setFont("NotoSans", 8.5)
        c.drawString(M + 33 * mm, H - 18.5 * mm, "Mon Freight Pty Ltd  ·  Австрали → Монгол агаарын карго")
        # box number chip
        c.setFillColor(AMBER)
        c.roundRect(M + 33 * mm, H - 27.5 * mm, 60 * mm, 6.5 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(NAVY2)
        c.setFont("NotoSans-Bold", 9)
        c.drawString(M + 36 * mm, H - 25.6 * mm, f"BOX {box_number}")
        c.setFillColor(colors.black)
        return H - band_h - 8 * mm

    y = header_band()

    def ensure(needed):
        nonlocal y, page
        if y - needed < 20 * mm:
            footer()
            c.showPage()
            page += 1
            y = header_band(continued=True)

    # ---------- section label ----------
    def section(label, mn):
        nonlocal y
        ensure(14 * mm)
        c.setFillColor(TEAL)
        c.rect(M, y - 1.2 * mm, 3 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("NotoSans-Bold", 10.5)
        c.drawString(M + 5 * mm, y - 1 * mm, label)
        c.setFillColor(MUTED)
        c.setFont("NotoSans", 8)
        c.drawString(M + 5 * mm + c.stringWidth(label, "NotoSans-Bold", 10.5) + 3 * mm, y - 1 * mm, mn)
        c.setFillColor(colors.black)
        y -= 7 * mm

    # ---------- sender / recipient side-by-side cards ----------
    def party_card(x, w, title, mn, name, phone, address):
        addr_lines = wrap_text(address, 44)
        card_h = (37 + 4.5 * max(1, len(addr_lines))) * mm
        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.setFillColor(colors.white)
        c.roundRect(x, y - card_h, w, card_h, 3 * mm, fill=1, stroke=1)
        # header strip
        c.setFillColor(SKY)
        c.roundRect(x, y - 8 * mm, w, 8 * mm, 3 * mm, fill=1, stroke=0)
        c.rect(x, y - 8 * mm, w, 4 * mm, fill=1, stroke=0)
        c.setFillColor(TEALD)
        c.setFont("NotoSans-Bold", 9.5)
        c.drawString(x + 4 * mm, y - 5.6 * mm, title)
        c.setFont("NotoSans", 8)
        c.drawRightString(x + w - 4 * mm, y - 5.6 * mm, mn)
        # fields
        yy = y - 13.5 * mm
        c.setFont("NotoSans", 7.5); c.setFillColor(MUTED)
        c.drawString(x + 4 * mm, yy, "FULL NAME / ОВОГ НЭР")
        c.setFont("NotoSans-Bold", 10); c.setFillColor(INK)
        c.drawString(x + 4 * mm, yy - 4.2 * mm, name)
        yy -= 9.5 * mm
        c.setFont("NotoSans", 7.5); c.setFillColor(MUTED)
        c.drawString(x + 4 * mm, yy, "PHONE / УТАС")
        c.setFont("NotoSans-Bold", 10); c.setFillColor(INK)
        c.drawString(x + 4 * mm, yy - 4.2 * mm, phone)
        yy -= 9.5 * mm
        c.setFont("NotoSans", 7.5); c.setFillColor(MUTED)
        c.drawString(x + 4 * mm, yy, "ADDRESS / ХАЯГ")
        c.setFont("NotoSans", 9); c.setFillColor(INK)
        ly = yy - 4.2 * mm
        for line in addr_lines:
            c.drawString(x + 4 * mm, ly, line)
            ly -= 4.5 * mm
        c.setFillColor(colors.black)
        return card_h

    gap = 6 * mm
    col_w = (CW - gap) / 2
    ensure(60 * mm)
    h1 = party_card(M, col_w, "SENDER", "Илгээгч", sender, sender_phone, sender_address)
    h2 = party_card(M + col_w + gap, col_w, "RECIPIENT", "Хүлээн авагч", recipient, recipient_phone, recipient_address)
    y -= max(h1, h2) + 8 * mm

    # ---------- goods table ----------
    section("GOODS DESCRIPTION", "Ачааны жагсаалт")
    header_row = ["#", "Description", "Qty", "Weight (kg)", "Origin", "Value (AUD)"]
    rows = goods_rows or [["-", "-", "-", "-", "-", "-"]]

    def table_style(n_rows):
        style = [
            ("FONTNAME", (0, 0), (-1, 0), "NotoSans-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "NotoSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("BACKGROUND", (0, 0), (-1, 0), SKY),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]
        for r in range(1, n_rows + 1):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), SOFT))
        return TableStyle(style)

    CHUNK = 10
    i = 0
    while i < len(rows):
        chunk = rows[i:i + CHUNK]
        ensure((len(chunk) + 1) * 8 * mm + 6 * mm)
        t = Table([header_row] + chunk,
                  colWidths=[10 * mm, 68 * mm, 15 * mm, 24 * mm, 26 * mm, 37 * mm])
        t.setStyle(table_style(len(chunk)))
        t.wrapOn(c, CW, y)
        t.drawOn(c, M, y - t._height)
        y -= t._height + 8 * mm
        i += CHUNK

    # ---------- weight & value chips ----------
    section("WEIGHT & MEASUREMENTS", "Жин, хэмжээс")
    ensure(26 * mm)

    def chip(x, w, label, value, accent=False):
        ch = 14 * mm
        c.setFillColor(AMBER if accent else SOFT)
        c.setStrokeColor(AMBER if accent else LINE)
        c.setLineWidth(1)
        c.roundRect(x, y - ch, w, ch, 2.5 * mm, fill=1, stroke=1)
        c.setFont("NotoSans", 7)
        c.setFillColor(NAVY2 if accent else MUTED)
        c.drawCentredString(x + w / 2, y - 4.6 * mm, label)
        c.setFont("NotoSans-Bold", 11)
        c.setFillColor(NAVY2 if accent else INK)
        c.drawCentredString(x + w / 2, y - 10.6 * mm, value)
        c.setFillColor(colors.black)

    cw4 = (CW - 3 * 4 * mm) / 4
    chip(M, cw4, "ACTUAL WEIGHT", f"{weight} kg")
    chip(M + (cw4 + 4 * mm), cw4, "VOLUMETRIC", f"{volumetric_weight} kg")
    chip(M + 2 * (cw4 + 4 * mm), cw4, "CHARGEABLE", f"{final_weight} kg", accent=True)
    chip(M + 3 * (cw4 + 4 * mm), cw4, "DECLARED VALUE", f"{declared_value} AUD")
    y -= 18 * mm
    c.setFont("NotoSans", 9)
    c.setFillColor(MUTED)
    c.drawString(M, y, f"Dimensions (L × W × H): {length} × {width_value} × {height} cm")
    c.setFillColor(colors.black)
    y -= 9 * mm

    # ---------- delivery option ----------
    section("DELIVERY OPTION", "Хүлээн авах хэлбэр")
    ensure(14 * mm)
    c.setFillColor(SKY)
    c.setStrokeColor(TEAL)
    c.setLineWidth(1)
    c.roundRect(M, y - 9 * mm, CW, 9 * mm, 2.5 * mm, fill=1, stroke=1)
    c.setFillColor(TEALD)
    c.setFont("NotoSans-Bold", 10)
    c.drawString(M + 5 * mm, y - 6 * mm, delivery_option)
    c.setFillColor(colors.black)
    y -= 15 * mm

    # ---------- signature ----------
    section("SIGNATURE", "Гарын үсэг")
    ensure(30 * mm)
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(1.2)
    c.setDash(3, 3)
    c.roundRect(M, y - 24 * mm, 85 * mm, 24 * mm, 3 * mm, fill=0, stroke=1)
    c.restoreState()
    c.setFont("NotoSans", 7.5)
    c.setFillColor(MUTED)
    c.drawString(M + 3 * mm, y - 22 * mm, "SENDER SIGNATURE / ИЛГЭЭГЧИЙН ГАРЫН ҮСЭГ")
    if signature_image:
        try:
            c.drawImage(signature_image, M + 12 * mm, y - 21 * mm, width=60 * mm,
                        height=17 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setFont("NotoSans", 7.5)
    c.setFillColor(MUTED)
    c.drawString(M + 95 * mm, y - 6 * mm, "DATE / ОГНОО")
    c.setFont("NotoSans-Bold", 11)
    c.setFillColor(INK)
    c.drawString(M + 95 * mm, y - 11.5 * mm, datetime.datetime.now().strftime("%Y-%m-%d"))
    c.setFillColor(colors.black)
    y -= 30 * mm

    footer()
    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


if __name__ == "__main__":
    app.run(debug=True)
