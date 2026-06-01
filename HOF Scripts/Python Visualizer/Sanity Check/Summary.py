import pandas as pd

# Define hardcoded paths
med_events_path = r"D:\HOF DATA\ACTIVE DATA\med_events.csv"
global_timeline_path = r"D:\HOF DATA\ACTIVE DATA\All_Events_Summary_Global_Timeline_Input.xlsx"

# Process med_events.csv
print("--- MED EVENTS SUMMARY ---")
try:
    df_med = pd.read_csv(med_events_path)
    # Group by file and event to get counts
    med_summary = df_med.groupby(['file', 'event']).size().reset_index(name='count')
    print(med_summary.to_string(index=False))
except Exception as e:
    print(f"Failed to process med_events.csv: {e}")

print("\n" + "="*50 + "\n")

# Process All_Events_Summary_Global_Timeline_Input.xlsx
print("--- GLOBAL TIMELINE SUMMARY ---")
try:
    df_global = pd.read_excel(global_timeline_path)
    # Group by Session and Event_Name to get counts
    global_summary = df_global.groupby(['Session', 'Event_Name']).size().reset_index(name='count')
    print(global_summary.to_string(index=False))
except Exception as e:
    print(f"Failed to process Global Timeline file: {e}")