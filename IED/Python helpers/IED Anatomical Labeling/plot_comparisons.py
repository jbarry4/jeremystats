import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os

# ================= CONFIGURATION =================
target_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3'
input_file = 'Final_Matched_and_Collapsed_Stats.xlsx'
sheet_name = 'Collapsed_by_Region'
output_folder = 'Anatomical_Region_Graphs'

custom_region_order = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]

# Metrics to plot
metrics = [
    {'col': 'TimeSlice_Val', 'label': 'After-spike slice', 'name': 'TimeSlice', 'y_text': 'CSD Units'},
    {'col': 'CenterSlice_Val', 'label': 'Ground-zero', 'name': 'CenterSlice', 'y_text': 'CSD Units'},
    
    # NEW VOLTAGE METRICS
    {'col': 'Voltage_GroundZero_Val', 'label': 'Voltage (Ground Zero)', 'name': 'Voltage_GroundZero', 'y_text': 'Microvolts (uV)'},
    {'col': 'Voltage_AfterSpike_Val', 'label': 'Voltage (After Spike)', 'name': 'Voltage_AfterSpike', 'y_text': 'Microvolts (uV)'}
]
# =================================================

def generate_plots():
    input_path = os.path.join(target_directory, input_file)
    output_dir = os.path.join(target_directory, output_folder)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Loading data from: {input_path}")
    
    # Dictionary to store dataframes for Excel export
    excel_sheets = {}

    try:
        # 1. Load & Filter Data
        # Fix: Ensure we use the global 'sheet_name' here. 
        # The variable used in the writing loop below has been renamed to avoid shadowing.
        df = pd.read_excel(input_path, sheet_name=sheet_name)
        df_filtered = df.copy()
        
        # Apply strict order
        df_filtered['Region'] = pd.Categorical(df_filtered['Region'], categories=custom_region_order, ordered=True)
        df_filtered = df_filtered.dropna(subset=['Region']).sort_values('Region')
        
        if 'Group' not in df_filtered.columns:
            print("Error: 'Group' column missing.")
            return

        # 2. Check Completeness
        mice = df_filtered['Mouse'].unique()
        for mouse in mice:
            mouse_data = df_filtered[df_filtered['Mouse'] == mouse]
            if len(mouse_data['Group'].unique()) < 2:
                print(f"Note: Mouse {mouse} incomplete groups.")

        # --- CALCULATE SHARED LIMITS FOR CSD ---
        csd_cols = ['TimeSlice_Val', 'CenterSlice_Val']
        csd_ylim = None
        
        if all(c in df_filtered.columns for c in csd_cols):
            all_csd = pd.concat([df_filtered[col] for col in csd_cols])
            c_min, c_max = all_csd.min(), all_csd.max()
            rng = c_max - c_min
            if rng == 0: rng = 1
            csd_ylim = (c_min - rng*0.05, c_max + rng*0.05)
            
        # --- CALCULATE SHARED LIMITS FOR VOLTAGE ---
        voltage_cols = ['Voltage_GroundZero_Val', 'Voltage_AfterSpike_Val']
        voltage_ylim = None
        
        if all(c in df_filtered.columns for c in voltage_cols):
            all_voltage = pd.concat([df_filtered[col] for col in voltage_cols])
            v_min, v_max = all_voltage.min(), all_voltage.max()
            rng = v_max - v_min
            if rng == 0: rng = 1
            voltage_ylim = (v_min - rng*0.05, v_max + rng*0.05)

        # 3. Main Loop (Base vs CNO)
        for m in metrics:
            metric_col = m['col']
            title_label = m['label']
            y_axis_text = m['y_text']
            file_suffix = m['name']
            
            print(f"Plotting {file_suffix} (Base vs CNO)...")

            # Determine Y-Limit
            if metric_col in csd_cols and csd_ylim:
                current_ylim = csd_ylim
            elif metric_col in voltage_cols and voltage_ylim:
                current_ylim = voltage_ylim
            else:
                # Independent scale if not in shared groups
                vals = df_filtered[metric_col]
                v_min_ind, v_max_ind = vals.min(), vals.max()
                rng = v_max_ind - v_min_ind
                if rng == 0: rng = 1
                current_ylim = (v_min_ind - rng*0.05, v_max_ind + rng*0.05)

            # --- STATS CALCULATION FOR EXCEL ---
            graph_title = f'Overall: {title_label} (Base vs CNO)'
            stats_df = df_filtered.groupby(['Region', 'Group'])[metric_col].agg(['mean', 'sem', 'count']).reset_index()
            stats_df.insert(0, 'Graph_Title', graph_title) # Add title column
            
            # Add to Excel collection (Sheet name limited to 31 chars)
            sheet_name_excel = f"Overall_{file_suffix}"[:31]
            excel_sheets[sheet_name_excel] = stats_df

            # --- PLOT A: OVERALL ---
            plt.figure(figsize=(12, 7))
            sns.lineplot(data=df_filtered, x='Region', y=metric_col, hue='Group', style='Group',
                         markers=True, dashes=False, errorbar='se', linewidth=2.5, markersize=8)
            plt.ylim(current_ylim)
            plt.title(graph_title, fontsize=16)
            plt.ylabel(y_axis_text, fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'Overall_Comparison_{file_suffix}.png'), dpi=300)
            plt.close()

            # --- PLOT B: PER MOUSE ---
            g = sns.relplot(data=df_filtered, x='Region', y=metric_col, hue='Group', style='Group',
                            col='Mouse', col_wrap=4, kind='line', markers=True, dashes=False,
                            errorbar=None, height=4, aspect=1.2, linewidth=2)
            g.set(ylim=current_ylim)
            g.fig.suptitle(f'Per Mouse: {title_label}', y=1.02, fontsize=16)
            g.set_axis_labels("Anatomical Region", y_axis_text)
            for ax in g.axes.flat:
                for label in ax.get_xticklabels():
                    label.set_rotation(45)
                    label.set_ha('right')
            plt.savefig(os.path.join(output_dir, f'Per_Mouse_Comparison_{file_suffix}.png'), dpi=300, bbox_inches='tight')
            plt.close()

        # 4. SPECIAL PLOTS: Combined GZ vs AS (Base & CNO)
        print("Processing Special Combined Plots (Base & CNO)...")
        
        unique_groups = df_filtered['Group'].unique()
        
        # Define configurations for groups to plot
        group_configs = []
        
        # Check for Base
        base_candidates = [g for g in unique_groups if 'base' in str(g).lower()]
        if base_candidates:
            group_configs.append({
                'group': base_candidates[0],
                'palette': ['#85C1E9', '#2E86C1'],  # Light Blue, Dark Blue
                'file_tag': 'Base'
            })

        # Check for CNO
        cno_candidates = [g for g in unique_groups if 'cno' in str(g).lower()]
        if cno_candidates:
            group_configs.append({
                'group': cno_candidates[0],
                'palette': ['#F8C471', '#D35400'],  # Light Orange, Dark Orange
                'file_tag': 'CNO'
            })

        for config in group_configs:
            group_name = config['group']
            current_palette = config['palette']
            file_tag = config['file_tag']
            
            print(f"  Processing Group: {group_name} ({file_tag})...")
            df_group = df_filtered[df_filtered['Group'] == group_name].copy()
            
            # --- 4A. Combined CSD (Ground-zero vs After-spike) ---
            df_melted_csd = df_group.melt(
                id_vars=['Region', 'Mouse'],
                value_vars=['TimeSlice_Val', 'CenterSlice_Val'],
                var_name='Measurement_Type', value_name='Value'
            )
            label_map_csd = {'TimeSlice_Val': 'After-spike slice', 'CenterSlice_Val': 'Ground-zero'}
            df_melted_csd['Measurement'] = df_melted_csd['Measurement_Type'].map(label_map_csd)

            # --- STATS FOR EXCEL (CSD) ---
            csd_title = f'Combined CSD Comparison: GZ vs AS ({group_name})'
            stats_csd = df_melted_csd.groupby(['Region', 'Measurement'])['Value'].agg(['mean', 'sem', 'count']).reset_index()
            stats_csd.insert(0, 'Graph_Title', csd_title)
            excel_sheets[f"Combined_CSD_{file_tag}"[:31]] = stats_csd

            # Plot Overall CSD
            plt.figure(figsize=(12, 7))
            sns.lineplot(data=df_melted_csd, x='Region', y='Value', hue='Measurement', style='Measurement',
                         palette=current_palette,
                         markers=True, dashes=False, errorbar='se', linewidth=2.5, markersize=8)
            if csd_ylim: plt.ylim(csd_ylim)
            plt.title(csd_title, fontsize=16)
            plt.ylabel('CSD Units', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'Combined_CSD_Comparison_{file_tag}.png'), dpi=300)
            plt.close()
            
            # Plot Per Mouse CSD
            g = sns.relplot(data=df_melted_csd, x='Region', y='Value', hue='Measurement', style='Measurement',
                            col='Mouse', col_wrap=4, kind='line', palette=current_palette,
                            markers=True, dashes=False,
                            errorbar=None, height=4, aspect=1.2, linewidth=2)
            if csd_ylim: g.set(ylim=csd_ylim)
            g.fig.suptitle(f'Per Mouse CSD Comparison ({group_name})', y=1.02, fontsize=16)
            g.set_axis_labels("Anatomical Region", "CSD Units")
            for ax in g.axes.flat:
                for label in ax.get_xticklabels():
                    label.set_rotation(45)
                    label.set_ha('right')
            plt.savefig(os.path.join(output_dir, f'Per_Mouse_Combined_CSD_Comparison_{file_tag}.png'), dpi=300, bbox_inches='tight')
            plt.close()

            # --- 4B. Combined Voltage (Ground-zero vs After-spike) ---
            df_melted_volt = df_group.melt(
                id_vars=['Region', 'Mouse'],
                value_vars=['Voltage_GroundZero_Val', 'Voltage_AfterSpike_Val'],
                var_name='Measurement_Type', value_name='Value'
            )
            label_map_volt = {'Voltage_GroundZero_Val': 'Voltage (Ground Zero)', 'Voltage_AfterSpike_Val': 'Voltage (After Spike)'}
            df_melted_volt['Measurement'] = df_melted_volt['Measurement_Type'].map(label_map_volt)

            # --- STATS FOR EXCEL (VOLTAGE) ---
            volt_title = f'Combined Voltage Comparison: GZ vs AS ({group_name})'
            stats_volt = df_melted_volt.groupby(['Region', 'Measurement'])['Value'].agg(['mean', 'sem', 'count']).reset_index()
            stats_volt.insert(0, 'Graph_Title', volt_title)
            excel_sheets[f"Combined_Volt_{file_tag}"[:31]] = stats_volt

            # Plot Overall Voltage
            plt.figure(figsize=(12, 7))
            sns.lineplot(data=df_melted_volt, x='Region', y='Value', hue='Measurement', style='Measurement',
                         palette=current_palette,
                         markers=True, dashes=False, errorbar='se', linewidth=2.5, markersize=8)
            if voltage_ylim: plt.ylim(voltage_ylim)
            plt.title(volt_title, fontsize=16)
            plt.ylabel('Microvolts (uV)', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'Combined_Voltage_Comparison_{file_tag}.png'), dpi=300)
            plt.close()

            # Plot Per Mouse Voltage
            g = sns.relplot(data=df_melted_volt, x='Region', y='Value', hue='Measurement', style='Measurement',
                            col='Mouse', col_wrap=4, kind='line', palette=current_palette,
                            markers=True, dashes=False,
                            errorbar=None, height=4, aspect=1.2, linewidth=2)
            if voltage_ylim: g.set(ylim=voltage_ylim)
            g.fig.suptitle(f'Per Mouse Voltage Comparison ({group_name})', y=1.02, fontsize=16)
            g.set_axis_labels("Anatomical Region", "Microvolts (uV)")
            for ax in g.axes.flat:
                for label in ax.get_xticklabels():
                    label.set_rotation(45)
                    label.set_ha('right')
            plt.savefig(os.path.join(output_dir, f'Per_Mouse_Combined_Voltage_Comparison_{file_tag}.png'), dpi=300, bbox_inches='tight')
            plt.close()

        # 5. SAVE STATS TO EXCEL
        stats_path = os.path.join(output_dir, 'Graph_Statistics.xlsx')
        print(f"Saving statistics to: {stats_path}")
        with pd.ExcelWriter(stats_path, engine='openpyxl') as writer:
            # Fix: Renamed loop variable 'sheet_name' to 'stats_sheet_name' 
            # to prevent it from shadowing the global 'sheet_name' variable.
            for stats_sheet_name, data in excel_sheets.items():
                data.to_excel(writer, sheet_name=stats_sheet_name, index=False)
        print("Statistics save complete.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_plots()