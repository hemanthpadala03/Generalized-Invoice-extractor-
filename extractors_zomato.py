import re
import pdfplumber
import pandas as pd


def safe_float(val):
    """Convert value to float safely"""
    if val is None:
        return 0.0
    val = str(val).replace("%", "").replace(",", "").strip()
    try:
        return float(val)
    except ValueError:
        return 0.0


def extract_with_rules_zomato(full_text):
    """Extract fields from Zomato invoice text"""
    text = re.sub(r"\s+", " ", full_text).strip()

    def grab(pattern):
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else ""

    data = {}
    data["invoice_type"] = "Tax Invoice"
    data["invoice_number"] = grab(r"Invoice No\.?\s*:\s*([\w\d]+)")
    data["invoice_date"] = grab(r"Invoice Date\s*:\s*([\d/]+)")
    data["order_number"] = grab(r"Order ID\s*:\s*(\d+)")

    # ---- Seller = Restaurant
    data["seller_name"] = grab(r"Restaurant Name\s*:\s*(.*?)Restaurant Address")
    data["seller_address"] = grab(r"Restaurant Address\s*:\s*(.*?)Restaurant GSTIN")
    data["seller_gst"] = grab(r"Restaurant GSTIN\s*:\s*([\w\d]+)")
    data["fssai_license"] = grab(r"Restaurant FSSAI\s*:\s*(\d+)")
    data["seller_info"] = f"{data['seller_name']}, {data['seller_address']}"

    # ---- Buyer / Receiver
    delivery_addr = grab(r"Delivery Address\s*:\s*(.*?)State name")
    data["billing_address"] = delivery_addr
    data["shipping_address"] = delivery_addr
    data["place_of_supply"] = grab(r"State name.*?:\s*(.*?)\(")
    data["place_of_delivery"] = data["place_of_supply"]

    state_code = grab(r"\((\d{2})\)")
    data["billing_state_code"] = state_code
    data["shipping_state_code"] = state_code
    data["amount_in_words"] = grab(r"Amount \(in words\)\s*:\s*(.*?Only)")

    return data


def extract_table_and_totals(pdf_path):
    """Extract line items and totals from Zomato invoice"""
    line_items = []
    net_value = total_value = tax_value = 0.0

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                df = pd.DataFrame(table).dropna(how="all")

                if df.shape[1] < 6:
                    continue

                header = df.iloc[0].astype(str).str.lower().tolist()

                if "particulars" not in " ".join(header):
                    continue

                df.columns = header
                df = df.iloc[1:].reset_index(drop=True)

                def find_col(keys):
                    for c in df.columns:
                        if all(k in c for k in keys):
                            return c
                    return None

                part_col = find_col(["particular"])
                gross_col = find_col(["gross"])
                disc_col = find_col(["discount"])
                net_col = find_col(["net"])
                cgst_rate_col = find_col(["cgst", "rate"])
                cgst_amt_col = find_col(["cgst", "inr"])
                sgst_rate_col = find_col(["sgst", "rate"])
                sgst_amt_col = find_col(["sgst", "inr"])
                total_col = find_col(["total"])

                sl = 1
                for _, row in df.iterrows():
                    part = str(row[part_col]).lower()

                    if "total value" in part:
                        net_value = safe_float(row[net_col])
                        total_value = safe_float(row[total_col])
                        tax_value = round(total_value - net_value, 2)
                        continue

                    if "item(s) total" in part:
                        continue

                    if part.strip():
                        line_items.append(
                            {
                                "Sl.No": sl,
                                "Description": row[part_col],
                                "UnitPrice": safe_float(row[gross_col]),
                                "Discount": safe_float(row[disc_col]),
                                "Qty": 1,
                                "NetAmount": safe_float(row[net_col]),
                                "TaxRate": f"{row[cgst_rate_col]} + {row[sgst_rate_col]}",
                                "TaxType": "CGST+SGST",
                                "TaxAmount": (
                                    safe_float(row[cgst_amt_col])
                                    + safe_float(row[sgst_amt_col])
                                ),
                                "TotalAmount": safe_float(row[total_col]),
                            }
                        )
                        sl += 1

                return pd.DataFrame(line_items), net_value, tax_value, total_value

    return pd.DataFrame(), 0.0, 0.0, 0.0