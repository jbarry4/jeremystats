import pandas as pd
import numpy as np
import os

# ================= CONFIGURATION =================
target_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3'

# Input File Names
anatomical_file = 'Combined_Anatomical_Details_Grouped.xlsx'
values_file = 'Simple_CSD_Collection_with_Theta.xlsx'

# Output File Name
output_file = 'Final_Matched_and_Collapsed_Stats.xlsx'

# SETTING: Handle missing Channel 64 in Theta
IGNORE_MISSING_THETA_64 = True 
# =================================================

def unpivot_data(df, value_name, channel_mapping_type='direct'):
    """
    Converts Wide format (Cols=Sessions) to Long format.
    channel_mapping_type:
      'even': Row 1 -> Ch 2, Row 2 -> Ch 4 (Used for CSD & Voltage)
      'direct': Row 1 -> Ch 1 (Used for Theta)
    """
    session_cols = [c for c in df.columns if str(c).lower() != 'channel']
    melted_list = []
    
    for session_col in session_cols:
        clean_session_id = str(session_col).strip().lower()
        session_data = df[session_col].values
        
        if 'Channel' in df.columns:
            source_indices = df['Channel'].values
        else:
            source_indices = np.arange(1, len(df) + 1)

        for idx, val in enumerate(session_data):
            source_idx = source_indices[idx]
            
            if channel_mapping_type == 'even':
                # Rule: Row 1 (Index 1) is actually Channel 2
                real_channel = int(source_idx) * 2
            else:
                real_channel = int(source_idx)
                
            melted_list.append({
                'Session_ID': clean_session_id,
                'Channel': int(real_channel),
                value_name: val
            })
            
    return pd.DataFrame(melted_list)

def process_matching():
    anat_path = os.path.join(target_directory, anatomical_file)
    vals_path = os.path.join(target_directory, values_file)
    
    print(f"Reading Anatomical Map: {anat_path}")
    print(f"Reading Data Values: {vals_path}\n")

    try:
        # 1. LOAD ANATOMICAL MAP
        df_anat = pd.read_excel(anat_path)
        df_anat['Session_ID'] = df_anat['Session_ID'].astype(str).str.strip().str.lower()
        
        # Ensure 'Row' maps to 'Channel'
        if 'Row' in df_anat.columns:
             df_anat['Channel'] = df_anat['Row'].astype(int)
        
        print(f"Loaded {len(df_anat)} anatomical rows.")

        # 2. LOAD & TRANSFORM VALUES
        
        # --- A. TimeSlice (Even Channels) ---
        print("Processing TimeSlice...")
        df_time = pd.read_excel(vals_path, sheet_name='TimeSlice')
        df_time_long = unpivot_data(df_time, 'TimeSlice_Val', channel_mapping_type='even')

        # --- B. CenterSlice (Even Channels) ---
        print("Processing CenterSlice...")
        df_center = pd.read_excel(vals_path, sheet_name='CenterSlice')
        df_center_long = unpivot_data(df_center, 'CenterSlice_Val', channel_mapping_type='even')

        # --- C. Voltage GroundZero (Even Channels) ---
        print("Processing Voltage GroundZero...")
        df_v_gz = pd.read_excel(vals_path, sheet_name='Voltage_GroundZero')
        df_v_gz_long = unpivot_data(df_v_gz, 'Voltage_GroundZero_Val', channel_mapping_type='even')

        # --- D. Voltage AfterSpike (Even Channels) ---
        print("Processing Voltage AfterSpike...")
        df_v_as = pd.read_excel(vals_path, sheet_name='Voltage_AfterSpike')
        df_v_as_long = unpivot_data(df_v_as, 'Voltage_AfterSpike_Val', channel_mapping_type='even')

        # --- E. Theta (Direct Mapping) ---
        print("Processing Theta MeanNegative...")
        df_theta = pd.read_excel(vals_path, sheet_name='Theta_MeanNegative')
        df_theta_long = unpivot_data(df_theta, 'Theta_Val', channel_mapping_type='direct')

        # 3. MERGE DATA
        print("Merging datasets...")
        df_merged = pd.merge(df_anat, df_time_long, on=['Session_ID', 'Channel'], how='left')
        df_merged = pd.merge(df_merged, df_center_long, on=['Session_ID', 'Channel'], how='left')
        df_merged = pd.merge(df_merged, df_v_gz_long, on=['Session_ID', 'Channel'], how='left')
        df_merged = pd.merge(df_merged, df_v_as_long, on=['Session_ID', 'Channel'], how='left')
        df_merged = pd.merge(df_merged, df_theta_long, on=['Session_ID', 'Channel'], how='left')

        # 4. HANDLE "IGNORED" LOGIC FOR THETA
        if IGNORE_MISSING_THETA_64:
            mask_64 = (df_merged['Channel'] == 64) & (df_merged['Theta_Val'].isna())
            df_merged['Theta_Display'] = df_merged['Theta_Val']
            df_merged.loc[mask_64, 'Theta_Display'] = "Ignored"
        else:
            df_merged['Theta_Display'] = df_merged['Theta_Val']

        # 5. COLLAPSE BY REGION
        print("Collapsing statistics by Region...")
        
        numeric_cols = [
            'TimeSlice_Val', 
            'CenterSlice_Val', 
            'Voltage_GroundZero_Val', 
            'Voltage_AfterSpike_Val', 
            'Theta_Val'
        ]
        
        for col in numeric_cols:
            df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')

        group_cols = ['Mouse', 'Group', 'Type', 'Session_ID', 'Region']
        actual_group_cols = [c for c in group_cols if c in df_merged.columns]
        
        df_collapsed = df_merged.groupby(actual_group_cols)[numeric_cols].mean().reset_index()

        # 6. SAVE
        output_path = os.path.join(target_directory, output_file)
        
        # Prepare detailed export
        df_export_detailed = df_merged.drop(columns=['Theta_Val']).rename(columns={'Theta_Display': 'Theta_Val'})
        
        # Reorder columns
        first_cols = ['Mouse', 'Group', 'Type', 'Session_ID', 'Channel', 'Region']
        remaining = [c for c in df_export_detailed.columns if c not in first_cols]
        df_export_detailed = df_export_detailed[first_cols + remaining]

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_export_detailed.to_excel(writer, sheet_name='Merged_Detailed_Data', index=False)
            df_collapsed.to_excel(writer, sheet_name='Collapsed_by_Region', index=False)
            
        print("-" * 40)
        print(f"Success! File saved to: {output_file}")
        print("-" * 40)
        print("Preview (Collapsed):")
        print(df_collapsed[['Mouse', 'Region', 'Voltage_GroundZero_Val']].head())

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    process_matching()