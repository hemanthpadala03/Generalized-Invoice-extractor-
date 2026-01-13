"""
AMAZON INVOICE EXTRACTOR - FIXED VERSION
Simple regex extraction with proper field boundaries
"""

import os
import re
import pdfplumber
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN


def extract_totals_amazon(pdf_path):
    """Extract tax and total amount from Amazon invoice"""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            table = max(tables, key=len)
            max_cols = max(len([c for c in row if c]) for row in table)

            if max_cols < 6:
                continue
            df = pd.DataFrame(table).dropna(how="all").reset_index(drop=True)
            header = df.iloc[0].astype(str)
            data = df.iloc[1:].reset_index(drop=True)

            tax_col, total_col = None, None
            for idx, col in enumerate(header):
                c = col.lower()
                if "tax" in c and "amount" in c:
                    tax_col = idx
                if "total" in c and "amount" in c:
                    total_col = idx

            if tax_col is None or total_col is None:
                return 0.0, 0.0

            for _, row in data.iterrows():
                if any("total" in str(cell).lower() for cell in row):
                    tax_val = re.findall(r"[\d.]+", str(row[tax_col]))
                    amt_val = re.findall(r"[\d.]+", str(row[total_col]))
                    return (
                        float(tax_val[0]) if tax_val else 0.0,
                        float(amt_val[0]) if amt_val else 0.0,
                    )

    return 0.0, 0.0


def extract_cluster_text_amazon(pdf_path):
    """Extract clustered text from Amazon invoice using DBSCAN"""
    blocks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chars = page.chars
            if not chars:
                continue

            points, refs = [], []
            for ch in chars:
                x = (ch["x0"] + ch["x1"]) / 2
                y = (ch["top"] + ch["bottom"]) / 2
                points.append([x, y])
                refs.append(ch)

            points = np.array(points)
            points = (points - points.mean(axis=0)) / points.std(axis=0)
            labels = DBSCAN(eps=0.1, min_samples=1).fit_predict(points)

            clusters = {}
            for lbl, ch in zip(labels, refs):
                if lbl != -1:
                    clusters.setdefault(lbl, []).append(ch)

            for group in clusters.values():
                group = sorted(group, key=lambda c: (c["top"], c["x0"]))
                text, prev_top = "", None
                for ch in group:
                    if prev_top is not None and abs(ch["top"] - prev_top) > 3:
                        text += " "
                    text += ch["text"]
                    prev_top = ch["top"]
                if len(text.strip()) > 30:
                    blocks.append(text.strip())

    return " | ".join(blocks)


