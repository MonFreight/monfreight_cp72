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
            "from": "Mon Freight <no-reply@monfreight.com.au>",
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
# PDF GENERATOR
# --------------------------
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
    width_page, height_page = A4
    page_number = 1 

    # --------------------------
    # LOGO (slightly bigger, top-right)
    # --------------------------
    logo_path = os.path.join("static", "monfreight_logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(
                logo_path,
                width_page - 55 * mm,       # a bit more left
                height_page - 24 * mm,      # slightly higher
                width=48 * mm,              # bigger logo (Option A)
                height=18 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # --------------------------
    # TITLE
    # --------------------------
    c.setFont("NotoSans-Bold", 16)
    c.drawString(20 * mm, height_page - 20 * mm, "MON FREIGHT")

    c.setFont("NotoSans-Bold", 13)
    c.drawString(20 * mm, height_page - 27 * mm, "CP72 CUSTOMS DECLARATION FORM")

    y = height_page - 40 * mm

    # --------------------------
    # SECTION HEADER TOOL
    # --------------------------
    def section_header(label):
        nonlocal y
        c.setFillColorRGB(0.10, 0.31, 0.36)
        c.rect(20 * mm, y, width_page - 40 * mm, 7 * mm, fill=1)
        c.setFillColor(colors.white)
        c.setFont("NotoSans-Bold", 10)
        c.drawString(23 * mm, y + 2.2 * mm, label)
        c.setFillColor(colors.black)
        y -= 8 * mm  # tight, but not too cramped

    # --------------------------
    # SENDER DETAILS (tight courier style)
    # --------------------------
    section_header("SENDER DETAILS")
    c.setFont("NotoSans", 10)
    c.setFont("NotoSans-Bold", 10)
    c.drawString(20 * mm, y, f"Full Name / Овог нэр: {sender}")
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Phone / Утас: {sender_phone}")
    y -= 4 * mm

    c.drawString(20 * mm, y, "Address / Хаяг:")
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Box Number: {box_number}")
    y -= 5 * mm


    for line in wrap_text(sender_address, 95):
        c.drawString(25 * mm, y, line)
        y -= 4 * mm

    y -= 6 * mm  # small gap before next block

    # --------------------------
    # RECIPIENT DETAILS
    # --------------------------
    section_header("RECIPIENT DETAILS")
    c.drawString(20 * mm, y, f"Full Name / Овог нэр: {recipient}")
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Phone / Утас: {recipient_phone}")
    y -= 4 * mm

    c.drawString(20 * mm, y, "Address / Хаяг:")
    y -= 4 * mm

    for line in wrap_text(recipient_address, 95):
        c.drawString(25 * mm, y, line)
        y -= 4 * mm

    y -= 6 * mm

    # --------------------------
    # GOODS DESCRIPTION TABLE
    # --------------------------
    section_header("GOODS DESCRIPTION")

    table_data = [["#", "Description", "Qty", "Weight (kg)", "Origin", "Value (AUD)"]]
    table_data.extend(goods_rows or [["-", "-", "-", "-", "-", "-"]])

    table = Table(
        table_data,
        colWidths=[10 * mm, 60 * mm, 15 * mm, 20 * mm, 25 * mm, 25 * mm],
    )

    table.setStyle(TableStyle([
           ("FONTNAME", (0, 0), (-1, 0), "NotoSans-Bold"),  # Header bold
           ("FONTNAME", (0, 1), (-1, -1), "NotoSans"),  # Body cells
           ("FONTSIZE", (0, 0), (-1, -1), 9),
           ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
           ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
           ("ALIGN", (0, 0), (0, -1), "CENTER"),
           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # --------------------------
    # MULTIPAGE TABLE (First 12 rows stay on page 1)
    # --------------------------

    max_first_page_rows = 12

    if len(goods_rows) > max_first_page_rows:
        first_part = goods_rows[:max_first_page_rows]
        remaining_part = goods_rows[max_first_page_rows:]
    else:
        first_part = goods_rows
        remaining_part = []

    # -------- TABLE STYLE ----------
    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "NotoSans-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "NotoSans"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ])

    # -------- PAGE 1 TABLE ----------
    table_data_page1 = [["#", "Description", "Qty", "Weight (kg)", "Origin", "Value (AUD)"]] + first_part
    table1 = Table(table_data_page1, colWidths=[10*mm, 60*mm, 15*mm, 20*mm, 25*mm, 25*mm])
    table1.setStyle(table_style)

    table1.wrapOn(c, width_page - 40*mm, y)
    table1.drawOn(c, 20*mm, y - table1._height)
    y -= table1._height + 10*mm

    # ---- Page number bottom of page ----
    c.setFont("NotoSans", 9)
    c.drawRightString(width_page - 15*mm, 10*mm, f"Page {page_number}")

    # -------- CONTINUE ON NEXT PAGE IF NEEDED ----------
    if remaining_part:
        page_number += 1
        c.showPage()

        # continuation title
        c.setFont("NotoSans-Bold", 13)
        c.drawString(20 * mm, height_page - 20 * mm, "CP72 CUSTOMS DECLARATION FORM (Continued)")
        y = height_page - 35 * mm

        table_data_page2 = [["#", "Description", "Qty", "Weight (kg)", "Origin", "Value (AUD)"]] + remaining_part
        table2 = Table(table_data_page2, colWidths=[10*mm, 60*mm, 15*mm, 20*mm, 25*mm, 25*mm])
        table2.setStyle(table_style)

        table2.wrapOn(c, width_page - 40*mm, y)
        table2.drawOn(c, 20*mm, y - table2._height)
        y -= table2._height + 10*mm

        # Page number on second page
        c.setFont("NotoSans", 9)
        c.drawRightString(width_page - 15*mm, 10*mm, f"Page {page_number}")

    # --------------------------
    # WEIGHT & MEASUREMENTS
    # --------------------------
    section_header("WEIGHT & MEASUREMENTS")
    c.drawString(20 * mm, y, f"Declared Value (AUD): {declared_value}")
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Actual Weight: {weight} kg")
    y -= 4 * mm

    c.drawString(
        20 * mm,
        y,
        f"Dimensions (L × W × H): {length} × {width_value} × {height} cm",
    )
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Volumetric Weight: {volumetric_weight} kg")
    y -= 4 * mm

    c.drawString(20 * mm, y, f"Chargeable Weight: {final_weight} kg")
    y -= 8 * mm

    # --------------------------
    # DELIVERY OPTION
    # --------------------------
    section_header("DELIVERY OPTION")
    c.drawString(20 * mm, y, f"Selected Option: {delivery_option}")
    y -= 10 * mm

    # --------------------------
    # SIGNATURE (aligned with text)
    # --------------------------
    section_header("SIGNATURE")
    c.drawString(20 * mm, y -1 * mm, "Sender Signature:")
    

    sig_y = y - 8 * mm

    if signature_image:
        try:
            c.drawImage(
                signature_image,
                65 * mm,
                sig_y,
                width=60 * mm,
                height=20 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.drawString(120 * mm, y, f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}")
    y -= 20 * mm

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


if __name__ == "__main__":
    app.run(debug=True)
