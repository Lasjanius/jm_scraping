import requests
from bs4 import BeautifulSoup
import re
import csv
import time
import random
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from datetime import datetime

class JobScraper:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.job_titles = []
        self.is_running = False
        self.should_stop = False
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")
    
    def extract_job_titles(self, url, page=1, max_pages=50):
        # 最大ページ数を超えたら終了
        if page > max_pages or self.should_stop:
            self.log(f"最大ページ数 ({max_pages}) に達したか、停止要求があったため抽出を終了します。")
            return
        
        # ページパラメータを追加
        if page > 1:
            if '?' in url:
                # すでにpage=Nがあれば置き換え、なければ追加
                if 'page=' in url:
                    current_url = re.sub(r'page=\d+', f'page={page}', url)
                else:
                    current_url = f"{url}&page={page}"
            else:
                current_url = f"{url}?page={page}"
        else:
            current_url = url
        
        self.log(f"ページ {page} を処理中... URL: {current_url}")
        
        # ランダムな遅延を追加してアクセス制限を回避
        delay = random.uniform(1.5, 3.0)
        time.sleep(delay)
        
        # Send a request to the URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            'Referer': 'https://job-medley.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        try:
            response = requests.get(current_url, headers=headers)
            
            # Check if the request was successful
            if response.status_code != 200:
                self.log(f"ページの取得に失敗しました: ステータスコード {response.status_code}")
                return
            
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find job titles based on the structure of job-medley.com
            # Look for h3 elements which typically contain job titles
            job_listings = soup.find_all('h3')
            
            # Words that indicate non-job title h3 elements
            ignore_words = ['なるほど', '会員登録', '正社員', 'パート', 'バイト', 'スカウト', '希望', '会員限定']
            
            # 現在のページのタイトル数
            page_titles_count = 0
            
            for listing in job_listings:
                if self.should_stop:
                    self.log("停止要求があったため処理を中断します。")
                    return
                
                # Clean up the text (remove extra whitespace and newlines)
                title = listing.text.strip()
                
                # Check if this is a real job title or navigation element
                should_ignore = False
                for word in ignore_words:
                    if word in title:
                        should_ignore = True
                        break
                
                if title and not should_ignore:
                    self.job_titles.append({'page': page, 'title': title})
                    page_titles_count += 1
            
            self.log(f"  {page_titles_count} 件の求人を見つけました")
            
            # 次のページへのリンクを複数の方法で探す
            next_page = None
            
            # 方法1: ページネーションリンクを探す
            pagination_links = soup.select('div.pagination a, ul.pagination a, nav.pagination a')
            for link in pagination_links:
                link_text = link.text.strip()
                href = link.get('href', '')
                # 「次へ」「次のページ」などのテキストを持つリンクを探す
                if '次' in link_text or ('page=' in href and f'page={page+1}' in href):
                    next_page = link
                    self.log(f"  次のページへのリンクを見つけました: {link.get('href')}")
                    break
            
            # 方法2: ページ番号のリンクから次のページを探す
            if not next_page:
                page_num_links = soup.select('a[href*="page="]')
                for link in page_num_links:
                    page_num_match = re.search(r'page=(\d+)', link.get('href', ''))
                    if page_num_match:
                        found_page = int(page_num_match.group(1))
                        if found_page == page + 1:
                            next_page = link
                            self.log(f"  次のページ({found_page})へのリンクを見つけました: {link.get('href')}")
                            break
            
            # 次のページが存在し、現在のページで求人が見つかった場合は続行
            if next_page and page_titles_count > 0 and not self.should_stop:
                self.extract_job_titles(url, page + 1, max_pages)
            elif page_titles_count > 0 and not self.should_stop:
                # 次のページへのリンクがないが、このページに求人がある場合は
                # 単純にページ番号を進めてみる
                self.log("  明示的な次ページリンクが見つかりませんでしたが、次のページを試みます")
                self.extract_job_titles(url, page + 1, max_pages)
            else:
                self.log("最後のページに到達したか、次のページで求人が見つかりませんでした。抽出を終了します。")
                
        except Exception as e:
            self.log(f"エラーが発生しました: {str(e)}")
    
    def save_to_csv(self, filename):
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['page', 'title']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for title in self.job_titles:
                    writer.writerow(title)
            
            self.log(f"結果を {filename} に保存しました。")
            return True
        except Exception as e:
            self.log(f"CSVファイルの保存中にエラーが発生しました: {str(e)}")
            return False
    
    def start_scraping(self, url, max_pages=50):
        self.should_stop = False
        self.is_running = True
        self.job_titles = []
        
        self.log("求人サイトから職場名を抽出を開始します...")
        self.extract_job_titles(url, max_pages=max_pages)
        
        self.is_running = False
        
        if self.job_titles:
            # ページごとの統計を表示
            page_counts = {}
            for title in self.job_titles:
                page = title['page']
                if page not in page_counts:
                    page_counts[page] = 0
                page_counts[page] += 1
            
            self.log(f"\n合計 {len(self.job_titles)} 件の求人が見つかりました。")
            
            self.log("\nページごとの求人数:")
            for page, count in sorted(page_counts.items()):
                self.log(f"  ページ {page}: {count} 件")
            
            return True
        else:
            self.log("求人情報が見つかりませんでした。")
            return False
    
    def stop_scraping(self):
        self.should_stop = True
        self.log("停止要求を受け付けました。処理を停止します...")


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Job Medley スクレイピングツール")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        self.scraper = JobScraper()
        self.setup_ui()
        self.update_log()
    
    def setup_ui(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # URL入力エリア
        url_frame = ttk.LabelFrame(main_frame, text="URLを入力", padding="5")
        url_frame.pack(fill=tk.X, pady=5)
        
        # URLのデフォルト値
        default_url = "https://job-medley.com/ans/search/?job_category_code=ans&prefecture_id=13&city_id%5B%5D=13101&city_id%5B%5D=13102&city_id%5B%5D=13103&city_id%5B%5D=13104&city_id%5B%5D=13105&city_id%5B%5D=13106&city_id%5B%5D=13107&city_id%5B%5D=13108&city_id%5B%5D=13109&city_id%5B%5D=13110&city_id%5B%5D=13111&city_id%5B%5D=13112&city_id%5B%5D=13113&city_id%5B%5D=13114&city_id%5B%5D=13115&city_id%5B%5D=13116&city_id%5B%5D=13117&city_id%5B%5D=13118&city_id%5B%5D=13119&city_id%5B%5D=13120&city_id%5B%5D=13121&city_id%5B%5D=13122&city_id%5B%5D=13123&designated_city_id=4&hw=1"
        
        self.url_var = tk.StringVar(value=default_url)
        ttk.Entry(url_frame, textvariable=self.url_var, width=80).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 設定エリア
        settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="5")
        settings_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(settings_frame, text="最大ページ数:").pack(side=tk.LEFT, padx=5)
        self.max_pages_var = tk.StringVar(value="50")
        ttk.Entry(settings_frame, textvariable=self.max_pages_var, width=5).pack(side=tk.LEFT, padx=5)
        
        # ボタンエリア
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        self.start_button = ttk.Button(button_frame, text="スクレイピング開始", command=self.start_scraping)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.save_button = ttk.Button(button_frame, text="CSVに保存", command=self.save_to_csv, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=5)
        
        # 進捗表示エリア
        progress_frame = ttk.LabelFrame(main_frame, text="進捗状況", padding="5")
        progress_frame.pack(fill=tk.X, pady=5)
        
        self.progress = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=5, pady=5)
        
        # ログ表示エリア
        log_frame = ttk.LabelFrame(main_frame, text="ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=80, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
    
    def update_log(self):
        # ログキューからメッセージを取得して表示
        try:
            while True:
                message = self.scraper.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.scraper.log_queue.task_done()
        except queue.Empty:
            pass
        
        # ボタンの状態を更新
        if self.scraper.is_running:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.save_button.config(state=tk.DISABLED)
            self.progress.start(10)
        else:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.progress.stop()
            if self.scraper.job_titles:
                self.save_button.config(state=tk.NORMAL)
        
        # 定期的に更新
        self.root.after(100, self.update_log)
    
    def start_scraping(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("エラー", "URLを入力してください。")
            return
        
        try:
            max_pages = int(self.max_pages_var.get())
            if max_pages <= 0:
                raise ValueError("最大ページ数は1以上の整数を指定してください。")
        except ValueError as e:
            messagebox.showerror("エラー", f"最大ページ数の指定が不正です: {str(e)}")
            return
        
        # 別スレッドでスクレイピングを実行
        threading.Thread(target=self.scraper.start_scraping, args=(url, max_pages), daemon=True).start()
    
    def stop_scraping(self):
        self.scraper.stop_scraping()
    
    def save_to_csv(self):
        if not self.scraper.job_titles:
            messagebox.showinfo("情報", "保存するデータがありません。")
            return
        
        # 保存先を選択
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="保存先を選択"
        )
        
        if file_path:
            success = self.scraper.save_to_csv(file_path)
            if success:
                messagebox.showinfo("成功", f"{len(self.scraper.job_titles)}件の求人情報を保存しました。")


if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop() 