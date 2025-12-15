import os
import re
import glob
import pandas as pd

# ================= CONFIGURATION =================
# Path to your main data folder
target_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3'

# Path to the Mice Group metadata file
mice_group_file = 'Mice_group.csv'

# Output filename
output_file = 'Combined_Anatomical_Details_Grouped.xlsx'
# =================================================

def load_metadata(path):
    """Loads the Mice_group.csv to a dictionary for easy lookup."""
    if not os.path.exists(path):
        print(f"Warning: Metadata file '{path}' not found. Metadata columns will be empty.")
        return None
    
    try:
        df = pd.read_csv(path)
        # Clean whitespace from column names and string values
        df.columns = df.columns.str.strip()
        
        # Ensure Simple_Name is the string format we expect (lowercase)
        if 'Simple_Name' in df.columns:
            df['Simple_Name'] = df['Simple_Name'].astype(str).str.strip().str.lower()
            return df
        else:
            print("Error: 'Simple_Name' column missing from Mice_group.csv")
            return None
    except Exception as e:
        print(f"Error reading metadata: {e}")
        return None

def combine_anatomical_files():
    # 1. Load Metadata
    meta_df = load_metadata(mice_group_file)
    
    print(f"Scanning directory: {target_directory}...\n")
    
    all_data = []
    files_found = 0
    
    # Regex pattern from getSessionDetail.py
    pattern = re.compile(r'(m\d+s\d+)', re.IGNORECASE)

    # 2. Iterate Folders
    try:
        items = os.listdir(target_directory)
    except FileNotFoundError:
        print("Error: Directory not found.")
        return

    for folder_name in items:
        full_path = os.path.join(target_directory, folder_name)

        if os.path.isdir(full_path):
            # Apply regex to find session ID (Simple Name)
            match = pattern.search(folder_name)
            
            if match:
                session_id = match.group(1).lower() # Normalize to lowercase (e.g., m13s17)
                
                # 3. Look for the specific CSV using a wildcard
                # This finds any file ending in _anatomical_detail.csv
                search_pattern = os.path.join(full_path, '*_anatomical_detail.csv')
                found_files = glob.glob(search_pattern)
                
                if found_files:
                    # Take the first match (usually there is only one)
                    target_file = found_files[0]
                    file_basename = os.path.basename(target_file)
                    
                    try:
                        # Read the anatomical CSV
                        df = pd.read_csv(target_file)
                        
                        # 4. Merge Metadata
                        # Default values if no metadata match found
                        mouse_val = "Unknown"
                        group_val = "Unknown"
                        type_val = "Unknown"
                        
                        if meta_df is not None:
                            # Find row where Simple_Name matches our session_id
                            meta_row = meta_df[meta_df['Simple_Name'] == session_id]
                            
                            if not meta_row.empty:
                                mouse_val = meta_row.iloc[0].get('Mouse', mouse_val)
                                group_val = meta_row.iloc[0].get('Group', group_val)
                                type_val = meta_row.iloc[0].get('Type', type_val)

                        # 5. Add Columns to the Dataframe
                        # Insert in reverse order so they appear at the front
                        df.insert(0, 'Source_File', file_basename)
                        df.insert(0, 'Session_ID', session_id)
                        df.insert(0, 'Type', type_val)
                        df.insert(0, 'Group', group_val)
                        df.insert(0, 'Mouse', mouse_val)
                        
                        all_data.append(df)
                        files_found += 1
                        print(f"[MATCH] {folder_name} -> Found: {file_basename}")
                        
                    except Exception as e:
                        print(f"[ERROR] Reading {file_basename}: {e}")
                else:
                    # Folder matches regex, but no anatomical file found
                    # print(f"[SKIP] No anatomical file in {folder_name}")
                    pass

    # 6. Save Result
    if all_data:
        print(f"\nCombining {files_found} files...")
        final_df = pd.concat(all_data, ignore_index=True)
        
        final_df.to_excel(output_file, index=False)
        print("-" * 40)
        print(f"Success! Saved to '{output_file}'")
        print(f"Total Rows: {len(final_df)}")
        print("-" * 40)
        print(final_df.head())
    else:
        print("\nNo matching anatomical files found.")

if __name__ == "__main__":
    combine_anatomical_files()