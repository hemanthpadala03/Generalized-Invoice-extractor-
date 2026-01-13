# main_production_v2.py
import os
import re
import pdfplumber
import pandas as pd
from pathlib import Path
from base import AmazonExtractor, FlipkartExtractor, ZomatoExtractor, BlinkitExtractor, InstamartExtractor

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = r"C:\Drive_d\Python\F-AI\T3"
INPUT_DIR = os.path.join(BASE_DIR, "Input")
OUTPUT_DIR = os.path.join(BASE_DIR, "Output")
TEMPLATE_PATH = os.path.join(BASE_DIR, "Output Template.xlsx")
DEBUG_DIR = os.path.join(OUTPUT_DIR, "debug_clusters")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

# =====================================================
# BRAND DETECTION
# =====================================================

def detect_brand(text_lower: str) -> str:
    """
    Auto-detect brand from PDF text.
    Order matters! Most specific first.
    """
    if "blinkit" in text_lower or ("zomato hyperpure" in text_lower):
        return "blinkit"
    elif "flipkart" in text_lower or "shopler estore" in text_lower:
        return "flipkart"
    elif "amazon" in text_lower or "amazon seller" in text_lower:
        return "amazon"
    elif "instamart" in text_lower or "b2c" in text_lower or ("swiggy" in text_lower and "invoice" in text_lower):
        return "instamart"
    elif ("zomato" in text_lower or "ethernal" in text_lower) and "restaurant" in text_lower:
        return "zomato"
    else:
        return None

# =====================================================
# FACTORY PATTERN - GET APPROPRIATE EXTRACTOR
# =====================================================

def get_extractor(pdf_path: str, brand: str):
    """Factory: return appropriate extractor instance"""
    extractors = {
        "amazon": AmazonExtractor,
        "flipkart": FlipkartExtractor,
        "zomato": ZomatoExtractor,
        "blinkit": BlinkitExtractor,
        "instamart": InstamartExtractor,
    }
    extractor_class = extractors.get(brand)
    if not extractor_class:
        return None
    return extractor_class(pdf_path)

# =====================================================
# MAIN PROCESSOR
# =====================================================

def process_invoice(pdf_path: str, output_dir: str) -> str:
    """
    Main router: detect brand, create extractor, extract data, save to Excel
    """
    filename = os.path.basename(pdf_path)
    
    try:
        # 1. Extract text for brand detection
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            text_lower = text.lower()
        
        # 2. Detect brand
        brand = detect_brand(text_lower)
        print(f"\n▶ {filename}")
        
        if not brand:
            print(f" ⚠️ Brand not recognized")
            return None
        
        # 3. Get appropriate extractor
        extractor = get_extractor(pdf_path, brand)
        if not extractor:
            print(f" ❌ No extractor for {brand}")
            return None
        
        # 4. Extract data (polymorphic call)
        header_dict, items_df = extractor.extract()
        
        # 5. Load template
        template_df = pd.read_excel(TEMPLATE_PATH)
        template_df["Value"] = template_df["Field"].map(header_dict).fillna("")
        
        # 6. Save Excel output
        out_path = os.path.join(
            output_dir,
            os.path.basename(pdf_path).replace(".pdf", f"_{brand}_output.xlsx")
        )
        
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            template_df.to_excel(writer, index=False, sheet_name="Invoice_Fields")
            if not items_df.empty:
                items_df.to_excel(writer, index=False, sheet_name="Line_Items")
        
        # Print brand emoji
        emoji_map = {
            "amazon": "🛍️",
            "flipkart": "🛒",
            "zomato": "🍽️",
            "blinkit": "⚡",
            "instamart": "🏪"
        }
        print(f" {emoji_map.get(brand, '📦')} Detected: {brand.upper()}")
        print(f" ✅ Saved: {os.path.basename(out_path)}")
        
        return out_path
        
    except Exception as e:
        print(f" ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# =====================================================
# MAIN EXECUTION
# =====================================================

if __name__ == "__main__":
    print("=" * 60)
    print("UNIVERSAL INVOICE EXTRACTOR - OOP PRODUCTION V2")
    print("=" * 60)
    
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Input folder not found: {INPUT_DIR}")
        exit(1)
    
    # Find all PDFs
    pdf_files = list(Path(INPUT_DIR).glob("*.pdf"))
    
    if not pdf_files:
        print(f"❌ No PDFs found in: {INPUT_DIR}")
        exit(1)
    
    print(f"📄 Found {len(pdf_files)} PDFs")
    print(f"📂 Output: {OUTPUT_DIR}")
    print(f"📝 Debug: {DEBUG_DIR}\n")
    
    # Process each PDF
    results = {"amazon": 0, "flipkart": 0, "zomato": 0, "blinkit": 0, "instamart": 0, "failed": 0}
    
    for pdf_file in sorted(pdf_files):
        out_path = process_invoice(str(pdf_file), OUTPUT_DIR)
        if out_path:
            for brand in results.keys():
                if f"_{brand}_" in out_path:
                    results[brand] += 1
                    break
        else:
            results["failed"] += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ Amazon: {results['amazon']} invoices")
    print(f"✅ Flipkart: {results['flipkart']} invoices")
    print(f"✅ Zomato: {results['zomato']} invoices")
    print(f"✅ Blinkit: {results['blinkit']} invoices")
    print(f"✅ Instamart: {results['instamart']} invoices")
    print(f"❌ Failed: {results['failed']} invoices")
    total_success = sum(results.values()) - results['failed']
    print(f"\n📊 Total: {total_success}/{len(pdf_files)} processed ✅")
    print("=" * 60)
