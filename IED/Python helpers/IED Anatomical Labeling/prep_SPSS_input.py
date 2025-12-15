import pandas as pd
import numpy as np
import os

def prep_data_long():
    # File configuration
    input_file = 'Final_Matched_and_Collapsed_Stats.xlsx'
    sheet_name = 'Merged_Detailed_Data'
    output_file = 'Prepped_Merged_Long_Format.csv'
    
    print(f"Loading data from {input_file} (Sheet: {sheet_name})...")
    
    try:
        df = pd.read_excel(input_file, sheet_name=sheet_name)
        
        # 1. INITIAL SETUP & CLEANING
        # ---------------------------
        df['Data_Type'] = 'Original'

        # Ensure data is sorted for the odd/even filling logic
        df.sort_values(by=['Session_ID', 'Channel'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # 2. FILLING LOGIC (Odd rows grab from Even)
        # ------------------------------------------
        next_row = df.shift(-1)
        
        is_odd_channel = (df['Channel'] % 2 != 0)
        is_pair_aligned = (next_row['Channel'] == df['Channel'] + 1)
        is_same_session = (next_row['Session_ID'] == df['Session_ID'])
        
        fill_mask = is_odd_channel & is_pair_aligned & is_same_session
        
        print(f"Found {fill_mask.sum()} odd rows to fill from even neighbors.")
        
        cols_to_fill = [
            'TimeSlice_Val', 'CenterSlice_Val', 
            'Voltage_GroundZero_Val', 'Voltage_AfterSpike_Val'
        ]
        
        for col in cols_to_fill:
            if col in df.columns:
                df.loc[fill_mask, col] = next_row.loc[fill_mask, col]
        
        # Mark filled rows
        df.loc[fill_mask, 'Data_Type'] = 'Interpolated_For_Viz'
        
        # Handle Theta for Channel 64
        if 'Theta_Val' in df.columns:
            df.loc[df['Channel'] == 64, 'Theta_Val'] = np.nan

        # 3. RESHAPING: WIDE TO LONG
        # --------------------------
        print("Reshaping data to Long format (GZ vs AS)...")
        
        # Identify "Metadata" columns (everything except the value columns we are melting)
        value_cols = [
            'TimeSlice_Val', 'CenterSlice_Val', 
            'Voltage_GroundZero_Val', 'Voltage_AfterSpike_Val'
        ]
        id_vars = [c for c in df.columns if c not in value_cols]

        # --- Create GZ (Ground Zero) Subset ---
        df_gz = df[id_vars].copy()
        df_gz['TimeFrame'] = 'GZ'
        df_gz['CSD_Val'] = df['CenterSlice_Val']
        df_gz['Voltage_Val'] = df['Voltage_GroundZero_Val']

        # --- Create AS (After Spike) Subset ---
        df_as = df[id_vars].copy()
        df_as['TimeFrame'] = 'AS'
        df_as['CSD_Val'] = df['TimeSlice_Val']
        df_as['Voltage_Val'] = df['Voltage_AfterSpike_Val']

        # --- Combine ---
        long_df = pd.concat([df_gz, df_as], ignore_index=True)
        
        # Sort for cleanliness (Group -> Mouse -> Channel -> TimeFrame)
        long_df.sort_values(by=['Group', 'Mouse', 'Session_ID', 'Channel', 'TimeFrame'], inplace=True)

        # 4. SAVE
        # -------
        long_df.to_csv(output_file, index=False)
        print(f"Successfully saved Long Format data to: {output_file}")
        print(f"Total Rows: {len(long_df)} (Original N={len(df)} x 2 TimeFrames)")
        print("Columns created: 'TimeFrame', 'CSD_Val', 'Voltage_Val'")
        print("NOTE: Use 'Data_Type' == 'Original' for statistics.")

    except FileNotFoundError:
        print(f"Error: Could not find file '{input_file}'.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    prep_data_long()