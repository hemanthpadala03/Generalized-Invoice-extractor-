# base.py
from abc import ABC, abstractmethod
import pandas as pd
from validators import InvoiceData, LineItem

class BaseExtractor(ABC):
    """Abstract base class for all invoice extractors"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
    
    @abstractmethod
    def extract_header(self) -> InvoiceData:
        """Extract header/metadata fields"""
        pass
    
    @abstractmethod
    def extract_line_items(self) -> pd.DataFrame:
        """Extract line items"""
        pass
    
    def extract(self) -> tuple:
        """Main extraction method - returns (header_data, line_items_df)"""
        try:
            header = self.extract_header()
            items = self.extract_line_items()
            return header.dict(), items
        except Exception as e:
            print(f"Error: {str(e)}")
            return {}, pd.DataFrame()


# Now create subclasses for each brand

from extractors_amazon import extract_with_rules_amazon, extract_cluster_text_amazon, extract_totals_amazon, extract_item_table_amazon
from extractors_flipkart import extract_cluster_text, extract_fields, extract_line_items as extract_line_items_flipkart
from extractors_zomato import extract_with_rules_zomato, extract_table_and_totals
from extractors_blinkit import extract_header as extract_header_blinkit, extract_items_and_totals as extract_items_and_totals_blinkit
from extractors_instamart import extract_header as extract_header_instamart, extract_items_and_totals as extract_items_and_totals_instamart
import pdfplumber

class AmazonExtractor(BaseExtractor):
    """Amazon invoice extractor"""
    
    def extract_header(self) -> InvoiceData:
        cluster_text = extract_cluster_text_amazon(self.pdf_path)
        data = extract_with_rules_amazon(cluster_text)
        tax, total = extract_totals_amazon(self.pdf_path)
        data["total_tax"] = tax
        data["total_amount"] = total
        return InvoiceData(**data)
    
    def extract_line_items(self) -> pd.DataFrame:
        return extract_item_table_amazon(self.pdf_path)


class FlipkartExtractor(BaseExtractor):
    """Flipkart invoice extractor"""
    
    def extract_header(self) -> InvoiceData:
        cluster_text = extract_cluster_text(self.pdf_path)
        data = extract_fields(cluster_text)
        return InvoiceData(**data)
    
    def extract_line_items(self) -> pd.DataFrame:
        return extract_line_items_flipkart(self.pdf_path)


class ZomatoExtractor(BaseExtractor):
    """Zomato invoice extractor"""
    
    def extract_header(self) -> InvoiceData:
        with pdfplumber.open(self.pdf_path) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        data = extract_with_rules_zomato(full_text)
        line_df, net_amt, tax_amt, total_amt = extract_table_and_totals(self.pdf_path)
        data["total_tax"] = tax_amt
        data["total_amount"] = total_amt
        return InvoiceData(**data)
    
    def extract_line_items(self) -> pd.DataFrame:
        line_df, _, _, _ = extract_table_and_totals(self.pdf_path)
        return line_df


class BlinkitExtractor(BaseExtractor):
    """Blinkit invoice extractor"""
    
    def extract_header(self) -> InvoiceData:
        with pdfplumber.open(self.pdf_path) as pdf:
            page = pdf.pages[0]
            table = page.extract_tables()[0]
            df = pd.DataFrame(table)
        data = extract_header_blinkit(df)
        items_df, tax, total = extract_items_and_totals_blinkit(df)
        data["total_tax"] = tax
        data["total_amount"] = total
        return InvoiceData(**data)
    
    def extract_line_items(self) -> pd.DataFrame:
        with pdfplumber.open(self.pdf_path) as pdf:
            page = pdf.pages[0]
            table = page.extract_tables()[0]
            df = pd.DataFrame(table)
        items_df, _, _ = extract_items_and_totals_blinkit(df)
        return items_df


class InstamartExtractor(BaseExtractor):
    """Instamart invoice extractor"""
    
    def extract_header(self) -> InvoiceData:
        header_data = extract_header_instamart(self.pdf_path)
        item_df, total_tax, total_amount = extract_items_and_totals_instamart(self.pdf_path)
        header_data["total_tax"] = total_tax
        header_data["total_amount"] = total_amount
        return InvoiceData(**header_data)
    
    def extract_line_items(self) -> pd.DataFrame:
        item_df, _, _ = extract_items_and_totals_instamart(self.pdf_path)
        return item_df
