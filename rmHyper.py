import fitz  # PyMuPDF
import os

def remove_hyperlinks(file_path):
    # Open the input PDF
    doc = fitz.open(file_path)

    # Iterate through each page
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # Get the list of links on the page
        links = page.get_links()

        # Remove each link
        for link in links:
            page.delete_link(link)

    # Save the modified PDF to a temporary file
    temp_pdf = file_path + '.tmp'
    doc.save(temp_pdf)
    doc.close()

    # Replace the original file with the temporary file
    os.replace(temp_pdf, file_path)
    print(f'Hyperlinks removed from: {file_path}')

def process_all_pdfs_in_folder(folder_path):
    # List all files in the directory
    for filename in os.listdir(folder_path):
        # Construct full file path
        file_path = os.path.join(folder_path, filename)

        # Check if it is a file and has a .pdf extension
        if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
            remove_hyperlinks(file_path)

# Specify the folder path
folder_path = "/home/zero/Documents/College/Latex/"

# Call the function to process all PDFs in the folder
process_all_pdfs_in_folder(folder_path)
