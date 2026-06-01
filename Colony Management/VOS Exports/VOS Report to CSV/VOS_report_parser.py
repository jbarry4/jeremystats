"""
Filename: parse_mouse_report_v3.py
Description: Parses the KCNT1 lab report PDF.
             Splits cards by 'X0-145', takes the top 3 per page,
             extracts metadata and notes. 
             *NEW*: Identifies multiple mice in a single cage based on 
             line breaks in the Notes, and creates a separate CSV row for each.
"""

import pdfplumber
import csv
import re

# --- CONFIGURATION ---
INPUT_PDF_FILENAME = 'VOS Report 052826.pdf'
OUTPUT_CSV_FILENAME = 'VOS Report 052826.csv'

# Date stamp is pulled from the filename automatically (e.g. '052826')
_stamp = re.search(r'\d{6}', INPUT_PDF_FILENAME)
STAMP  = _stamp.group() if _stamp else ''

# Output column order: first 4 get the date stamp, rest follow unchanged
COLUMN_MAP = [
    ('Extracted Sorting ID', f'Extracted Sorting ID {STAMP}'),
    ('Cage Card',            f'Cage Card {STAMP}'),
    ('DOB',                  f'DOB {STAMP}'),
    ('Sex',                  f'Sex {STAMP}'),
    ('Strain',               'Strain'),
    ('Notes',                'Notes'),
    ('Source Page',          'Source Page'),
    ('Position on Page',     'Position on Page'),
    ('Raw Card Text',        'Raw Card Text'),
]

def extract_all_ids(notes_text):
    """
    Finds ALL 3 or 4 digit Mouse IDs in the notes.
    It skips lines containing an 'x' (which usually indicate the parents),
    and collects all other standalone 3/4 digit numbers.
    """
    if not notes_text:
        return [0]
        
    lines = notes_text.split('\n')
    valid_ids = []
    
    for line in lines:
        # Skip lines that look like parent pairings (e.g., '328x313' or '329 (M) x 302 (F)')
        if 'x' in line.lower():
            continue
            
        # Find all 3 to 4 digit numbers on this specific line
        numbers = re.findall(r'\b\d{3,4}\b', line)
        
        # Add them to our list of valid IDs
        for num in numbers:
            valid_ids.append(int(num))
            
    # If we couldn't find any valid offspring IDs, return a default of 0
    if not valid_ids:
        return [0]
        
    return valid_ids

def parse_pdf_to_csv():
    print(f"[STATUS] Opening PDF: '{INPUT_PDF_FILENAME}'...")
    all_mouse_records = []

    try:
        with pdfplumber.open(INPUT_PDF_FILENAME) as pdf:
            print(f"[STATUS] Found {len(pdf.pages)} pages. Processing...")
            
            for page_num, page in enumerate(pdf.pages):
                current_page = page_num + 1
                text = page.extract_text()
                
                if not text:
                    continue
                
                # --- SPLIT THE PAGE INTO CARDS ---
                raw_blocks = text.split('X0-145')
                card_blocks = [block.strip() for block in raw_blocks if len(block.strip()) > 10]
                
                # Grab ONLY the top 3 cards from this page
                top_3_cards = card_blocks[:3]
                
                for i, card_text in enumerate(top_3_cards):
                    # Set up the base record for this card
                    base_record = {
                        'Source Page': current_page,
                        'Position on Page': i + 1,
                        'Cage Card': '',
                        'Sex': '',
                        'Strain': '',
                        'DOB': '',
                        'Notes': '',
                        'Extracted Sorting ID': 0,
                        'Raw Card Text': 'X0-145 ' + ' '.join(card_text.split('\n'))
                    }
                    
                    # 1. EXTRACT CAGE CARD
                    cc_match = re.search(r'(CC-\d+(?:-\d+)?)', card_text)
                    if cc_match:
                        base_record['Cage Card'] = cc_match.group(1)
                        
                    # 2. EXTRACT SEX 
                    sex_match = re.search(r'Sex\s+([A-Za-z]+)', card_text)
                    if sex_match:
                        base_record['Sex'] = sex_match.group(1)
                        
                    # 3. EXTRACT STRAIN 
                    strain_match = re.search(r'Strain\s+(.*?)(?=\n|Code)', card_text)
                    if strain_match:
                        base_record['Strain'] = strain_match.group(1).strip()
                        
                    # 4. EXTRACT DOB 
                    dob_match = re.search(r'DOB\s+([\d/-]+)', card_text)
                    if dob_match:
                        base_record['DOB'] = dob_match.group(1)
                        
                    # 5. EXTRACT NOTES AND SPLIT MULTIPLE MICE
                    notes_match = re.search(r'Notes\s+(.*?)(?=Created)', card_text, re.DOTALL)
                    if notes_match:
                        notes_raw = notes_match.group(1).strip()
                        
                        # Save the cleaned-up notes for the CSV
                        base_record['Notes'] = ' | '.join(notes_raw.split('\n'))
                        
                        # --- THE MULTI-MOUSE MAGIC HAPPENS HERE ---
                        # Extract all IDs found in the notes
                        extracted_ids = extract_all_ids(notes_raw)
                        
                        # For every ID found, duplicate the base record, assign the specific ID, and save it
                        for mouse_id in extracted_ids:
                            new_record = base_record.copy()
                            new_record['Extracted Sorting ID'] = mouse_id
                            all_mouse_records.append(new_record)
                    else:
                        # If no notes were found at all, just append the base record with 0 as ID
                        all_mouse_records.append(base_record)

    except Exception as e:
        print(f"[ERROR] Failed during PDF parsing: {e}")
        return

    if not all_mouse_records:
        print("[WARNING] No records found to save.")
        return

    # --- SORT BY THE EXTRACTED MOUSE ID ---
    print(f"[STATUS] Extracted {len(all_mouse_records)} individual mice. Sorting numerically...")
    all_mouse_records.sort(key=lambda x: x['Extracted Sorting ID'])

    # --- WRITE TO CSV ---
    print(f"[STATUS] Writing records to '{OUTPUT_CSV_FILENAME}'...")

    out_headers = [new for _, new in COLUMN_MAP]

    try:
        with open(OUTPUT_CSV_FILENAME, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=out_headers)
            writer.writeheader()
            for rec in all_mouse_records:
                writer.writerow({new: rec[orig] for orig, new in COLUMN_MAP})
        print("[SUCCESS] Done! Your multi-mouse CSV is ready.")
    except Exception as e:
        print(f"[ERROR] Failed to write CSV: {e}")

if __name__ == "__main__":
    parse_pdf_to_csv()