import re
import pdfplumber
import pandas as pd


def safe_float(val):
    """Convert value to float safely"""
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except:
        return None


def chars_to_lines(chars, y_tol=3, x_gap=3):
    """Convert characters to lines with layout awareness"""
    buckets = []

    for ch in sorted(chars, key=lambda c: (c["top"], c["x0"])):
        placed = False
        for b in buckets:
            if abs(b["y"] - ch["top"]) <= y_tol:
                b["chars"].append(ch)
                placed = True
                break

        if not placed:
            buckets.append({"y": ch["top"], "chars": [ch]})

    lines = []
    for b in sorted(buckets, key=lambda x: x["y"]):
        line = ""
        prev_x1 = None

        for c in sorted(b["chars"], key=lambda c: c["x0"]):
            if prev_x1 is not None and c["x0"] - prev_x1 > x_gap:
                line += " "
            line += c["text"]
            prev_x1 = c["x1"]

        clean = re.sub(r"\s+", " ", line).strip()
        if clean:
            lines.append(clean)

    return lines


def extract_amount_in_words(left_lines, right_lines):
    """Extract amount in words from left and right columns"""
    all_lines = left_lines + right_lines
    normalized = []

    for l in all_lines:
        clean = re.sub(r"[^a-zA-Z]", "", l).lower()
        normalized.append(clean)

    joined = " ".join(normalized)

    if "amountinwords" not in joined:
        return ""

    text = joined.split("amountinwords", 1)[-1]

    if "only" in text:
        text = text.split("only", 1)[0] + " only"

    text = text.replace("rupees", " rupees ")
    text = text.replace("paise", " paise ")
    text = re.sub(r"\s+", " ", text).strip()

    return text.capitalize()


def extract_header(pdf_path):
    """Extract header data from Instamart invoice"""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        chars = [c for c in page.chars if c["text"].strip()]

        mid_x = page.width / 2

        left_chars, right_chars = [], []

        for ch in chars:
            x_center = (ch["x0"] + ch["x1"]) / 2
            if x_center < mid_x:
                left_chars.append(ch)
            else:
                right_chars.append(ch)

        left_lines = chars_to_lines(left_chars)
        right_lines = chars_to_lines(right_chars)

        # Normalize glued labels
        def normalize(lines):
            out = []
            for l in lines:
                l = l.replace("InvoiceTo", "Invoice To")
                l = l.replace("CustomerAddress", "Customer Address")
                l = l.replace("OrderID", "Order ID")
                l = l.replace("InvoiceNo", "Invoice No")
                l = l.replace("DateofInvoice", "Date of Invoice")
                l = l.replace("SellerName", "Seller Name")
                l = l.replace("SellerGSTIN", "Seller GSTIN")
                l = l.replace("PlaceofSupply", "Place of Supply")
                out.append(l)
            return out

        left_lines = normalize(left_lines)
        right_lines = normalize(right_lines)

        # ---------- CUSTOMER ADDRESS (LEFT)
        customer_addr_lines = []
        capture = False

        for l in left_lines:
            if "Customer Address" in l:
                capture = True
                l = l.split("Customer Address", 1)[-1].replace(":", "").strip()
                if l:
                    customer_addr_lines.append(l)
                continue

            if capture:
                if "Order ID" in l:
                    break
                customer_addr_lines.append(l)

        customer_address = " ".join(customer_addr_lines).strip()

        # ---------- SIMPLE GRABS
        def grab_left(key):
            for l in left_lines:
                if l.startswith(key):
                    return l.split(key, 1)[-1].replace(":", "").strip()
            return ""

        def grab_right(key):
            for r in right_lines:
                if r.startswith(key):
                    return r.split(key, 1)[-1].replace(":", "").strip()
            return ""

        # ---------- SELLER ADDRESS (RIGHT, MULTI-LINE)
        seller_addr_lines = []
        capture = False

        for r in right_lines:
            if r.startswith("Address"):
                capture = True
                r = r.split("Address", 1)[-1].replace(":", "").strip()
                if r:
                    seller_addr_lines.append(r)
                continue

            if capture:
                if r.startswith("State"):
                    break
                seller_addr_lines.append(r)

        seller_address = " ".join(seller_addr_lines).strip()
        seller_name = grab_right("Seller Name")

        # ---------- AMOUNT IN WORDS
        amount_in_words = extract_amount_in_words(left_lines, right_lines)

        data = {
            "invoice_type": "Tax Invoice",
            "order_number": grab_left("Order ID"),
            "invoice_number": grab_left("Invoice No"),
            "invoice_details": grab_left("Invoice No"),
            "invoice_date": grab_left("Date of Invoice"),
            "billing_address": customer_address,
            "shipping_address": customer_address,
            "seller_name": seller_name,
            "seller_address": seller_address,
            "seller_info": f"{seller_name}, {seller_address}",
            "seller_gst": grab_right("Seller GSTIN"),
            "fssai_license": grab_right("FSSAI"),
            "place_of_supply": grab_right("Place of Supply"),
            "place_of_delivery": grab_right("Place of Supply"),
            "amount_in_words": amount_in_words,
        }

        return data


def extract_items_and_totals(pdf_path):
    """Extract line items and totals from Instamart invoice"""
    items = []
    total_tax = 0.0
    total_amount = 0.0
    sl = 1

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

        for table in tables:
            df = pd.DataFrame(table).dropna(how="all")

            if len(df) < 4:
                continue

            header_text = " ".join(df.iloc[2].astype(str).tolist()).lower()

            if "description of goods" not in header_text:
                continue

            df_items = df.iloc[3:].reset_index(drop=True)

            for _, row in df_items.iterrows():
                if len(row) < 16:
                    continue

                desc = str(row[1]).strip()

                if not desc or "invoice value" in desc.lower():
                    continue

                net_val = safe_float(row[7])
                total_val = safe_float(row[15])

                if net_val is None or total_val is None:
                    continue

                tax_val = round(total_val - net_val, 2)

                items.append(
                    {
                        "Sl.No": sl,
                        "Description": desc.replace("\n", " "),
                        "UnitPrice": "",
                        "Discount": "",
                        "Qty": safe_float(row[2]),
                        "NetAmount": net_val,
                        "TaxRate": "",
                        "TaxType": "GST",
                        "TaxAmount": tax_val,
                        "TotalAmount": total_val,
                    }
                )

                total_tax += tax_val
                total_amount += total_val
                sl += 1

            break  # correct table processed

    return pd.DataFrame(items), round(total_tax, 2), round(total_amount, 2)