import pandas as pd
import numpy as np
import os

# ==========================================
# CONFIGURATION
# ==========================================
input_file = 'Final_Matched_and_Collapsed_Stats.xlsx'
output_file = 'Golden_Template_Full_Probe.xlsx'

# The specific anatomical order (Internal regions)
internal_regions = [
    'CA1 SLM', 
    'DG OML1', 
    'DG MML1', 
    'DG GCL1', 
    'HIL', 
    'DG GCL2', 
    'DG MML2', 
    'DG OML2'
]

# Final order including padding
full_region_order = ['ABOVE CA1 SLM'] + internal_regions + ['BELOW DG OML2']

def generate_golden_template():
    print("========================================================")
    print(f"STEP 1: Loading data from {input_file}...")
    
    # 1. Load Data
    # Fallback logic for CSV
    csv_name = 'Final_Matched_and_Collapsed_Stats.xlsx - Merged_Detailed_Data.csv'
    if os.path.exists(csv_name):
        print(f" -> Loading from CSV: {csv_name}")
        df = pd.read_csv(csv_name)
    else:
        # Try Excel
        try:
            df = pd.read_excel(input_file, sheet_name='Merged_Detailed_Data')
        except:
            df = pd.read_excel(input_file, sheet_name=0)
    
    print(f" -> Loaded {len(df)} rows.")

    # 2. Identify Session Boundaries & Region Stats
    print("\n[INFO] Calculating region stats per session...")
    df['Region'] = df['Region'].astype(str).str.strip()
    
    # Filter for internal regions
    df_filtered = df[df['Region'].isin(internal_regions)].copy()
    
    # Group by Session+Region
    region_stats = df_filtered.groupby(['Session_ID', 'Region'])['Channel'].agg(['count', 'min', 'max']).reset_index()
    region_stats.rename(columns={'count': 'Thickness', 'min': 'Region_Min_Ch', 'max': 'Region_Max_Ch'}, inplace=True)
    
    # Get Session Boundaries (Actual recorded range)
    session_bounds = df.groupby('Session_ID')['Channel'].agg(['min', 'max']).reset_index()
    session_bounds.rename(columns={'min': 'Session_Min_Ch', 'max': 'Session_Max_Ch'}, inplace=True)
    
    # 3. Calculate "ABOVE" and "BELOW" Thicknesses
    print("[INFO] Calculating padding (ABOVE / BELOW)...")
    
    padding_rows = []
    
    for session in session_bounds['Session_ID'].unique():
        # Get CA1 SLM start for this session
        ca1_data = region_stats[(region_stats['Session_ID'] == session) & (region_stats['Region'] == 'CA1 SLM')]
        
        # Get DG OML2 end for this session
        oml2_data = region_stats[(region_stats['Session_ID'] == session) & (region_stats['Region'] == 'DG OML2')]
        
        # --- Calculate ABOVE ---
        if not ca1_data.empty:
            # Thickness is everything from 1 to Start-1
            ca1_start = ca1_data.iloc[0]['Region_Min_Ch']
            thick_above = max(0, ca1_start - 1)
            
            padding_rows.append({
                'Session_ID': session,
                'Region': 'ABOVE CA1 SLM',
                'Thickness': thick_above,
                'Region_Min_Ch': 1,
                'Region_Max_Ch': ca1_start - 1,
                'Session_Min_Ch': session_bounds[session_bounds['Session_ID'] == session]['Session_Min_Ch'].values[0],
                'Session_Max_Ch': session_bounds[session_bounds['Session_ID'] == session]['Session_Max_Ch'].values[0]
            })
            
        # --- Calculate BELOW ---
        if not oml2_data.empty:
            # Thickness is everything from End+1 to 64
            oml2_end = oml2_data.iloc[0]['Region_Max_Ch']
            thick_below = max(0, 64 - oml2_end)
            
            padding_rows.append({
                'Session_ID': session,
                'Region': 'BELOW DG OML2',
                'Thickness': thick_below,
                'Region_Min_Ch': oml2_end + 1,
                'Region_Max_Ch': 64,
                'Session_Min_Ch': session_bounds[session_bounds['Session_ID'] == session]['Session_Min_Ch'].values[0],
                'Session_Max_Ch': session_bounds[session_bounds['Session_ID'] == session]['Session_Max_Ch'].values[0]
            })
            
    # Combine everything
    padding_df = pd.DataFrame(padding_rows)
    # Merge padding stats back with main region stats
    region_stats = pd.merge(region_stats, session_bounds, on='Session_ID', how='left')
    full_stats = pd.concat([region_stats, padding_df], ignore_index=True)
    
    # 4. Apply Exclusion Logic (Strict Edges)
    print("[INFO] Applying strict exclusion...")
    
    def get_status(row):
        status = 'Kept (Internal)'
        
        if row['Region'] == 'CA1 SLM':
            # Check if it touches session min (usually 1)
            if row['Region_Min_Ch'] == row['Session_Min_Ch']:
                status = 'Excluded (Edge)'
        
        elif row['Region'] == 'DG OML2':
            # Check if it touches session max
            if row['Region_Max_Ch'] == row['Session_Max_Ch']:
                status = 'Excluded (Edge)'
                
        elif row['Region'] == 'ABOVE CA1 SLM':
            # If thickness is 0, it means CA1 SLM started at 1 -> Excluded
            if row['Thickness'] == 0:
                status = 'Excluded (Zero Thickness)'
                
        elif row['Region'] == 'BELOW DG OML2':
            # If thickness is 0, it means DG OML2 ended at 64 -> Excluded
            if row['Thickness'] == 0:
                status = 'Excluded (Zero Thickness)'
        
        return status

    full_stats['Status'] = full_stats.apply(get_status, axis=1)
    
    # 5. Compute Golden Template
    print("[INFO] Computing Final Golden Template (Sum=64)...")
    
    # Filter for Kept
    valid_df = full_stats[full_stats['Status'].str.startswith('Kept')]
    
    template = valid_df.groupby('Region')['Thickness'].mean().reset_index()
    template.rename(columns={'Thickness': 'Mean_Thickness'}, inplace=True)
    
    # Round to int
    template['Target_Thickness'] = template['Mean_Thickness'].round().astype(int)
    
    # Reorder
    template['Region'] = pd.Categorical(template['Region'], categories=full_region_order, ordered=True)
    template = template.sort_values('Region')
    
    # 6. Force Sum to 64
    current_sum = template['Target_Thickness'].sum()
    diff = 64 - current_sum
    
    print(f" -> Initial Sum: {current_sum}")
    print(f" -> Adjustment needed: {diff}")
    
    if diff != 0:
        # Adjustment Logic: Add/Sub diff from the largest "Padding" region
        try:
            above_idx = template[template['Region'] == 'ABOVE CA1 SLM'].index[0]
            below_idx = template[template['Region'] == 'BELOW DG OML2'].index[0]
            
            thick_above = template.loc[above_idx, 'Target_Thickness']
            thick_below = template.loc[below_idx, 'Target_Thickness']
            
            # Apply to whichever is larger
            if thick_above >= thick_below:
                template.loc[above_idx, 'Target_Thickness'] += diff
                print(f" -> Applied adjustment ({diff}) to ABOVE CA1 SLM")
            else:
                template.loc[below_idx, 'Target_Thickness'] += diff
                print(f" -> Applied adjustment ({diff}) to BELOW DG OML2")
                
        except IndexError:
            print(" -> Error: Could not find padding regions to adjust.")
            
    # Final Check
    final_sum = template['Target_Thickness'].sum()
    print(f" -> Final Sum: {final_sum}")
    
    # 7. Print & Save
    print("\n--- GOLDEN TEMPLATE (64 CH) ---")
    print(template[['Region', 'Target_Thickness', 'Mean_Thickness']])
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        template.to_excel(writer, sheet_name='Golden_Template', index=False)
        full_stats.to_excel(writer, sheet_name='All_Stats', index=False)
        
        pivot = full_stats.pivot(index='Session_ID', columns='Region', values='Thickness')
        pivot = pivot.reindex(columns=full_region_order)
        pivot.to_excel(writer, sheet_name='Thickness_Pivot')

    print(f"\nSaved to {output_file}")

if __name__ == "__main__":
    generate_golden_template()