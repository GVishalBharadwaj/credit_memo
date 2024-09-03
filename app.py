# app.py

from flask import Flask, request, render_template, jsonify
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import json
from pdfminer.high_level import extract_text
import re
import logging
import os
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Define UI fields
ui_fields = {
    "Customer Name": "",
    "Invoice Number": "",
    "Total Amount": "",
    "Issue Date": "",
    "Line Items": []
}

def extract_credit_memo_data(pdf_text):
    data = {}

    # Extract customer name
    customer_match = re.search(r'Customer:\s*(.*)', pdf_text)
    if customer_match:
        data['customer'] = customer_match.group(1).strip()
    else:
        app.logger.warning("Customer name not found in PDF")

    # Extract invoice number
    inv_match = re.search(r'Invoice\s*#?\s*(\w+[-]?\d+)', pdf_text, re.IGNORECASE)
    if inv_match:
        data['inv_num'] = inv_match.group(1)
    else:
        app.logger.warning("Invoice number not found in PDF")

    # Extract total amount
    total_match = re.search(r'Total\s*:\s*\$?\s*([\d,]+\.?\d*)', pdf_text, re.IGNORECASE)
    if total_match:
        data['total'] = float(total_match.group(1).replace(',', ''))
    else:
        app.logger.warning("Total amount not found in PDF")

    # Extract date
    date_match = re.search(r'Date\s*:\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})', pdf_text, re.IGNORECASE)
    if date_match:
        data['date_issued'] = date_match.group(1)
    else:
        app.logger.warning("Date not found in PDF")

    # Extract line items (updated to account for dash at beginning)
    items_section = re.findall(r'-\s*(.*?)\s+(\d+)\s+\$(\d+\.?\d*)', pdf_text)
    data['items'] = [{"description": item[0].strip(), "quantity": int(item[1]), "price": float(item[2])} for item in items_section]
    if not data['items']:
        app.logger.warning("No line items found in PDF")

    return data

def fuzzy_match(target, choices, threshold=70):
    match = process.extractOne(target, choices, scorer=fuzz.token_sort_ratio)
    return match if match[1] >= threshold else None

def match_fields(credit_memo, ui_fields):
    matched_fields = {}
    for ui_field in ui_fields:
        match = fuzzy_match(ui_field, credit_memo.keys())
        if match:
            matched_fields[ui_field] = credit_memo[match[0]]
        else:
            matched_fields[ui_field] = "No match found"
    return matched_fields

@app.route('/', methods=['GET', 'POST'])
def upload_credit_memo():
    if request.method == 'POST':
        app.logger.info("Received POST request")
        
        try:
            if 'file' not in request.files:
                app.logger.error("No file part in the request")
                return jsonify({"error": "No file part"}), 400
            
            file = request.files['file']
            
            if file.filename == '':
                app.logger.error("No selected file")
                return jsonify({"error": "No selected file"}), 400
            
            if file and file.filename.lower().endswith('.pdf'):
                app.logger.info(f"Processing file: {file.filename}")
                
                # Save the file temporarily
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, secure_filename(file.filename))
                file.save(temp_path)
                
                try:
                    pdf_text = extract_text(temp_path)
                    app.logger.debug(f"Extracted text: {pdf_text[:100]}...")  # Log first 100 characters
                except Exception as e:
                    app.logger.error(f"Error extracting text from PDF: {str(e)}", exc_info=True)
                    return jsonify({"error": f"Error extracting text from PDF: {str(e)}"}), 400
                finally:
                    # Clean up the temporary file
                    os.remove(temp_path)
                
                credit_memo = extract_credit_memo_data(pdf_text)
                app.logger.debug(f"Extracted credit memo data: {credit_memo}")
                matched_fields = match_fields(credit_memo, ui_fields)
                app.logger.info("Processing completed successfully")
                return jsonify({"matched_fields": matched_fields, "extracted_json": credit_memo})
            else:
                app.logger.error(f"Invalid file type: {file.filename}")
                return jsonify({"error": "Invalid file type. Please upload a PDF."}), 400
        except Exception as e:
            app.logger.error(f"Error processing file: {str(e)}", exc_info=True)
            return jsonify({"error": str(e)}), 400
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)
