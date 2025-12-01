import requests
import os
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pathlib import Path
import sys

class KTUNotesSelectorScraper:
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
            
            # Check if it's a valid PDF
            with open(save_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    print(f"⚠️  Warning: File may not be a valid PDF: {os.path.basename(save_path)}")
                    return False
            
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
            
            # Method 1: Look for subject buttons with book icons
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
                                'SYLLABUS' not in subject_name.upper() and
                                'QUESTION' not in subject_name.upper()):
                                full_url = urljoin(semester_url, href)
                                subject_links.append((full_url, subject_name))
            
            # Method 2: If no buttons found, look for any subject links
            if not subject_links:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    if (href and text and 
                        '/ktu-' in href and 
                        '-notes-' in href and
                        len(text) > 10):  # Subject names are usually longer
                        subject_name = text
                        subject_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
                        subject_name = re.sub(r'\s+', ' ', subject_name).strip()
                        
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
                r'/d/([a-zA-Z0-9_-]+)/view',
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
    
    def scrape_subject(self, subject_url, subject_name, subject_dir):
        """Scrape a subject page and download all PDFs"""
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
            # Try to find any links with "module" in the text
            soup = BeautifulSoup(html_content, 'html.parser')
            module_links = []
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True).lower()
                if 'module' in text or 'mod' in text or 'mod-' in text:
                    href = link.get('href')
                    if href and 'drive.google.com' in href:
                        file_id = self.extract_file_id(href)
                        if file_id:
                            drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                            if drive_url not in [link[0] for link in drive_links]:
                                drive_links.append((drive_url, file_id))
                                print(f"   Found module link: {text}")
            
            if not drive_links:
                return 0
        
        print(f"   📄 Found {len(drive_links)} Google Drive link(s)")
        
        downloaded_count = 0
        for i, (drive_url, file_id) in enumerate(drive_links, 1):
            # Try to determine module number from context
            module_num = None
            
            # Look for module patterns in the HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            all_text = soup.get_text()
            
            # Find position of file_id in text
            idx = all_text.find(file_id)
            if idx != -1:
                # Look backward for module number
                before_text = all_text[max(0, idx-300):idx]
                
                # Try different module patterns
                module_patterns = [
                    r'Module\s*[:\-]?\s*(\d+)',
                    r'Mod\s*[:\-]?\s*(\d+)',
                    r'M\s*[:\-]?\s*(\d+)',
                    r'MODULE\s*[:\-]?\s*(\d+)',
                    r'Module\s*[:\-]?\s*([IVXivx]+)',
                    r'Mod\s*[:\-]?\s*([IVXivx]+)',
                ]
                
                for pattern in module_patterns:
                    match = re.search(pattern, before_text, re.IGNORECASE)
                    if match:
                        module_num = match.group(1)
                        break
            
            # Create filename
            if module_num:
                if module_num.isdigit():
                    filename = f"Module_{int(module_num):02d}.pdf"
                else:
                    filename = f"Module_{module_num}.pdf"
            else:
                filename = f"Document_{i:02d}.pdf"
            
            # Clean filename
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # Full save path
            save_path = os.path.join(subject_dir, filename)
            
            # Check if file already exists
            if os.path.exists(save_path):
                print(f"   ⏭️  Skipping (already exists): {filename}")
                continue
            
            # Download with delay
            print(f"   📥 Downloading [{i}/{len(drive_links)}]: {filename}")
            time.sleep(1.5)
            
            if self.download_drive_pdf(drive_url, save_path):
                downloaded_count += 1
        
        return downloaded_count
    
    def get_semester_name_from_url(self, url):
        """Extract semester name from URL"""
        # Try to extract semester from URL
        patterns = [
            r'/s(\d+)-',
            r'/semester-(\d+)-',
            r'/(s\d+)-',
            r's(\d+)_',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return f"S{match.group(1)}"
        
        # Default
        return "Unknown_Semester"
    
    def run(self):
        """Main interactive runner"""
        print("\n" + "="*60)
        print("🎓 KTU NOTES DOWNLOADER")
        print("="*60)
        
        # Get semester URL
        default_url = "https://www.ktunotes.in/ktu-s6-cse-notes-2019-scheme/"
        url_input = input(f"\nEnter semester URL (default: {default_url}): ").strip()
        
        if not url_input:
            semester_url = default_url
        else:
            semester_url = url_input
        
        # Extract semester name
        semester_name = self.get_semester_name_from_url(semester_url)
        print(f"\n📅 Detected semester: {semester_name}")
        
        # Get download location
        default_dir = f"KTU_{semester_name}_Notes"
        dir_input = input(f"\nDownload folder name (default: {default_dir}): ").strip()
        download_dir = dir_input if dir_input else default_dir
        
        self.download_dir = Path(download_dir)
        
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
            
            # Handle ranges like "1-5"
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
        
        # Confirm download
        confirm = input("\nStart download? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Download cancelled.")
            return
        
        # Create semester directory
        semester_dir = self.download_dir / semester_name
        semester_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📁 Download location: {semester_dir.absolute()}")
        print("\n" + "="*60)
        print("🚀 STARTING DOWNLOAD")
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
            clean_name = clean_name[:80]  # Limit length
            
            # Create subject directory
            subject_dir = semester_dir / clean_name
            subject_dir.mkdir(parents=True, exist_ok=True)
            
            # Scrape the subject
            downloaded = self.scrape_subject(subject_url, subject_name, subject_dir)
            total_downloaded += downloaded
            
            # Progress summary
            print(f"   📊 Progress: {i}/{total_subjects} subjects")
            print(f"   📈 Downloaded so far: {total_downloaded} files")
            
            # Add delay between subjects (except last one)
            if i < total_subjects:
                print(f"   ⏳ Waiting 2 seconds before next subject...")
                time.sleep(2)
        
        # Final summary
        print(f"\n{'='*60}")
        print("✅ DOWNLOAD COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • Semester: {semester_name}")
        print(f"  • Subjects processed: {total_subjects}")
        print(f"  • Total files downloaded: {total_downloaded}")
        print(f"  • Location: {semester_dir.absolute()}")
        print(f"{'='*60}")
        
        # Show folder structure
        print(f"\n📁 FOLDER STRUCTURE:")
        for item in semester_dir.iterdir():
            if item.is_dir():
                file_count = len([f for f in item.iterdir() if f.is_file()])
                print(f"  ├── {item.name}/ ({file_count} files)")
        
        print(f"\n🎉 Done! All notes have been downloaded.")

# Quick test function
def quick_test():
    """Quick test with S6"""
    scraper = KTUNotesSelectorScraper()
    
    # Test URL
    test_url = "https://www.ktunotes.in/ktu-s6-cse-notes-2019-scheme/"
    
    # Get subjects
    print("Testing subject extraction...")
    subjects = scraper.get_subject_links(test_url)
    
    if subjects:
        print(f"\nFound {len(subjects)} subjects:")
        for i, (url, name) in enumerate(subjects, 1):
            print(f"{i}. {name}")
        
        # Test downloading first subject
        test_choice = input("\nTest download first subject? (yes/no): ").strip().lower()
        if test_choice in ['yes', 'y']:
            subject_url, subject_name = subjects[0]
            print(f"\nTesting download for: {subject_name}")
            
            test_dir = Path("KTU_Test") / "S6" / subject_name
            test_dir.mkdir(parents=True, exist_ok=True)
            
            scraper.scrape_subject(subject_url, subject_name, test_dir)
    else:
        print("❌ No subjects found")

# Main function
def main():
    print("\n🎓 KTU NOTES SELECTIVE DOWNLOADER")
    print("   Download only the subjects you need!\n")
    
    # Create scraper instance
    scraper = KTUNotesSelectorScraper()
    
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Download interrupted by user.")
        print("Partial downloads have been saved.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        print("Please check your internet connection and try again.")

if __name__ == "__main__":
    # Uncomment to run quick test first
    # quick_test()
    
    # Run the main interactive scraper
    main()
