import re
import pdfplumber
import pandas as pd


def safe_float(val):
    """Convert value to float safely"""
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except:
        return 0.0


def clean(text):
    """Clean whitespace from text"""
    return re.sub(r"\s+", " ", str(text)).strip()


def extract_header(df):
    """Extract header data from Blinkit invoice table"""
    data = {}

    # -------------------------
    # R1 C10 → Invoice Number
    # -------------------------
    r1c10 = clean(df.iloc[1, 10])
    m = re.search(r"Invoice Number\s*:\s*([\w\-]+)", r1c10)
    data["invoice_number"] = m.group(1) if m else ""

    # -------------------------
    # Seller name & address (R1 C0)
    # -------------------------
    r1c0 = clean(df.iloc[1, 0])
    seller_name = "Zomato Hyperpure Private Limited ZHPL"
    data["seller_name"] = seller_name
    if seller_name in r1c0:
        data["seller_address"] = r1c0.split(seller_name, 1)[-1].strip()
    else:
        data["seller_address"] = ""
    data["seller_info"] = f"{seller_name}, {data['seller_address']}"

    # -------------------------
    # R2 C0 → GSTIN
    # -------------------------
    r2c0 = clean(df.iloc[2, 0])
    m = re.search(r"GSTIN\s*:\s*([\w\d]+)", r2c0)
    data["seller_gst"] = m.group(1) if m else ""

    # -------------------------
    # R3 C0 → FSSAI
    # -------------------------
    r3c0 = clean(df.iloc[3, 0])
    m = re.search(r"FSSAI.*?(\d{10,})", r3c0)
    data["fssai_license"] = m.group(1) if m else ""

    # -------------------------
    # R4 C0 → Invoice To + Address
    # -------------------------
    r4c0 = clean(df.iloc[4, 0])
    m = re.search(r"Invoice To Name\s*:\s*([^,]+)", r4c0, re.I)
    data["invoice_to"] = m.group(1).strip() if m else ""

    m = re.search(r"Address\s*:\s*(.*?)(Order Id|$)", r4c0, re.I)
    address = m.group(1).strip() if m else ""
    data["billing_address"] = address
    data["shipping_address"] = address

    # -------------------------
    # R4 C10 → Order / Date / Place
    # -------------------------
    r4c10 = clean(df.iloc[4, 10])
    m = re.search(r"Order Id\s*:\s*(\d+)", r4c10)
    data["order_number"] = m.group(1) if m else ""

    m = re.search(r"Invoice\s*:\s*([\w\-]+)", r4c10)
    data["invoice_date"] = m.group(1) if m else ""
    data["order_date"] = data["invoice_date"]

    m = re.search(r"Place of\s*:\s*(\w+)", r4c10, re.I)
    pos = m.group(1) if m else ""
    data["place_of_supply"] = pos
    data["place_of_delivery"] = pos

    # -------------------------
    # R8 C0 → Amount in Words
    # -------------------------
    r8c0 = clean(df.iloc[8, 0])
    m = re.search(r"Amount in\s+(.*?)\s+Words", r8c0, re.I)
    data["amount_in_words"] = m.group(1).strip() if m else ""

    data["invoice_type"] = "Tax Invoice"

    return data


def extract_items_and_totals(df):
    """Extract line items and totals from Blinkit invoice table"""
    items = []
    total_tax = 0.0
    total_amount = 0.0
    sl = 1

    FIRST_ITEM_ROW = 6

    for i in range(FIRST_ITEM_ROW, len(df)):
        row = df.iloc[i]

        # TOTAL ROW
        if str(row[0]).strip().lower() == "total":
            total_tax = safe_float(row[8]) + safe_float(row[10])
            total_amount = safe_float(row[13])
            break

        desc = clean(row[2])

        if not desc:
            continue

        net_val = safe_float(row[6])
        total_val = safe_float(row[13])
        tax_val = round(total_val - net_val, 2)

        items.append(
            {
                "Sl.No": sl,
                "Description": desc,
                "UnitPrice": safe_float(row[3]),
                "Discount": safe_float(row[4]),
                "Qty": safe_float(row[5]),
                "NetAmount": net_val,
                "TaxRate": "",
                "TaxType": "GST",
                "TaxAmount": tax_val,
                "TotalAmount": total_val,
            }
        )
        sl += 1

    return pd.DataFrame(items), round(total_tax, 2), round(total_amount, 2)