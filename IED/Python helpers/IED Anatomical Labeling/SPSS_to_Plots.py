import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os
import numpy as np

# ================= CONFIGURATION =================
# Update this if the file is in a different location
input_file = 'SPSS Plotting Values Output.xlsx'
output_dir = 'SPSS_Graphs_GlobalY'

# Anatomical Order
custom_region_order = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]

# Color Palettes (Matching previous plots)
palette_map = {
    'Base': {'GZ': '#2E86C1', 'AS': '#85C1E9'},  # Dark Blue, Light Blue
    'CNO':  {'GZ': '#D35400', 'AS': '#F8C471'}   # Dark Orange, Light Orange
}

# Label Mapping for Legend
label_map = {
    'GZ': 'Ground-zero',
    'AS': 'After-spike slice'
}
# =================================================

def get_sheet_category(sheet_name):
    """
    Determines the category of data based on sheet name 
    to assign the correct global Y-axis.
    Returns: 'Voltage_Raw', 'Voltage_Norm', 'CSD_Raw', 'CSD_Norm', or None
    """
    sheet_upper = sheet_name.upper()
    
    is_voltage = 'VOLTAGE' in sheet_upper
    is_csd = 'CSD' in sheet_upper 
    if not is_voltage: is_csd = True 

    is_normalized = 'NORMALIZED' in sheet_upper

    if is_voltage:
        return 'Voltage_Norm' if is_normalized else 'Voltage_Raw'
    else:
        return 'CSD_Norm' if is_normalized else 'CSD_Raw'

