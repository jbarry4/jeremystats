import os
import re
import pandas as pd

# ================= CONFIGURATION =================
# Replace this with the path to your folder
target_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3' 

# Output filename
output_file = 'session_ids_log.xlsx'
# =================================================

def extract_session_ids(directory):
    data_list = []

    # Regex pattern explanation:
    # [mM] matches 'm' or 'M'
    # \d+  matches one or more digits
    # [sS] matches 's' or 'S'
    # \d+  matches one or more digits
    pattern = re.compile(r'(m\d+s\d+)', re.IGNORECASE)

    print(f"Scanning directory: {directory}...\n")

    # Get all items in the directory
    try:
        items = os.listdir(directory)
    except FileNotFoundError:
        print("Error: The specified directory was not found.")
        return

    for folder_name in items:
        # Construct full path to check if it's a folder (ignoring random files)
        full_path = os.path.join(directory, folder_name)
        
        if os.path.isdir(full_path):
            match = pattern.search(folder_name)
            
            if match:
                # Found a pattern like m3s1
                session_id = match.group(1)
            else:
                # No pattern found (e.g., "Collected_results")
                session_id = "Ignored"
            
            # Append to our data list
            data_list.append({
                'Full Folder Name': folder_name,
                'Session ID': session_id
            })

    # Create DataFrame and save to Excel
    if data_list:
        df = pd.DataFrame(data_list)
        
        # Sort for neatness (optional)
        df = df.sort_values(by='Full Folder Name')
        
        df.to_excel(output_file, index=False)
        print(f"Success! Spreadsheet saved as '{output_file}' in your current directory.")
        print("-" * 30)
        print(df.head()) # Print first few rows to console for verification
    else:
        print("No folders found in the target directory.")

if __name__ == "__main__":
    extract_session_ids(target_directory)