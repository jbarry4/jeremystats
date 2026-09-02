import subprocess
import sys
import time
import os

# ================= CONFIGURATION =================
# Scripts to run in EXACT order
scripts_to_run = [
    {
        "name": "1. Scan Sessions",
        "file": "getSessionDetail.py",
        "desc": "Scanning folders and generating session log..."
    },
    {
        "name": "2. Collect Anatomical Details",
        "file": "collect_anatomical_detail.py", 
        "desc": "Combining anatomical CSVs from all session folders..."
    },
    {
        "name": "3. Collect All Values",
        "file": "collect_all_values.py",
        "desc": "Aggregating CSD, Voltage Raster, and Theta values..."
    },
    {
        "name": "4. Merge & Collapse Data",
        "file": "merge_and_collapse_stats.py",
        "desc": "Matching locations, merging Voltage/CSD, and collapsing..."
    },
    {
        "name": "5. Generate Graphs",
        "file": "plot_comparisons.py",
        "desc": "Plotting Base vs CNO (CSD & Voltage) and Comparisons..."
    }
]
# =================================================

def run_pipeline():
    print("="*60)
    print("      STARTING AUTOMATED ANALYSIS PIPELINE      ")
    print("="*60 + "\n")

    total_start = time.time()

    for step in scripts_to_run:
        script_name = step["file"]
        step_name = step["name"]
        description = step["desc"]

        if not os.path.exists(script_name):
            print(f"[ERROR] Script not found: {script_name}")
            print("Please ensure all scripts are in the same directory.")
            sys.exit(1)

        print(f"--- {step_name} ---")
        print(f"Action: {description}")
        
        step_start = time.time()
        
        try:
            # Run the script as a subprocess
            result = subprocess.run([sys.executable, script_name], check=True)
            elapsed = time.time() - step_start
            print(f"✔ Status: Complete ({elapsed:.2f}s)\n")
            
        except subprocess.CalledProcessError:
            print(f"\n[CRITICAL FAILURE] Error running {script_name}.")
            print("The pipeline has been stopped.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] An unexpected error occurred: {e}")
            sys.exit(1)

    total_elapsed = time.time() - total_start
    print("="*60)
    print(f"      PIPELINE COMPLETE in {total_elapsed:.2f} seconds      ")
    print("="*60)
    print("Outputs generated:")
    print(" - session_ids_log.xlsx")
    print(" - Combined_Anatomical_Details_Grouped.xlsx")
    print(" - Simple_CSD_Collection_with_Theta.xlsx (Now includes VoltageRaster)")
    print(" - Final_Matched_and_Collapsed_Stats.xlsx")
    print(" - /Anatomical_Region_Graphs")

if __name__ == "__main__":
    run_pipeline()