def extract_with_rules_amazon(cluster_text):
    """Extract fields using SIMPLE REGEX"""
    text = re.sub(r'\s+', ' ', cluster_text.replace('|', ' ')).strip()
    text_lower = text.lower()
    
    data = {}
    
    # =====================================================
    # BASIC FIELDS
    # =====================================================
    
    # Order/Invoice Numbers
    m = re.search(r"Order (Number|Id)[:\s]*([\w\-]+)", text, re.I)
    data["order_number"] = m.group(2).strip() if m else ""
    
    m = re.search(r"Invoice (No|Number)[:\s]*([\w\-]+)", text, re.I)
    data["invoice_number"] = m.group(2).strip() if m else ""
    
    # Dates
    date_pattern = r"\d{2}[./-]\d{2}[./-]\d{4}"
    m = re.search(r"Order Date[:\s]*(" + date_pattern + ")", text, re.I)
    data["order_date"] = m.group(1) if m else ""
    
    m = re.search(r"Invoice Date[:\s]*(" + date_pattern + ")", text, re.I)
    data["invoice_date"] = m.group(1) if m else ""
    
    # =====================================================
    # INVOICE DETAILS - Stop before date
    # =====================================================
    
    m = re.search(r"Invoice Details[:\s]*(.+?)(?=Invoice Date|Order Date|Sl\.)", text, re.I)
    if m:
        inv_detail = m.group(1).strip()
        inv_detail = re.sub(r'\s+', ' ', inv_detail)
        data["invoice_details"] = inv_detail[:100]
    else:
        data["invoice_details"] = ""
    
    # =====================================================
    # ADDRESSES - Stop at pincode OR state
    # =====================================================
    
    # =====================================================
    # ADDRESSES - Capture FULL ADDRESS including 6-digit pin code
    # =====================================================

    # Billing Address - capture until AND including 6-digit pin code
    m = re.search(
        r"Billing Address[:\s]*([\s\S]*?\d{6})",
        text,
        re.I | re.S
    )
    data["billing_address"] = m.group(1).strip() if m else ""

    # Shipping Address - capture until AND including 6-digit pin code
    m = re.search(
        r"Shipping Address[:\s]*([\s\S]*?\d{6})",
        text,
        re.I | re.S
    )
    data["shipping_address"] = m.group(1).strip() if m else ""

    
    # =====================================================
    # SELLER INFO
    # =====================================================
    
    m = re.search(r"Sold By[:\s]*([^,\n]+)", text, re.I)
    data["seller_name"] = m.group(1).strip() if m else ""
    
    m = re.search(r"Sold By[:\s]*(.+?)(?=PAN No|GST Registration|Billing Address)", text, re.I | re.S)
    data["seller_address"] = m.group(1).strip() if m else ""
    
    # =====================================================
    # TAX IDs
    # =====================================================
    
    m = re.search(r"GST Registration No[:\s]*(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])", text, re.I)
    data["seller_gst"] = m.group(1) if m else ""
    
    m = re.search(r"PAN No[:\s]*([A-Z]{5}\d{4}[A-Z])", text, re.I)
    data["seller_pan"] = m.group(1) if m else ""
    
    # =====================================================
    # STATE & PLACE
    # =====================================================
    
    m = re.search(r"State/UT Code[:\s]*(\d{1,2})", text, re.I)
    state_code = m.group(1) if m else ""
    data["billing_state_code"] = state_code
    data["shipping_state_code"] = state_code
    
    m = re.search(r"Place of (?:supply|delivery)[:\s]*([A-Z\s]+?)(?=Place of|Invoice|$)", text, re.I)
    data["place_of_supply"] = m.group(1).strip() if m else ""
    data["place_of_delivery"] = m.group(1).strip() if m else ""
    
    # =====================================================
    # AMOUNT IN WORDS
    # =====================================================
    
    m = re.search(r"Amount in Words[:\s]*(.+?)(?=Net|Tax|Whether|$)", text, re.I)
    if m:
        amt_words = m.group(1).strip()
        amt_words = re.sub(r'\s+', ' ', amt_words)
        data["amount_in_words"] = amt_words[:100]
    else:
        data["amount_in_words"] = ""
    
    # =====================================================
    # DEFAULTS
    # =====================================================
    
    data["invoice_type"] = "Tax Invoice"
    data.setdefault("total_tax", 0.0)
    data.setdefault("total_amount", 0.0)
    
    return data


def extract_item_table_amazon(pdf_path):
    """Extract line items from Amazon invoice"""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            for table in tables:
                table = [r for r in table if any(c and c.strip() for c in r)]

                if not table:
                    continue
                
                header = [str(c).lower() if c else "" for c in table[0]]

                if (
                    any("description" in h for h in header)
                    and any("qty" in h or "quantity" in h for h in header)
                    and any("total" in h for h in header)
                ):
                    rows = [
                        [cell.strip() if cell else "" for cell in row]
                        for row in table[1:]
                    ]

                    clean_header = [
                        h.replace(" ", "_").title() if h else f"Col_{i}"
                        for i, h in enumerate(header)
                    ]

                    return pd.DataFrame(rows, columns=clean_header)

    return pd.DataFrame()
