
# config/county_config.py

import os

# List of counties in Kentucky
COUNTIES_IN_KENTUCKY = [
    "Adair", "Allen", "Anderson", "Ballard", "Barren", "Bath", "Bell", "Boone",
    "Bourbon", "Boyd", "Boyle", "Bracken", "Breathitt", "Breckinridge", "Bullitt",
    "Butler", "Caldwell", "Calloway", "Campbell", "Carlisle", "Carroll", "Carter",
    "Casey", "Christian", "Clark", "Clay", "Clinton", "Crittenden", "Cumberland",
    "Daviess", "Edmonson", "Elliott", "Estill", "Fayette", "Fleming", "Floyd",
    "Franklin", "Fulton", "Gallatin", "Garrard", "Grant", "Graves", "Grayson",
    "Green", "Greenup", "Hancock", "Hardin", "Harlan", "Harrison", "Hart", "Henderson",
    "Henry", "Hickman", "Hopkins", "Jackson", "Jefferson", "Jessamine", "Johnson",
    "Kenton", "Knott", "Knox", "Larue", "Laurel", "Lawrence", "Lee", "Leslie",
    "Letcher", "Lewis", "Lincoln", "Livingston", "Logan", "Lyon", "McCracken",
    "McCreary", "McLean", "Madison", "Magoffin", "Marion", "Marshall", "Martin",
    "Mason", "Meade", "Menifee", "Mercer", "Metcalfe", "Monroe", "Montgomery",
    "Morgan", "Muhlenberg", "Nelson", "Nicholas", "Ohio", "Oldham", "Owen", "Owsley",
    "Pendleton", "Perry", "Pike", "Powell", "Pulaski", "Robertson", "Rockcastle",
    "Rowan", "Russell", "Scott", "Shelby", "Simpson", "Spencer", "Taylor", "Todd",
    "Trigg", "Trimble", "Union", "Warren", "Washington", "Wayne", "Webster",
    "Whitley", "Wolfe", "Woodford"
]

def get_county_folder_counts(base_path='/database/data') -> dict:
    """
    Returns a dictionary with counties as keys and the number of folders in each county's directory as values.

    Parameters:
    - base_path (str): The base directory path where county directories are located.

    Returns:
    - dict: A dictionary where keys are county names and values are the number of folders in each county's directory.
    """
    county_folder_counts = {}
    for county in COUNTIES_IN_KENTUCKY:
        county_path = os.path.join(base_path, county)
        if os.path.isdir(county_path):
            # List the folders in the county directory
            try:
                with os.scandir(county_path) as entries:
                    folder_count = sum(1 for entry in entries if entry.is_dir())
                    county_folder_counts[county] = folder_count
            except OSError as e:
                # Handle potential errors with reading directories
                county_folder_counts[county] = 0
                print(f"Error reading directory for county '{county}': {e}")
        else:
            county_folder_counts[county] = 0  # If the directory doesn't exist
    return county_folder_counts
