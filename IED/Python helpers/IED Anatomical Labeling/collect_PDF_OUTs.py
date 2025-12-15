import os
import shutil
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages

# ================= CONFIGURATION =================
# Update these paths to match your actual environment
root_directory = r'C:\Users\Z390\Desktop\IED DATA\Take 3' 
csv_file_path = r'C:\Users\Z390\Desktop\IED DATA\Take 3\Mice_group.csv'

# Name of the final collection folder
final_output_folder_name = 'Final_Collected_Results'
# =================================================

def collect_and_process_data(root_dir, csv_path):
    # 1. Setup Output Directory
    final_output_path = os.path.join(root_dir, final_output_folder_name)
    if not os.path.exists(final_output_path):
        os.makedirs(final_output_path)
        print(f"Created output directory: {final_output_path}")

    # 2. Load the CSV
    try:
        df = pd.read_csv(csv_path)
        print(f"Loaded CSV with {len(df)} rows.")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return

    # List to track images for the summary PDF
    collected_images_for_pdf = []

    # 3. Iterate through each mouse/session in the CSV
    for index, row in df.iterrows():
        long_session_id = str(row['Session']).strip()
        short_session_id = str(row['Simple_Name']).strip()
        group_type = str(row['Group']).strip()
        
        print(f"\nProcessing: {short_session_id} ({long_session_id}) - Group: {group_type}...")

        # 4. Find the matching folder (Case Insensitive)
        found_session_folder = None
        try:
            for item in os.listdir(root_dir):
                if os.path.isdir(os.path.join(root_dir, item)):
                    if long_session_id.lower() in item.lower(): 
                        found_session_folder = item
                        break
        except FileNotFoundError:
            print(f"Error: Root directory not found: {root_dir}")
            return

        if not found_session_folder:
            print(f"  [!] Could not find folder for session {long_session_id}. Skipping.")
            continue

        # Define paths
        session_path = os.path.join(root_dir, found_session_folder)
        pipeline_path = os.path.join(session_path, 'Pipeline Output')
        pdf_out_source = os.path.join(pipeline_path, 'PDF_OUT')

        # 5. Create destination folder
        dest_folder_name = f"PDF_OUT_{short_session_id}_{group_type}"
        dest_path = os.path.join(final_output_path, dest_folder_name)
        
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)

        # ================= TASK A: Handle the SOLID PNG =================
        solid_found = False
        if os.path.exists(pipeline_path):
            for file in os.listdir(pipeline_path):
                if file.lower().endswith('.png') and 'solid' in file.lower():
                    src_file = os.path.join(pipeline_path, file)
                    new_filename = f"Master_view_{short_session_id}_{group_type}.png"
                    dst_file = os.path.join(dest_path, new_filename)
                    
                    # Copy the file
                    shutil.copy2(src_file, dst_file)
                    print(f"  -> Copied Master View: {new_filename}")
                    
                    # Add to list for Summary PDF generation later
                    collected_images_for_pdf.append({
                        'path': dst_file,
                        'title': f"Session: {short_session_id}  |  Group: {group_type}"
                    })
                    
                    solid_found = True
                    break 
            if not solid_found:
                print("  [!] Warning: No 'SOLID' png found in Pipeline Output.")
        else:
            print(f"  [!] Pipeline Output folder missing in {found_session_folder}")

        # ================= TASK B: Handle PDFs =================
        if os.path.exists(pdf_out_source):
            pdf_files = [f for f in os.listdir(pdf_out_source) if f.lower().endswith('.pdf')]
            
            if not pdf_files:
                print("  [!] PDF_OUT folder exists but contains no PDFs.")
            
            for pdf in pdf_files:
                original_name = pdf
                name_body, ext = os.path.splitext(original_name)
                
                # --- RENAMING LOGIC START ---
                
                # 1. Raster_Avg_SOLID -> Prepend Voltage_
                if name_body.startswith('Raster_Avg_SOLID'):
                    name_body = 'Voltage_' + name_body

                # 2. Cut everything after SOLID (remove metadata)
                if 'SOLID' in name_body:
                    parts = name_body.split('SOLID')
                    name_body = parts[0] + 'SOLID'
                
                # 3. CenterSlices -> GroundZero
                if 'CenterSlices' in name_body:
                    name_body = name_body.replace('CenterSlices', 'GroundZero')
                
                # 4. TimeAvg -> AfterSpike
                if 'TimeAvg' in name_body:
                    name_body = name_body.replace('TimeAvg', 'AfterSpike')
                
                # 5. Add Session ID and Group Suffix
                final_pdf_name = f"{name_body}_{short_session_id}_{group_type}{ext}"
                
                # --- RENAMING LOGIC END ---

                try:
                    shutil.copy2(
                        os.path.join(pdf_out_source, pdf),
                        os.path.join(dest_path, final_pdf_name)
                    )
                except Exception as e:
                    print(f"  [!] Error copying PDF {pdf}: {e}")

            if pdf_files:
                print(f"  -> Copied and renamed {len(pdf_files)} PDFs.")
            
        else:
            print("  [!] PDF_OUT folder not found.")

    # ================= TASK C: Generate Summary PDF (Landscape + High Res) =================
    if collected_images_for_pdf:
        print("\n" + "="*30)
        print(f"Generating Summary PDF for {len(collected_images_for_pdf)} sessions...")
        
        summary_pdf_path = os.path.join(final_output_path, "Summary_Master_Views.pdf")
        
        try:
            with PdfPages(summary_pdf_path) as pdf:
                for item in collected_images_for_pdf:
                    try:
                        # Create a figure in LANDSCAPE orientation (11 inches wide, 8.5 tall)
                        # We do NOT set DPI here, we set it at the save step for the file
                        fig, ax = plt.subplots(figsize=(11, 8.5)) 
                        
                        # Load and display image
                        img = mpimg.imread(item['path'])
                        
                        # 'bilinear' interpolation helps smooth out pixels if the image is slightly resized
                        ax.imshow(img, interpolation='bilinear', aspect='auto')
                        
                        # Add Title
                        ax.set_title(item['title'], fontsize=14, fontweight='bold', pad=15)
                        
                        # Remove axes
                        ax.axis('off')
                        
                        # Save page with 300 DPI (High Resolution)
                        plt.tight_layout()
                        pdf.savefig(fig, dpi=300) # <--- THIS FIXES THE PIXELATION
                        plt.close(fig)
                        
                    except Exception as e:
                        print(f"  [!] Error adding page for {item['title']}: {e}")
            
            print(f"SUCCESS: Summary PDF saved to: {summary_pdf_path}")
        except Exception as e:
            print(f"Error creating summary PDF: {e}")
    else:
        print("\nNo Master View images were found, skipping Summary PDF generation.")

    print("\n" + "="*30)
    print("Processing Complete!")

if __name__ == "__main__":
    collect_and_process_data(root_directory, csv_file_path)