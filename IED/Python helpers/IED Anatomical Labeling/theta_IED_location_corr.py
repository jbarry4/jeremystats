import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# ================= CONFIGURATION =================
input_file = 'Final_Matched_and_Collapsed_Stats.xlsx'
target_sheet = 'Collapsed_by_Region'
output_dir = 'GrandAverage_Correlation_Plots'

# Anatomical Order
custom_region_order = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]

# Plot Settings
theta_color = 'tab:purple'
theta_label = 'Theta CSD (a.u.)'  # Renamed and units changed to a.u.
csd_color = 'black'
csd_label = 'CSD (a.u.)'          # Units changed to a.u.
# =================================================

def generate_global_grandaverage():
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"--- Loading Data from {input_file} ---")
    try:
        df = pd.read_excel(input_file, sheet_name=target_sheet)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # 1. Filter and Order
    print("Cleaning data...")
    df['Region'] = df['Region'].astype(str).str.strip()
    df = df[df['Region'].isin(custom_region_order)].copy()
    
    # Enforce Anatomical Order
    df['Region'] = pd.Categorical(df['Region'], categories=custom_region_order, ordered=True)
    df.sort_values('Region', inplace=True)
    
    # 2. Collapse Across Groups (Grand Average of EVERYTHING)
    print("Calculating Global Grand Averages (Base + CNO combined)...")
    
    # Calculate Mean and SEM
    # We use agg to get both mean and standard error of the mean (sem)
    stats_df = df.groupby('Region')[['Theta_Val', 'CenterSlice_Val']].agg(['mean', 'sem']).reset_index()
    
    # Flatten columns for easier access
    stats_df.columns = ['Region', 'Theta_Mean', 'Theta_SEM', 'CSD_Mean', 'CSD_SEM']
    
    # Drop empty regions if any
    stats_df.dropna(inplace=True)

    # (Stats calculation removed as requested)

    # 3. Plotting (Dual Axis Profile)
    print("Generating Global Profile Plot...")
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # X-Axis
    x = stats_df['Region']
    
    # --- Axis 1: Theta CSD ---
    ax1.errorbar(x, stats_df['Theta_Mean'], yerr=stats_df['Theta_SEM'], 
                 color=theta_color, marker='o', linewidth=2, label='Theta CSD', capsize=5)
    ax1.set_ylabel(theta_label, color=theta_color, fontweight='bold', fontsize=12)
    ax1.tick_params(axis='y', labelcolor=theta_color)
    ax1.set_xlabel("Anatomical Region", fontsize=12)
    ax1.set_xticklabels(x, rotation=45, ha='right', fontsize=10)
    
    # --- Axis 2: CSD ---
    ax2 = ax1.twinx()
    ax2.errorbar(x, stats_df['CSD_Mean'], yerr=stats_df['CSD_SEM'], 
                 color=csd_color, marker='s', linestyle='--', linewidth=2, label='CSD', capsize=5)
    ax2.set_ylabel(csd_label, color=csd_color, fontweight='bold', fontsize=12)
    ax2.tick_params(axis='y', labelcolor=csd_color)
    
    # Zero line for CSD
    ax2.axhline(0, color='gray', linewidth=1, alpha=0.5)
    
    # Title & Legend
    plt.title("Global Grand Average Profile (Base + CNO)", fontsize=14, y=1.05)
    
    lines = [plt.Line2D([0], [0], color=theta_color, marker='o', lw=2),
             plt.Line2D([0], [0], color=csd_color, marker='s', linestyle='--', lw=2)]
    
    # Updated Legend Label
    ax1.legend(lines, ['Theta CSD', 'CSD Sink/Source'], loc='upper left')
    
    ax1.grid(True, axis='x', linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    
    # --- Save Output ---
    
    # 1. Save PNG
    save_path_png = os.path.join(output_dir, 'Global_GrandAverage_Profile_Plot.png')
    plt.savefig(save_path_png, dpi=300)
    print(f"PNG saved to: {save_path_png}")

    # 2. Save PDF
    save_path_pdf = os.path.join(output_dir, 'Global_GrandAverage_Profile_Plot.pdf')
    plt.savefig(save_path_pdf, format='pdf')
    print(f"PDF saved to: {save_path_pdf}")

    plt.close()

    print("Done.")

if __name__ == "__main__":
    generate_global_grandaverage()