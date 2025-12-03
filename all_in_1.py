import requests
import os
import re
import time
import fitz  # PyMuPDF
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pathlib import Path
import sys

class AllInOneKTUScraper:
    def __init__(self, download_dir="KTU_Notes"):
        self.base_url = "https://www.ktunotes.in"
        self.download_dir = Path(download_dir)
        self.session = requests.Session()
        self.setup_session()
        
    def setup_session(self):
        """Setup session with headers"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session.headers.update(headers)
    
    # ==================== DOWNLOAD FUNCTIONS ====================
    
    def extract_file_id(self, url):
        """Extract Google Drive file ID from URL"""
        patterns = [
            r'/file/d/([a-zA-Z0-9_-]+)',
            r'/d/([a-zA-Z0-9_-]+)/',
            r'id=([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def download_drive_pdf(self, url, save_path):
        """Download PDF from Google Drive link"""
        file_id = self.extract_file_id(url)
        
        if not file_id:
            print(f"❌ Could not extract file ID from: {url}")
            return False
        
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        try:
            # First request
            response = self.session.get(download_url, stream=True, timeout=30)
            
            # Check for warning page
            if "Google Drive - Virus scan warning" in response.text:
                # Extract confirm token
                confirm_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', response.text)
                if confirm_match:
                    confirm_token = confirm_match.group(1)
                    download_url = f"{download_url}&confirm={confirm_token}"
                    response = self.session.get(download_url, stream=True, timeout=30)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Save the file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(save_path)
            print(f"    ✅ Downloaded: {os.path.basename(save_path)} ({file_size:,} bytes)")
            return True
            
        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
            return False
    
    def get_subject_links(self, semester_url):
        """Extract subject links from a semester page"""
        try:
            print(f"\n🔍 Fetching subjects from: {semester_url}")
            response = self.session.get(semester_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            subject_links = []
            
            # Look for subject buttons with book icons
            buttons = soup.find_all('a', class_='elementor-button')
            
            for button in buttons:
                href = button.get('href')
                if href:
                    # Check if it's a notes link
                    if '/ktu-' in href and '-notes-' in href:
                        # Extract subject name from button text
                        text_element = button.find('span', class_='elementor-button-text')
                        if text_element:
                            subject_name = text_element.get_text(strip=True)
                            # Clean subject name
                            subject_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
                            subject_name = re.sub(r'\s+', ' ', subject_name).strip()
                            
                            # Filter out non-subject buttons
                            if (len(subject_name) > 5 and 
                                'CURRICULUM' not in subject_name.upper() and
                                'SYLLABUS' not in subject_name.upper()):
                                full_url = urljoin(semester_url, href)
                                subject_links.append((full_url, subject_name))
            
            # Remove duplicates while preserving order
            seen = set()
            unique_links = []
            for link_url, link_text in subject_links:
                if link_url not in seen:
                    seen.add(link_url)
                    unique_links.append((link_url, link_text))
            
            return unique_links
            
        except Exception as e:
            print(f"❌ Error fetching subject links: {e}")
            return []
    
    def find_drive_links_on_page(self, url):
        """Find all Google Drive links on a subject page"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            drive_links = []
            
            # Find all Google Drive file IDs in the page
            patterns = [
                r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
                r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
                r'drive\.google\.com/uc\?[^"\'>]*id=([a-zA-Z0-9_-]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                for file_id in matches:
                    drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                    if drive_url not in [link[0] for link in drive_links]:
                        drive_links.append((drive_url, file_id))
            
            return drive_links
            
        except Exception as e:
            print(f"❌ Error finding drive links on {url}: {e}")
            return []
    
    # ==================== PDF PROCESSING FUNCTIONS ====================
    
    def remove_part_from_filename(self, file_path, part_to_remove=' -Ktunotes.in'):
        """Remove specific part from filename"""
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Remove the specific part from the filename using regex
        new_filename = re.sub(re.escape(part_to_remove), '', filename, flags=re.IGNORECASE)
        
        # Also remove any other common unwanted patterns
        patterns_to_remove = [
            r' - Ktunotes\.in',
            r' - ktunotes\.in',
            r' -ktunotes',
            r' - KTUnotes',
            r' - ktunotes',
            r'_Ktunotes\.in',
            r'_ktunotes\.in',
        ]
        
        for pattern in patterns_to_remove:
            new_filename = re.sub(pattern, '', new_filename, flags=re.IGNORECASE)
        
        # Remove extra spaces
        new_filename = re.sub(r'\s+', ' ', new_filename).strip()
        
        if new_filename != filename:
            new_file_path = os.path.join(directory, new_filename)
            
            # Ensure we don't overwrite existing file
            counter = 1
            while os.path.exists(new_file_path):
                name_part, ext = os.path.splitext(new_filename)
                new_filename = f"{name_part}_{counter}{ext}"
                new_file_path = os.path.join(directory, new_filename)
                counter += 1
            
            os.rename(file_path, new_file_path)
            print(f"    📝 Renamed: {filename} → {new_filename}")
            return new_file_path
        
        return file_path
    
    def remove_hyperlinks_from_pdf(self, file_path):
        """Remove hyperlinks from PDF using PyMuPDF"""
        try:
            # Open the input PDF
            doc = fitz.open(file_path)
            modified = False
            
            # Iterate through each page
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Get the list of links on the page
                links = page.get_links()
                
                # Remove each link
                for link in links:
                    page.delete_link(link)
                    modified = True
            
            if modified:
                # Save to a temporary file
                temp_pdf = file_path + '.tmp'
                doc.save(temp_pdf)
                doc.close()
                
                # Replace the original file
                os.replace(temp_pdf, file_path)
                print(f"    🔗 Removed hyperlinks from: {os.path.basename(file_path)}")
            else:
                doc.close()
                
            return True
            
        except Exception as e:
            print(f"❌ Error removing hyperlinks from {file_path}: {e}")
            return False
    
    def process_pdf_file(self, file_path, options):
        """Process a single PDF file with selected options"""
        filename = os.path.basename(file_path)
        
        # 1. Rename file if requested
        if options.get('rename', False):
            file_path = self.remove_part_from_filename(file_path)
        
        # 2. Remove hyperlinks if requested
        if options.get('remove_hyperlinks', False):
            self.remove_hyperlinks_from_pdf(file_path)
        
        return file_path
    
    def process_all_pdfs_in_folder(self, folder_path, options):
        """Process all PDFs in a folder"""
        print(f"\n📄 Processing PDFs in: {folder_path}")
        
        pdf_files = []
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
                pdf_files.append(file_path)
        
        if not pdf_files:
            print("   No PDF files found in this folder")
            return
        
        print(f"   Found {len(pdf_files)} PDF file(s)")
        
        for i, file_path in enumerate(pdf_files, 1):
            print(f"   [{i}/{len(pdf_files)}] Processing: {os.path.basename(file_path)}")
            self.process_pdf_file(file_path, options)
    
    # ==================== MAIN SCRAPER FUNCTION ====================
    
    def scrape_subject(self, subject_url, subject_name, subject_dir, options):
        """Scrape a subject page and download all PDFs with processing"""
        print(f"\n📚 Processing: {subject_name}")
        print(f"   🔗 URL: {subject_url}")
        
        # Get HTML content
        try:
            response = self.session.get(subject_url, timeout=15)
            html_content = response.text
        except Exception as e:
            print(f"❌ Error accessing page: {e}")
            return 0
        
        # Find all drive links
        drive_links = self.find_drive_links_on_page(subject_url)
        
        if not drive_links:
            print(f"   ⚠️  No Google Drive links found on this page")
            return 0
        
        print(f"   📄 Found {len(drive_links)} Google Drive link(s)")
        
        downloaded_count = 0
        for i, (drive_url, file_id) in enumerate(drive_links, 1):
            # Try to determine module number
            module_num = None
            
            # Look for module patterns in the HTML
            idx = html_content.find(file_id)
            if idx != -1:
                before_text = html_content[max(0, idx-300):idx]
                
                module_patterns = [
                    r'Module\s*[:\-]?\s*(\d+)',
                    r'Mod\s*[:\-]?\s*(\d+)',
                    r'M\s*[:\-]?\s*(\d+)',
                    r'MODULE\s*[:\-]?\s*(\d+)',
                ]
                
                for pattern in module_patterns:
                    match = re.search(pattern, before_text, re.IGNORECASE)
                    if match:
                        module_num = match.group(1)
                        break
            
            # Create filename
            if module_num:
                filename = f"Module_{int(module_num):02d}.pdf"
            else:
                filename = f"Document_{i:02d}.pdf"
            
            # Clean filename
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # Full save path
            save_path = os.path.join(subject_dir, filename)
            
            # Check if file already exists
            if os.path.exists(save_path):
                print(f"   ⏭️  Skipping (already exists): {filename}")
                
                # Process existing file if options are enabled
                if options.get('rename', False) or options.get('remove_hyperlinks', False):
                    self.process_pdf_file(save_path, options)
                    
                continue
            
            # Download with delay
            print(f"   📥 Downloading [{i}/{len(drive_links)}]: {filename}")
            time.sleep(1.5)
            
            if self.download_drive_pdf(drive_url, save_path):
                downloaded_count += 1
                
                # Process the downloaded file
                self.process_pdf_file(save_path, options)
        
        return downloaded_count
    
    # ==================== INTERACTIVE RUNNER ====================
    
    def get_processing_options(self):
        """Get PDF processing options from user"""
        print("\n" + "-"*60)
        print("⚙️  PDF PROCESSING OPTIONS")
        print("-"*60)
        
        options = {}
        
        # Rename option
        rename_choice = input("Remove '-Ktunotes.in' from filenames? (yes/no, default: yes): ").strip().lower()
        options['rename'] = rename_choice in ['yes', 'y', '']
        
        # Hyperlinks option
        hyperlinks_choice = input("Remove hyperlinks from PDFs? (yes/no, default: no): ").strip().lower()
        options['remove_hyperlinks'] = hyperlinks_choice in ['yes', 'y']
        
        return options
    
    def run(self):
        """Main interactive runner"""
        print("\n" + "="*60)
        print("🎓 ALL-IN-ONE KTU NOTES DOWNLOADER & PROCESSOR")
        print("="*60)
        
        # Get semester URL
        default_url = "https://www.ktunotes.in/ktu-s6-cse-notes-2019-scheme/"
        url_input = input(f"\nEnter semester URL (default: {default_url}): ").strip()
        
        if not url_input:
            semester_url = default_url
        else:
            semester_url = url_input
        
        # Get download location
        default_dir = "KTU_Notes"
        dir_input = input(f"\nDownload folder name (default: {default_dir}): ").strip()
        download_dir = dir_input if dir_input else default_dir
        
        self.download_dir = Path(download_dir)
        
        # Get processing options
        options = self.get_processing_options()
        
        # Get subject links
        print("\n🔍 Fetching available subjects...")
        subject_links = self.get_subject_links(semester_url)
        
        if not subject_links:
            print("❌ No subjects found. Please check the URL.")
            return
        
        print(f"\n✅ Found {len(subject_links)} subjects:")
        for i, (url, name) in enumerate(subject_links, 1):
            print(f"  {i}. {name}")
        
        # Subject selection
        print("\n" + "-"*60)
        print("📝 SUBJECT SELECTION")
        print("-"*60)
        print("Options:")
        print("  • Enter numbers separated by commas (e.g., 1,3,5)")
        print("  • Enter range (e.g., 1-5)")
        print("  • Enter 'all' for all subjects")
        print("  • Enter 'none' to exit")
        
        while True:
            choice = input("\nSelect subjects to download: ").strip().lower()
            
            if choice == 'none':
                print("Exiting...")
                return
            
            selected_indices = []
            
            if choice == 'all':
                selected_indices = list(range(len(subject_links)))
                break
            
            # Handle ranges
            elif '-' in choice:
                try:
                    start, end = map(int, choice.split('-'))
                    if 1 <= start <= end <= len(subject_links):
                        selected_indices = list(range(start-1, end))
                        break
                    else:
                        print(f"❌ Invalid range. Please enter between 1 and {len(subject_links)}")
                except:
                    print("❌ Invalid format. Use format like '1-5'")
            
            # Handle comma-separated list
            else:
                try:
                    indices = [int(idx.strip()) for idx in choice.split(',')]
                    valid_indices = []
                    for idx in indices:
                        if 1 <= idx <= len(subject_links):
                            valid_indices.append(idx-1)
                        else:
                            print(f"❌ Index {idx} is out of range (1-{len(subject_links)})")
                    
                    if valid_indices:
                        selected_indices = valid_indices
                        break
                    else:
                        print("❌ No valid indices selected")
                except ValueError:
                    print("❌ Please enter valid numbers")
            
            print(f"Available subjects: 1 to {len(subject_links)}")
        
        if not selected_indices:
            print("❌ No subjects selected")
            return
        
        # Show selection summary
        print(f"\n📋 SELECTED {len(selected_indices)} SUBJECT(S):")
        for idx in selected_indices:
            url, name = subject_links[idx]
            print(f"  • {name}")
        
        # Show processing options
        print(f"\n⚙️  PROCESSING OPTIONS:")
        if options['rename']:
            print("  • Remove '-Ktunotes.in' from filenames: ✅ ENABLED")
        if options['remove_hyperlinks']:
            print("  • Remove hyperlinks from PDFs: ✅ ENABLED")
        if not options['rename'] and not options['remove_hyperlinks']:
            print("  • No processing options selected (raw download only)")
        
        # Confirm download
        confirm = input("\nStart download and processing? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Download cancelled.")
            return
        
        # Create main directory
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📁 Download location: {self.download_dir.absolute()}")
        print("\n" + "="*60)
        print("🚀 STARTING DOWNLOAD & PROCESSING")
        print("="*60)
        
        total_downloaded = 0
        total_subjects = len(selected_indices)
        
        for i, subject_idx in enumerate(selected_indices, 1):
            subject_url, subject_name = subject_links[subject_idx]
            
            print(f"\n{'─'*40}")
            print(f"📚 Subject {i}/{total_subjects}: {subject_name}")
            
            # Clean subject name for folder
            clean_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            clean_name = clean_name[:80]
            
            # Create subject directory
            subject_dir = self.download_dir / clean_name
            subject_dir.mkdir(parents=True, exist_ok=True)
            
            # Scrape and process the subject
            downloaded = self.scrape_subject(subject_url, subject_name, subject_dir, options)
            total_downloaded += downloaded
            
            # Progress summary
            print(f"   📊 Progress: {i}/{total_subjects} subjects")
            print(f"   📈 Downloaded so far: {total_downloaded} files")
            
            # Add delay between subjects
            if i < total_subjects:
                print(f"   ⏳ Waiting 2 seconds before next subject...")
                time.sleep(2)
        
        # Final summary
        print(f"\n{'='*60}")
        print("✅ DOWNLOAD & PROCESSING COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • Subjects processed: {total_subjects}")
        print(f"  • Total files downloaded: {total_downloaded}")
        print(f"  • Location: {self.download_dir.absolute()}")
        print(f"{'='*60}")
        
        # Show folder structure
        print(f"\n📁 FOLDER STRUCTURE:")
        for item in sorted(self.download_dir.iterdir()):
            if item.is_dir():
                pdf_count = len([f for f in item.iterdir() if f.is_file() and f.suffix.lower() == '.pdf'])
                if pdf_count > 0:
                    print(f"  ├── {item.name}/ ({pdf_count} PDFs)")
        
        print(f"\n🎉 All notes have been downloaded and processed!")

def main():
    print("\n🎓 ALL-IN-ONE KTU NOTES SCRAPER")
    print("   Downloads, renames, and processes PDFs automatically!\n")
    
    # Check if PyMuPDF is installed
    try:
        import fitz
    except ImportError:
        print("⚠️  PyMuPDF (fitz) is not installed.")
        print("   Hyperlink removal feature will not work.")
        print("   Install it with: pip install PyMuPDF")
        print("\n   Continue without hyperlink removal? (yes/no): ", end="")
        choice = input().strip().lower()
        if choice not in ['yes', 'y']:
            print("Please install PyMuPDF and try again.")
            return
    
    # Create scraper instance
    scraper = AllInOneKTUScraper()
    
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user.")
        print("Partial downloads have been saved.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()
        print("\nPlease check your internet connection and try again.")

if __name__ == "__main__":
    # Install required packages if missing
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
        print("Packages installed. Please run the script again.")
        sys.exit(0)
    
    main()

