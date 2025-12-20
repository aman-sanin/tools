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
        idx = html_content.find(file_id)
        if idx != -1:
            context_start = max(0, idx - 300)
            context_end = min(len(html_content), idx + 150)
            context = html_content[context_start:context_end]
            
            module_patterns = [
                r'Module\s*[:\-]?\s*(\d+)[^<]*',
                r'Mod\s*[:\-]?\s*(\d+)[^<]*',
                r'M\s*[:\-]?\s*(\d+)[^<]*',
                r'MODULE\s*[:\-]?\s*(\d+)[^<]*',
                r'Module\s*([IVXivx]+)[^<]*',
                r'Mod\s*([IVXivx]+)[^<]*',
            ]
            
            for pattern in module_patterns:
                match = re.search(pattern, context, re.IGNORECASE)
                if match:
                    module_num = match.group(1)
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5'}
                    module_num = roman_map.get(module_num.upper(), module_num)
                    return f"Module_{module_num.zfill(2)}"
        
        if link_text:
            link_lower = link_text.lower()
            if 'module' in link_lower or 'mod' in link_lower:
                num_match = re.search(r'(\d+|i{1,3}|iv|v)', link_text, re.IGNORECASE)
                if num_match:
                    module_num = num_match.group(1)
                    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                                 'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5'}
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
    
    def get_subject_links(self, semester_url):
        """Extract ALL subject links from a semester page"""
        try:
            print(f"\n🔍 Fetching subjects from: {semester_url}")
            response = self.session.get(semester_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            subject_links = []
            
            buttons = soup.find_all('a', class_='elementor-button')
            for button in buttons:
                href = button.get('href')
                if href:
                    if '/ktu-' in href and ('-notes-' in href or 'notes/' in href):
                        text_element = button.find('span', class_='elementor-button-text')
                        if text_element:
                            subject_name = text_element.get_text(strip=True)
                            subject_name = re.sub(r'[<>:"/\\|?*&]', '_', subject_name)
                            subject_name = re.sub(r'\s+', ' ', subject_name).strip()
                            exclude_keywords = ['CURRICULUM', 'SYLLABUS', 'QUESTION PAPER', 'EXAM', 'TIMETABLE']
                            if (len(subject_name) > 5 and 
                                not any(keyword in subject_name.upper() for keyword in exclude_keywords)):
                                full_url = urljoin(semester_url, href)
                                subject_links.append((full_url, subject_name))
            
            content_sections = soup.select('.elementor-widget-wrap, .elementor-section')
            for section in content_sections:
                links = section.find_all('a', href=True)
                for link in links:
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    
                    if (href and text and len(text) > 5 and
                        ('/ktu-' in href or 'notes' in href.lower()) and
                        not any(excl in text.upper() for excl in ['CURRICULUM', 'SYLLABUS', 'QUESTION'])):
                        
                        if not any(term in text.lower() for term in ['home', 'about', 'contact', 'privacy']):
                            full_url = urljoin(semester_url, href)
                            if not any(url == full_url for url, _ in subject_links):
                                clean_name = re.sub(r'[<>:"/\\|?*&]', '_', text)
                                clean_name = re.sub(r'\s+', ' ', clean_name).strip()
                                subject_links.append((full_url, clean_name))
            
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
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                link_text = link.get_text(strip=True)
                
                if 'drive.google.com' in href:
                    file_id = self.extract_file_id(href)
                    if file_id:
                        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
                        if not any(fid == file_id for _, fid, _ in drive_links):
                            drive_links.append((drive_url, file_id, link_text))
            
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
                        link_text = ""
                        idx = html_content.find(file_id)
                        if idx != -1:
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
    
    def scrape_subject(self, subject_url, subject_name, subject_dir):
        """Scrape a subject page and download PDFs"""
        print(f"\n📚 Processing: {subject_name}")
        print(f"   🔗 URL: {subject_url}")
        
        drive_links, html_content = self.find_drive_links_on_page(subject_url)
        
        if not drive_links:
            print(f"   ⚠️  No Google Drive links found on this page")
            return 0
        
        print(f"   📄 Found {len(drive_links)} Google Drive link(s)")
        
        downloaded_count = 0
        for i, (drive_url, file_id, link_text) in enumerate(drive_links, 1):
            print(f"   📥 Processing link {i}/{len(drive_links)}")
            
            module_info = self.extract_module_info_from_context(html_content, file_id, link_text)
            if module_info:
                filename = f"{module_info}.pdf"
            else:
                filename = f"Document_{i:02d}.pdf"
            
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
        
        return downloaded_count
    
    def run_downloader(self):
        """Run the downloader module"""
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
            
            downloaded = self.scrape_subject(subject_url, subject_name, subject_dir)
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
    def rename_pdfs_in_directory(directory):
        """Remove ktunotes patterns from PDF filenames in a directory"""
        directory = Path(directory)
        
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return 0
        
        renamed_count = 0
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
        
        for pdf_file in directory.rglob("*.pdf"):
            try:
                filename = pdf_file.name
                new_filename = filename
                
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
                    renamed_count += 1
                    
            except Exception as e:
                print(f"❌ Error renaming {pdf_file.name}: {e}")
        
        return renamed_count
    
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
    
    @staticmethod
    def process_directory(directory, rename=True, remove_hyperlinks=True):
        """Process all PDFs in a directory"""
        directory = Path(directory)
        
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return
        
        print(f"\n🔧 Processing PDFs in: {directory}")
        
        pdf_files = list(directory.rglob("*.pdf"))
        if not pdf_files:
            print("⚠️  No PDF files found in this directory")
            return
        
        print(f"📄 Found {len(pdf_files)} PDF file(s)")
        
        processed_count = 0
        renamed_count = 0
        hyperlinks_removed = 0
        
        for pdf_file in pdf_files:
            try:
                print(f"\n   Processing: {pdf_file.name}")
                
                if rename:
                    filename = pdf_file.name
                    new_filename = filename
                    patterns_to_remove = [
                        r' - Ktunotes\.in', r' - ktunotes\.in', r' -ktunotes\.in',
                        r' - KTUnotes', r' - ktunotes', r'_Ktunotes\.in',
                        r'_ktunotes\.in', r'\(Ktunotes\.in\)', r'\(ktunotes\.in\)',
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
                        print(f"      📝 Renamed: {filename} → {new_filename}")
                        renamed_count += 1
                        pdf_file = new_file_path
                
                if remove_hyperlinks:
                    if PDFProcessor.remove_hyperlinks_from_pdf(pdf_file):
                        hyperlinks_removed += 1
                
                processed_count += 1
                
            except Exception as e:
                print(f"❌ Error processing {pdf_file.name}: {e}")
        
        print(f"\n{'='*60}")
        print("✅ PROCESSING COMPLETE!")
        print("="*60)
        print(f"📊 Summary:")
        print(f"  • PDF files processed: {processed_count}")
        if rename:
            print(f"  • Files renamed: {renamed_count}")
        if remove_hyperlinks:
            print(f"  • Hyperlinks removed from: {hyperlinks_removed} files")
        print(f"{'='*60}")
    
    def run_processor(self):
        """Run the PDF processor module"""
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
        
        print(f"\n📁 Directory: {directory.absolute()}")
        print(f"⚙️  Options:")
        if rename:
            print("  • Rename files: ✅ ENABLED")
        if remove_hyperlinks:
            print("  • Remove hyperlinks: ✅ ENABLED")
        
        confirm = input("\nStart processing? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y', '']:
            print("Processing cancelled.")
            return
        
        self.process_directory(directory, rename, remove_hyperlinks)


class AllInOneKTUScraper:
    """Main orchestrator that combines downloader and processor"""
    
    @staticmethod
    def main_menu():
        """Display main menu and handle user choice"""
        print("\n" + "="*60)
        print("🎓 KTU NOTES MANAGER")
        print("="*60)
        print("\nWhat would you like to do?")
        print("1. 📥 Download KTU Notes")
        print("2. 🔧 Process Existing PDFs (Rename & Remove Hyperlinks)")
        print("3. 📥 + 🔧 Download AND Process")
        print("4. 🚪 Exit")
        
        while True:
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                # Download only
                downloader = KTUNotesDownloader()
                downloader.run_downloader()
                break
                
            elif choice == '2':
                # Process only
                processor = PDFProcessor()
                processor.run_processor()
                break
                
            elif choice == '3':
                # Download and process
                print("\n" + "="*60)
                print("📥 + 🔧 DOWNLOAD AND PROCESS")
                print("="*60)
                
                # Step 1: Download
                print("\n📥 STEP 1: DOWNLOADING")
                print("-"*40)
                downloader = KTUNotesDownloader()
                downloader.run_downloader()
                
                # Step 2: Ask for processing options
                print("\n" + "="*60)
                print("🔧 STEP 2: POST-PROCESSING")
                print("="*60)
                
                process_dir = input(f"\nEnter directory to process (default: {downloader.download_dir}): ").strip()
                if not process_dir:
                    process_dir = downloader.download_dir
                
                processor = PDFProcessor()
                
                print("\n" + "-"*60)
                print("⚙️  PROCESSING OPTIONS")
                print("-"*60)
                
                rename_choice = input("Remove 'Ktunotes.in' from filenames? (yes/no, default: yes): ").strip().lower()
                rename = rename_choice in ['yes', 'y', '']
                
                hyperlinks_choice = input("Remove hyperlinks from PDFs? (yes/no, default: no): ").strip().lower()
                remove_hyperlinks = hyperlinks_choice in ['yes', 'y']
                
                if rename or remove_hyperlinks:
                    confirm = input("\nStart post-processing? (yes/no): ").strip().lower()
                    if confirm in ['yes', 'y', '']:
                        processor.process_directory(process_dir, rename, remove_hyperlinks)
                else:
                    print("⚠️  No processing options selected. Skipping post-processing.")
                
                break
                
            elif choice == '4':
                print("\n👋 Goodbye!")
                sys.exit(0)
                
            else:
                print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")


def main():
    print("\n🎓 KTU NOTES MANAGER - MODULAR VERSION")
    print("   Downloader and PDF Processor\n")
    
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
