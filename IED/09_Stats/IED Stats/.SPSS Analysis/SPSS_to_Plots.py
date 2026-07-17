import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker  # Import ticker for custom tick locations
import os
import numpy as np

# ================= CONFIGURATION =================
# Update this if the file is in a different location
input_file = 'SPSS Plotting Values Output.xlsx'
output_dir = 'SPSS_Graphs_VerticalProfile'

# Anatomical Order (Top to Bottom)
custom_region_order = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]

# Regions to mark as significant (Hardcoded as requested)
sig_regions_target = ['HIL', 'DG MML2', 'DG OML2']

# Color Palettes
# Updated: "Deep Red" for IP (GZ) and "Slightly Darker Light Red" for PP (AS)
palette_map = {
    'Base': {'GZ': '#C00000', 'AS': '#E57373'},  # Deep Red, Darker Light Red
    'CNO':  {'GZ': '#C00000', 'AS': '#E57373'}   # Same colors for CNO
}

# Label Mapping for Legend
label_map = {
    'GZ': 'Initiation Phase',
    'AS': 'Propagation Phase'
}
# =================================================

def get_sheet_category(sheet_name):
    """
    Determines the category of data based on sheet name
    to assign the correct global limits.
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

def draw_significance_bracket(ax, y_pos, x1, x2, offset_direction=1):
    """
    Draws a bracket connecting x1 and x2 at height y_pos.
    For a vertical profile (Y=Category, X=Value), the bracket is horizontal.
    """
    # Ensure x1 is left and x2 is right
    start = min(x1, x2)
    end = max(x1, x2)
    mid = (start + end) / 2

    # Calculate bracket vertical offset (in data coordinates)
    y_line = y_pos - 0.15  # The horizontal line of the bracket
    y_tick = y_pos - 0.10  # The tips of the bracket pointing down to the points

    # Draw the line
    ax.plot([start, end], [y_line, y_line], color='black', lw=1)

    # Draw the downward ticks at ends
    ax.plot([start, start], [y_line, y_tick], color='black', lw=1)
    ax.plot([end, end], [y_line, y_tick], color='black', lw=1)

    # Draw the star
    ax.text(mid, y_line - 0.05, '*', ha='center', va='bottom',
            fontsize=18, fontweight='bold', color='black')

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
        print("\n--- Pass 1: Calculating Global Limits ---")

        loaded_sheets = {}
        categories = ['Voltage_Raw', 'Voltage_Norm', 'CSD_Raw', 'CSD_Norm']
        global_limits = {cat: {'min': float('inf'), 'max': float('-inf')} for cat in categories}

        for sheet in sheet_names:
            category = get_sheet_category(sheet)
            if not category: continue

            try:
                # Load header=1
                df = pd.read_excel(xls, sheet_name=sheet, header=1)

                if df.shape[1] < 5:
                    continue

                # Clean Data
                df_clean = df.iloc[:, [0, 1, 2, 3, 4]].copy()
                df_clean.columns = ['Group', 'TimeFrame', 'Region', 'Mean', 'SE']

                df_clean = df_clean[pd.to_numeric(df_clean['Mean'], errors='coerce').notna()]
                df_clean['Group'] = df_clean['Group'].ffill()
                df_clean['TimeFrame'] = df_clean['TimeFrame'].ffill()
                df_clean['Mean'] = df_clean['Mean'].astype(float)
                df_clean['SE'] = df_clean['SE'].astype(float)

                # Filter Regions
                df_clean = df_clean[df_clean['Region'].isin(custom_region_order)]
                if df_clean.empty: continue

                loaded_sheets[sheet] = df_clean

                # Calculate Min/Max (Applied to X-axis now)
                sheet_max = (df_clean['Mean'] + df_clean['SE']).max()
                sheet_min = (df_clean['Mean'] - df_clean['SE']).min()

                if sheet_max > global_limits[category]['max']:
                    global_limits[category]['max'] = sheet_max
                if sheet_min < global_limits[category]['min']:
                    global_limits[category]['min'] = sheet_min

            except Exception as e:
                print(f"Error reading sheet {sheet} in Pass 1: {e}")

        # Add padding
        final_limits = {}
        for cat, lims in global_limits.items():
            if lims['min'] == float('inf'): continue
            data_range = lims['max'] - lims['min']
            if data_range == 0: data_range = 1.0
            pad = data_range * 0.1
            final_limits[cat] = (lims['min'] - pad, lims['max'] + pad)

        # --- PASS 2: GENERATE PLOTS (VERTICAL PROFILE) ---
        print("\n--- Pass 2: Generating Vertical Profile Plots ---")

        # Map region names to integer indices for plotting on Y-axis
        region_map = {name: i for i, name in enumerate(custom_region_order)}

        for sheet, df_clean in loaded_sheets.items():
            print(f"Processing Sheet: {sheet}")

            category = get_sheet_category(sheet)
            x_min, x_max = final_limits.get(category, (None, None)) # Applied to X-axis

            # Determine Labels
            is_voltage = 'VOLTAGE' in sheet.upper()
            is_normalized = 'NORMALIZED' in sheet.upper()

            if is_voltage:
                metric_name = "Voltage"
                x_label_text = r"Voltage ($\mu$V)"
            else:
                metric_name = "CSD"
                x_label_text = "CSD Units"

            if is_normalized:
                x_label_text = f"Normalized {metric_name}"
                title_suffix = "[Normalized]"
            else:
                title_suffix = ""

            # Ensure Categorical Ordering
            df_clean['Region'] = pd.Categorical(df_clean['Region'], categories=custom_region_order, ordered=True)
            df_clean.sort_values('Region', inplace=True)

            groups = df_clean['Group'].unique()

            for group in groups:
                group_data = df_clean[df_clean['Group'] == group]
                colors = palette_map.get(group, None)

                # Initialize Plot
                fig, ax = plt.subplots(figsize=(8, 10)) # Tall aspect ratio

                # Plot Lines first (Connectivity)
                for tf in ['GZ', 'AS']:
                    tf_data = group_data[group_data['TimeFrame'] == tf]
                    if tf_data.empty: continue

                    color = colors[tf] if colors else None
                    label = label_map.get(tf, tf)

                    # Map regions to Y-indices
                    y_vals = [region_map[r] for r in tf_data['Region']]
                    x_vals = tf_data['Mean']
                    x_errs = tf_data['SE']

                    # Plot Errorbar
                    ax.errorbar(
                        x=x_vals,
                        y=y_vals,
                        xerr=x_errs,
                        fmt='-o',
                        color=color,
                        label=label,
                        linewidth=2.5,
                        markersize=8,
                        capsize=5
                    )

                # --- Draw Significance Brackets ---
                for region_name in sig_regions_target:
                    if region_name not in custom_region_order: continue

                    reg_data = group_data[group_data['Region'] == region_name]
                    gz_row = reg_data[reg_data['TimeFrame'] == 'GZ']
                    as_row = reg_data[reg_data['TimeFrame'] == 'AS']

                    if not gz_row.empty and not as_row.empty:
                        x1 = gz_row.iloc[0]['Mean']
                        x2 = as_row.iloc[0]['Mean']
                        y_idx = region_map[region_name]
                        draw_significance_bracket(ax, y_idx, x1, x2)

                # --- Formatting ---
                ax.invert_yaxis() # Top region at top

                # Set Y Ticks
                ax.set_yticks(range(len(custom_region_order)))
                ax.set_yticklabels(custom_region_order, fontsize=11)

                # --- X-AXIS TICKS (Forcing 1000) ---
                # 1. Force ticks at multiples of 500 (0, 500, 1000)
                ax.xaxis.set_major_locator(ticker.MultipleLocator(500))
                
                # 2. Ensure limits cover at least 1000 if positive or -1000 if negative
                current_xlim = ax.get_xlim()
                new_left = current_xlim[0]
                new_right = current_xlim[1]
                
                # Force visibility of 1000 if data is in that positive range
                if new_right > 0:
                    new_right = max(new_right, 1050) # Extend slightly past 1000
                
                # Force visibility of -1000 if data is in that negative range
                if new_left < 0:
                    new_left = min(new_left, -1050)

                # 3. Apply limits only if we calculated a change, else respect global calc
                if x_min is not None and x_max is not None:
                     # If global limits are passed, prioritize them but ensure 1000 is included if reasonable
                     final_left = min(x_min, new_left)
                     final_right = max(x_max, new_right)
                     ax.set_xlim(left=final_left, right=final_right)
                else:
                     ax.set_xlim(left=new_left, right=new_right)

                # Titles and Labels
                ax.set_title(f'{metric_name} Depth Profile ({group})', fontsize=16, pad=15)
                ax.set_xlabel(x_label_text, fontsize=12)
                ax.set_ylabel("Anatomical Region", fontsize=12)

                # Clean Up
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)

                # Remove Grid
                ax.grid(False)
                
                # Set Inward Ticks (Both Axes)
                ax.tick_params(axis='both', direction='in', length=6, width=1)

                # Transparent Legend
                ax.legend(title="Time Frame", frameon=False, loc='best')

                plt.tight_layout()

                # Save
                filename = f"VerticalProfile_{sheet}_{group}"
                save_png = os.path.join(output_dir, filename + ".png")
                save_pdf = os.path.join(output_dir, filename + ".pdf")

                plt.savefig(save_png, dpi=300)
                plt.savefig(save_pdf, format='pdf')
                print(f"    Saved: {save_png}")
                plt.close()

        print("\nAll sheets processed.")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_spss_plots()