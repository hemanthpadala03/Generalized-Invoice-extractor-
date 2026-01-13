import os
import re
import pdfplumber
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN


def extract_cluster_text(pdf_path):
    """Extract clustered text from Flipkart invoice using DBSCAN"""
    blocks = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chars = page.chars

            if not chars:
                continue

            tables = page.extract_tables()
            max_cols = 0

            if tables:
                table = max(tables, key=len)
                max_cols = max(len([c for c in row if c]) for row in table)

            points, refs = [], []

            for ch in chars:
                x = (ch["x0"] + ch["x1"]) / 2
                y = (ch["top"] + ch["bottom"]) / 2
                points.append([x, y])
                refs.append(ch)

            points = np.array(points)

            if max_cols >= 6:
                points = (points - points.mean(axis=0)) / points.std(axis=0)
                labels = DBSCAN(eps=0.1, min_samples=1).fit_predict(points)
            else:
                x = (points[:, 0] - points[:, 0].mean()) / points[:, 0].std()
                y = (points[:, 1] - points[:, 1].mean()) / points[:, 1].std()
                labels = DBSCAN(eps=0.12, min_samples=1).fit_predict(
                    np.column_stack([x * 3, y])
                )

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


def extract_fields(cluster: str):
    """Extract field data from clustered text using regex"""

    def grab(pattern, flags=re.I):
        m = re.search(pattern, cluster, flags)
        return m.group(1).strip() if m else ""

    data = {}

    data["invoice_type"] = "Tax Invoice"

    # Order / invoice basics
    data["order_number"] = grab(r"Order\s*Id[:\s]*([A-Z0-9]+)")
    data["order_date"] = grab(r"Order\s*Date[:\s]*([\d\-,: ]+[APM]{2})")
    data["invoice_number"] = grab(r"Invoice\s*No[:\s]*([A-Z0-9]+)")
    data["invoice_date"] = grab(r"Invoice\s*Date[:\s]*([\d\-,: ]+[APM]{2})")

    # Tax IDs
    data["seller_gst"] = grab(r"GSTIN[:\s]*([0-9A-Z]{15})")
    data["seller_pan"] = grab(r"PAN[:\s]*([A-Z]{5}\d{4}[A-Z])")

    # Seller name: after 'Sold By' up to first comma
    data["seller_name"] = grab(r"Sold\s*By\s+([^,|]+)")

    # Seller address: between seller name and 'Billing Address' or 'BillingAddress'
    data["seller_address"] = grab(
        r"Sold\s*By.*?,\s*(.*?)\s*(Billing\s*Address|BillingAddress)",
        flags=re.I | re.S,
    )

    # Billing / shipping blocks – tolerant to spaces/case, stop before next marker
    data["billing_address"] = grab(
        r"Billing\s*Address\s+(.*?)\s+Shipping\s*ADDRESS",
        flags=re.I | re.S,
    )

    data["shipping_address"] = grab(
        r"Shipping\s*ADDRESS\s+(.*?)\s+Seller\s*Registered\s*Address",
        flags=re.I | re.S,
    )

    # Total amount – handle "TOTAL PRICE"
    data["total_amount"] = grab(r"TOTAL\s*PRICE[:\s]*([\\d.]+)")

    data["reverse_charge"] = "No"

    # State codes from IN-XX
    state = grab(r"IN-([A-Z]{2})")

    data["billing_state_code"] = state
    data["shipping_state_code"] = state
    data["place_of_supply"] = state
    data["place_of_delivery"] = state

    # Combined / optional
    data["seller_info"] = f"{data['seller_name']}, {data['seller_address']}".strip(
        ", "
    )

    data["invoice_details"] = ""
    data["fssai_license"] = ""
    data["amount_in_words"] = ""

    return data


def extract_line_items(pdf_path):
    """Extract line items from Flipkart invoice"""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

        if not tables:
            return pd.DataFrame()

        table = tables[0]
        lines = []

        for row in table:
            for cell in row:
                if cell:
                    lines.extend(cell.split("\n"))

        rows, desc = [], []

        for line in lines:
            nums = re.findall(r"\d+\.\d+|\d+", line)

            if len(nums) >= 6:
                rows.append((desc, nums[-6:]))
                desc = []
            else:
                desc.append(line)

        items = []

        for i, (d, n) in enumerate(rows, 1):
            full_desc = " ".join(d)

            if any(k in full_desc.lower() for k in ["shipping", "handling"]):
                continue

            items.append(
                {
                    "Sl.No": i,
                    "Description": full_desc,
                    "UnitPrice": n[1],
                    "Discount": n[2],
                    "Qty": n[0],
                    "NetAmount": n[3],
                    "TaxRate": "",
                    "TaxType": "IGST",
                    "TaxAmount": n[4],
                    "TotalAmount": n[5],
                }
            )

        return pd.DataFrame(items)