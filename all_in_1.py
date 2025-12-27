import requests
import os
import re
import time
import fitz  # PyMuPDF
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from pathlib import Path
import sys

class KTUNotesDownloader:
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
    
    def get_drive_filename(self, file_id):
        """Try to get the original filename from Google Drive"""
        try:
            view_url = f"https://drive.google.com/file/d/{file_id}/view"
            response = self.session.get(view_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Method 1: Look for title tag
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text.strip()
                if ' - Google Drive' in title:
                    filename = title.replace(' - Google Drive', '').strip()
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
        # Check link text first
        if link_text:
            # Common patterns in link text
            patterns = [
                r'(?:Module|Mod|MODULE|MOD|M)\s*[:\-]?\s*(\d+)[^<]*',
                r'(?:Module|Mod|MODULE|MOD|M)\s*[:\-]?\s*([IVXivx]+)[^<]*',
                r'(?:Module|Mod)\s*[:\-]?\s*(\d+)\s*[-–]\s*[^<]*',  # Module 1 - Topic
                r'Module\s*(\d+)\s*[-–]\s*[^<]*',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, link_text, re.IGNORECASE)
                if match:
                    module_num = match.group(1)
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
                                 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
                    module_num = roman_map.get(module_num.upper(), module_num)
                    return f"Module_{module_num.zfill(2)}"
        
        # Search in surrounding context
        idx = html_content.find(file_id)
        if idx != -1:
            context_start = max(0, idx - 500)
            context_end = min(len(html_content), idx + 300)
            context = html_content[context_start:context_end]
            
            # Remove HTML tags for cleaner search
            soup_context = BeautifulSoup(context, 'html.parser')
            clean_context = soup_context.get_text()
            
            module_patterns = [
                r'Module\s*[:\-]?\s*(\d+)[^<]*',
                r'Mod\s*[:\-]?\s*(\d+)[^<]*',
                r'M\s*[:\-]?\s*(\d+)[^<]*',
                r'MODULE\s*[:\-]?\s*(\d+)[^<]*',
                r'Module\s*([IVXivx]+)[^<]*',
                r'Mod\s*([IVXivx]+)[^<]*',
                r'Unit\s*[:\-]?\s*(\d+)[^<]*',
                r'UNIT\s*[:\-]?\s*(\d+)[^<]*',
                r'Lecture\s*[:\-]?\s*(\d+)[^<]*',
                r'LECTURE\s*[:\-]?\s*(\d+)[^<]*',
            ]
            
            for pattern in module_patterns:
                match = re.search(pattern, clean_context, re.IGNORECASE)
                if match:
                    module_num = match.group(1)
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
                                 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
                    module_num = roman_map.get(module_num.upper(), module_num)
                    return f"Module_{module_num.zfill(2)}"
        
        return None
    
    def download_drive_pdf(self, url, save_path, context_html="", link_text=""):
        """Download PDF from Google Drive link"""
        file_id = self.extract_file_id(url)
        
        if not file_id:
            print(f"❌ Could not extract file ID from: {url}")
            return False
        
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        try:
            response = self.session.get(download_url, stream=True, timeout=30)
            
            if "Google Drive - Virus scan warning" in response.text:
                confirm_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', response.text)
                if confirm_match:
                    confirm_token = confirm_match.group(1)
                    download_url = f"{download_url}&confirm={confirm_token}"
                    response = self.session.get(download_url, stream=True, timeout=30)
            
            content_disposition = response.headers.get('content-disposition', '')
            original_filename = None
            
            if 'filename=' in content_disposition:
                filename_match = re.search(r'filename\*?=["\']?(?:UTF-8[\'"]*)?([^"\';]+)', content_disposition, re.IGNORECASE)
                if filename_match:
                    original_filename = unquote(filename_match.group(1))
                else:
                    filename_match = re.search(r'filename=["\']?([^"\']+)["\']?', content_disposition, re.IGNORECASE)
                    if filename_match:
                        original_filename = filename_match.group(1)
            
            if not original_filename:
                original_filename = self.get_drive_filename(file_id)
            
            if original_filename:
                original_filename = unquote(original_filename)
                original_filename = re.sub(r'\.pdf\.pdf$', '.pdf', original_filename, flags=re.IGNORECASE)
                if not original_filename.lower().endswith('.pdf'):
                    original_filename += '.pdf'
                original_filename = re.sub(r'[<>:"/\\|?*]', '_', original_filename)
                filename = original_filename
            else:
                module_info = self.extract_module_info_from_context(context_html, file_id, link_text)
                if module_info:
                    filename = f"{module_info}.pdf"
                else:
                    filename = f"Document_{int(time.time()) % 10000}.pdf"
            
            new_save_path = Path(save_path).parent / filename
            os.makedirs(os.path.dirname(new_save_path), exist_ok=True)
            
            with open(new_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(new_save_path)
            print(f"    ✅ Downloaded: {filename} ({file_size:,} bytes)")
            
            try:
                with open(new_save_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        print(f"⚠️  Warning: File may not be a valid PDF: {filename}")
                        return False
            except:
                pass
            
            return new_save_path
            
        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
            return False
    
    def is_similar_subject(self, subject1, subject2):
        """Check if two subject names are similar"""
        # Remove common words and compare
        common_words = ['and', 'the', 'in', 'of', 'for', 'to', '&', '-', '_']
        
        def clean_text(text):
            text = text.lower()
            for word in common_words:
                text = text.replace(word, ' ')
            # Remove special characters
            text = re.sub(r'[^a-z0-9\s]', '', text)
            return re.sub(r'\s+', ' ', text).strip()
        
        clean1 = clean_text(subject1)
        clean2 = clean_text(subject2)
        
        # Check if one contains the other or they share significant words
        words1 = set(clean1.split())
        words2 = set(clean2.split())
        
        # Check for significant overlap
        common_words = words1.intersection(words2)
        if len(common_words) >= 2:  # At least 2 common words
            return True
            
        # Check if one is substring of the other
        if (clean1 in clean2 or clean2 in clean1) and len(clean1) > 3 and len(clean2) > 3:
            return True
            
        return False
    
    def get_subject_links(self, semester_url):
        """Extract ALL subject links from a semester page - handles both notes and question papers"""
        try:
            print(f"\n🔍 Fetching subjects from: {semester_url}")
            response = self.session.get(semester_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            subject_links = []
            
            # METHOD 1: Look for elementor buttons (works for both notes and question papers)
            buttons = soup.find_all('a', class_=lambda x: x and 'elementor-button' in x)
            
            for button in buttons:
                href = button.get('href')
                if not href:
                    continue
                    
                # Get button text
                text_element = button.find('span', class_='elementor-button-text')
                if not text_element:
                    continue
                    
                subject_name = text_element.get_text(strip=True)
                
                # Clean up the subject name
                subject_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
                subject_name = re.sub(r'\s+', ' ', subject_name).strip()
                
                # Skip if too short
                if len(subject_name) < 3:
                    continue
                    
                # Skip unwanted buttons
                exclude_keywords = ['HOME', 'ABOUT', 'CONTACT', 'PRIVACY', 'MORE', 'UPLOAD']
                if any(keyword in subject_name.upper() for keyword in exclude_keywords):
                    continue
                
                # Handle different types of links
                if 'drive.google.com' in href:
                    # This is a direct Google Drive link on a question papers page
                    # We'll create a subject entry that points to the current page
                    # The actual downloading will happen in scrape_subject
                    subject_links.append((semester_url, subject_name))
                elif '/ktu-' in href or 'notes' in href.lower() or 'question' in href.lower():
                    # This is a link to another page (notes or question papers)
                    full_url = urljoin(semester_url, href)
                    
                    # Check if it's a syllabus or curriculum page
                    if not any(keyword in subject_name.upper() 
                              for keyword in ['CURRICULUM', 'SYLLABUS', 'TIMETABLE']):
                        subject_links.append((full_url, subject_name))
            
            # METHOD 2: Look for other subject links in the content
            if len(subject_links) <= 1:  # If we didn't find many via buttons
                content_sections = soup.select('.elementor-widget-wrap, .elementor-section, .post_content')
                for section in content_sections:
                    links = section.find_all('a', href=True)
                    for link in links:
                        href = link['href']
                        text = link.get_text(strip=True)
                        
                        if not text or len(text) < 5:
                            continue
                        
                        # Check if this looks like a subject link
                        if ('/ktu-' in href or 
                            'notes' in href.lower() or 
                            'question' in href.lower() or
                            'drive.google.com' in href):
                            
                            # Skip unwanted links
                            if any(excl in text.upper() for excl in 
                                  ['CURRICULUM', 'SYLLABUS', 'QUESTION BANK', 'HOME', 'ABOUT']):
                                continue
                            
                            clean_name = re.sub(r'[<>:"/\\|?*&]', '_', text)
                            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
                            
                            if 'drive.google.com' in href:
                                # Direct Google Drive link
                                subject_links.append((semester_url, clean_name))
                            else:
                                # Link to another page
                                full_url = urljoin(semester_url, href)
                                if not any(url == full_url for url, _ in subject_links):
                                    subject_links.append((full_url, clean_name))
            
            # Remove duplicates by subject name (case-insensitive)
            seen_names = set()
            unique_links = []
            
            for link_url, link_text in subject_links:
                # Normalize the name for comparison
                normalized_name = re.sub(r'\s+', ' ', link_text.lower()).strip()
                
                if normalized_name not in seen_names and link_text:
                    seen_names.add(normalized_name)
                    unique_links.append((link_url, link_text))
            
            print(f"   📊 Found {len(unique_links)} subjects:")
            for i, (url, name) in enumerate(unique_links, 1):
                print(f"     {i}. {name}")
                if 'drive.google.com' not in url and url != semester_url:
                    print(f"        🔗 {url}")
            
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
            
            print(f"🔍 Looking for drive links on: {url}")
            
            # CASE 1: Find links in button widgets (common pattern for single links)
            elementor_buttons = soup.find_all('a', class_=lambda x: x and 'elementor-button' in x)
            for button in elementor_buttons:
                href = button.get('href')
                link_text = button.get_text(strip=True)
                
                if href and 'drive.google.com' in href:
                    file_id = self.extract_file_id(href)
                    if file_id:
                        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                        print(f"   ✅ Found drive link in elementor button: {link_text[:50]}... (ID: {file_id[:8]})")
                        drive_links.append((drive_url, file_id, link_text))
            
            # CASE 2: Check all links on the page
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link['href']
                link_text = link.get_text(strip=True)
                
                if 'drive.google.com' in href:
                    file_id = self.extract_file_id(href)
                    if file_id:
                        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                        # Check if this exact combination (file_id + link_text) already exists
                        if not any(fid == file_id and text == link_text for _, fid, text in drive_links):
                            print(f"   ✅ Found drive link: {link_text[:50]}... (ID: {file_id[:8]})")
                            drive_links.append((drive_url, file_id, link_text))
            
            # CASE 3: Search in text content for drive URLs (fallback)
            if not drive_links:
                print(f"   🔍 Searching text content for drive URLs...")
                patterns = [
                    r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
                    r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
                    r'drive\.google\.com/uc\?[^"\'>]*id=([a-zA-Z0-9_-]+)',
                    r'drive\.google\.com/drive/(?:folders|u/0)?/([a-zA-Z0-9_-]+)',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html_content)
                    for file_id in matches:
                        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                        # Try to find context around the file_id
                        link_text = ""
                        idx = html_content.find(file_id)
                        if idx != -1:
                            start = max(0, idx - 150)
                            end = min(len(html_content), idx + 150)
                            context = html_content[start:end]
                            soup_context = BeautifulSoup(context, 'html.parser')
                            
                            # Try to find link text
                            link_elem = soup_context.find('a', href=lambda x: x and file_id in x)
                            if link_elem:
                                link_text = link_elem.get_text(strip=True)
                            else:
                                # Extract some text from the context
                                all_text = soup_context.get_text(strip=True)
                                link_text = all_text[:100] if all_text else f"Document_{file_id[:8]}"
                        
                        if not any(fid == file_id for _, fid, _ in drive_links):
                            print(f"   ✅ Found drive link in text: {link_text[:50]}... (ID: {file_id[:8]})")
                            drive_links.append((drive_url, file_id, link_text or f"Document_{file_id[:8]}"))
            
            # Remove duplicates by file_id AND link_text
            unique_drive_links = []
            seen_combinations = set()
            for link in drive_links:
                url, file_id, text = link
                combination = f"{file_id}_{text}"
                if combination not in seen_combinations:
                    seen_combinations.add(combination)
                    unique_drive_links.append(link)
            
            # Sort links by text (helps with module order)
            unique_drive_links.sort(key=lambda x: x[2].lower())
            
            print(f"   📊 Total unique drive links found: {len(unique_drive_links)}")
            
            return unique_drive_links, html_content
            
        except Exception as e:
            print(f"❌ Error finding drive links on {url}: {e}")
            return [], ""
    
    def scrape_subject(self, subject_url, subject_name, subject_dir, process_after=False, processor_options=None):
        """Scrape a subject page and download PDFs"""
        print(f"\n📚 Processing: {subject_name}")
        print(f"   🔗 URL: {subject_url}")
        
        # First, check if this subject_name matches any button text on the page
        drive_links, html_content = self.find_drive_links_on_page(subject_url)
        
        if not drive_links:
            print(f"   ⚠️  No Google Drive links found on this page")
            return 0
        
        # Filter links by subject name if we're on a multi-subject page
        filtered_drive_links = []
        
        # Try to match the subject name with link texts
        subject_name_lower = subject_name.lower()
        for drive_url, file_id, link_text in drive_links:
            link_text_lower = link_text.lower()
            
            # Check if this link belongs to our subject
            if (subject_name_lower in link_text_lower or 
                link_text_lower in subject_name_lower or
                self.is_similar_subject(subject_name, link_text)):
                filtered_drive_links.append((drive_url, file_id, link_text))
        
        # If we didn't find matches, use all links (for single-subject pages)
        if not filtered_drive_links:
            filtered_drive_links = drive_links
            print(f"   📄 Found {len(drive_links)} Google Drive link(s)")
        else:
            print(f"   📄 Found {len(filtered_drive_links)} Google Drive link(s) for '{subject_name}'")
        
# Special handling for single document
        if len(filtered_drive_links) == 1:
            print(f"   ⚙️  Single document detected")
            drive_url, file_id, link_text = filtered_drive_links[0]
            
            # Use subject name for filename
            clean_subject_name = re.sub(r'[<>:"/\\|?*]', '_', subject_name)
            clean_subject_name = re.sub(r'\s+', ' ', clean_subject_name).strip()
            
            # Check if it ends with .pdf, if not add it
            if not clean_subject_name.lower().endswith('.pdf'):
                clean_subject_name += '.pdf'
            
            # Limit filename length
            if len(clean_subject_name) > 100:
                clean_subject_name = clean_subject_name[:95] + '.pdf'
            
            save_path = os.path.join(subject_dir, clean_subject_name)
            
            if os.path.exists(save_path):
                print(f"   ⏭️  Skipping (already exists): {clean_subject_name}")
                downloaded_count = 1  # <-- CHANGED: Use variable instead of return
            else:
                time.sleep(1.5)
                result = self.download_drive_pdf(drive_url, save_path, html_content, link_text)
                downloaded_count = 1 if result else 0  # <-- CHANGED: Use variable instead of return
            
        else:
            # Multiple documents
            downloaded_count = 0
            for i, (drive_url, file_id, link_text) in enumerate(filtered_drive_links, 1):
                print(f"   📥 Processing link {i}/{len(filtered_drive_links)}")
                
                # Try to extract module info
                module_info = self.extract_module_info_from_context(html_content, file_id, link_text)
                
                if module_info:
                    filename = f"{module_info}.pdf"
                elif link_text and len(link_text) > 3:
                    # Use link text as filename
                    clean_text = re.sub(r'[<>:"/\\|?*]', '_', link_text)
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                    if len(clean_text) > 50:
                        clean_text = clean_text[:47] + '...'
                    filename = f"{clean_text}.pdf"
                else:
                    filename = f"Document_{i:02d}.pdf"
                
                # Ensure it ends with .pdf
                if not filename.lower().endswith('.pdf'):
                    filename += '.pdf'
                
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                save_path = os.path.join(subject_dir, filename)
                
                if os.path.exists(save_path):
                    print(f"   ⏭️  Skipping (already exists): {filename}")
                    downloaded_count += 1
                    continue
                
                time.sleep(1.5)
                
                result = self.download_drive_pdf(drive_url, save_path, html_content, link_text)
                
                if result:
                    downloaded_count += 1
        
        # Process after download if requested
        if process_after and downloaded_count > 0 and processor_options:
            processor = PDFProcessor()
            print(f"\n   🔧 Processing downloaded files in: {subject_dir}")
            processor.process_single_directory(subject_dir, **processor_options)
        
        return downloaded_count
    
    def run_downloader(self, process_after=False, processor_options=None):
        """Run the downloader module with optional post-processing"""
        print("\n" + "="*60)
        print("🎓 KTU NOTES DOWNLOADER")
        print("="*60)
        
        default_url = "https://www.ktunotes.in/ktu-s6-cse-notes-2019-scheme/"
        url_input = input(f"\nEnter semester URL (default: {default_url}): ").strip()
        semester_url = url_input if url_input else default_url
        
        default_dir = "KTU_Notes"
        dir_prompt = f"\nEnter download folder name or full path (default: {default_dir}): "
        dir_input = input(dir_prompt).strip()
        download_dir = dir_input if dir_input else default_dir
        
        self.download_dir = Path(download_dir)
        if not self.download_dir.is_absolute():
            self.download_dir = Path.cwd() / self.download_dir
        
        print(f"\n📁 Download location: {self.download_dir.absolute()}")
        
        print("\n🔍 Fetching available subjects...")
        subject_links = self.get_subject_links(semester_url)
        
        if not subject_links:
            print("❌ No subjects found. Please check the URL.")
            return
        
        print(f"\n✅ Found {len(subject_links)} subjects:")
        for i, (url, name) in enumerate(subject_links, 1):
            print(f"  {i}. {name}")
        
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
        
        print(f"\n📋 SELECTED {len(selected_indices)} SUBJECT(S):")
        for idx in selected_indices:
            _, name = subject_links[idx]
            print(f"  • {name}")
        
        if process_after:
            print(f"\n⚙️  POST-PROCESSING: Will process each folder after download")
        
        confirm = input("\nStart download? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Download cancelled.")
            return
        
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n" + "="*60)
        print("🚀 STARTING DOWNLOAD")
        print("="*60)
        
        total_downloaded = 0
        
        for i, subject_idx in enumerate(selected_indices, 1):
            subject_url, subject_name = subject_links[subject_idx]
            
            print(f"\n{'─'*40}")
            print(f"📚 Subject {i}/{len(selected_indices)}: {subject_name}")
            
            clean_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            clean_name = clean_name[:80]
            subject_dir = self.download_dir / clean_name
            subject_dir.mkdir(parents=True, exist_ok=True)
            
            downloaded = self.scrape_subject(
                subject_url, 
                subject_name, 
                subject_dir, 
                process_after=process_after,
                processor_options=processor_options
            )
            total_downloaded += downloaded
            
            print(f"   📊 Progress: {i}/{len(selected_indices)} subjects")
            print(f"   📈 Downloaded so far: {total_downloaded} files")
            
            if i < len(selected_indices):
                print(f"   ⏳ Waiting 2 seconds...")
                time.sleep(2)
        
        print(f"\n{'='*60}")
        print("✅ DOWNLOAD COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • Subjects processed: {len(selected_indices)}")
        print(f"  • Total files downloaded: {total_downloaded}")
        print(f"  • Location: {self.download_dir.absolute()}")
        print(f"{'='*60}")


class PDFProcessor:
    """Handles PDF post-processing: renaming and hyperlink removal"""
    
    @staticmethod
    def rename_pdf_file(pdf_file):
        """Remove ktunotes patterns from a single PDF filename"""
        try:
            filename = pdf_file.name
            new_filename = filename
            
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
                r'\s+Ktunotes\.in',
                r'\s+ktunotes\.in',
            ]
            
            for pattern in patterns_to_remove:
                new_filename = re.sub(pattern, '', new_filename, flags=re.IGNORECASE)
            
            new_filename = re.sub(r'\s+', ' ', new_filename).strip()
            new_filename = re.sub(r'\.pdf\.pdf$', '.pdf', new_filename, flags=re.IGNORECASE)
            
            if new_filename != filename:
                new_file_path = pdf_file.parent / new_filename
                
                counter = 1
                while new_file_path.exists():
                    name_part, ext = os.path.splitext(new_filename)
                    new_filename = f"{name_part}_{counter}{ext}"
                    new_file_path = pdf_file.parent / new_filename
                    counter += 1
                
                pdf_file.rename(new_file_path)
                print(f"    📝 Renamed: {filename} → {new_filename}")
                return new_file_path, True
            else:
                return pdf_file, False
                
        except Exception as e:
            print(f"❌ Error renaming {pdf_file.name}: {e}")
            return pdf_file, False
    
    @staticmethod
    def remove_hyperlinks_from_pdf(file_path):
        """Remove hyperlinks from a single PDF file"""
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
                temp_pdf = str(file_path) + '.tmp'
                doc.save(temp_pdf)
                doc.close()
                os.replace(temp_pdf, file_path)
                print(f"    🔗 Removed hyperlinks from: {os.path.basename(file_path)}")
                return True
            else:
                doc.close()
                return False
                
        except Exception as e:
            print(f"❌ Error removing hyperlinks from {file_path}: {e}")
            return False
    
    def process_single_directory(self, directory, rename=True, remove_hyperlinks=True, recursive=False):
        """Process all PDFs in a single directory (no recursion)"""
        directory = Path(directory)
        
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return 0, 0, 0
        
        pdf_files = list(directory.glob("*.pdf"))
        if not pdf_files:
            return 0, 0, 0
        
        processed_count = 0
        renamed_count = 0
        hyperlinks_removed = 0
        
        for pdf_file in pdf_files:
            try:
                current_file = pdf_file
                
                if rename:
                    current_file, renamed = self.rename_pdf_file(current_file)
                    if renamed:
                        renamed_count += 1
                
                if remove_hyperlinks:
                    if self.remove_hyperlinks_from_pdf(current_file):
                        hyperlinks_removed += 1
                
                processed_count += 1
                
            except Exception as e:
                print(f"❌ Error processing {pdf_file.name}: {e}")
        
        return processed_count, renamed_count, hyperlinks_removed
    
    def process_directory_recursive(self, directory, rename=True, remove_hyperlinks=True):
        """Process all PDFs in a directory and all subdirectories"""
        directory = Path(directory)
        
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return
        
        print(f"\n🔍 Scanning directory recursively: {directory}")
        
        # Find all PDF files recursively
        pdf_files = list(directory.rglob("*.pdf"))
        if not pdf_files:
            print("⚠️  No PDF files found in this directory or its subdirectories")
            return
        
        print(f"📄 Found {len(pdf_files)} PDF file(s) in {len(set(f.parent for f in pdf_files))} folder(s)")
        
        total_processed = 0
        total_renamed = 0
        total_hyperlinks_removed = 0
        
        # Group files by directory
        dir_files = {}
        for pdf_file in pdf_files:
            parent_dir = pdf_file.parent
            if parent_dir not in dir_files:
                dir_files[parent_dir] = []
            dir_files[parent_dir].append(pdf_file)
        
        # Process each directory
        for dir_path, files in dir_files.items():
            print(f"\n{'─'*30}")
            print(f"📁 Processing: {dir_path.relative_to(directory) if dir_path != directory else '(Main Directory)'}")
            print(f"   Found {len(files)} PDF file(s)")
            
            dir_processed = 0
            dir_renamed = 0
            dir_hyperlinks_removed = 0
            
            for pdf_file in files:
                try:
                    current_file = pdf_file
                    
                    if rename:
                        current_file, renamed = self.rename_pdf_file(current_file)
                        if renamed:
                            dir_renamed += 1
                            total_renamed += 1
                    
                    if remove_hyperlinks:
                        if self.remove_hyperlinks_from_pdf(current_file):
                            dir_hyperlinks_removed += 1
                            total_hyperlinks_removed += 1
                    
                    dir_processed += 1
                    total_processed += 1
                    
                except Exception as e:
                    print(f"❌ Error processing {pdf_file.name}: {e}")
            
            print(f"   ✅ Processed: {dir_processed} files")
            if rename:
                print(f"     📝 Renamed: {dir_renamed} files")
            if remove_hyperlinks:
                print(f"     🔗 Hyperlinks removed: {dir_hyperlinks_removed} files")
        
        print(f"\n{'='*60}")
        print("✅ RECURSIVE PROCESSING COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • Total folders processed: {len(dir_files)}")
        print(f"  • Total PDF files processed: {total_processed}")
        if rename:
            print(f"  • Total files renamed: {total_renamed}")
        if remove_hyperlinks:
            print(f"  • Total hyperlinks removed from: {total_hyperlinks_removed} files")
        print(f"{'='*60}")
    
    def run_processor(self):
        """Run the PDF processor module with recursive option"""
        print("\n" + "="*60)
        print("🔧 PDF POST-PROCESSOR")
        print("="*60)
        
        dir_prompt = "\nEnter directory path containing PDFs: "
        dir_input = input(dir_prompt).strip()
        
        if not dir_input:
            print("❌ No directory specified.")
            return
        
        directory = Path(dir_input)
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return
        
        print("\n" + "-"*60)
        print("⚙️  PROCESSING OPTIONS")
        print("-"*60)
        
        rename_choice = input("Remove 'Ktunotes.in' from filenames? (yes/no, default: yes): ").strip().lower()
        rename = rename_choice in ['yes', 'y', '']
        
        hyperlinks_choice = input("Remove hyperlinks from PDFs? (yes/no, default: no): ").strip().lower()
        remove_hyperlinks = hyperlinks_choice in ['yes', 'y']
        
        if not rename and not remove_hyperlinks:
            print("⚠️  No processing options selected. Nothing to do.")
            return
        
        print("\n" + "-"*60)
        print("📁 PROCESSING SCOPE")
        print("-"*60)
        print("1. Process only the selected directory")
        print("2. Process recursively (all subdirectories)")
        
        while True:
            scope_choice = input("\nSelect processing scope (1 or 2): ").strip()
            
            if scope_choice == '1':
                recursive = False
                break
            elif scope_choice == '2':
                recursive = True
                break
            else:
                print("❌ Invalid choice. Please enter 1 or 2.")
        
        print(f"\n📁 Directory: {directory.absolute()}")
        print(f"⚙️  Options:")
        if rename:
            print("  • Rename files: ✅ ENABLED")
        if remove_hyperlinks:
            print("  • Remove hyperlinks: ✅ ENABLED")
        if recursive:
            print("  • Processing scope: 🔄 RECURSIVE (all subdirectories)")
        else:
            print("  • Processing scope: 📂 CURRENT DIRECTORY ONLY")
        
        confirm = input("\nStart processing? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Processing cancelled.")
            return
        
        if recursive:
            self.process_directory_recursive(directory, rename, remove_hyperlinks)
        else:
            print(f"\n🔧 Processing directory: {directory}")
            processed, renamed, hyperlinks_removed = self.process_single_directory(
                directory, rename, remove_hyperlinks
            )
            
            print(f"\n{'='*60}")
            print("✅ PROCESSING COMPLETE!")
            print("="*60)
            print(f"📊 Summary:")
            print(f"  • PDF files processed: {processed}")
            if rename:
                print(f"  • Files renamed: {renamed}")
            if remove_hyperlinks:
                print(f"  • Hyperlinks removed from: {hyperlinks_removed} files")
            print(f"{'='*60}")


class AllInOneKTUScraper:
    """Main orchestrator that combines downloader and processor"""
    
    @staticmethod
    def get_processor_options():
        """Get PDF processing options from user"""
        print("\n" + "-"*60)
        print("⚙️  PDF PROCESSING OPTIONS")
        print("-"*60)
        
        rename_choice = input("Remove 'Ktunotes.in' from filenames? (yes/no, default: yes): ").strip().lower()
        rename = rename_choice in ['yes', 'y', '']
        
        hyperlinks_choice = input("Remove hyperlinks from PDFs? (yes/no, default: no): ").strip().lower()
        remove_hyperlinks = hyperlinks_choice in ['yes', 'y']
        
        return {'rename': rename, 'remove_hyperlinks': remove_hyperlinks}
    
    @staticmethod
    def main_menu():
        """Display main menu and handle user choice"""
        print("\n" + "="*60)
        print("🎓 KTU NOTES MANAGER")
        print("="*60)
        print("\nWhat would you like to do?")
        print("1. 📥 Download KTU Notes (Download Only)")
        print("2. 🔧 Process Existing PDFs (Rename & Remove Hyperlinks)")
        print("3. 📥 + 🔧 Download AND Process (Auto-process after each folder)")
        print("4. 🚪 Exit")
        
        while True:
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                # Download only
                downloader = KTUNotesDownloader()
                downloader.run_downloader()
                break
                
            elif choice == '2':
                # Process only with recursive option
                processor = PDFProcessor()
                processor.run_processor()
                break
                
            elif choice == '3':
                # Download and process with auto-processing after each folder
                print("\n" + "="*60)
                print("📥 + 🔧 DOWNLOAD AND PROCESS")
                print("="*60)
                print("Files will be processed immediately after each folder is downloaded.\n")
                
                # Get processing options
                processor_options = AllInOneKTUScraper.get_processor_options()
                
                if not processor_options['rename'] and not processor_options['remove_hyperlinks']:
                    print("⚠️  No processing options selected. Switching to download-only mode.")
                    downloader = KTUNotesDownloader()
                    downloader.run_downloader()
                else:
                    # Run downloader with auto-processing
                    downloader = KTUNotesDownloader()
                    downloader.run_downloader(
                        process_after=True,
                        processor_options=processor_options
                    )
                
                break
                
            elif choice == '4':
                print("\n👋 Goodbye!")
                sys.exit(0)
                
            else:
                print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")


def main():
    print("\n🎓 KTU NOTES MANAGER - ENHANCED VERSION")
    print("   • Modular architecture")
    print("   • Recursive processing")
    print("   • Auto-processing after download")
    print("   • Single document support")
    print("   • Question papers support\n")
    
    # Check for PyMuPDF
    try:
        import fitz
    except ImportError:
        print("⚠️  PyMuPDF not installed. Hyperlink removal will be disabled.")
        print("   Install: pip install PyMuPDF")
    
    # Check for required packages
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
        print("Packages installed. Please run again.")
        sys.exit(0)
    
    # Run the main menu
    while True:
        AllInOneKTUScraper.main_menu()
        
        # Ask if user wants to do another operation
        another = input("\nPerform another operation? (yes/no): ").strip().lower()
        if another not in ['yes', 'y', '']:
            print("\n👋 Goodbye!")
            break
        print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
