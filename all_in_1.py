import requests
import os
import re
import time
import fitz  # PyMuPDF
from urllib.parse import urljoin, unquote
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
    
    # ==================== IMPROVED DOWNLOAD FUNCTIONS ====================
    
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
    
    def get_drive_filename(self, file_id):
        """Try to get the original filename from Google Drive"""
        try:
            # Get the view page to extract filename
            view_url = f"https://drive.google.com/file/d/{file_id}/view"
            response = self.session.get(view_url, timeout=10)
            
            # Look for the title in the HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Method 1: Look for title tag
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text.strip()
                # Title format is usually "filename - Google Drive"
                if ' - Google Drive' in title:
                    filename = title.replace(' - Google Drive', '').strip()
                    # Clean the filename
                    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                    if filename.endswith('.pdf') or '.pdf' in filename.lower():
                        return filename
                    else:
                        return f"{filename}.pdf"
            
            # Method 2: Look for meta property og:title
            meta_title = soup.find('meta', property='og:title')
            if meta_title and meta_title.get('content'):
                filename = meta_title.get('content').strip()
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                return filename
            
        except Exception as e:
            print(f"⚠️  Could not get filename from Drive: {e}")
        
        return None
    
    def extract_module_info_from_context(self, html_content, file_id, link_text=""):
        """Extract module information from context for better filename"""
        # Try different methods to get module number
        
        # Method 1: Look for module patterns near the file_id
        idx = html_content.find(file_id)
        if idx != -1:
            # Look around the file_id (200 chars before, 100 chars after)
            context_start = max(0, idx - 300)
            context_end = min(len(html_content), idx + 150)
            context = html_content[context_start:context_end]
            
            # Common module patterns
            module_patterns = [
                r'Module\s*[:\-]?\s*(\d+)[^<]*',  # Module 1, Module: 1, Module-1
                r'Mod\s*[:\-]?\s*(\d+)[^<]*',     # Mod 1, Mod: 1, Mod-1
                r'M\s*[:\-]?\s*(\d+)[^<]*',       # M1, M:1, M-1
                r'MODULE\s*[:\-]?\s*(\d+)[^<]*',  # MODULE 1
                r'Module\s*([IVXivx]+)[^<]*',     # Module I, Module II
                r'Mod\s*([IVXivx]+)[^<]*',        # Mod I, Mod II
            ]
            
            for pattern in module_patterns:
                match = re.search(pattern, context, re.IGNORECASE)
                if match:
                    module_num = match.group(1)
                    # Convert Roman numerals to numbers if needed
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5'}
                    module_num = roman_map.get(module_num.upper(), module_num)
                    return f"Module_{module_num.zfill(2)}"
        
        # Method 2: Check link text
        if link_text:
            link_lower = link_text.lower()
            if 'module' in link_lower or 'mod' in link_lower:
                # Extract number from link text
                num_match = re.search(r'(\d+|i{1,3}|iv|v)', link_text, re.IGNORECASE)
                if num_match:
                    module_num = num_match.group(1)
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5'}
                    module_num = roman_map.get(module_num.upper(), module_num)
                    return f"Module_{module_num.zfill(2)}"
        
        return None
    
    def download_drive_pdf(self, url, save_path, context_html="", link_text=""):
        """Download PDF from Google Drive link with better filename"""
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
            
            # Try to get content-disposition for original filename
            content_disposition = response.headers.get('content-disposition', '')
            original_filename = None
            
            if 'filename=' in content_disposition:
                # Extract filename from content-disposition
                filename_match = re.search(r'filename\*?=["\']?(?:UTF-8[\'"]*)?([^"\';]+)', content_disposition, re.IGNORECASE)
                if filename_match:
                    original_filename = unquote(filename_match.group(1))
                else:
                    # Fallback to simpler extraction
                    filename_match = re.search(r'filename=["\']?([^"\']+)["\']?', content_disposition, re.IGNORECASE)
                    if filename_match:
                        original_filename = filename_match.group(1)
            
            # If no content-disposition, try to get from Google Drive page
            if not original_filename:
                original_filename = self.get_drive_filename(file_id)
            
            # If we have an original filename, use it
            if original_filename:
                # Clean the filename
                original_filename = unquote(original_filename)
                # Remove .pdf.pdf if present
                original_filename = re.sub(r'\.pdf\.pdf$', '.pdf', original_filename, flags=re.IGNORECASE)
                # Ensure it ends with .pdf
                if not original_filename.lower().endswith('.pdf'):
                    original_filename += '.pdf'
                # Clean invalid characters
                original_filename = re.sub(r'[<>:"/\\|?*]', '_', original_filename)
                filename = original_filename
            else:
                # Try to get module info for better naming
                module_info = self.extract_module_info_from_context(context_html, file_id, link_text)
                if module_info:
                    filename = f"{module_info}.pdf"
                else:
                    # Generate a meaningful name based on current filename
                    current_name = Path(save_path).name
                    name_without_ext = Path(save_path).stem
                    # If it's already Document_XX, keep it
                    if name_without_ext.startswith('Document_'):
                        filename = current_name
                    else:
                        # Otherwise create a sequential name
                        filename = f"Document_{int(time.time()) % 10000}.pdf"
            
            # Update save_path with new filename
            new_save_path = Path(save_path).parent / filename
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(new_save_path), exist_ok=True)
            
            # Save the file
            with open(new_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(new_save_path)
            print(f"    ✅ Downloaded: {filename} ({file_size:,} bytes)")
            
            # Check if it's a valid PDF
            try:
                with open(new_save_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        print(f"⚠️  Warning: File may not be a valid PDF: {filename}")
                        return False
            except:
                pass
            
            return new_save_path  # Return the new path with better filename
            
        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
            return False
    
    def get_subject_links(self, semester_url):
        """Extract ALL subject links from a semester page including all subjects"""
        try:
            print(f"\n🔍 Fetching subjects from: {semester_url}")
            response = self.session.get(semester_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            subject_links = []
            
            # Method 1: Look for ALL elementor-button links (ALL subjects including fa-book-open)
            buttons = soup.find_all('a', class_='elementor-button')
            
            for button in buttons:
                href = button.get('href')
                if href:
                    # Check if it's a notes link - broader check
                    if '/ktu-' in href and ('-notes-' in href or 'notes/' in href):
                        # Extract subject name from button text
                        text_element = button.find('span', class_='elementor-button-text')
                        if text_element:
                            subject_name = text_element.get_text(strip=True)
                            
                            # Clean subject name
                            subject_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
                            subject_name = re.sub(r'\s+', ' ', subject_name).strip()
                            
                            # Filter out non-subject buttons (but keep ALL actual subjects)
                            exclude_keywords = ['CURRICULUM', 'SYLLABUS', 'QUESTION PAPER', 'EXAM', 'TIMETABLE']
                            if (len(subject_name) > 5 and 
                                not any(keyword in subject_name.upper() for keyword in exclude_keywords)):
                                full_url = urljoin(semester_url, href)
                                subject_links.append((full_url, subject_name))
            
            # Method 2: Also look for any links that might be subjects in the main content
            # This catches any subjects that might be missed by method 1
            content_sections = soup.select('.elementor-widget-wrap, .elementor-section')
            for section in content_sections:
                links = section.find_all('a', href=True)
                for link in links:
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    
                    # Look for subject links (more flexible)
                    if (href and text and len(text) > 5 and
                        ('/ktu-' in href or 'notes' in href.lower()) and
                        not any(excl in text.upper() for excl in ['CURRICULUM', 'SYLLABUS', 'QUESTION'])):
                        
                        # Check if it looks like a subject name
                        if not any(term in text.lower() for term in ['home', 'about', 'contact', 'privacy']):
                            full_url = urljoin(semester_url, href)
                            # Check if we already have this URL
                            if not any(url == full_url for url, _ in subject_links):
                                clean_name = re.sub(r'[<>:"/\\|?*&]', '_', text)
                                clean_name = re.sub(r'\s+', ' ', clean_name).strip()
                                subject_links.append((full_url, clean_name))
            
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
        """Find all Google Drive links on a subject page with context"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            drive_links = []
            
            # Find all Google Drive links with their context
            # Look for links in the HTML
            for link in soup.find_all('a', href=True):
                href = link['href']
                link_text = link.get_text(strip=True)
                
                if 'drive.google.com' in href:
                    file_id = self.extract_file_id(href)
                    if file_id:
                        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                        # Check if we already have this file_id
                        if not any(fid == file_id for _, fid, _ in drive_links):
                            drive_links.append((drive_url, file_id, link_text))
            
            # Also search in raw text for drive links
            patterns = [
                r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
                r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
                r'drive\.google\.com/uc\?[^"\'>]*id=([a-zA-Z0-9_-]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content)
                for file_id in matches:
                    drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                    if not any(fid == file_id for _, fid, _ in drive_links):
                        # Try to find link text near this file_id
                        link_text = ""
                        idx = html_content.find(file_id)
                        if idx != -1:
                            # Look for nearby text
                            start = max(0, idx - 150)
                            end = min(len(html_content), idx + 150)
                            context = html_content[start:end]
                            soup_context = BeautifulSoup(context, 'html.parser')
                            link_elem = soup_context.find('a', href=lambda x: x and file_id in x)
                            if link_elem:
                                link_text = link_elem.get_text(strip=True)
                        
                        drive_links.append((drive_url, file_id, link_text))
            
            return drive_links, html_content
            
        except Exception as e:
            print(f"❌ Error finding drive links on {url}: {e}")
            return [], ""
    
    # ==================== PDF PROCESSING FUNCTIONS ====================
    
    def remove_part_from_filename(self, file_path):
        """Remove ktunotes patterns from filename"""
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Patterns to remove
        patterns_to_remove = [
            r' - Ktunotes\.in',
            r' - ktunotes\.in',
            r' -ktunotes\.in',
            r' - KTUnotes',
            r' - ktunotes',
            r'_Ktunotes\.in',
            r'_ktunotes\.in',
            r'\(Ktunotes\.in\)',
            r'\(ktunotes\.in\)',
        ]
        
        new_filename = filename
        for pattern in patterns_to_remove:
            new_filename = re.sub(pattern, '', new_filename, flags=re.IGNORECASE)
        
        # Remove extra spaces and clean up
        new_filename = re.sub(r'\s+', ' ', new_filename).strip()
        new_filename = re.sub(r'\.pdf\.pdf$', '.pdf', new_filename, flags=re.IGNORECASE)
        
        if new_filename != filename:
            new_file_path = os.path.join(directory, new_filename)
            
            # Avoid overwriting
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
        """Remove hyperlinks from PDF"""
        try:
            doc = fitz.open(file_path)
            modified = False
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                links = page.get_links()
                
                for link in links:
                    page.delete_link(link)
                    modified = True
            
            if modified:
                temp_pdf = file_path + '.tmp'
                doc.save(temp_pdf)
                doc.close()
                os.replace(temp_pdf, file_path)
                print(f"    🔗 Removed hyperlinks from: {os.path.basename(file_path)}")
            else:
                doc.close()
            
            return True
            
        except Exception as e:
            print(f"❌ Error removing hyperlinks: {e}")
            return False
    
    def process_pdf_file(self, file_path, options):
        """Process a single PDF file"""
        filename = os.path.basename(file_path)
        
        if options.get('rename', False):
            file_path = self.remove_part_from_filename(file_path)
        
        if options.get('remove_hyperlinks', False):
            self.remove_hyperlinks_from_pdf(file_path)
        
        return file_path
    
    # ==================== MAIN SCRAPER FUNCTION ====================
    
    def scrape_subject(self, subject_url, subject_name, subject_dir, options):
        """Scrape a subject page with proper filenames"""
        print(f"\n📚 Processing: {subject_name}")
        print(f"   🔗 URL: {subject_url}")
        
        # Get drive links with context
        drive_links, html_content = self.find_drive_links_on_page(subject_url)
        
        if not drive_links:
            print(f"   ⚠️  No Google Drive links found on this page")
            return 0
        
        print(f"   📄 Found {len(drive_links)} Google Drive link(s)")
        
        downloaded_count = 0
        for i, (drive_url, file_id, link_text) in enumerate(drive_links, 1):
            print(f"   📥 Processing link {i}/{len(drive_links)}")
            
            # Create initial filename (will be improved during download)
            module_info = self.extract_module_info_from_context(html_content, file_id, link_text)
            if module_info:
                filename = f"{module_info}.pdf"
            else:
                filename = f"Document_{i:02d}.pdf"
            
            # Clean filename
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # Full save path
            save_path = os.path.join(subject_dir, filename)
            
            # Check if file already exists
            if os.path.exists(save_path):
                print(f"   ⏭️  Skipping (already exists): {filename}")
                
                # Process existing file
                if options.get('rename', False) or options.get('remove_hyperlinks', False):
                    self.process_pdf_file(save_path, options)
                continue
            
            # Download with delay
            time.sleep(1.5)
            
            # Download with improved filename handling
            result = self.download_drive_pdf(drive_url, save_path, html_content, link_text)
            
            if result:
                if isinstance(result, str):  # New path returned
                    save_path = result
                downloaded_count += 1
                
                # Process the downloaded file
                self.process_pdf_file(save_path, options)
        
        return downloaded_count
    
    # ==================== INTERACTIVE RUNNER ====================
    
    def get_processing_options(self):
        """Get PDF processing options"""
        print("\n" + "-"*60)
        print("⚙️  PDF PROCESSING OPTIONS")
        print("-"*60)
        
        options = {}
        
        rename_choice = input("Remove 'Ktunotes.in' from filenames? (yes/no, default: yes): ").strip().lower()
        options['rename'] = rename_choice in ['yes', 'y', '']
        
        hyperlinks_choice = input("Remove hyperlinks from PDFs? (yes/no, default: no): ").strip().lower()
        options['remove_hyperlinks'] = hyperlinks_choice in ['yes', 'y']
        
        return options
    
    def run(self):
        """Main interactive runner"""
        print("\n" + "="*60)
        print("🎓 IMPROVED KTU NOTES DOWNLOADER")
        print("   Now with proper filenames and ALL subjects!")
        print("="*60)
        
        # Get semester URL
        default_url = "https://www.ktunotes.in/ktu-s6-cse-notes-2019-scheme/"
        url_input = input(f"\nEnter semester URL (default: {default_url}): ").strip()
        semester_url = url_input if url_input else default_url
        
        # Get download location - ACCEPTS FULL PATHS
        default_dir = "KTU_Notes"
        dir_prompt = f"\nEnter download folder name or full path\nExamples:\n"
        dir_prompt += f"  • Folder name: '{default_dir}' (creates in current directory)\n"
        dir_prompt += f"  • Full path: 'C:\\Users\\Name\\Documents\\KTU' or '/home/user/KTU'\n"
        dir_prompt += f"Download location (default: {default_dir}): "
        
        dir_input = input(dir_prompt).strip()
        download_dir = dir_input if dir_input else default_dir
        
        # Handle full paths
        self.download_dir = Path(download_dir)
        if not self.download_dir.is_absolute():
            # If it's a relative path, make it absolute relative to current directory
            self.download_dir = Path.cwd() / self.download_dir
        
        print(f"\n📁 Download location: {self.download_dir.absolute()}")
        
        # Get processing options
        options = self.get_processing_options()
        
        # Get subject links - NOW INCLUDES ALL SUBJECTS
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
        print("  • Numbers separated by commas: 1,3,5")
        print("  • Range: 1-5")
        print("  • 'all' for all subjects")
        print("  • 'none' to exit")
        
        while True:
            choice = input("\nSelect subjects to download: ").strip().lower()
            
            if choice == 'none':
                print("Exiting...")
                return
            
            selected_indices = []
            
            if choice == 'all':
                selected_indices = list(range(len(subject_links)))
                break
            
            elif '-' in choice:
                try:
                    start, end = map(int, choice.split('-'))
                    if 1 <= start <= end <= len(subject_links):
                        selected_indices = list(range(start-1, end))
                        break
                    else:
                        print(f"❌ Invalid range. Use 1-{len(subject_links)}")
                except:
                    print("❌ Invalid format. Use '1-5'")
            
            else:
                try:
                    indices = [int(idx.strip()) for idx in choice.split(',')]
                    valid_indices = []
                    for idx in indices:
                        if 1 <= idx <= len(subject_links):
                            valid_indices.append(idx-1)
                        else:
                            print(f"❌ Index {idx} out of range (1-{len(subject_links)})")
                    
                    if valid_indices:
                        selected_indices = valid_indices
                        break
                    else:
                        print("❌ No valid indices selected")
                except ValueError:
                    print("❌ Please enter valid numbers")
            
            print(f"Available: 1 to {len(subject_links)}")
        
        if not selected_indices:
            print("❌ No subjects selected")
            return
        
        # Show selection
        print(f"\n📋 SELECTED {len(selected_indices)} SUBJECT(S):")
        for idx in selected_indices:
            _, name = subject_links[idx]
            print(f"  • {name}")
        
        print(f"\n⚙️  PROCESSING OPTIONS:")
        if options['rename']:
            print("  • Remove 'Ktunotes.in' from filenames: ✅ ENABLED")
        if options['remove_hyperlinks']:
            print("  • Remove hyperlinks from PDFs: ✅ ENABLED")
        if not options['rename'] and not options['remove_hyperlinks']:
            print("  • No processing selected (raw download)")
        
        # Confirm
        confirm = input("\nStart download? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Download cancelled.")
            return
        
        # Create main directory
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n" + "="*60)
        print("🚀 STARTING DOWNLOAD")
        print("="*60)
        
        total_downloaded = 0
        
        for i, subject_idx in enumerate(selected_indices, 1):
            subject_url, subject_name = subject_links[subject_idx]
            
            print(f"\n{'─'*40}")
            print(f"📚 Subject {i}/{len(selected_indices)}: {subject_name}")
            
            # Create subject directory
            clean_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            clean_name = clean_name[:80]
            subject_dir = self.download_dir / clean_name
            subject_dir.mkdir(parents=True, exist_ok=True)
            
            # Scrape subject
            downloaded = self.scrape_subject(subject_url, subject_name, subject_dir, options)
            total_downloaded += downloaded
            
            print(f"   📊 Progress: {i}/{len(selected_indices)} subjects")
            print(f"   📈 Downloaded so far: {total_downloaded} files")
            
            if i < len(selected_indices):
                print(f"   ⏳ Waiting 2 seconds...")
                time.sleep(2)
        
        # Final summary
        print(f"\n{'='*60}")
        print("✅ DOWNLOAD COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • Subjects processed: {len(selected_indices)}")
        print(f"  • Total files downloaded: {total_downloaded}")
        print(f"  • Location: {self.download_dir.absolute()}")
        print(f"{'='*60}")
        
        print(f"\n📁 FOLDER STRUCTURE:")
        for item in sorted(self.download_dir.iterdir()):
            if item.is_dir():
                pdf_count = len([f for f in item.iterdir() if f.is_file() and f.suffix.lower() == '.pdf'])
                if pdf_count > 0:
                    print(f"  ├── {item.name}/ ({pdf_count} PDFs)")
        
        print(f"\n🎉 Done! Files now have proper names!")

def main():
    print("\n🎓 KTU NOTES DOWNLOADER - IMPROVED VERSION")
    print("   Fixes: All subjects + Better filenames + Full paths support\n")
    
    # Check dependencies
    try:
        import fitz
    except ImportError:
        print("⚠️  PyMuPDF not installed. Hyperlink removal disabled.")
        print("   Install: pip install PyMuPDF")
    
    scraper = AllInOneKTUScraper()
    
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
        print("Packages installed. Please run again.")
        sys.exit(0)
    
    main()
