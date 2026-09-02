import os
import pandas as pd
import numpy as np
import scipy.io
import re

# ================= CONFIGURATION =================
target_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3'
output_file = 'Simple_CSD_Collection_with_Theta.xlsx'

# CSV Files to look for (Relative to session folder)
csv_targets = {
    'TimeSlice': os.path.join('CSD Center Slices Output', 'CSD_Timeslices_Values_SOLID.csv'),
    'CenterSlice': os.path.join('CSD Center Slices Output', 'CSD_CenterSlices_Values_SOLID.csv'),
    # Voltage Raster location
    'VoltageRaster': os.path.join('Voltage Raster Output', 'VoltageRaster_Avg_Values_SOLID.csv')
}

# MATLAB File to look for
mat_target_rel = os.path.join('Theta_Plots', 'MeanNegative.mat')
# =================================================

def parse_voltage_time(col_name):
    """
    Parses column headers like 'T_m2p27ms' to float -2.27
    and 'T_12p17ms' to float 12.17.
    Returns None if format doesn't match.
    """
    # Regex: T_ (optional m) (digits) p (digits) ms
    match = re.match(r'^T_(m?)(\d+)p(\d+)ms$', col_name)
    if match:
        is_negative = match.group(1) == 'm'
        integer_part = match.group(2)
        decimal_part = match.group(3)
        
        value = float(f"{integer_part}.{decimal_part}")
        if is_negative:
            value = -value
        return value
    return None

def process_csv(file_path, data_type):
    """
    Reads CSVs. 
    Returns a dictionary of standardized series (Channels 1-32).
    keys = metric names (e.g. 'TimeSlice', 'Voltage_GroundZero')
    """
    try:
        df = pd.read_csv(file_path)
        results = {}

        # --- LOGIC FOR VOLTAGE RASTER (Time Windowing) ---
        if data_type == 'VoltageRaster':
            # Map column names to time values
            time_map = {}
            for col in df.columns:
                t = parse_voltage_time(col)
                if t is not None:
                    time_map[col] = t
            
            if not time_map:
                return None

            # Define Windows
            # Ground Zero: [-1, 1] ms
            gz_cols = [c for c, t in time_map.items() if -1.0 <= t <= 1.0]
            
            # After Spike: [2, 10] ms
            as_cols = [c for c, t in time_map.items() if 2.0 <= t <= 10.0]

            # Calculate Means
            if gz_cols:
                results['Voltage_GroundZero'] = df[gz_cols].mean(axis=1)
            else:
                results['Voltage_GroundZero'] = pd.Series(np.nan, index=df.index)

            if as_cols:
                results['Voltage_AfterSpike'] = df[as_cols].mean(axis=1)
            else:
                results['Voltage_AfterSpike'] = pd.Series(np.nan, index=df.index)

        # --- LOGIC FOR CSD (Simple Row Average) ---
        else:
            # CSD files typically have 'Evt_' prefixes
            data_cols = [c for c in df.columns if c.startswith('Evt_')]
            if not data_cols: 
                return None
            
            # Return using the original data_type as the key (e.g., 'TimeSlice')
            results[data_type] = df[data_cols].mean(axis=1)

        # --- STANDARDIZE TO 32 CHANNELS ---
        final_output = {}
        for key, series in results.items():
            # Container strictly for 32 rows (representing the sampled channels)
            std_series = pd.Series(index=range(1, 33), dtype=float)
            
            # Fill available data
            count = min(len(series), 32)
            std_series.iloc[:count] = series.iloc[:count].values
            final_output[key] = std_series
            
        return final_output

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def process_mat(file_path):
    """
    Reads .mat file for Theta MeanNegative.
    Expects a 64x1 or 1x64 array.
    """
    try:
        mat = scipy.io.loadmat(file_path)
        if 'MeanNegative' in mat:
            data = mat['MeanNegative']
            data = data.flatten()
            return pd.Series(data, index=range(1, len(data) + 1))
    except Exception as e:
        print(f"Error processing MAT {file_path}: {e}")
    return None

def collect_values():
    print(f"Scanning directory: {target_directory}...\n")
    
    # regex for session ID
    pattern = re.compile(r'(m\d+s\d+)', re.IGNORECASE)

    # Dictionary to hold collected data
    # Structure: {'TimeSlice': {session: series}, 'Voltage_GroundZero': {session: series}, ...}
    # Initialize with known keys plus potential new voltage keys
    master_collection = {
        'TimeSlice': {},
        'CenterSlice': {},
        'Voltage_GroundZero': {},
        'Voltage_AfterSpike': {},
        'Theta_MeanNegative': {}
    }

    try:
        items = os.listdir(target_directory)
    except FileNotFoundError:
        print("Directory not found.")
        return

    for folder_name in items:
        full_path = os.path.join(target_directory, folder_name)
        
        if os.path.isdir(full_path):
            match = pattern.search(folder_name)
            if match:
                session_id = match.group(1).lower()
                
                # 1. Process CSV Targets
                for sheet_key, rel_path in csv_targets.items():
                    target_abs_path = os.path.join(full_path, rel_path)
                    
                    if os.path.exists(target_abs_path):
                        # Returns a dict of series (e.g. {'Voltage_GroundZero': ..., 'Voltage_AfterSpike': ...})
                        result_dict = process_csv(target_abs_path, sheet_key)
                        
                        if result_dict:
                            for metric_name, series in result_dict.items():
                                if metric_name not in master_collection:
                                    master_collection[metric_name] = {}
                                master_collection[metric_name][session_id] = series

                # 2. Process Theta MAT
                mat_path = os.path.join(full_path, mat_target_rel)
                if os.path.exists(mat_path):
                    res = process_mat(mat_path)
                    if res is not None:
                        master_collection['Theta_MeanNegative'][session_id] = res

    # --- STEP 2: WRITE TO EXCEL ---
    # Filter out empty dictionaries
    active_sheets = {k: v for k, v in master_collection.items() if len(v) > 0}

    if active_sheets:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            for sheet_name, data_dict in active_sheets.items():
                df = pd.DataFrame(data_dict)
                df = df.sort_index(axis=1) # Sort sessions alphabetically
                df.index.name = 'Channel'
                
                # CSD and Voltage are typically 32 rows
                if sheet_name != 'Theta_MeanNegative':
                    df = df.reindex(range(1, 33))
                
                df.to_excel(writer, sheet_name=sheet_name)
                print(f"Sheet '{sheet_name}': Added {len(df.columns)} sessions. (Rows: {len(df)})")
        
        print(f"\nSuccess! Spreadsheet saved as '{output_file}'")
    else:
        print("No matching data files found in any subfolders.")

if __name__ == "__main__":
    collect_values()