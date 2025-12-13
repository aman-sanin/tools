import os
import re

def remove_part_from_filenames(directory, part_to_remove, recursive=False):
    """
    Remove a specific part from filenames in a directory.
    
    Args:
        directory (str): Path to the directory
        part_to_remove (str): String or regex pattern to remove from filenames
        recursive (bool): Whether to process subdirectories recursively
    """
    processed_files = 0
    
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        
        # Handle directories
        if os.path.isdir(file_path):
            if recursive:
                # Recursively process subdirectory
                processed_files += remove_part_from_filenames(file_path, part_to_remove, recursive)
            continue
        
        # Process files only
        if os.path.isfile(file_path):
            # Remove the specific part from the filename
            new_filename = re.sub(part_to_remove, '', filename)
            
            # Only rename if the filename actually changed
            if new_filename != filename:
                new_file_path = os.path.join(directory, new_filename)
                
                # Check if new filename already exists
                if os.path.exists(new_file_path):
                    print(f'Warning: {new_filename} already exists. Skipping {filename}')
                    continue
                
                # Rename the file
                try:
                    os.rename(file_path, new_file_path)
                    print(f'Renamed: {filename} to {new_filename}')
                    processed_files += 1
                except Exception as e:
                    print(f'Error renaming {filename}: {e}')
    
    return processed_files

def get_user_input():
    """Get directory, pattern, and recursive option from user."""
    
    # Get directory path
    directory = input("Enter the directory path (default: ~/Documents/S6): ").strip()
    if not directory:
        directory = "~/Documents/S6"
    
    # Expand user home directory
    directory = os.path.expanduser(directory)
    
    # Verify directory exists
    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        return None, None, None
    
    # Get pattern to remove
    part_to_remove = input("Enter the text/pattern to remove from filenames (default: ' -Ktunotes.in'): ").strip()
    if not part_to_remove:
        part_to_remove = ' -Ktunotes.in'
    
    # Ask about recursive processing
    recursive_input = input("Process subdirectories recursively? (y/n, default: n): ").strip().lower()
    recursive = recursive_input in ['y', 'yes', '1', 'true']
    
    # Show summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Directory: {directory}")
    print(f"Pattern to remove: '{part_to_remove}'")
    print(f"Recursive: {'Yes' if recursive else 'No'}")
    print("="*50)
    
    # Ask for confirmation
    confirm = input("\nProceed with renaming? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Operation cancelled.")
        return None, None, None
    
    return directory, part_to_remove, recursive

def main():
    """Main function to run the program."""
    print("File Rename Utility")
    print("-" * 50)
    
    # Get user input
    directory, part_to_remove, recursive = get_user_input()
    
    if directory is None:
        return
    
    # Process the files
    try:
        print(f"\nStarting rename operation...")
        processed_count = remove_part_from_filenames(directory, part_to_remove, recursive)
        print(f"\nOperation completed. {processed_count} file(s) renamed.")
        
    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

# Alternative: If you want to keep the original simple call style
def simple_remove_part(directory, part_to_remove, recursive=False):
    """Simple version that doesn't prompt for input."""
    directory = os.path.expanduser(directory)
    return remove_part_from_filenames(directory, part_to_remove, recursive)

if __name__ == "__main__":
    # Run with interactive prompts
    main()
    
    # Or use the simple version directly:
    # directory = "~/Documents/"
    # part_to_remove = ' -Ktunotes.in'
    # recursive = True  # Set to True for recursive processing
    # simple_remove_part(directory, part_to_remove, recursive)
