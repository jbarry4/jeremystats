import os
from PIL import Image

# --- Parameters to Change ---

# The total number of images you want to create (e.g., 10 will create 001 to 010)
TOTAL_IMAGES = 25

# The dimensions (width and height) of the blank images in pixels
IMAGE_WIDTH = 100
IMAGE_HEIGHT = 100

# The color of the blank image (R, G, B)
# (255, 255, 255) is white
# (0, 0, 0) is black
BACKGROUND_COLOR = (255, 255, 255)

# The folder where the images will be saved.
# It will be created if it doesn't exist.
OUTPUT_DIR = "blank_images"

# --- End of Parameters ---


def create_blank_images():
    """
    Creates a series of blank PNG images in the specified output directory.
    """
    # Ensure the output directory exists
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"Output directory set to: '{OUTPUT_DIR}'")
    except OSError as e:
        print(f"Error creating directory {OUTPUT_DIR}: {e}")
        return

    print(f"Starting to create {TOTAL_IMAGES} blank images...")

    for i in range(1, TOTAL_IMAGES + 1):
        # Format the number with leading zeros (e.g., 1 -> "001")
        file_number = f"{i:03d}"

        # Construct the file name
        file_name = f"Evt{file_number}_5ch.png"
        file_path = os.path.join(OUTPUT_DIR, file_name)

        try:
            # Create a new blank image
            # 'RGB' mode for a color image
            img = Image.new('RGB', (IMAGE_WIDTH, IMAGE_HEIGHT), color=BACKGROUND_COLOR)
            
            # Save the image as a PNG
            img.save(file_path)
            
            print(f"Successfully created: {file_path}")

        except Exception as e:
            print(f"Error creating file {file_path}: {e}")

    print("\nImage creation complete.")


if __name__ == "__main__":
    # Before running this script, you may need to install the Pillow library:
    # pip install Pillow
    
    create_blank_images()