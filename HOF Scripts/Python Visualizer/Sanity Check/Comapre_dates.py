import pandas as pd
import re

# Hardcoded Paths
med_path = r"D:\HOF DATA\ACTIVE DATA\med_events.csv"
global_path = r"D:\HOF DATA\ACTIVE DATA\All_Events_Summary_Global_Timeline_Input.xlsx"

# 1. Parse MED Events
try:
    df_med = pd.read_csv(med_path)
    
    # Extract strict YYYY-MM-DD from the string
    def extract_med_date(filename):
        match = re.search(r'!(\d{4}-\d{2}-\d{2})', str(filename))
        return match.group(1) if match else None

    med_files = df_med[['file']].drop_duplicates().copy()
    med_files['Date'] = med_files['file'].apply(extract_med_date)
    
    # Group by date
    med_grouped = med_files.groupby('Date')['file'].apply(lambda x: ' | '.join(x)).reset_index(name='MED_Files')

except Exception as e:
    print(f"Failed parsing MED events: {e}")
    med_grouped = pd.DataFrame(columns=['Date', 'MED_Files'])

# 2. Parse Global Timeline
try:
    df_global = pd.read_excel(global_path)
    
    # Extract MMDDYY from the end of string and convert to YYYY-MM-DD
    def extract_global_date(session):
        match = re.search(r'_(\d{2})(\d{2})(\d{2})$', str(session))
        if match:
            m, d, y = match.groups()
            return f"20{y}-{m}-{d}"
        return None

    global_sessions = df_global[['Session']].drop_duplicates().copy()
    global_sessions['Date'] = global_sessions['Session'].apply(extract_global_date)
    
    # Group by date
    global_grouped = global_sessions.groupby('Date')['Session'].apply(lambda x: ' | '.join(x)).reset_index(name='Global_Sessions')

except Exception as e:
    print(f"Failed parsing Global Timeline: {e}")
    global_grouped = pd.DataFrame(columns=['Date', 'Global_Sessions'])

# 3. Merge and Output
merged = pd.merge(med_grouped, global_grouped, on='Date', how='outer').fillna('None')
merged = merged.sort_values(by='Date').reset_index(drop=True)

# Expand column width for display
pd.set_option('display.max_colwidth', None)
print(merged.to_string(index=False))