def generate_spss_plots():
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Loading SPSS data from: {input_file}")
    
    try:
        # 1. Load Excel File wrapper
        xls = pd.ExcelFile(input_file)
        sheet_names = xls.sheet_names
        print(f"Found sheets: {sheet_names}")

        # --- PASS 1: LOAD ALL DATA AND CALCULATE GLOBAL LIMITS ---
        print("\n--- Pass 1: Calculating Global Y-Limits ---")
        
        # Store loaded dataframes to avoid re-reading
        loaded_sheets = {} 
        
        # Track min/max for each category
        categories = ['Voltage_Raw', 'Voltage_Norm', 'CSD_Raw', 'CSD_Norm']
        global_limits = {cat: {'min': float('inf'), 'max': float('-inf')} for cat in categories}

        for sheet in sheet_names:
            category = get_sheet_category(sheet)
            if not category: continue

            try:
                # Load header=1 to capture 'Condition', 'Mean', 'Std. Error' etc.
                df = pd.read_excel(xls, sheet_name=sheet, header=1)
                
                # Check columns
                if df.shape[1] < 5:
                    print(f"Skipping sheet {sheet} (Pass 1): Insufficient columns.")
                    continue

                # Clean Data
                df_clean = df.iloc[:, [0, 1, 2, 3, 4]].copy()
                df_clean.columns = ['Group', 'TimeFrame', 'Region', 'Mean', 'SE']
                
                # Drop rows where Mean is NaN
                df_clean = df_clean[pd.to_numeric(df_clean['Mean'], errors='coerce').notna()]
                
                # Forward Fill Metadata
                df_clean['Group'] = df_clean['Group'].ffill()
                df_clean['TimeFrame'] = df_clean['TimeFrame'].ffill()
                
                # Convert types
                df_clean['Mean'] = df_clean['Mean'].astype(float)
                df_clean['SE'] = df_clean['SE'].astype(float)

                # Filter Regions
                df_clean = df_clean[df_clean['Region'].isin(custom_region_order)]

                if df_clean.empty: continue

                # Store for Pass 2
                loaded_sheets[sheet] = df_clean

                # Calculate Min/Max for this sheet (Mean +/- SE)
                sheet_max = (df_clean['Mean'] + df_clean['SE']).max()
                sheet_min = (df_clean['Mean'] - df_clean['SE']).min()

                # Update Global Limits for this category
                if sheet_max > global_limits[category]['max']:
                    global_limits[category]['max'] = sheet_max
                if sheet_min < global_limits[category]['min']:
                    global_limits[category]['min'] = sheet_min

            except Exception as e:
                print(f"Error reading sheet {sheet} in Pass 1: {e}")

        # Add padding to global limits (e.g. 10%)
        final_limits = {}
        for cat, lims in global_limits.items():
            if lims['min'] == float('inf'): continue # No data for this category
            
            data_range = lims['max'] - lims['min']
            if data_range == 0: data_range = 1.0
            
            # Add 10% padding on top and bottom
            pad = data_range * 0.1
            final_limits[cat] = (lims['min'] - pad, lims['max'] + pad)
            
            print(f"  Category '{cat}' limits set to: {final_limits[cat]}")


        # --- PASS 2: GENERATE PLOTS ---
        print("\n--- Pass 2: Generating Plots ---")

        for sheet, df_clean in loaded_sheets.items():
            print(f"Processing Sheet: {sheet}")
            
            category = get_sheet_category(sheet)
            y_min, y_max = final_limits.get(category, (None, None))

            # Determine Labels
            is_voltage = 'VOLTAGE' in sheet.upper()
            is_normalized = 'NORMALIZED' in sheet.upper()
            
            if is_voltage:
                metric_name = "Voltage"
                base_unit = "Microvolts (uV)"
            else:
                metric_name = "CSD"
                base_unit = "CSD Units"
            
            if is_normalized:
                y_label_text = f"Normalized {metric_name}"
                title_suffix = "[Normalized]"
            else:
                y_label_text = base_unit
                title_suffix = ""

            # Ensure Categorical Ordering
            df_clean['Region'] = pd.Categorical(df_clean['Region'], categories=custom_region_order, ordered=True)
            df_clean.sort_values('Region', inplace=True)

            # Generate Plots (One per Group)
            groups = df_clean['Group'].unique()
            
            for group in groups:
                print(f"    Plotting Group: {group}")
                group_data = df_clean[df_clean['Group'] == group]
                
                if group not in palette_map:
                    print(f"    Warning: No palette defined for {group}, skipping color mapping.")
                    colors = None
                else:
                    colors = palette_map[group]

                plt.figure(figsize=(12, 7))
                
                # --- A. PLOT ERROR BARS ---
                for tf in ['GZ', 'AS']: # Strict order
                    tf_data = group_data[group_data['TimeFrame'] == tf]
                    
                    if tf_data.empty: continue
                    
                    # Get Color and Label
                    color = colors[tf] if colors else None
                    label = label_map.get(tf, tf)
                    
                    # Plot Standard Error Bars
                    plt.errorbar(
                        x=tf_data['Region'], 
                        y=tf_data['Mean'], 
                        yerr=tf_data['SE'], 
                        fmt='-o',               # Line with markers
                        color=color,
                        label=label,
                        linewidth=2.5, 
                        markersize=8,
                        capsize=5               # Error bar caps
                    )

                # --- B. ADD SIGNIFICANCE ASTERISKS (*) ---
                if y_max is not None and y_min is not None:
                    global_range = y_max - y_min
                    offset = global_range * 0.03
                else:
                    offset = 1.0

                for region in custom_region_order:
                    # Extract GZ and AS data for this specific region
                    gz = group_data[(group_data['TimeFrame'] == 'GZ') & (group_data['Region'] == region)]
                    as_ = group_data[(group_data['TimeFrame'] == 'AS') & (group_data['Region'] == region)]
                    
                    if not gz.empty and not as_.empty:
                        m_gz, se_gz = gz.iloc[0]['Mean'], gz.iloc[0]['SE']
                        m_as, se_as = as_.iloc[0]['Mean'], as_.iloc[0]['SE']
                        
                        top_gz = m_gz + se_gz
                        bot_gz = m_gz - se_gz
                        top_as = m_as + se_as
                        bot_as = m_as - se_as
                        
                        # Check for Separation (No Overlap)
                        is_separated = (bot_gz > top_as) or (bot_as > top_gz)
                        
                        if is_separated:
                            highest_y = max(top_gz, top_as)
                            star_y_pos = highest_y + offset
                            
                            plt.text(
                                x=region, 
                                y=star_y_pos, 
                                s='*', 
                                ha='center', 
                                va='bottom', 
                                fontsize=20, 
                                color='black', 
                                fontweight='bold'
                            )

                # --- C. APPLY GLOBAL LIMITS ---
                if y_min is not None and y_max is not None:
                    plt.ylim(bottom=y_min, top=y_max)

                # Formatting
                plt.title(f'Combined {metric_name} Comparison: Ground-zero vs After-spike ({group}) {title_suffix}', fontsize=16)
                plt.ylabel(y_label_text, fontsize=12)
                plt.xlabel('Anatomical Region', fontsize=12)
                plt.xticks(rotation=45, ha='right')
                plt.grid(True, linestyle='--', alpha=0.5)
                plt.legend(title="Time Frame")
                plt.tight_layout()
                
                # --- SAVE AS PNG (Bitmap) ---
                filename_png = f"{sheet}_{group}_GlobalY.png"
                save_path_png = os.path.join(output_dir, filename_png)
                plt.savefig(save_path_png, dpi=300)
                
                # --- SAVE AS PDF (Vector/Editable) ---
                filename_pdf = f"{sheet}_{group}_GlobalY.pdf"
                save_path_pdf = os.path.join(output_dir, filename_pdf)
                plt.savefig(save_path_pdf, format='pdf')
                
                print(f"    Saved PNG & PDF: {save_path_png}")
                plt.close()

        print("\nAll sheets processed.")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_spss_plots()