import os
import re

def remove_part_from_filenames(directory, part_to_remove):
    # List all files in the directory
    for filename in os.listdir(directory):
        # Construct full file path
        file_path = os.path.join(directory, filename)

        # Check if it is a file
        if os.path.isfile(file_path):
            # Remove the specific part from the filename
            new_filename = re.sub(part_to_remove, '', filename)

            # Construct the new file path
            new_file_path = os.path.join(directory, new_filename)

            # Rename the file
            os.rename(file_path, new_file_path)
            print(f'Renamed: {filename} to {new_filename}')

# Specify the directory and the part to remove
directory = "C:\\my\\file\\path"
part_to_remove = ' -Ktunotes.in'  # This can be a regex pattern

# Call the function
remove_part_from_filenames(directory, part_to_remove)
